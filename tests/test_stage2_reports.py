import time
import inspect
import datetime
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from app.main import app
from app.functions import make_report
from app.inngest_client import inngest_client
from app.reports import create_report, get_report, clear_reports

client = TestClient(app)


@pytest.fixture(autouse=True)
def cleanup():
    clear_reports()
    yield
    clear_reports()


def test_post_reports_returns_202_id_and_pending():
    """Requirement A: POST /reports with topic returns 202, id, and status=pending."""
    with patch.object(inngest_client, "send", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = ["event-id-123"]
        response = client.post("/reports", json={"topic": "cats"})

        assert response.status_code == 202
        data = response.json()
        assert "id" in data
        assert data["status"] == "pending"

        # Verify event was dispatched with id and topic
        mock_send.assert_awaited_once()
        event_arg = mock_send.call_args[0][0]
        assert event_arg.name == "report/requested"
        assert event_arg.data["id"] == data["id"]
        assert event_arg.data["topic"] == "cats"


def test_post_reports_fast_response_no_slow_work():
    """Requirement B: Verify POST /reports returns immediately (<1s) and does not wait 8s."""
    with patch.object(inngest_client, "send", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = ["event-id-123"]
        start_time = time.time()
        response = client.post("/reports", json={"topic": "cats"})
        elapsed = time.time() - start_time

        assert response.status_code == 202
        assert elapsed < 1.0, f"Expected endpoint to return in <1s, took {elapsed}s"


def test_get_report_returns_pending_initially():
    """Requirement C: GET /reports/{id} for newly-created report returns pending."""
    report = create_report(topic="cats")
    response = client.get(f"/reports/{report['id']}")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == report["id"]
    assert data["topic"] == "cats"
    assert data["status"] == "pending"
    assert data["result"] is None


def test_get_unknown_report_returns_404():
    """Requirement D: GET /reports/{unknown-id} returns 404."""
    response = client.get("/reports/unknown-id-12345")
    assert response.status_code == 404
    assert response.json()["detail"] == "Report not found"


@pytest.mark.anyio
async def test_make_report_execution_workflow_and_completion():
    """Requirement E: make-report function executes 8s sleep and build-report step to mark report done."""
    report = create_report(topic="cats")
    report_id = report["id"]

    mock_step = MagicMock()
    mock_step.sleep = AsyncMock(return_value=None)

    async def fake_step_run(step_id, handler, *args):
        if inspect.iscoroutinefunction(handler):
            return await handler(*args)
        return handler(*args)

    mock_step.run = AsyncMock(side_effect=fake_step_run)

    mock_ctx = MagicMock()
    mock_ctx.event.data = {"id": report_id, "topic": "cats"}
    mock_ctx.step = mock_step

    # Execute the function handler
    handler = make_report._handler
    output = await handler(mock_ctx)

    # 1. Verify Step 1: do-the-slow-work (8 seconds sleep)
    mock_step.sleep.assert_awaited_once_with(
        "do-the-slow-work",
        datetime.timedelta(seconds=8),
    )

    # 2. Verify Step 2: build-report
    assert mock_step.run.call_args[0][0] == "build-report"
    assert output["status"] == "done"
    assert "cats" in output["result"]

    # 3. Verify in-memory store updated
    stored = get_report(report_id)
    assert stored["status"] == "done"
    assert stored["result"] == output["result"]


def test_make_report_configuration():
    """Requirement F: Verify Inngest function registration and trigger configuration."""
    assert make_report.local_id == "make-report"
    config = make_report.get_config("http://127.0.0.1:8000/api/inngest")
    triggers = [t.event for t in config.main.triggers if hasattr(t, "event")]
    assert "report/requested" in triggers

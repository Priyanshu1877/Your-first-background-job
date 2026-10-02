import inspect
import datetime
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from app.main import app
from app.functions import make_report
from app.inngest_client import inngest_client
from app.reports import reports_db, clear_reports

client = TestClient(app)


@pytest.fixture(autouse=True)
def cleanup():
    clear_reports()
    yield
    clear_reports()


def test_post_reports_missing_topic_returns_400():
    """Requirement A: POST /reports with missing or empty topic returns HTTP 400."""
    # 1. Missing topic key in payload
    resp1 = client.post("/reports", json={})
    assert resp1.status_code == 400
    assert "topic" in resp1.json()["detail"].lower()

    # 2. Empty string topic
    resp2 = client.post("/reports", json={"topic": ""})
    assert resp2.status_code == 400

    # 3. Whitespace-only topic
    resp3 = client.post("/reports", json={"topic": "   "})
    assert resp3.status_code == 400


def test_missing_topic_does_not_create_report():
    """Requirement B: Verify missing-topic requests do not create a report in store."""
    client.post("/reports", json={})
    assert len(reports_db) == 0

    client.post("/reports", json={"topic": ""})
    assert len(reports_db) == 0


def test_missing_topic_does_not_send_event():
    """Requirement C: Verify missing-topic requests do not send the report/requested event."""
    with patch.object(inngest_client, "send", new_callable=AsyncMock) as mock_send:
        client.post("/reports", json={})
        mock_send.assert_not_called()

        client.post("/reports", json={"topic": ""})
        mock_send.assert_not_called()


def test_make_report_configured_with_retries_2():
    """Requirement D: Verify make-report is configured with retries=2."""
    assert make_report._opts.retries == 2
    config = make_report.get_config("http://127.0.0.1:8000/api/inngest")
    assert config.main.steps["step"].retries.attempts == 2


@pytest.mark.anyio
async def test_make_report_fail_topic_raises_error():
    """Requirement E: Verify topic 'fail' raises 'The report oven is broken!'."""
    mock_step = MagicMock()
    mock_step.sleep = AsyncMock(return_value=None)

    async def fake_step_run(step_id, handler, *args):
        if inspect.iscoroutinefunction(handler):
            return await handler(*args)
        return handler(*args)

    mock_step.run = AsyncMock(side_effect=fake_step_run)

    mock_ctx = MagicMock()
    mock_ctx.event.data = {"id": "test-id-fail", "topic": "fail"}
    mock_ctx.step = mock_step

    handler = make_report._handler

    with pytest.raises(Exception) as exc_info:
        await handler(mock_ctx)

    assert "The report oven is broken!" in str(exc_info.value)

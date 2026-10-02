import inspect
import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.functions import heartbeat
from app.reports import reports_db, clear_reports

client = TestClient(app)


@pytest.fixture(autouse=True)
def cleanup():
    clear_reports()
    yield
    clear_reports()


def test_heartbeat_function_exists_and_id():
    """Requirement A: heartbeat function exists with fn_id='heartbeat'."""
    assert heartbeat is not None
    assert heartbeat.local_id == "heartbeat"


def test_heartbeat_cron_trigger_schedule():
    """Requirement B: heartbeat uses required cron schedule '* * * * *'."""
    config = heartbeat.get_config("http://127.0.0.1:8000/api/inngest")
    triggers = config.main.triggers
    assert len(triggers) == 1
    assert hasattr(triggers[0], "cron")
    assert triggers[0].cron == "* * * * *"


def test_heartbeat_no_http_or_event_trigger():
    """Requirement C: heartbeat is not configured with an HTTP route or event trigger."""
    # 1. No event trigger
    config = heartbeat.get_config("http://127.0.0.1:8000/api/inngest")
    for t in config.main.triggers:
        assert getattr(t, "event", None) is None

    # 2. No dedicated HTTP endpoint created for heartbeat
    app_routes = [route.path for route in app.routes]
    assert "/heartbeat" not in app_routes
    assert "/api/heartbeat" not in app_routes

    # Probing /heartbeat returns 404
    resp = client.get("/heartbeat")
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_heartbeat_counts_pending_done_failed():
    """Requirement D: heartbeat logic correctly aggregates pending, done, and failed reports."""
    # Seed in-memory store
    reports_db["rep-1"] = {"id": "rep-1", "topic": "cats", "status": "pending"}
    reports_db["rep-2"] = {"id": "rep-2", "topic": "dogs", "status": "pending"}
    reports_db["rep-3"] = {"id": "rep-3", "topic": "birds", "status": "done", "result": "..."}
    reports_db["rep-4"] = {"id": "rep-4", "topic": "fish", "status": "done", "result": "..."}
    reports_db["rep-5"] = {"id": "rep-5", "topic": "frogs", "status": "done", "result": "..."}
    reports_db["rep-6"] = {"id": "rep-6", "topic": "fail", "status": "failed"}

    mock_step = MagicMock()

    async def fake_step_run(step_id, handler, *args):
        if inspect.iscoroutinefunction(handler):
            return await handler(*args)
        return handler(*args)

    mock_step.run = AsyncMock(side_effect=fake_step_run)

    mock_ctx = MagicMock()
    mock_ctx.step = mock_step

    handler = heartbeat._handler
    output = await handler(mock_ctx)

    assert output == "Heartbeat: pending=2 done=3 failed=1"
    mock_step.run.assert_awaited_once()
    assert mock_step.run.call_args[0][0] == "log-summary"

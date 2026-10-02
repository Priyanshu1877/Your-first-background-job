import datetime
import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.functions import say_hello
from app.inngest_client import inngest_client

client = TestClient(app)


def test_inngest_client_configuration():
    assert inngest_client.app_id == "report-api"


def test_inngest_endpoint_reachable():
    response = client.get("/api/inngest")
    assert response.status_code == 200
    data = response.json()
    assert data["function_count"] >= 1
    assert data["mode"] == "dev"


def test_say_hello_configuration():
    assert say_hello.local_id == "say-hello"
    config = say_hello.get_config("http://127.0.0.1:8000/api/inngest")
    triggers = [t.event for t in config.main.triggers if hasattr(t, "event")]
    assert "test/hello" in triggers


@pytest.mark.anyio
async def test_say_hello_execution_logic():
    # Mock Inngest Context and Step to test durable function behavior
    mock_step = MagicMock()
    mock_step.sleep = AsyncMock(return_value=None)

    mock_ctx = MagicMock()
    mock_ctx.step = mock_step

    # Call the async handler directly
    handler = say_hello._handler
    result = await handler(mock_ctx)

    assert result == "Hello from the background!"
    mock_step.sleep.assert_awaited_once_with(
        "sleep-5s",
        datetime.timedelta(seconds=5),
    )

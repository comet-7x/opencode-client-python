"""Smoke tests for the educational examples.

Each example ships with a ``main()`` coroutine; these drive it against
respx mocks so ``uv run pytest examples/`` verifies the teaching code.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Generator
from pathlib import Path

import httpx
import pytest
import respx

sys.path.insert(0, str(Path(__file__).parent))

import browse_history  # noqa: E402
import quickstart  # noqa: E402
import stream_events  # noqa: E402

BASE = "http://localhost:4096"

SESSION = {
    "id": "ses_e",
    "slug": "s",
    "projectID": "prj",
    "directory": "/tmp",
    "path": "",
    "title": "my session",
    "version": "1",
    "time": {"created": 1, "updated": 1},
}

ASSISTANT = {
    "id": "msg_a",
    "sessionID": "ses_e",
    "role": "assistant",
    "time": {"created": 1, "completed": 2},
    "parentID": "msg_u",
    "modelID": "m",
    "providerID": "p",
    "mode": "build",
    "agent": "build",
    "path": {"cwd": "/tmp", "root": "/tmp"},
    "cost": 0.0,
    "tokens": {"total": 2.0, "input": 1, "output": 1, "reasoning": 0, "cache": {"read": 0, "write": 0}},
    "finish": "stop",
}

TEXT_PART = {"id": "prt_t", "sessionID": "ses_e", "messageID": "msg_a", "type": "text", "text": "pong"}


@pytest.fixture(autouse=True)
def mock_server() -> Generator[respx.MockRouter, None, None]:
    """Mock the endpoints the examples touch (not all are used by every test)."""
    with respx.mock(base_url=BASE, assert_all_called=False) as router:
        router.get("/global/health").mock(return_value=httpx.Response(200, json={"healthy": True, "version": "1.0"}))
        router.post("/session").mock(return_value=httpx.Response(200, json=SESSION))
        router.delete("/session/ses_e").mock(return_value=httpx.Response(200, json=True))
        router.post("/session/ses_e/message").mock(
            return_value=httpx.Response(200, json={"info": ASSISTANT, "parts": [TEXT_PART]})
        )
        router.get("/session").mock(return_value=httpx.Response(200, json=[SESSION]))
        router.get("/session/ses_e/message").mock(
            return_value=httpx.Response(200, json=[{"info": ASSISTANT, "parts": [TEXT_PART]}])
        )
        router.post("/session/ses_e/prompt_async").mock(return_value=httpx.Response(204))
        sse = (
            f"data: {json.dumps({'type': 'message.part.delta', 'properties': {'sessionID': 'ses_e', 'field': 'text', 'delta': 'hello '}})}\n\n"
            f"data: {json.dumps({'type': 'message.part.delta', 'properties': {'sessionID': 'ses_e', 'field': 'text', 'delta': 'world'}})}\n\n"
            f"data: {json.dumps({'type': 'session.idle', 'properties': {'sessionID': 'ses_e'}})}\n\n"
        ).encode()
        router.get("/event").mock(
            return_value=httpx.Response(200, headers={"Content-Type": "text/event-stream"}, content=sse)
        )
        yield router


async def test_quickstart(mock_server: respx.MockRouter, capsys: pytest.CaptureFixture[str]) -> None:
    """quickstart.main drives health → create → prompt → parts → delete."""
    await quickstart.main(BASE)
    out = capsys.readouterr().out
    assert "health: 1.0" in out
    assert "assistant: pong" in out
    assert "tokens: 2.0" in out


async def test_browse_history(mock_server: respx.MockRouter, capsys: pytest.CaptureFixture[str]) -> None:
    """browse_history.main lists sessions then renders message parts."""
    await browse_history.main(BASE)
    out = capsys.readouterr().out
    assert "ses_e" in out
    assert "[assistant] msg_a  finish=stop" in out
    assert "text: 'pong'" in out


async def test_stream_events(mock_server: respx.MockRouter, capsys: pytest.CaptureFixture[str]) -> None:
    """stream_events.main prints deltas as they arrive and stops at session.idle."""
    await stream_events.main(BASE)
    out = capsys.readouterr().out
    assert "hello world" in out
    assert "session.idle" in out

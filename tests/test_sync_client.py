"""Mirror the async client tests against the synchronous ``OpenCodeClient``.

Ensures the sync and async surfaces stay behaviourally identical (same wire
format, same parsing, same error mapping) and adds coverage for the
client-level options: retries, ``with_options``, and layered exceptions.
"""

from __future__ import annotations

import json
from collections.abc import Generator
from typing import Any

import httpx
import pytest
import respx

from opencode_client import (
    OpenCodeClient,
    OpenCodeNotFoundError,
    OpenCodeServerError,
    OpenCodeTimeoutError,
    OpenCodeTransportError,
)

BASE = "http://localhost:4096"


def _session_payload(session_id: str = "ses_abc") -> dict[str, Any]:
    return {
        "id": session_id,
        "slug": "hello",
        "projectID": "prj_1",
        "directory": "/tmp/proj",
        "path": "",
        "title": "new session",
        "version": "0.1.0",
        "time": {"created": 1000, "updated": 2000},
    }


def _assistant_message(session_id: str = "ses_abc") -> dict[str, Any]:
    return {
        "id": "msg_2",
        "sessionID": session_id,
        "role": "assistant",
        "time": {"created": 1100, "completed": 1200},
        "parentID": "msg_1",
        "modelID": "claude-x",
        "providerID": "anthropic",
        "mode": "build",
        "agent": "build",
        "path": {"cwd": "/tmp", "root": "/tmp"},
        "cost": 0.01,
        "tokens": {"input": 10, "output": 5, "reasoning": 0, "cache": {"read": 0, "write": 0}},
    }


@pytest.fixture(autouse=True)
def mock_server() -> Generator[respx.MockRouter, None, None]:
    with respx.mock(base_url=BASE) as router:
        yield router


class TestSyncSurface:
    def test_health(self, mock_server: respx.MockRouter) -> None:
        mock_server.get("/global/health").mock(
            return_value=httpx.Response(200, json={"healthy": True, "version": "1.2.3"})
        )
        with OpenCodeClient(BASE) as client:
            health = client.server.health()
        assert health.healthy is True
        assert health.version == "1.2.3"

    def test_create_with_body(self, mock_server: respx.MockRouter) -> None:
        mock_server.post("/session").mock(return_value=httpx.Response(200, json=_session_payload("ses_new")))
        from opencode_client import CreateSessionRequest, ModelID

        with OpenCodeClient(BASE) as client:
            session = client.sessions.create(
                body=CreateSessionRequest(title="hello", model=ModelID(id="m", provider_id="p"))
            )
        assert session.id == "ses_new"
        sent = json.loads(mock_server.post("/session").calls.last.request.content)
        assert sent["model"] == {"id": "m", "providerID": "p"}

    def test_prompt_serialises_text(self, mock_server: respx.MockRouter) -> None:
        mock_server.post("/session/ses_abc/message").mock(
            return_value=httpx.Response(200, json={"info": _assistant_message(), "parts": []})
        )
        with OpenCodeClient(BASE) as client:
            result = client.sessions.prompt("ses_abc", "say hi")
        assert result.info.role == "assistant"
        sent = json.loads(mock_server.post("/session/ses_abc/message").calls.last.request.content)
        assert sent["parts"] == [{"type": "text", "text": "say hi"}]

    def test_sync_event_stream(self, mock_server: respx.MockRouter) -> None:
        body = f"data: {json.dumps({'type': 'session.created', 'properties': {}})}\n\n".encode()
        mock_server.get("/event").mock(
            return_value=httpx.Response(200, headers={"Content-Type": "text/event-stream"}, content=body)
        )
        with OpenCodeClient(BASE) as client:
            with client.server.stream_events() as stream:
                events = list(stream.iter_events())
        assert [e.type for e in events] == ["session.created"]


class TestRetries:
    def test_retries_then_succeeds(self, mock_server: respx.MockRouter) -> None:
        route = mock_server.get("/global/health")
        route.side_effect = [
            httpx.Response(503, json={"name": "Unavailable"}),
            httpx.Response(200, json={"healthy": True, "version": "1.2.3"}),
        ]
        with OpenCodeClient(BASE, max_retries=1) as client:
            health = client.server.health()
        assert health.version == "1.2.3"
        assert route.calls.call_count == 2

    def test_no_retry_on_4xx(self, mock_server: respx.MockRouter) -> None:
        mock_server.get("/session/ses_missing").mock(
            return_value=httpx.Response(404, json={"name": "NotFound", "data": {"message": "nope"}})
        )
        with OpenCodeClient(BASE, max_retries=3) as client:
            with pytest.raises(OpenCodeNotFoundError):
                client.sessions.get("ses_missing")
        assert mock_server.get("/session/ses_missing").calls.call_count == 1

    def test_retry_exhausted_raises_server_error(self, mock_server: respx.MockRouter) -> None:
        mock_server.get("/global/health").mock(return_value=httpx.Response(500, json={"name": "Internal", "data": {}}))
        with OpenCodeClient(BASE, max_retries=1) as client:
            with pytest.raises(OpenCodeServerError):
                client.server.health()
        # 1 initial + 1 retry = 2 calls.
        assert mock_server.get("/global/health").calls.call_count == 2

    def test_transport_error_wrapped(self, mock_server: respx.MockRouter) -> None:
        mock_server.get("/global/health").mock(side_effect=httpx.ConnectError("conn reset"))
        with OpenCodeClient(BASE, max_retries=0) as client:
            with pytest.raises(OpenCodeTransportError):
                client.server.health()

    def test_timeout_wrapped_to_timeout_error(self, mock_server: respx.MockRouter) -> None:
        mock_server.get("/global/health").mock(side_effect=httpx.ReadTimeout("slow"))
        with OpenCodeClient(BASE, max_retries=0) as client:
            with pytest.raises(OpenCodeTimeoutError):
                client.server.health()


class TestWithOptions:
    def test_override_and_keep(self) -> None:
        client = OpenCodeClient(BASE, timeout=5, max_retries=1)
        assert client.base_url == BASE
        assert client.timeout == 5
        overridden = client.with_options(timeout=30)
        assert overridden.timeout == 30
        assert overridden.max_retries == 1  # kept
        assert overridden.base_url == BASE  # kept

    def test_override_base_url(self) -> None:
        client = OpenCodeClient(BASE, password="s3cret")
        copy = client.with_options(base_url="http://other:1")
        assert copy.base_url == "http://other:1"
        # The copy shares the password option even though we only overrode the URL.
        assert copy.http is not client.http

import json
from collections.abc import Generator
from typing import Any

import httpx
import pytest
import respx

from opencode_client import (
    AsyncOpenCodeClient,
    CreateSessionRequest,
    MessageWithParts,
    ModelID,
    OpenCodeApiError,
    OpenCodeNotFoundError,
    PromptModel,
    TextPartInput,
    UpdateSessionRequest,
)

BASE = "http://localhost:4096"


@pytest.fixture
def client() -> AsyncOpenCodeClient:
    return AsyncOpenCodeClient(BASE)


@pytest.fixture(autouse=True)
def mock_server() -> Generator[respx.MockRouter, None, None]:
    with respx.mock(base_url=BASE) as router:
        yield router


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


def _user_message(session_id: str = "ses_abc") -> dict[str, Any]:
    return {
        "id": "msg_1",
        "sessionID": session_id,
        "role": "user",
        "time": {"created": 1000},
        "agent": "build",
        "model": {"providerID": "anthropic", "modelID": "claude-x"},
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


class TestHealth:
    async def test_health(self, mock_server: respx.MockRouter, client: AsyncOpenCodeClient) -> None:
        mock_server.get("/global/health").mock(
            return_value=httpx.Response(200, json={"healthy": True, "version": "1.2.3"})
        )
        health = await client.server.health()
        assert health.healthy is True
        assert health.version == "1.2.3"


class TestSessions:
    async def test_list_sessions(self, mock_server: respx.MockRouter, client: AsyncOpenCodeClient) -> None:
        mock_server.get("/session").mock(return_value=httpx.Response(200, json=[_session_payload()]))
        sessions = await client.sessions.list_sessions(directory="/tmp/proj")
        assert len(sessions) == 1
        assert sessions[0].id == "ses_abc"
        request = mock_server.get("/session").calls.last.request
        assert request.url.params["directory"] == "/tmp/proj"

    async def test_create_session_minimal(self, mock_server: respx.MockRouter, client: AsyncOpenCodeClient) -> None:
        mock_server.post("/session").mock(return_value=httpx.Response(200, json=_session_payload()))
        session = await client.sessions.create()
        assert session.id == "ses_abc"
        request = mock_server.post("/session").calls.last.request
        assert request.content == b"{}"

    async def test_create_session_with_body(self, mock_server: respx.MockRouter, client: AsyncOpenCodeClient) -> None:
        mock_server.post("/session").mock(return_value=httpx.Response(200, json=_session_payload("ses_new")))
        body = CreateSessionRequest(
            title="hello",
            model=ModelID(id="claude-x", provider_id="anthropic"),
        )
        session = await client.sessions.create(body=body)
        assert session.id == "ses_new"
        sent = json.loads(mock_server.post("/session").calls.last.request.content)
        assert sent["title"] == "hello"
        assert sent["model"] == {"id": "claude-x", "providerID": "anthropic"}
        assert "parentID" not in sent

    async def test_get_and_update_session(self, mock_server: respx.MockRouter, client: AsyncOpenCodeClient) -> None:
        mock_server.get("/session/ses_abc").mock(return_value=httpx.Response(200, json=_session_payload()))
        mock_server.patch("/session/ses_abc").mock(return_value=httpx.Response(200, json=_session_payload()))
        got = await client.sessions.get("ses_abc")
        assert got.title == "new session"
        updated = await client.sessions.update("ses_abc", UpdateSessionRequest(title="renamed"))
        assert updated.title == "new session"
        sent = json.loads(mock_server.patch("/session/ses_abc").calls.last.request.content)
        assert sent == {"title": "renamed"}

    async def test_delete_session(self, mock_server: respx.MockRouter, client: AsyncOpenCodeClient) -> None:
        mock_server.delete("/session/ses_abc").mock(return_value=httpx.Response(200, json=True))
        assert await client.sessions.delete("ses_abc") is True

    async def test_abort_session(self, mock_server: respx.MockRouter, client: AsyncOpenCodeClient) -> None:
        mock_server.post("/session/ses_abc/abort").mock(return_value=httpx.Response(200, json=True))
        assert await client.sessions.abort("ses_abc") is True

    async def test_api_error(self, mock_server: respx.MockRouter, client: AsyncOpenCodeClient) -> None:
        mock_server.get("/session/ses_missing").mock(
            return_value=httpx.Response(
                404,
                json={"name": "NotFoundError", "data": {"message": "Session not found"}},
            )
        )
        with pytest.raises(OpenCodeNotFoundError) as exc_info:
            await client.sessions.get("ses_missing")
        assert isinstance(exc_info.value, OpenCodeApiError)
        assert exc_info.value.status_code == 404
        payload = exc_info.value.payload
        assert payload["data"]["message"] == "Session not found"


class TestAsyncEventStream:
    async def test_stream_events_end_to_end(self, mock_server: respx.MockRouter, client: AsyncOpenCodeClient) -> None:
        events = [
            json.dumps({"id": "evt_1", "type": "session.created", "properties": {"info": _session_payload()}}),
            json.dumps({"id": "evt_2", "type": "message.updated", "properties": {"info": _assistant_message()}}),
        ]
        body = "".join(f"data: {e}\n\n" for e in events).encode()
        mock_server.get("/event").mock(
            return_value=httpx.Response(
                200,
                headers={"Content-Type": "text/event-stream"},
                content=body,
            )
        )
        async with client.server.stream_events() as stream:
            assert stream.connections_opened == 1
            received = [event async for event in stream.aiter_events()]
        assert [e.type for e in received] == ["session.created", "message.updated"]
        assert received[1].properties["info"]["role"] == "assistant"


class TestPrompt:
    async def test_prompt_with_text(self, mock_server: respx.MockRouter, client: AsyncOpenCodeClient) -> None:
        mock_server.post("/session/ses_abc/message").mock(
            return_value=httpx.Response(
                200,
                json={"info": _assistant_message(), "parts": []},
            )
        )
        result = await client.sessions.prompt("ses_abc", "say hi")
        assert isinstance(result, MessageWithParts)
        assert result.info.role == "assistant"
        sent = json.loads(mock_server.post("/session/ses_abc/message").calls.last.request.content)
        assert sent["parts"] == [{"type": "text", "text": "say hi"}]

    async def test_prompt_with_parts_and_model(
        self, mock_server: respx.MockRouter, client: AsyncOpenCodeClient
    ) -> None:
        mock_server.post("/session/ses_abc/message").mock(
            return_value=httpx.Response(200, json={"info": _user_message(), "parts": []})
        )
        await client.sessions.prompt(
            "ses_abc",
            [TextPartInput(type="text", text="hi", synthetic=True)],
            model=PromptModel(provider_id="anthropic", model_id="claude-x"),
        )
        sent = json.loads(mock_server.post("/session/ses_abc/message").calls.last.request.content)
        assert sent["parts"][0] == {"type": "text", "text": "hi", "synthetic": True}
        assert sent["model"] == {"providerID": "anthropic", "modelID": "claude-x"}

    async def test_list_messages_parses_union(self, mock_server: respx.MockRouter, client: AsyncOpenCodeClient) -> None:
        mock_server.get("/session/ses_abc/message").mock(
            return_value=httpx.Response(
                200,
                json=[
                    {"info": _user_message(), "parts": []},
                    {"info": _assistant_message(), "parts": []},
                ],
            )
        )
        messages = await client.sessions.list_messages("ses_abc")
        assert len(messages) == 2
        assert messages[0].info.role == "user"
        assert messages[1].info.role == "assistant"
        user = messages[0].info
        assert user.model.provider_id == "anthropic"
        asst = messages[1].info
        assert asst.tokens.cache.read == 0
        assert asst.path.cwd == "/tmp"

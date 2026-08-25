"""Tests for the session-domain extras added in IT-011 (sync + async)."""

from __future__ import annotations

import json
from collections.abc import Generator
from typing import Any

import httpx
import pytest
import respx

from opencode_client import (
    AsyncOpenCodeClient,
    MessageWithParts,
    OpenCodeClient,
    OpenCodeConflictError,
    PromptModel,
    SessionFileDiff,
    SessionStatusBusy,
    SessionStatusIdle,
    SessionStatusRetry,
    TextPart,
    Todo,
)

BASE = "http://localhost:4096"

_SESSION = {
    "id": "ses_1",
    "slug": "test",
    "projectID": "proj_1",
    "directory": "/tmp",
    "path": "/tmp",
    "title": "t",
    "version": "1",
    "time": {"created": 1, "updated": 2},
}


def _assistant_message_wire() -> dict[str, Any]:
    return {
        "id": "msg_1",
        "sessionID": "ses_1",
        "role": "assistant",
        "time": {"created": 1},
        "parentID": "msg_0",
        "modelID": "m",
        "providerID": "p",
        "mode": "build",
        "agent": "build",
        "path": {"cwd": "/tmp", "root": "/tmp"},
        "cost": 0,
        "tokens": {"input": 0, "output": 0, "reasoning": 0, "cache": {"read": 0, "write": 0}},
    }


def _part_wire() -> dict[str, Any]:
    return {"id": "prt_1", "messageID": "msg_1", "sessionID": "ses_1", "type": "text", "text": "hi"}


@pytest.fixture(autouse=True)
def mock_server() -> Generator[respx.MockRouter, None, None]:
    with respx.mock(base_url=BASE) as router:
        yield router


class TestSessionExtrasSync:
    def test_status_parses_discriminated_union(self, mock_server: respx.MockRouter) -> None:
        payload = {
            "ses_idle": {"type": "idle"},
            "ses_busy": {"type": "busy"},
            "ses_retry": {
                "type": "retry",
                "attempt": 2,
                "message": "boom",
                "next": 123,
                "action": {"reason": "r", "provider": "p", "title": "t", "message": "m", "label": "l"},
            },
        }
        mock_server.get("/session/status").mock(return_value=httpx.Response(200, json=payload))
        with OpenCodeClient(BASE) as client:
            status = client.sessions.status()
        assert isinstance(status["ses_idle"], SessionStatusIdle)
        assert isinstance(status["ses_busy"], SessionStatusBusy)
        retry = status["ses_retry"]
        assert isinstance(retry, SessionStatusRetry)
        assert retry.attempt == 2 and retry.action is not None and retry.action.provider == "p"

    def test_children_returns_sessions(self, mock_server: respx.MockRouter) -> None:
        route = mock_server.get("/session/ses_1/children").mock(return_value=httpx.Response(200, json=[_SESSION]))
        with OpenCodeClient(BASE) as client:
            children = client.sessions.children("ses_1")
        assert children[0].id == "ses_1"
        assert "directory" not in route.calls.last.request.url.params

    def test_list_todos(self, mock_server: respx.MockRouter) -> None:
        mock_server.get("/session/ses_1/todo").mock(
            return_value=httpx.Response(200, json=[{"content": "do it", "status": "pending", "priority": "high"}])
        )
        with OpenCodeClient(BASE) as client:
            todos = client.sessions.list_todos("ses_1")
        assert isinstance(todos[0], Todo)
        assert todos[0].status == "pending" and todos[0].priority == "high"

    def test_diff_sends_optional_message_id(self, mock_server: respx.MockRouter) -> None:
        route = mock_server.get("/session/ses_1/diff").mock(
            return_value=httpx.Response(200, json=[{"additions": 1, "deletions": 0}])
        )
        with OpenCodeClient(BASE) as client:
            items = client.sessions.diff("ses_1", message_id="msg_9")
        sent = route.calls.last.request.url.params
        assert sent["messageID"] == "msg_9"
        # only additions/deletions are guaranteed by the wire schema
        item = items[0]
        assert isinstance(item, SessionFileDiff)
        assert item.file is None and item.patch is None and item.additions == 1

    def test_revert_sends_body_and_returns_session(self, mock_server: respx.MockRouter) -> None:
        route = mock_server.post("/session/ses_1/revert").mock(return_value=httpx.Response(200, json=_SESSION))
        with OpenCodeClient(BASE) as client:
            session = client.sessions.revert("ses_1", "msg_1", part_id="prt_1")
        assert session.id == "ses_1"
        body = json.loads(route.calls.last.request.content)
        assert body == {"messageID": "msg_1", "partID": "prt_1"}

    def test_revert_busy_maps_to_conflict(self, mock_server: respx.MockRouter) -> None:
        mock_server.post("/session/ses_1/revert").mock(
            return_value=httpx.Response(409, json={"name": "SessionBusyError", "data": {"message": "busy"}})
        )
        with OpenCodeClient(BASE) as client:
            with pytest.raises(OpenCodeConflictError):
                client.sessions.revert("ses_1", "msg_1")

    def test_unrevert_and_init(self, mock_server: respx.MockRouter) -> None:
        unrevert_route = mock_server.post("/session/ses_1/unrevert").mock(
            return_value=httpx.Response(200, json=_SESSION)
        )
        init_route = mock_server.post("/session/ses_1/init").mock(return_value=httpx.Response(200, json=True))
        with OpenCodeClient(BASE) as client:
            session = client.sessions.unrevert("ses_1")
            ok = client.sessions.init("ses_1", provider_id="p", model_id="m", message_id="msg_1")
        assert session.id == "ses_1" and ok is True
        # unrevert carries no body; init's body names the init model
        assert unrevert_route.calls.last.request.content == b""
        assert json.loads(init_route.calls.last.request.content) == {
            "providerID": "p",
            "modelID": "m",
            "messageID": "msg_1",
        }

    def test_command_joins_model_into_wire_string(self, mock_server: respx.MockRouter) -> None:
        route = mock_server.post("/session/ses_1/command").mock(
            return_value=httpx.Response(200, json={"info": _assistant_message_wire(), "parts": [_part_wire()]})
        )
        with OpenCodeClient(BASE) as client:
            result = client.sessions.command("ses_1", "init", "", model=PromptModel(provider_id="p", model_id="m"))
        assert isinstance(result, MessageWithParts)
        body = json.loads(route.calls.last.request.content)
        assert body["model"] == "p/m"
        assert body["command"] == "init" and body["arguments"] == ""

    def test_shell_requires_agent_and_keeps_model_object(self, mock_server: respx.MockRouter) -> None:
        route = mock_server.post("/session/ses_1/shell").mock(
            return_value=httpx.Response(200, json={"info": _assistant_message_wire(), "parts": [_part_wire()]})
        )
        with OpenCodeClient(BASE) as client:
            result = client.sessions.shell(
                "ses_1", "ls -la", agent="build", model=PromptModel(provider_id="p", model_id="m")
            )
        assert isinstance(result, MessageWithParts)
        body = json.loads(route.calls.last.request.content)
        assert body == {
            "agent": "build",
            "command": "ls -la",
            "model": {"providerID": "p", "modelID": "m"},
        }

    def test_delete_part(self, mock_server: respx.MockRouter) -> None:
        route = mock_server.delete("/session/ses_1/message/msg_1/part/prt_1").mock(
            return_value=httpx.Response(200, json=True)
        )
        with OpenCodeClient(BASE) as client:
            assert client.sessions.delete_part("ses_1", "msg_1", "prt_1") is True
        assert route.calls.last.request.method == "DELETE"

    def test_update_part_sends_wire_body(self, mock_server: respx.MockRouter) -> None:
        route = mock_server.patch("/session/ses_1/message/msg_1/part/prt_1").mock(
            return_value=httpx.Response(200, json=_part_wire())
        )
        part = TextPart(type="text", id="prt_1", session_id="ses_1", message_id="msg_1", text="edited")
        with OpenCodeClient(BASE) as client:
            updated = client.sessions.update_part("ses_1", "msg_1", "prt_1", part)
        # the echoed part comes from the mocked response body
        assert isinstance(updated, TextPart)
        assert updated.text == "hi"
        body = json.loads(route.calls.last.request.content)
        assert body["id"] == "prt_1" and body["sessionID"] == "ses_1" and body["messageID"] == "msg_1"
        assert body["text"] == "edited"


class TestSessionExtrasAsync:
    async def test_status_children_todos_diff(self, mock_server: respx.MockRouter) -> None:
        mock_server.get("/session/status").mock(return_value=httpx.Response(200, json={"ses_1": {"type": "busy"}}))
        mock_server.get("/session/ses_1/children").mock(return_value=httpx.Response(200, json=[]))
        mock_server.get("/session/ses_1/todo").mock(return_value=httpx.Response(200, json=[]))
        mock_server.get("/session/ses_1/diff").mock(return_value=httpx.Response(200, json=[]))
        async with AsyncOpenCodeClient(BASE) as client:
            status = await client.sessions.status()
            children = await client.sessions.children("ses_1")
            todos = await client.sessions.list_todos("ses_1")
            diffs = await client.sessions.diff("ses_1")
        assert isinstance(status["ses_1"], SessionStatusBusy)
        assert children == [] and todos == [] and diffs == []

    async def test_revert_unrevert_init_command_shell_parts(self, mock_server: respx.MockRouter) -> None:
        mock_server.post("/session/ses_1/revert").mock(return_value=httpx.Response(200, json=_SESSION))
        mock_server.post("/session/ses_1/unrevert").mock(return_value=httpx.Response(200, json=_SESSION))
        mock_server.post("/session/ses_1/init").mock(return_value=httpx.Response(200, json=True))
        mock_server.post("/session/ses_1/command").mock(
            return_value=httpx.Response(200, json={"info": _assistant_message_wire(), "parts": []})
        )
        mock_server.post("/session/ses_1/shell").mock(
            return_value=httpx.Response(200, json={"info": _assistant_message_wire(), "parts": []})
        )
        mock_server.delete("/session/ses_1/message/msg_1/part/prt_1").mock(return_value=httpx.Response(200, json=True))
        mock_server.patch("/session/ses_1/message/msg_1/part/prt_1").mock(
            return_value=httpx.Response(200, json=_part_wire())
        )
        async with AsyncOpenCodeClient(BASE) as client:
            s = await client.sessions.revert("ses_1", "msg_1")
            assert (await client.sessions.unrevert("ses_1")).id == s.id
            assert await client.sessions.init("ses_1", provider_id="p", model_id="m", message_id="msg_1") is True
            await client.sessions.command("ses_1", "init", "")
            await client.sessions.shell("ses_1", "ls", agent="build")
            assert await client.sessions.delete_part("ses_1", "msg_1", "prt_1") is True
            part = TextPart(type="text", id="prt_1", session_id="ses_1", message_id="msg_1", text="hi")
            assert (await client.sessions.update_part("ses_1", "msg_1", "prt_1", part)).id == "prt_1"

    async def test_unrevert_busy_maps_to_conflict(self, mock_server: respx.MockRouter) -> None:
        mock_server.post("/session/ses_1/unrevert").mock(
            return_value=httpx.Response(409, json={"name": "SessionBusyError", "data": {}})
        )
        async with AsyncOpenCodeClient(BASE) as client:
            with pytest.raises(OpenCodeConflictError):
                await client.sessions.unrevert("ses_1")


class TestSessionExtrasRaw:
    def test_raw_views_mirror_new_methods(self, mock_server: respx.MockRouter) -> None:
        for method, path in [
            ("GET", "/session/status"),
            ("GET", "/session/ses_1/children"),
            ("GET", "/session/ses_1/todo"),
            ("GET", "/session/ses_1/diff"),
            ("POST", "/session/ses_1/revert"),
            ("POST", "/session/ses_1/unrevert"),
            ("POST", "/session/ses_1/init"),
            ("POST", "/session/ses_1/command"),
            ("POST", "/session/ses_1/shell"),
            ("DELETE", "/session/ses_1/message/msg_1/part/prt_1"),
            ("PATCH", "/session/ses_1/message/msg_1/part/prt_1"),
        ]:
            mock_server.request(method.upper(), path).mock(return_value=httpx.Response(200, json={}))

        with OpenCodeClient(BASE) as client:
            raw = client.sessions.with_raw_response
            responses = [
                raw.status(),
                raw.children("ses_1"),
                raw.list_todos("ses_1"),
                raw.diff("ses_1"),
                raw.revert("ses_1", "msg_1"),
                raw.unrevert("ses_1"),
                raw.init("ses_1", provider_id="p", model_id="m", message_id="msg_1"),
                raw.command("ses_1", "init", ""),
                raw.shell("ses_1", "ls", agent="build"),
                raw.delete_part("ses_1", "msg_1", "prt_1"),
                raw.update_part(
                    "ses_1",
                    "msg_1",
                    "prt_1",
                    TextPart(type="text", id="prt_1", session_id="ses_1", message_id="msg_1", text="hi"),
                ),
            ]
        assert all(isinstance(r, httpx.Response) for r in responses)

    async def test_async_raw_views_mirror_new_methods(self, mock_server: respx.MockRouter) -> None:
        for method, path in [
            ("GET", "/session/status"),
            ("GET", "/session/ses_1/children"),
            ("GET", "/session/ses_1/todo"),
            ("GET", "/session/ses_1/diff"),
            ("POST", "/session/ses_1/revert"),
            ("POST", "/session/ses_1/unrevert"),
            ("POST", "/session/ses_1/init"),
            ("POST", "/session/ses_1/command"),
            ("POST", "/session/ses_1/shell"),
            ("DELETE", "/session/ses_1/message/msg_1/part/prt_1"),
            ("PATCH", "/session/ses_1/message/msg_1/part/prt_1"),
        ]:
            mock_server.request(method.upper(), path).mock(return_value=httpx.Response(200, json={}))

        async with AsyncOpenCodeClient(BASE) as client:
            raw = client.sessions.with_raw_response
            responses = [
                await raw.status(),
                await raw.children("ses_1"),
                await raw.list_todos("ses_1"),
                await raw.diff("ses_1"),
                await raw.revert("ses_1", "msg_1"),
                await raw.unrevert("ses_1"),
                await raw.init("ses_1", provider_id="p", model_id="m", message_id="msg_1"),
                await raw.command("ses_1", "init", ""),
                await raw.shell("ses_1", "ls", agent="build"),
                await raw.delete_part("ses_1", "msg_1", "prt_1"),
                await raw.update_part(
                    "ses_1",
                    "msg_1",
                    "prt_1",
                    TextPart(type="text", id="prt_1", session_id="ses_1", message_id="msg_1", text="hi"),
                ),
            ]
        assert all(isinstance(r, httpx.Response) for r in responses)

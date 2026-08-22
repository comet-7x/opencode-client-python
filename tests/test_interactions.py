"""Tests for the permission/question interaction endpoints (sync + async)."""

from __future__ import annotations

import json
from collections.abc import Generator
from typing import Any

import httpx
import pytest
import respx

from opencode_client import (
    AsyncOpenCodeClient,
    OpenCodeClient,
    PermissionRequest,
    QuestionRequest,
)

BASE = "http://localhost:4096"


def _permission_payload(request_id: str = "per_1") -> dict[str, Any]:
    return {
        "id": request_id,
        "sessionID": "ses_abc",
        "permission": "bash",
        "patterns": ["rm -rf *"],
        "metadata": {"cwd": "/tmp"},
        "always": ["rm -rf *"],
        "tool": {"messageID": "msg_1", "callID": "call_1"},
    }


def _question_payload(request_id: str = "que_1") -> dict[str, Any]:
    return {
        "id": request_id,
        "sessionID": "ses_abc",
        "questions": [
            {
                "question": "Which framework?",
                "header": "Framework",
                "options": [
                    {"label": "React", "description": "JS library"},
                    {"label": "Vue", "description": "Alternative"},
                ],
                "multiple": False,
                "custom": True,
            }
        ],
        "tool": {"messageID": "msg_1", "callID": "call_2"},
    }


@pytest.fixture(autouse=True)
def mock_server() -> Generator[respx.MockRouter, None, None]:
    with respx.mock(base_url=BASE) as router:
        yield router


class TestPermissionsSync:
    def test_list_permissions_parses(self, mock_server: respx.MockRouter) -> None:
        mock_server.get("/permission").mock(return_value=httpx.Response(200, json=[_permission_payload()]))
        with OpenCodeClient(BASE) as client:
            result = client.server.list_permissions()
        assert len(result) == 1
        req = result[0]
        assert isinstance(req, PermissionRequest)
        assert req.id == "per_1"
        assert req.session_id == "ses_abc"
        assert req.permission == "bash"
        assert req.patterns == ["rm -rf *"]
        assert req.always == ["rm -rf *"]
        assert req.tool is not None and req.tool.call_id == "call_1"

    def test_reply_permission_once(self, mock_server: respx.MockRouter) -> None:
        mock_server.post("/permission/per_1/reply").mock(return_value=httpx.Response(200, json=True))
        with OpenCodeClient(BASE) as client:
            ok = client.server.reply_permission("per_1", "once")
        assert ok is True
        sent = json.loads(mock_server.post("/permission/per_1/reply").calls.last.request.content)
        assert sent == {"reply": "once"}

    def test_reply_permission_always_with_message(self, mock_server: respx.MockRouter) -> None:
        mock_server.post("/permission/per_1/reply").mock(return_value=httpx.Response(200, json=True))
        with OpenCodeClient(BASE) as client:
            client.server.reply_permission("per_1", "always", message="trusted dir")
        sent = json.loads(mock_server.post("/permission/per_1/reply").calls.last.request.content)
        assert sent == {"reply": "always", "message": "trusted dir"}


class TestQuestionsSync:
    def test_list_questions_parses(self, mock_server: respx.MockRouter) -> None:
        mock_server.get("/question").mock(return_value=httpx.Response(200, json=[_question_payload()]))
        with OpenCodeClient(BASE) as client:
            result = client.server.list_questions()
        assert len(result) == 1
        req = result[0]
        assert isinstance(req, QuestionRequest)
        assert req.id == "que_1"
        assert req.questions[0].header == "Framework"
        assert req.questions[0].options[0].label == "React"
        assert req.tool is not None and req.tool.message_id == "msg_1"

    def test_reply_question(self, mock_server: respx.MockRouter) -> None:
        mock_server.post("/question/que_1/reply").mock(return_value=httpx.Response(200, json=True))
        with OpenCodeClient(BASE) as client:
            ok = client.server.reply_question("que_1", [["React"]])
        assert ok is True
        sent = json.loads(mock_server.post("/question/que_1/reply").calls.last.request.content)
        assert sent == {"answers": [["React"]]}

    def test_reject_question(self, mock_server: respx.MockRouter) -> None:
        mock_server.post("/question/que_1/reject").mock(return_value=httpx.Response(200, json=True))
        with OpenCodeClient(BASE) as client:
            ok = client.server.reject_question("que_1")
        assert ok is True
        assert mock_server.post("/question/que_1/reject").calls.last.request.content in (b"", b"{}")

    def test_empty_lists(self, mock_server: respx.MockRouter) -> None:
        mock_server.get("/permission").mock(return_value=httpx.Response(200, json=[]))
        mock_server.get("/question").mock(return_value=httpx.Response(200, json=[]))
        with OpenCodeClient(BASE) as client:
            assert client.server.list_permissions() == []
            assert client.server.list_questions() == []


class TestInteractionsAsync:
    async def test_list_and_reply_permission(self, mock_server: respx.MockRouter) -> None:
        mock_server.get("/permission").mock(return_value=httpx.Response(200, json=[_permission_payload()]))
        mock_server.post("/permission/per_1/reply").mock(return_value=httpx.Response(200, json=True))
        async with AsyncOpenCodeClient(BASE) as client:
            perms = await client.server.list_permissions()
            ok = await client.server.reply_permission(perms[0].id, "reject")
        assert len(perms) == 1 and ok is True
        sent = json.loads(mock_server.post("/permission/per_1/reply").calls.last.request.content)
        assert sent == {"reply": "reject"}

    async def test_reply_and_reject_question(self, mock_server: respx.MockRouter) -> None:
        mock_server.get("/question").mock(return_value=httpx.Response(200, json=[_question_payload()]))
        mock_server.post("/question/que_1/reply").mock(return_value=httpx.Response(200, json=True))
        mock_server.post("/question/que_2/reject").mock(return_value=httpx.Response(200, json=True))
        async with AsyncOpenCodeClient(BASE) as client:
            qs = await client.server.list_questions()
            ok = await client.server.reply_question(qs[0].id, [["Vue"]])
            ok2 = await client.server.reject_question("que_2")
        assert ok is True and ok2 is True
        sent = json.loads(mock_server.post("/question/que_1/reply").calls.last.request.content)
        assert sent == {"answers": [["Vue"]]}


class TestInteractionErrors:
    def test_reply_missing_permission_raises_not_found(self, mock_server: respx.MockRouter) -> None:
        mock_server.post("/permission/per_missing/reply").mock(
            return_value=httpx.Response(404, json={"name": "NotFoundError", "data": {"message": "no such request"}})
        )
        from opencode_client import OpenCodeNotFoundError

        with OpenCodeClient(BASE) as client:
            with pytest.raises(OpenCodeNotFoundError):
                client.server.reply_permission("per_missing", "once")

    async def test_reply_missing_question_raises_not_found(self, mock_server: respx.MockRouter) -> None:
        mock_server.post("/question/que_missing/reply").mock(
            return_value=httpx.Response(404, json={"name": "NotFoundError", "data": {"message": "no such request"}})
        )
        from opencode_client import OpenCodeNotFoundError

        async with AsyncOpenCodeClient(BASE) as client:
            with pytest.raises(OpenCodeNotFoundError):
                await client.server.reply_question("que_missing", [["x"]])

"""Lock the ``with_raw_response`` mirror invariant and behaviour.

Structural: every resource's raw twin keeps the exact same public method
surface (and parameter order) as the parsed view — server drops only
``stream_events``, which yields an :class:`AsyncEventStream`, not a one-shot
response. Behavioural: raw calls hit the identical wire as parsed calls,
return the unprocessed :class:`httpx.Response`, and keep the shared
retry/error mapping. Only the package-root public API is used here on
purpose: the raw classes are reachable via ``<resource>.with_raw_response``.
"""

from __future__ import annotations

import inspect
import json
from collections.abc import Generator
from typing import Any

import httpx
import pytest
import respx

from opencode_client import (
    AsyncOpenCodeClient,
    CreateSessionRequest,
    McpLocalConfig,
    ModelID,
    OpenCodeClient,
    OpenCodeNotFoundError,
    OpenCodeServerError,
    Session,
)

BASE = "http://localhost:4096"

DOMAINS = ["sessions", "server", "vcs", "mcp", "files", "projects", "auth"]

# stream_events 返回 AsyncEventStream 而非一次性响应，是唯一没有 raw 变体的方法
RAW_EXCLUDED = {"stream_events", "stream_global_events"}


def _public_methods(cls: Any) -> dict[str, inspect.Signature]:
    return {
        name: inspect.signature(fn)
        for name, fn in inspect.getmembers(cls, inspect.isfunction)
        if not name.startswith("_")
    }


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


@pytest.fixture(autouse=True)
def mock_server() -> Generator[respx.MockRouter, None, None]:
    with respx.mock(base_url=BASE) as router:
        yield router


@pytest.fixture
def client() -> AsyncOpenCodeClient:
    return AsyncOpenCodeClient(BASE)


class TestMirrorParity:
    """The raw view must never drift from the parsed view."""

    @pytest.mark.parametrize("domain", DOMAINS)
    def test_sync_raw_matches_normal(self, domain: str) -> None:
        with OpenCodeClient(BASE) as sync_client:
            normal = getattr(sync_client, domain)
            raw = normal.with_raw_response
        normal_methods = _public_methods(type(normal))
        raw_methods = _public_methods(type(raw))
        assert set(raw_methods) == set(normal_methods) - RAW_EXCLUDED, domain
        for name in raw_methods:
            assert list(raw_methods[name].parameters) == list(normal_methods[name].parameters), (domain, name)

    @pytest.mark.parametrize("domain", DOMAINS)
    async def test_async_raw_matches_normal(self, client: AsyncOpenCodeClient, domain: str) -> None:
        normal = getattr(client, domain)
        raw = normal.with_raw_response
        normal_methods = _public_methods(type(normal))
        raw_methods = _public_methods(type(raw))
        assert set(raw_methods) == set(normal_methods) - RAW_EXCLUDED, domain
        for name in raw_methods:
            assert list(raw_methods[name].parameters) == list(normal_methods[name].parameters), (domain, name)

    async def test_stream_events_has_no_raw_variant(self, client: AsyncOpenCodeClient) -> None:
        assert not hasattr(client.server.with_raw_response, "stream_events")
        assert hasattr(client.server, "stream_events")


class TestRawSessions:
    def test_get_returns_raw_response(self, mock_server: respx.MockRouter) -> None:
        mock_server.get("/session/ses_abc").mock(return_value=httpx.Response(200, json=_session_payload()))
        with OpenCodeClient(BASE) as client:
            response = client.sessions.with_raw_response.get("ses_abc")
        assert isinstance(response, httpx.Response)
        assert response.status_code == 200
        # raw body 与正常路径解析出的模型等价
        assert Session.model_validate(response.json()).id == "ses_abc"

    def test_wire_matches_parsed_view(self, mock_server: respx.MockRouter) -> None:
        mock_server.get("/session").mock(return_value=httpx.Response(200, json=[_session_payload()]))
        with OpenCodeClient(BASE) as client:
            client.sessions.list_sessions(directory="/tmp/proj", search="hello")
            first_url = mock_server.get("/session").calls.last.request.url
            raw = client.sessions.with_raw_response.list_sessions(directory="/tmp/proj", search="hello")
        assert mock_server.get("/session").calls.last.request.url == first_url
        assert raw.status_code == 200

    def test_create_serialises_same_body(self, mock_server: respx.MockRouter) -> None:
        mock_server.post("/session").mock(return_value=httpx.Response(200, json=_session_payload("ses_new")))
        body = CreateSessionRequest(title="hello", model=ModelID(id="m", provider_id="p"))
        with OpenCodeClient(BASE) as client:
            raw = client.sessions.with_raw_response.create(body=body)
        sent = json.loads(mock_server.post("/session").calls.last.request.content)
        assert sent["model"] == {"id": "m", "providerID": "p"}
        assert raw.status_code == 200

    def test_error_mapping_preserved(self, mock_server: respx.MockRouter) -> None:
        mock_server.get("/session/ses_missing").mock(
            return_value=httpx.Response(404, json={"name": "NotFoundError", "data": {"message": "nope"}})
        )
        with OpenCodeClient(BASE) as client:
            with pytest.raises(OpenCodeNotFoundError) as exc_info:
                client.sessions.with_raw_response.get("ses_missing")
        assert exc_info.value.status_code == 404

    def test_retries_shared(self, mock_server: respx.MockRouter) -> None:
        route = mock_server.get("/session/ses_abc")
        route.side_effect = [httpx.Response(503), httpx.Response(200, json=_session_payload())]
        with OpenCodeClient(BASE, max_retries=1) as client:
            raw = client.sessions.with_raw_response.get("ses_abc")
        assert raw.status_code == 200
        assert route.calls.call_count == 2

    def test_prompt_async_returns_raw_response(self, mock_server: respx.MockRouter) -> None:
        mock_server.post("/session/ses_abc/prompt_async").mock(return_value=httpx.Response(204))
        with OpenCodeClient(BASE) as client:
            client.sessions.prompt_async("ses_abc", "hi")  # 正常视图：返回 None（不取返回值）
            raw = client.sessions.with_raw_response.prompt_async("ses_abc", "hi")
        assert isinstance(raw, httpx.Response)
        assert raw.status_code == 204


class TestRawServer:
    async def test_health_raw(self, mock_server: respx.MockRouter, client: AsyncOpenCodeClient) -> None:
        mock_server.get("/global/health").mock(
            return_value=httpx.Response(200, json={"healthy": True, "version": "1.2.3"})
        )
        raw = await client.server.with_raw_response.health()
        assert isinstance(raw, httpx.Response)
        assert raw.json()["healthy"] is True

    async def test_update_config_same_body(self, mock_server: respx.MockRouter, client: AsyncOpenCodeClient) -> None:
        route = mock_server.patch("/config")
        route.mock(return_value=httpx.Response(200, json={}))
        await client.server.update_config({"share": "disabled"})
        first_body = json.loads(route.calls.last.request.content)
        raw = await client.server.with_raw_response.update_config({"share": "disabled"})
        assert json.loads(route.calls.last.request.content) == first_body
        assert raw.status_code == 200

    async def test_reply_permission_raw(self, mock_server: respx.MockRouter, client: AsyncOpenCodeClient) -> None:
        mock_server.post("/permission/per_1/reply").mock(return_value=httpx.Response(200, json=True))
        raw = await client.server.with_raw_response.reply_permission("per_1", "once")
        sent = json.loads(mock_server.post("/permission/per_1/reply").calls.last.request.content)
        assert sent == {"reply": "once"}
        assert raw.json() is True

    async def test_server_error_mapping_preserved(
        self, mock_server: respx.MockRouter, client: AsyncOpenCodeClient
    ) -> None:
        mock_server.get("/agent").mock(
            return_value=httpx.Response(500, json={"name": "InternalServerError", "data": {"message": "boom"}})
        )
        with pytest.raises(OpenCodeServerError) as exc_info:
            await client.server.with_raw_response.list_agents()
        assert exc_info.value.status_code == 500


class TestRawVcsAndMcp:
    def test_vcs_diff_raw_response(self, mock_server: respx.MockRouter) -> None:
        mock_server.get("/vcs/diff").mock(return_value=httpx.Response(200, json=[]))
        with OpenCodeClient(BASE) as client:
            raw = client.vcs.with_raw_response.diff("git", context=5)
        request = mock_server.get("/vcs/diff").calls.last.request
        assert request.url.params["mode"] == "git"
        assert request.url.params["context"] == "5"
        assert raw.status_code == 200

    async def test_mcp_add_raw(self, mock_server: respx.MockRouter, client: AsyncOpenCodeClient) -> None:
        mock_server.post("/mcp").mock(return_value=httpx.Response(200, json={}))
        raw = await client.mcp.with_raw_response.add(
            "fs", McpLocalConfig(type="local", command=["npx", "-y", "@modelcontextprotocol/server-filesystem"])
        )
        sent = json.loads(mock_server.post("/mcp").calls.last.request.content)
        assert sent["name"] == "fs"
        assert sent["config"]["type"] == "local"
        assert raw.status_code == 200

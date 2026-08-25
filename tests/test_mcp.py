"""Tests for the MCP endpoints (status/add + OAuth/connect lifecycle, sync + async)."""

from __future__ import annotations

import json
from collections.abc import Generator
from typing import Any

import httpx
import pytest
import respx

from opencode_client import (
    AsyncOpenCodeClient,
    McpLocalConfig,
    McpOAuthConfig,
    McpOAuthStart,
    McpRemoteConfig,
    MCPStatusConnected,
    MCPStatusFailed,
    MCPStatusNeedsAuth,
    MCPStatusNeedsClientRegistration,
    OpenCodeClient,
    OpenCodeNotFoundError,
)

BASE = "http://localhost:4096"


def _status_map() -> dict[str, Any]:
    return {
        "fs": {"status": "connected"},
        "notes": {"status": "disabled"},
        "search": {"status": "failed", "error": "spawn ENOENT"},
        "authed": {"status": "needs_auth"},
        "reg": {"status": "needs_client_registration", "error": "register first"},
    }


@pytest.fixture(autouse=True)
def mock_server() -> Generator[respx.MockRouter, None, None]:
    with respx.mock(base_url=BASE) as router:
        yield router


class TestMcpStatusSync:
    def test_parses_discriminated_union(self, mock_server: respx.MockRouter) -> None:
        mock_server.get("/mcp").mock(return_value=httpx.Response(200, json=_status_map()))
        with OpenCodeClient(BASE) as client:
            statuses = client.mcp.status(directory="/tmp/dir")
        assert set(statuses) == {"fs", "notes", "search", "authed", "reg"}
        assert isinstance(statuses["fs"], MCPStatusConnected) and statuses["fs"].status == "connected"
        assert statuses["notes"].status == "disabled"
        failed = statuses["search"]
        assert isinstance(failed, MCPStatusFailed) and failed.error == "spawn ENOENT"
        assert isinstance(statuses["authed"], MCPStatusNeedsAuth)
        reg = statuses["reg"]
        assert reg.status == "needs_client_registration" and reg.error == "register first"

    def test_empty_map(self, mock_server: respx.MockRouter) -> None:
        mock_server.get("/mcp").mock(return_value=httpx.Response(200, json={}))
        with OpenCodeClient(BASE) as client:
            assert client.mcp.status() == {}


class TestMcpAddSync:
    def test_add_local(self, mock_server: respx.MockRouter) -> None:
        mock_server.post("/mcp").mock(return_value=httpx.Response(200, json={"fs": {"status": "connected"}}))
        config = McpLocalConfig(type="local", command=["node", "server.js"], environment={"KEY": "v"})
        with OpenCodeClient(BASE) as client:
            result = client.mcp.add("fs", config)
        assert result == {"fs": {"status": "connected"}}
        sent = json.loads(mock_server.post("/mcp").calls.last.request.content)
        assert sent == {
            "name": "fs",
            "config": {"type": "local", "command": ["node", "server.js"], "environment": {"KEY": "v"}},
        }

    def test_add_remote_with_oauth_false(self, mock_server: respx.MockRouter) -> None:
        mock_server.post("/mcp").mock(return_value=httpx.Response(200, json={"r": {"status": "needs_auth"}}))
        config = McpRemoteConfig(type="remote", url="https://mcp.example", oauth=False, headers={"X": "1"})
        with OpenCodeClient(BASE) as client:
            client.mcp.add("r", config)
        sent = json.loads(mock_server.post("/mcp").calls.last.request.content)
        assert sent["config"] == {"type": "remote", "url": "https://mcp.example", "headers": {"X": "1"}, "oauth": False}

    def test_add_remote_with_oauth_config(self, mock_server: respx.MockRouter) -> None:
        mock_server.post("/mcp").mock(return_value=httpx.Response(200, json={"r": {"status": "connected"}}))
        config = McpRemoteConfig(
            type="remote",
            url="https://mcp.example",
            oauth=McpOAuthConfig(client_id="cid", client_secret="sec", scope="read"),
        )
        with OpenCodeClient(BASE) as client:
            client.mcp.add("r", config)
        sent = json.loads(mock_server.post("/mcp").calls.last.request.content)
        assert sent["config"]["oauth"] == {"clientId": "cid", "clientSecret": "sec", "scope": "read"}


class TestMcpAsync:
    async def test_status(self, mock_server: respx.MockRouter) -> None:
        mock_server.get("/mcp").mock(return_value=httpx.Response(200, json=_status_map()))
        async with AsyncOpenCodeClient(BASE) as client:
            statuses = await client.mcp.status()
        failed = statuses["search"]
        assert isinstance(failed, MCPStatusFailed) and failed.status == "failed"
        reg = statuses["reg"]
        assert isinstance(reg, MCPStatusNeedsClientRegistration) and reg.error == "register first"

    async def test_add(self, mock_server: respx.MockRouter) -> None:
        mock_server.post("/mcp").mock(return_value=httpx.Response(200, json={"fs": {"status": "connected"}}))
        config = McpLocalConfig(type="local", command=["uvx", "mcp-server"])
        async with AsyncOpenCodeClient(BASE) as client:
            result = await client.mcp.add("fs", config)
        assert result["fs"]["status"] == "connected"
        sent = json.loads(mock_server.post("/mcp").calls.last.request.content)
        assert sent["config"]["command"] == ["uvx", "mcp-server"]


class TestMcpLifecycleSync:
    """OAuth lifecycle + connect/disconnect (the six /mcp/{name} endpoints)."""

    def test_start_oauth_parses_camel_case_document(self, mock_server: respx.MockRouter) -> None:
        route = mock_server.post("/mcp/notes/auth").mock(
            return_value=httpx.Response(
                200, json={"authorizationUrl": "https://auth.example/authorize", "oauthState": "st-1"}
            )
        )
        with OpenCodeClient(BASE) as client:
            started = client.mcp.start_oauth("notes")
        assert isinstance(started, McpOAuthStart)
        assert started.authorization_url == "https://auth.example/authorize"
        assert started.oauth_state == "st-1"
        assert route.calls.last.request.url.path == "/mcp/notes/auth"

    def test_complete_oauth_sends_code_and_parses_status(self, mock_server: respx.MockRouter) -> None:
        route = mock_server.post("/mcp/notes/auth/callback").mock(
            return_value=httpx.Response(200, json={"status": "connected"})
        )
        with OpenCodeClient(BASE) as client:
            status = client.mcp.complete_oauth("notes", code="abc123")
        assert isinstance(status, MCPStatusConnected)
        sent = json.loads(route.calls.last.request.content)
        assert sent == {"code": "abc123"}

    def test_authenticate_returns_status(self, mock_server: respx.MockRouter) -> None:
        mock_server.post("/mcp/notes/auth/authenticate").mock(
            return_value=httpx.Response(200, json={"status": "connected"})
        )
        with OpenCodeClient(BASE) as client:
            status = client.mcp.authenticate("notes")
        assert status.status == "connected"

    def test_remove_oauth(self, mock_server: respx.MockRouter) -> None:
        route = mock_server.delete("/mcp/notes/auth").mock(return_value=httpx.Response(200, json={"success": True}))
        with OpenCodeClient(BASE) as client:
            assert client.mcp.remove_oauth("notes") is True
        assert route.calls.last.request.method == "DELETE"

    def test_connect_disconnect(self, mock_server: respx.MockRouter) -> None:
        mock_server.post("/mcp/fs/connect").mock(return_value=httpx.Response(200, json=True))
        mock_server.post("/mcp/fs/disconnect").mock(return_value=httpx.Response(200, json=True))
        with OpenCodeClient(BASE) as client:
            assert client.mcp.connect("fs") is True
            assert client.mcp.disconnect("fs") is True

    def test_unknown_server_maps_to_not_found(self, mock_server: respx.MockRouter) -> None:
        mock_server.post("/mcp/ghost/connect").mock(
            return_value=httpx.Response(404, json={"name": "NotFound", "data": {"message": "no server"}})
        )
        with OpenCodeClient(BASE) as client:
            with pytest.raises(OpenCodeNotFoundError):
                client.mcp.connect("ghost")


class TestMcpLifecycleAsync:
    async def test_full_browser_flow(self, mock_server: respx.MockRouter) -> None:
        mock_server.post("/mcp/r/auth").mock(
            return_value=httpx.Response(
                200, json={"authorizationUrl": "https://auth.example/authorize", "oauthState": "st"}
            )
        )
        mock_server.post("/mcp/r/auth/callback").mock(return_value=httpx.Response(200, json={"status": "needs_auth"}))
        async with AsyncOpenCodeClient(BASE) as client:
            started = await client.mcp.start_oauth("r")
            status = await client.mcp.complete_oauth("r", code="c0de")
        assert isinstance(started, McpOAuthStart)
        assert isinstance(status, MCPStatusNeedsAuth)

    async def test_authenticate_remove_connect_disconnect(self, mock_server: respx.MockRouter) -> None:
        mock_server.post("/mcp/r/auth/authenticate").mock(
            return_value=httpx.Response(200, json={"status": "failed", "error": "nope"})
        )
        mock_server.delete("/mcp/r/auth").mock(return_value=httpx.Response(200, json={"success": True}))
        mock_server.post("/mcp/r/connect").mock(return_value=httpx.Response(200, json=True))
        mock_server.post("/mcp/r/disconnect").mock(return_value=httpx.Response(200, json=True))
        async with AsyncOpenCodeClient(BASE) as client:
            status = await client.mcp.authenticate("r")
            removed = await client.mcp.remove_oauth("r")
            connected = await client.mcp.connect("r")
            disconnected = await client.mcp.disconnect("r")
        assert isinstance(status, MCPStatusFailed)
        assert (removed, connected, disconnected) == (True, True, True)

    async def test_raw_start_oauth_returns_unparsed_response(self, mock_server: respx.MockRouter) -> None:
        mock_server.post("/mcp/r/auth").mock(
            return_value=httpx.Response(
                200, json={"authorizationUrl": "https://auth.example/authorize", "oauthState": "st"}
            )
        )
        async with AsyncOpenCodeClient(BASE) as client:
            response = await client.mcp.with_raw_response.start_oauth("r")
        assert response.json()["oauthState"] == "st"

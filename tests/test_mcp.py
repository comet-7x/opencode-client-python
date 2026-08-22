"""Tests for the MCP endpoints (status + add, sync + async)."""

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
    McpRemoteConfig,
    MCPStatusConnected,
    MCPStatusFailed,
    MCPStatusNeedsAuth,
    MCPStatusNeedsClientRegistration,
    OpenCodeClient,
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

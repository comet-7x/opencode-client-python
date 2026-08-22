"""MCP resource: server status and adding servers.

Maps to the ``GET/POST /mcp`` endpoints and ships in two flavours:

- :class:`McpResource` — synchronous, backed by :class:`OpenCodeClient`;
- :class:`AsyncMcpResource` — asynchronous, backed by :class:`AsyncOpenCodeClient`.

``status`` returns the full server-name -> :data:`MCPStatus` map so callers can
poll any server's lifecycle state (``connected`` / ``needs_auth`` / ...).
The connect/disconnect/auth flows are intentionally out of scope here.
"""

from __future__ import annotations

from typing import Any

from ..models import McpLocalConfig, McpRemoteConfig, MCPStatus
from ._wire import TYPE_ADAPTERS, mcp_add_body, request_spec, validate_response
from .base import AsyncResource, Resource

__all__ = ["AsyncMcpResource", "McpResource"]


class McpResource(Resource):
    """Synchronous client for the ``/mcp`` endpoints."""

    def status(self, directory: str | None = None, workspace: str | None = None) -> dict[str, MCPStatus]:
        """Get the status of every configured MCP server, keyed by name."""
        response = self._send("GET", "/mcp", **request_spec(directory=directory, workspace=workspace))
        return validate_response(response, TYPE_ADAPTERS.mcp_status)

    def add(
        self,
        name: str,
        config: McpLocalConfig | McpRemoteConfig,
        directory: str | None = None,
        workspace: str | None = None,
    ) -> dict[str, Any]:
        """Register a new MCP server (local command or remote URL).

        Args:
            name: The name under which to register the server.
            config: A :class:`McpLocalConfig` (stdio) or :class:`McpRemoteConfig`
                (HTTP/SSE).

        Returns:
            The server's resulting status document.
        """
        json_body = mcp_add_body(name, config)
        response = self._send(
            "POST", "/mcp", **request_spec(directory=directory, workspace=workspace, json_body=json_body)
        )
        return validate_response(response, TYPE_ADAPTERS.mcp_add)


class AsyncMcpResource(AsyncResource):
    """Asynchronous client for the ``/mcp`` endpoints."""

    async def status(self, directory: str | None = None, workspace: str | None = None) -> dict[str, MCPStatus]:
        """Get the status of every configured MCP server, keyed by name."""
        response = await self._send("GET", "/mcp", **request_spec(directory=directory, workspace=workspace))
        return validate_response(response, TYPE_ADAPTERS.mcp_status)

    async def add(
        self,
        name: str,
        config: McpLocalConfig | McpRemoteConfig,
        directory: str | None = None,
        workspace: str | None = None,
    ) -> dict[str, Any]:
        """Register a new MCP server (local command or remote URL).

        Args:
            name: The name under which to register the server.
            config: A :class:`McpLocalConfig` (stdio) or :class:`McpRemoteConfig`.

        Returns:
            The server's resulting status document.
        """
        json_body = mcp_add_body(name, config)
        response = await self._send(
            "POST", "/mcp", **request_spec(directory=directory, workspace=workspace, json_body=json_body)
        )
        return validate_response(response, TYPE_ADAPTERS.mcp_add)

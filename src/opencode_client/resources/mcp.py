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

import httpx

from ..models import McpLocalConfig, McpRemoteConfig, MCPStatus
from ._wire import TYPE_ADAPTERS, mcp_add_body, request_spec, validate_response
from .base import AsyncResource, Resource

__all__ = ["AsyncMcpResource", "AsyncMcpResourceWithRawResponse", "McpResource", "McpResourceWithRawResponse"]


class McpResource(Resource):
    """Synchronous client for the ``/mcp`` endpoints."""

    @property
    def with_raw_response(self) -> McpResourceWithRawResponse:
        """Prefix for the raw-response variants of every method below.

        Each call returns the unprocessed :class:`httpx.Response` instead of
        the parsed model (same retries, same error mapping on non-2xx).
        """
        return McpResourceWithRawResponse(self._client)

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

    @property
    def with_raw_response(self) -> AsyncMcpResourceWithRawResponse:
        """Prefix for the raw-response variants of every method below.

        Each call returns the unprocessed :class:`httpx.Response` instead of
        the parsed model (same retries, same error mapping on non-2xx).
        """
        return AsyncMcpResourceWithRawResponse(self._client)

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


class McpResourceWithRawResponse(Resource):
    """Synchronous raw-response view of the ``/mcp`` endpoints.

    Mirrors :class:`McpResource` method-for-method but returns the
    unprocessed response instead of the parsed model. Non-2xx still raise
    the same mapped errors; retries are shared.
    """

    def status(self, directory: str | None = None, workspace: str | None = None) -> httpx.Response:
        """Get every MCP server's status; return the raw response."""
        return self._send("GET", "/mcp", **request_spec(directory=directory, workspace=workspace))

    def add(
        self,
        name: str,
        config: McpLocalConfig | McpRemoteConfig,
        directory: str | None = None,
        workspace: str | None = None,
    ) -> httpx.Response:
        """Register a new MCP server; return the raw response."""
        json_body = mcp_add_body(name, config)
        return self._send("POST", "/mcp", **request_spec(directory=directory, workspace=workspace, json_body=json_body))


class AsyncMcpResourceWithRawResponse(AsyncResource):
    """Asynchronous raw-response view of the ``/mcp`` endpoints.

    Mirrors :class:`AsyncMcpResource` method-for-method but returns the
    unprocessed response instead of the parsed model. Non-2xx still raise
    the same mapped errors; retries are shared.
    """

    async def status(self, directory: str | None = None, workspace: str | None = None) -> httpx.Response:
        """Get every MCP server's status; return the raw response."""
        return await self._send("GET", "/mcp", **request_spec(directory=directory, workspace=workspace))

    async def add(
        self,
        name: str,
        config: McpLocalConfig | McpRemoteConfig,
        directory: str | None = None,
        workspace: str | None = None,
    ) -> httpx.Response:
        """Register a new MCP server; return the raw response."""
        json_body = mcp_add_body(name, config)
        return await self._send(
            "POST", "/mcp", **request_spec(directory=directory, workspace=workspace, json_body=json_body)
        )

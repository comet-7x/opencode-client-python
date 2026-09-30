"""MCP resource: server status, registration and OAuth/connect lifecycle.

Maps to the ``/mcp`` endpoint family and ships in two flavours:

- :class:`McpResource` — synchronous, backed by :class:`OpenCodeClient`;
- :class:`AsyncMcpResource` — asynchronous, backed by :class:`AsyncOpenCodeClient`.

``status`` returns the full server-name -> :data:`MCPStatus` map so callers can
poll any server's lifecycle state (``connected`` / ``needs_auth`` / ...).
OAuth comes in two flows: browser-based (:meth:`McpResource.start_oauth` +
:meth:`McpResource.complete_oauth`) and headless
(:meth:`McpResource.authenticate`).
"""

from __future__ import annotations

from typing import Any

import httpx

from ..models import McpLocalConfig, McpOAuthStart, McpRemoteConfig, MCPStatus
from ._wire import (
    TYPE_ADAPTERS,
    mcp_add_body,
    path_segment,
    request_spec,
    validate_response,
)
from .base import AsyncResource, Resource

__all__ = ["AsyncMcpResource", "AsyncMcpResourceWithRawResponse", "McpResource", "McpResourceWithRawResponse"]


def _name_path(name: str, suffix: str = "") -> str:
    """Build a ``/mcp/{name}`` sub-path with the name percent-encoded."""
    return f"/mcp/{path_segment(name)}{suffix}"


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

    def start_oauth(self, name: str, directory: str | None = None, workspace: str | None = None) -> McpOAuthStart:
        """Start the browser-based OAuth flow for a remote MCP server.

        The server rejects this with an error when the server does not
        support OAuth.  Send the user to ``authorization_url``; the provider
        redirects back with a code that :meth:`complete_oauth` exchanges.

        Args:
            name: The MCP server's registered name.
        """
        response = self._send(
            "POST", _name_path(name, "/auth"), **request_spec(directory=directory, workspace=workspace)
        )
        return validate_response(response, TYPE_ADAPTERS.mcp_oauth_start)

    def complete_oauth(
        self, name: str, code: str, directory: str | None = None, workspace: str | None = None
    ) -> MCPStatus:
        """Finish the browser OAuth flow with the provider's redirect code.

        Maps to the wire's ``/auth/callback`` endpoint.

        Args:
            name: The MCP server's registered name.
            code: The authorization code from the OAuth redirect.
        """
        response = self._send(
            "POST",
            _name_path(name, "/auth/callback"),
            **request_spec(directory=directory, workspace=workspace, json_body={"code": code}),
        )
        return validate_response(response, TYPE_ADAPTERS.mcp_single_status)

    def authenticate(self, name: str, directory: str | None = None, workspace: str | None = None) -> MCPStatus:
        """Run the headless (non-browser) OAuth flow and return the new status."""
        response = self._send(
            "POST", _name_path(name, "/auth/authenticate"), **request_spec(directory=directory, workspace=workspace)
        )
        return validate_response(response, TYPE_ADAPTERS.mcp_single_status)

    def remove_oauth(self, name: str, directory: str | None = None, workspace: str | None = None) -> bool:
        """Remove stored OAuth credentials for the server. Returns ``True`` on success."""
        response = self._send(
            "DELETE", _name_path(name, "/auth"), **request_spec(directory=directory, workspace=workspace)
        )
        # wire wraps the result: {"success": true}
        return validate_response(response, TYPE_ADAPTERS.mcp_oauth_remove)["success"]

    def connect(self, name: str, directory: str | None = None, workspace: str | None = None) -> bool:
        """Connect to the MCP server now. Returns ``True`` on success."""
        response = self._send(
            "POST", _name_path(name, "/connect"), **request_spec(directory=directory, workspace=workspace)
        )
        return validate_response(response, TYPE_ADAPTERS.bool)

    def disconnect(self, name: str, directory: str | None = None, workspace: str | None = None) -> bool:
        """Disconnect the MCP server without removing its registration.

        Returns ``True`` on success.
        """
        response = self._send(
            "POST", _name_path(name, "/disconnect"), **request_spec(directory=directory, workspace=workspace)
        )
        return validate_response(response, TYPE_ADAPTERS.bool)


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

    async def start_oauth(self, name: str, directory: str | None = None, workspace: str | None = None) -> McpOAuthStart:
        """Start the browser-based OAuth flow for a remote MCP server.

        The server rejects this with an error when the server does not
        support OAuth.  Send the user to ``authorization_url``; the provider
        redirects back with a code that :meth:`complete_oauth` exchanges.

        Args:
            name: The MCP server's registered name.
        """
        response = await self._send(
            "POST", _name_path(name, "/auth"), **request_spec(directory=directory, workspace=workspace)
        )
        return validate_response(response, TYPE_ADAPTERS.mcp_oauth_start)

    async def complete_oauth(
        self, name: str, code: str, directory: str | None = None, workspace: str | None = None
    ) -> MCPStatus:
        """Finish the browser OAuth flow with the provider's redirect code.

        Maps to the wire's ``/auth/callback`` endpoint.

        Args:
            name: The MCP server's registered name.
            code: The authorization code from the OAuth redirect.
        """
        response = await self._send(
            "POST",
            _name_path(name, "/auth/callback"),
            **request_spec(directory=directory, workspace=workspace, json_body={"code": code}),
        )
        return validate_response(response, TYPE_ADAPTERS.mcp_single_status)

    async def authenticate(self, name: str, directory: str | None = None, workspace: str | None = None) -> MCPStatus:
        """Run the headless (non-browser) OAuth flow and return the new status."""
        response = await self._send(
            "POST", _name_path(name, "/auth/authenticate"), **request_spec(directory=directory, workspace=workspace)
        )
        return validate_response(response, TYPE_ADAPTERS.mcp_single_status)

    async def remove_oauth(self, name: str, directory: str | None = None, workspace: str | None = None) -> bool:
        """Remove stored OAuth credentials for the server. Returns ``True`` on success."""
        response = await self._send(
            "DELETE", _name_path(name, "/auth"), **request_spec(directory=directory, workspace=workspace)
        )
        # wire wraps the result: {"success": true}
        return validate_response(response, TYPE_ADAPTERS.mcp_oauth_remove)["success"]

    async def connect(self, name: str, directory: str | None = None, workspace: str | None = None) -> bool:
        """Connect to the MCP server now. Returns ``True`` on success."""
        response = await self._send(
            "POST", _name_path(name, "/connect"), **request_spec(directory=directory, workspace=workspace)
        )
        return validate_response(response, TYPE_ADAPTERS.bool)

    async def disconnect(self, name: str, directory: str | None = None, workspace: str | None = None) -> bool:
        """Disconnect the MCP server without removing its registration.

        Returns ``True`` on success.
        """
        response = await self._send(
            "POST", _name_path(name, "/disconnect"), **request_spec(directory=directory, workspace=workspace)
        )
        return validate_response(response, TYPE_ADAPTERS.bool)


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

    def start_oauth(self, name: str, directory: str | None = None, workspace: str | None = None) -> httpx.Response:
        """Start the browser OAuth flow; return the raw response."""
        return self._send("POST", _name_path(name, "/auth"), **request_spec(directory=directory, workspace=workspace))

    def complete_oauth(
        self, name: str, code: str, directory: str | None = None, workspace: str | None = None
    ) -> httpx.Response:
        """Finish the browser OAuth flow with a redirect code; return the raw response."""
        return self._send(
            "POST",
            _name_path(name, "/auth/callback"),
            **request_spec(directory=directory, workspace=workspace, json_body={"code": code}),
        )

    def authenticate(self, name: str, directory: str | None = None, workspace: str | None = None) -> httpx.Response:
        """Run the headless OAuth flow; return the raw response."""
        return self._send(
            "POST", _name_path(name, "/auth/authenticate"), **request_spec(directory=directory, workspace=workspace)
        )

    def remove_oauth(self, name: str, directory: str | None = None, workspace: str | None = None) -> httpx.Response:
        """Remove stored OAuth credentials; return the raw response."""
        return self._send("DELETE", _name_path(name, "/auth"), **request_spec(directory=directory, workspace=workspace))

    def connect(self, name: str, directory: str | None = None, workspace: str | None = None) -> httpx.Response:
        """Connect to the MCP server; return the raw response."""
        return self._send(
            "POST", _name_path(name, "/connect"), **request_spec(directory=directory, workspace=workspace)
        )

    def disconnect(self, name: str, directory: str | None = None, workspace: str | None = None) -> httpx.Response:
        """Disconnect the MCP server; return the raw response."""
        return self._send(
            "POST", _name_path(name, "/disconnect"), **request_spec(directory=directory, workspace=workspace)
        )


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

    async def start_oauth(
        self, name: str, directory: str | None = None, workspace: str | None = None
    ) -> httpx.Response:
        """Start the browser OAuth flow; return the raw response."""
        return await self._send(
            "POST", _name_path(name, "/auth"), **request_spec(directory=directory, workspace=workspace)
        )

    async def complete_oauth(
        self, name: str, code: str, directory: str | None = None, workspace: str | None = None
    ) -> httpx.Response:
        """Finish the browser OAuth flow with a redirect code; return the raw response."""
        return await self._send(
            "POST",
            _name_path(name, "/auth/callback"),
            **request_spec(directory=directory, workspace=workspace, json_body={"code": code}),
        )

    async def authenticate(
        self, name: str, directory: str | None = None, workspace: str | None = None
    ) -> httpx.Response:
        """Run the headless OAuth flow; return the raw response."""
        return await self._send(
            "POST", _name_path(name, "/auth/authenticate"), **request_spec(directory=directory, workspace=workspace)
        )

    async def remove_oauth(
        self, name: str, directory: str | None = None, workspace: str | None = None
    ) -> httpx.Response:
        """Remove stored OAuth credentials; return the raw response."""
        return await self._send(
            "DELETE", _name_path(name, "/auth"), **request_spec(directory=directory, workspace=workspace)
        )

    async def connect(self, name: str, directory: str | None = None, workspace: str | None = None) -> httpx.Response:
        """Connect to the MCP server; return the raw response."""
        return await self._send(
            "POST", _name_path(name, "/connect"), **request_spec(directory=directory, workspace=workspace)
        )

    async def disconnect(self, name: str, directory: str | None = None, workspace: str | None = None) -> httpx.Response:
        """Disconnect the MCP server; return the raw response."""
        return await self._send(
            "POST", _name_path(name, "/disconnect"), **request_spec(directory=directory, workspace=workspace)
        )

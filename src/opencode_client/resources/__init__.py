"""Resource groups for the opencode REST API.

Each public group is attached to the clients
(:class:`~opencode_client.OpenCodeClient` / :class:`~opencode_client.AsyncOpenCodeClient`)
and exposes the endpoints for one API area, in both sync and async flavours:

- :class:`SessionsResource` / :class:`AsyncSessionsResource` — everything under ``/session``;
- :class:`ServerResource` / :class:`AsyncServerResource` — server-level endpoints;
- :class:`VcsResource` / :class:`AsyncVcsResource` — repository info, status, diffs, patch apply;
- :class:`McpResource` / :class:`AsyncMcpResource` — MCP server status/registration.

Import the clients (and therefore the groups) via the package root
(``from opencode_client import OpenCodeClient``) rather than from submodules;
submodule paths are implementation details.
"""

from __future__ import annotations

from .base import AsyncResource, Resource
from .mcp import AsyncMcpResource, McpResource
from .server import AsyncServerResource, ServerResource
from .sessions import AsyncSessionsResource, SessionsResource
from .vcs import AsyncVcsResource, VcsResource

__all__ = [
    "AsyncMcpResource",
    "AsyncResource",
    "AsyncServerResource",
    "AsyncSessionsResource",
    "AsyncVcsResource",
    "McpResource",
    "Resource",
    "ServerResource",
    "SessionsResource",
    "VcsResource",
]

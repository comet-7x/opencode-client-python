"""Resource groups for the opencode REST API.

Each public group is attached to the clients
(:class:`~opencode_client.OpenCodeClient` / :class:`~opencode_client.AsyncOpenCodeClient`)
and exposes the endpoints for one API area, in both sync and async flavours:

- :class:`SessionsResource` / :class:`AsyncSessionsResource` — everything under ``/session``;
- :class:`ServerResource` / :class:`AsyncServerResource` — server-level endpoints;
- :class:`VcsResource` / :class:`AsyncVcsResource` — repository info, status, diffs, patch apply;
- :class:`McpResource` / :class:`AsyncMcpResource` — MCP server status/registration.

Each resource also exposes a ``with_raw_response`` property returning the
matching ``*WithRawResponse`` twin: identical signatures, but calls return
the unprocessed :class:`httpx.Response` instead of the parsed model
(``stream_events`` has no raw variant).

Import the clients (and therefore the groups) via the package root
(``from opencode_client import OpenCodeClient``) rather than from submodules;
submodule paths are implementation details.
"""

from __future__ import annotations

from .base import AsyncResource, Resource
from .mcp import AsyncMcpResource, AsyncMcpResourceWithRawResponse, McpResource, McpResourceWithRawResponse
from .server import (
    AsyncServerResource,
    AsyncServerResourceWithRawResponse,
    ServerResource,
    ServerResourceWithRawResponse,
)
from .sessions import (
    AsyncSessionsResource,
    AsyncSessionsResourceWithRawResponse,
    SessionsResource,
    SessionsResourceWithRawResponse,
)
from .vcs import AsyncVcsResource, AsyncVcsResourceWithRawResponse, VcsResource, VcsResourceWithRawResponse

__all__ = [
    "AsyncMcpResource",
    "AsyncMcpResourceWithRawResponse",
    "AsyncResource",
    "AsyncServerResource",
    "AsyncServerResourceWithRawResponse",
    "AsyncSessionsResource",
    "AsyncSessionsResourceWithRawResponse",
    "AsyncVcsResource",
    "AsyncVcsResourceWithRawResponse",
    "McpResource",
    "McpResourceWithRawResponse",
    "Resource",
    "ServerResource",
    "ServerResourceWithRawResponse",
    "SessionsResource",
    "SessionsResourceWithRawResponse",
    "VcsResource",
    "VcsResourceWithRawResponse",
]

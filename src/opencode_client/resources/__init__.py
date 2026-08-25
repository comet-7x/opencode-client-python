"""Resource groups for the opencode REST API.

Each public group is attached to the clients
(:class:`~opencode_client.OpenCodeClient` / :class:`~opencode_client.AsyncOpenCodeClient`)
and exposes the endpoints for one API area, in both sync and async flavours:

- :class:`SessionsResource` / :class:`AsyncSessionsResource` — everything under ``/session``;
- :class:`ServerResource` / :class:`AsyncServerResource` — server-level endpoints;
- :class:`VcsResource` / :class:`AsyncVcsResource` — repository info, status, diffs, patch apply;
- :class:`McpResource` / :class:`AsyncMcpResource` — MCP server status/registration;
- :class:`FilesResource` / :class:`AsyncFilesResource` — file browsing, search, formatters;
- :class:`ProjectsResource` / :class:`AsyncProjectsResource` — registered workspaces;
- :class:`AuthResource` / :class:`AsyncAuthResource` — provider credentials.

Each resource also exposes a ``with_raw_response`` property returning the
matching ``*WithRawResponse`` twin: identical signatures, but calls return
the unprocessed :class:`httpx.Response` instead of the parsed model
(``stream_events`` has no raw variant).

Import the clients (and therefore the groups) via the package root
(``from opencode_client import OpenCodeClient``) rather than from submodules;
submodule paths are implementation details.
"""

from __future__ import annotations

from .auth import AsyncAuthResource, AsyncAuthResourceWithRawResponse, AuthResource, AuthResourceWithRawResponse
from .base import AsyncResource, Resource
from .files import AsyncFilesResource, AsyncFilesResourceWithRawResponse, FilesResource, FilesResourceWithRawResponse
from .mcp import AsyncMcpResource, AsyncMcpResourceWithRawResponse, McpResource, McpResourceWithRawResponse
from .projects import (
    AsyncProjectsResource,
    AsyncProjectsResourceWithRawResponse,
    ProjectsResource,
    ProjectsResourceWithRawResponse,
)
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
    "AsyncAuthResource",
    "AsyncAuthResourceWithRawResponse",
    "AsyncFilesResource",
    "AsyncFilesResourceWithRawResponse",
    "AsyncMcpResource",
    "AsyncMcpResourceWithRawResponse",
    "AsyncResource",
    "AsyncServerResource",
    "AsyncServerResourceWithRawResponse",
    "AsyncSessionsResource",
    "AsyncSessionsResourceWithRawResponse",
    "AsyncProjectsResource",
    "AsyncProjectsResourceWithRawResponse",
    "AsyncVcsResource",
    "AsyncVcsResourceWithRawResponse",
    "AuthResource",
    "AuthResourceWithRawResponse",
    "FilesResource",
    "FilesResourceWithRawResponse",
    "McpResource",
    "McpResourceWithRawResponse",
    "Resource",
    "ServerResource",
    "ServerResourceWithRawResponse",
    "ProjectsResource",
    "ProjectsResourceWithRawResponse",
    "SessionsResource",
    "SessionsResourceWithRawResponse",
    "VcsResource",
    "VcsResourceWithRawResponse",
]

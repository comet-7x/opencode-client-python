"""Models for the /mcp endpoints: server status and server configs."""

from __future__ import annotations

from typing import Annotated, Literal

import pydantic
from pydantic import Field

from .base import OpencodeModel

__all__ = [
    "McpConfig",
    "McpLocalConfig",
    "McpOAuthConfig",
    "McpRemoteConfig",
    "MCPStatus",
    "MCPStatusConnected",
    "MCPStatusDisabled",
    "MCPStatusFailed",
    "MCPStatusNeedsAuth",
    "MCPStatusNeedsClientRegistration",
]


# -- status -----------------------------------------------------------------
#
# Five sibling models instead of a base class: narrowing a ``Literal`` in a
# subclass is a type error under strict pyright, while standalone siblings
# match the :class:`Message` union pattern used elsewhere in this package.


class MCPStatusConnected(OpencodeModel):
    """Server is connected."""

    status: Literal["connected"]


class MCPStatusDisabled(OpencodeModel):
    """Server is defined but disabled."""

    status: Literal["disabled"]


class MCPStatusFailed(OpencodeModel):
    """Connection attempt failed (``error`` carries the reason)."""

    status: Literal["failed"]
    error: str | None = None


class MCPStatusNeedsAuth(OpencodeModel):
    """Server requires authentication before it can connect."""

    status: Literal["needs_auth"]


class MCPStatusNeedsClientRegistration(OpencodeModel):
    """Server is ready once the client finishes OAuth registration (``error``)."""

    status: Literal["needs_client_registration"]
    error: str | None = None


#: Discriminated union of the five MCP server states.
MCPStatus = Annotated[
    MCPStatusConnected | MCPStatusDisabled | MCPStatusFailed | MCPStatusNeedsAuth | MCPStatusNeedsClientRegistration,
    pydantic.Field(discriminator="status"),
]


# -- config (request-side) ---------------------------------------------------


class McpOAuthConfig(OpencodeModel):
    """OAuth parameters for a remote MCP server.

    Wire uses lowercase ``Id`` (``clientId``/``clientSecret``) — unlike the
    API's usual uppercase ``ID`` — so the aliases are explicit. They are split
    into validation/serialization aliases so Python constructors keep taking
    snake_case field names.
    """

    client_id: str = Field(validation_alias="clientId", serialization_alias="clientId")
    client_secret: str = Field(validation_alias="clientSecret", serialization_alias="clientSecret")
    scope: str | None = None
    callback_port: int | None = None
    redirect_uri: str | None = None


class McpLocalConfig(OpencodeModel):
    """A stdio MCP server spawned as a local command."""

    type: Literal["local"]
    command: list[str]
    cwd: str | None = None
    environment: dict[str, str] | None = None
    enabled: bool | None = None
    timeout: int | None = None


class McpRemoteConfig(OpencodeModel):
    """An HTTP/SSE MCP server at a remote URL."""

    type: Literal["remote"]
    url: str
    enabled: bool | None = None
    headers: dict[str, str] | None = None
    # wire permits the OAuth config object or the literal ``false`` (disable auto-detect)
    oauth: McpOAuthConfig | Literal[False] | None = None
    timeout: int | None = None


#: Discriminated union of the two MCP server config shapes.
McpConfig = Annotated[
    McpLocalConfig | McpRemoteConfig,
    pydantic.Field(discriminator="type"),
]

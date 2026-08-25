"""Models for server system-info endpoints: /path, /lsp, /log and /global/*."""

from __future__ import annotations

from typing import Annotated, Any, Literal, cast

import pydantic
from pydantic import Field, model_validator

from .base import OpencodeModel

__all__ = [
    "GlobalEvent",
    "LSPStatus",
    "LogEntry",
    "ProviderAuthAuthorization",
    "ProviderAuthMethod",
    "ProviderAuthPrompt",
    "ProviderAuthPromptSelect",
    "ProviderAuthPromptText",
    "ServerPaths",
]


class ServerPaths(OpencodeModel):
    """Server-side filesystem layout from ``GET /path``.

    The wire schema is named ``Path``; the Python name avoids confusion
    with filesystem path types at call sites.
    """

    home: str
    state: str
    config: str
    worktree: str
    directory: str


class LSPStatus(OpencodeModel):
    """One language server's status from ``GET /lsp``."""

    id: str
    name: str
    root: str
    status: Literal["connected", "error"]


class LogEntry(OpencodeModel):
    """Request-side payload for ``POST /log`` — everything but level optional.

    Written into the server's log so remote debugging sessions leave a
    trace on the machine that actually runs the tools.
    """

    service: str | None = None
    level: Literal["debug", "info", "error", "warn"] | None = Field(default=None)
    message: str | None = None
    extra: dict[str, object] | None = None


# -- GET /provider/auth --------------------------------------------------------


class _AuthPromptCondition(OpencodeModel):
    """Show a prompt only when another answer matches (``key``/``op``/``value``)."""

    key: str
    op: Literal["eq", "neq"]
    value: str


class ProviderAuthPromptText(OpencodeModel):
    """A free-text credential prompt in a provider's auth flow."""

    type: Literal["text"]
    key: str
    message: str
    placeholder: str | None = None
    when: _AuthPromptCondition | None = None


class ProviderAuthPromptSelect(OpencodeModel):
    """A multiple-choice prompt in a provider's auth flow."""

    type: Literal["select"]
    key: str
    message: str
    options: list[dict[str, Any]]
    when: _AuthPromptCondition | None = None


#: Discriminated union of the two prompt shapes (discriminator ``type``).
ProviderAuthPrompt = Annotated[
    ProviderAuthPromptText | ProviderAuthPromptSelect,
    pydantic.Field(discriminator="type"),
]


class ProviderAuthMethod(OpencodeModel):
    """One auth method offered by a provider (from ``GET /provider/auth``).

    The wire returns a ``provider id -> methods[]`` map; ``prompts`` lists
    what the user must answer for the non-OAuth flow.
    """

    type: Literal["oauth", "api"]
    label: str
    prompts: list[ProviderAuthPrompt] = pydantic.Field(default_factory=list)  # pyright: ignore[reportUnknownVariableType]


class ProviderAuthAuthorization(OpencodeModel):
    """Kick-off document from ``POST /provider/{id}/oauth/authorize``.

    ``method == "auto"`` means the flow completes by itself; ``"code"``
    means the user must come back with a code for
    :meth:`AuthResource.complete_provider_oauth`.
    """

    url: str
    method: Literal["auto", "code"]
    instructions: str


# -- GET /global/event ---------------------------------------------------------


class GlobalEvent(OpencodeModel):
    """One event envelope from the global SSE stream (``GET /global/event``).

    Unlike instance events, the payload is carried under ``payload`` and is
    a uniform ``{id, type, properties}`` structure whose ``type`` spans ~90
    known kinds (session.*, pty.*, workspace.* ...) — modelled loosely as
    strings so new server-side kinds flow through untouched.
    """

    directory: str | None = None
    project: str | None = None
    workspace: str | None = None
    id: str | None = None
    type: str | None = None
    properties: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _hoist_payload(cls, data: Any) -> Any:
        """Flatten the nested ``payload`` document to the top level."""
        source = cast("dict[str, Any]", data)
        payload = source.get("payload")
        if isinstance(payload, dict):
            merged: dict[str, Any] = {k: v for k, v in source.items() if k != "payload"}
            merged.update(cast("dict[str, Any]", payload))
            return merged
        return cast("dict[str, Any]", data)

    @property
    def payload(self) -> dict[str, Any]:
        """The nested ``{id, type, properties}`` event document."""
        return {
            "id": self.id,
            "type": self.type,
            "properties": self.properties,
        }

    @property
    def payload_type(self) -> str | None:
        """The inner event's ``type`` (e.g. ``"session.idle"``)."""
        return self.type

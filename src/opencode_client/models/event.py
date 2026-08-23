"""Event models for the ``GET /event`` (SSE) stream.

The stream carries a self-describing envelope (``{"type": ..., "properties":
...}``) per event.  The base :class:`Event` keeps ``properties`` a free-form
dict so *unknown* event types always flow through untouched.  A small set of
*frequently consumed* ("hot") event types additionally maps to typed
subclasses whose payload fields reuse the existing REST models
(:class:`~opencode_client.models.Part`,
:class:`~opencode_client.models.PermissionRequest`,
:class:`~opencode_client.models.QuestionRequest`).

:class:`EventType` is an *open set* of known event names (``str``-mixed enum,
so a member compares equal to its raw string).  The server is the producer
and may add types at any time; code must keep accepting unknown type strings.
Newer server versions may also change a hot payload's shape — when that
happens the event degrades to the base :class:`Event` instead of breaking
the stream (see :func:`typed_event`).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, cast

from pydantic import model_validator

from .base import OpencodeModel
from .interaction import PermissionRequest, QuestionRequest
from .part import Part

__all__ = [
    "EVENT_CATALOG",
    "Event",
    "EventType",
    "MessagePartDeltaEvent",
    "MessagePartDeltaPayload",
    "MessagePartUpdatedEvent",
    "MessageUpdatedEvent",
    "PermissionAskedEvent",
    "QuestionAskedEvent",
    "SessionIdleEvent",
    "typed_event",
]


class EventType(StrEnum):
    """Known ``/event`` type names (open set; compare against raw strings).

    Seeded from the server's v1 event surface (its ``/doc`` OpenAPI export,
    57 types as of 2026-08-23).  The server may emit types not listed here;
    they are still delivered, as the base :class:`Event`.  Update this
    enum when the server manifest grows.
    """

    CATALOG_UPDATED = "catalog.updated"
    COMMAND_EXECUTED = "command.executed"
    FILE_EDITED = "file.edited"
    FILE_WATCHER_UPDATED = "file.watcher.updated"
    GLOBAL_DISPOSED = "global.disposed"
    INSTALLATION_UPDATE_AVAILABLE = "installation.update-available"
    INSTALLATION_UPDATED = "installation.updated"
    INTEGRATION_CONNECTION_UPDATED = "integration.connection.updated"
    INTEGRATION_UPDATED = "integration.updated"
    LSP_UPDATED = "lsp.updated"
    MCP_BROWSER_OPEN_FAILED = "mcp.browser.open.failed"
    MCP_TOOLS_CHANGED = "mcp.tools.changed"
    MESSAGE_PART_DELTA = "message.part.delta"
    MESSAGE_PART_REMOVED = "message.part.removed"
    MESSAGE_PART_UPDATED = "message.part.updated"
    MESSAGE_REMOVED = "message.removed"
    MESSAGE_UPDATED = "message.updated"
    MODELS_DEV_REFRESHED = "models-dev.refreshed"
    PERMISSION_ASKED = "permission.asked"
    PERMISSION_REPLIED = "permission.replied"
    PERMISSION_V2_ASKED = "permission.v2.asked"
    PERMISSION_V2_REPLIED = "permission.v2.replied"
    PLUGIN_ADDED = "plugin.added"
    PROJECT_DIRECTORIES_UPDATED = "project.directories.updated"
    PROJECT_UPDATED = "project.updated"
    PTY_CREATED = "pty.created"
    PTY_DELETED = "pty.deleted"
    PTY_EXITED = "pty.exited"
    PTY_UPDATED = "pty.updated"
    QUESTION_ASKED = "question.asked"
    QUESTION_REJECTED = "question.rejected"
    QUESTION_REPLIED = "question.replied"
    QUESTION_V2_ASKED = "question.v2.asked"
    QUESTION_V2_REJECTED = "question.v2.rejected"
    QUESTION_V2_REPLIED = "question.v2.replied"
    REFERENCE_UPDATED = "reference.updated"
    SERVER_CONNECTED = "server.connected"
    SERVER_INSTANCE_DISPOSED = "server.instance.disposed"
    SESSION_COMPACTED = "session.compacted"
    SESSION_CREATED = "session.created"
    SESSION_DELETED = "session.deleted"
    SESSION_DIFF = "session.diff"
    SESSION_ERROR = "session.error"
    SESSION_IDLE = "session.idle"
    SESSION_STATUS = "session.status"
    SESSION_UPDATED = "session.updated"
    TODO_UPDATED = "todo.updated"
    TUI_COMMAND_EXECUTE = "tui.command.execute"
    TUI_PROMPT_APPEND = "tui.prompt.append"
    TUI_SESSION_SELECT = "tui.session.select"
    TUI_TOAST_SHOW = "tui.toast.show"
    VCS_BRANCH_UPDATED = "vcs.branch.updated"
    WORKSPACE_FAILED = "workspace.failed"
    WORKSPACE_READY = "workspace.ready"
    WORKSPACE_STATUS = "workspace.status"
    WORKTREE_FAILED = "worktree.failed"
    WORKTREE_READY = "worktree.ready"


class Event(OpencodeModel):
    """A single server event.

    The base envelope: ``type`` plus a free-form :attr:`properties` dict
    (branch on ``event.type``).  Frequently consumed types are delivered as
    the typed subclasses below; unknown types always arrive as this class.
    """

    id: str | None = None
    type: str
    properties: dict[str, Any] = {}


class _TypedEvent(Event):
    """Common base for typed hot events: hoists the payload from ``properties``.

    The wire nests the payload under ``properties``; the flat fields below
    are populated by merging that payload to the top level (payload keys win
    on conflict, e.g. ``permission.asked`` carries the request ``id``).  The
    original ``properties`` dict is preserved as-is for pass-through use.
    """

    @model_validator(mode="before")
    @classmethod
    def _hoist_properties(cls, data: Any) -> Any:
        # pydantic hands a before-validator the raw mapping; the cast keeps
        # the (partial-unknown) narrowing of ``data`` from leaking into the return
        source = cast("dict[str, Any]", data)
        payload = source.get("properties")
        if not isinstance(payload, dict):
            return source
        merged: dict[str, Any] = dict(source)
        merged.update(cast("dict[str, Any]", payload))
        return merged


class MessagePartDeltaPayload(OpencodeModel):
    """Payload of a ``message.part.delta`` event.

    A text increment for one part.  The ``field`` value is ``"text"`` for
    *both* text and reasoning parts (the server emits the same field from
    both call sites), so the part's kind is only known via the earlier
    ``message.part.updated`` event for the same ``part_id``.
    """

    session_id: str
    message_id: str
    part_id: str
    field: str
    delta: str


class MessagePartUpdatedEvent(_TypedEvent):
    """``message.part.updated`` — a full part object (creation or state change)."""

    session_id: str
    part: Part
    time: float


class MessagePartDeltaEvent(_TypedEvent):
    """``message.part.delta`` — a streaming text increment.

    ``field`` is ``"text"`` for both text and reasoning parts; see
    :class:`MessagePartDeltaPayload` for the caveat.
    """

    session_id: str
    message_id: str
    part_id: str
    field: str
    delta: str


class MessageUpdatedEvent(_TypedEvent):
    """``message.updated`` — message info changed.

    ``info`` is the wire message object (``role``-discriminated user/
    assistant), kept unvalidated on purpose: consumers validate it on demand
    (``Message.model_validate(event.info)``) when they need the union.
    """

    session_id: str
    info: Any


class SessionIdleEvent(_TypedEvent):
    """``session.idle`` — the session finished its current turn."""

    session_id: str


class PermissionAskedEvent(_TypedEvent):
    """``permission.asked`` — a tool call awaits a permission reply.

    The properties are the full permission request; :attr:`request` exposes
    it typed.  The request id lands on the inherited :attr:`Event.id`.
    """

    session_id: str
    permission: str
    patterns: list[str]
    metadata: dict[str, Any] = {}
    always: list[str] = []
    tool: dict[str, str] | None = None

    @property
    def request(self) -> PermissionRequest:
        """The event payload as a :class:`~opencode_client.models.PermissionRequest`."""
        return PermissionRequest.model_validate(self.properties)


class QuestionAskedEvent(_TypedEvent):
    """``question.asked`` — a question awaits user answers.

    The properties are the full question request; :attr:`request` exposes
    it typed.  The request id lands on the inherited :attr:`Event.id`.
    """

    session_id: str
    questions: list[dict[str, Any]]
    tool: dict[str, str] | None = None

    @property
    def request(self) -> QuestionRequest:
        """The event payload as a :class:`~opencode_client.models.QuestionRequest`."""
        return QuestionRequest.model_validate(self.properties)


#: Hot event types with a typed payload, mapped to their event subclass.
EVENT_CATALOG: dict[str, type[Event]] = {
    "message.part.updated": MessagePartUpdatedEvent,
    "message.part.delta": MessagePartDeltaEvent,
    "message.updated": MessageUpdatedEvent,
    "session.idle": SessionIdleEvent,
    "permission.asked": PermissionAskedEvent,
    "question.asked": QuestionAskedEvent,
}


def typed_event(raw: dict[str, Any]) -> Event:
    """Upgrade a decoded event to its typed subclass when the catalog knows it.

    Returns the base :class:`Event` for unknown types or when a hot payload
    no longer validates (the server changed its shape) — the stream must
    never break over a schema drift.
    """
    event = Event.model_validate(raw)
    cls = EVENT_CATALOG.get(event.type)
    if cls is None:
        return event
    try:
        return cls.model_validate(raw)
    except Exception:
        return event

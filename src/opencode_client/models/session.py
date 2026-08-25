"""Models for the /session endpoints and their nested types."""

from typing import Annotated, Any, Literal, TypeAlias

import pydantic

from .base import OpencodeModel

__all__ = [
    "CreateSessionRequest",
    "ModelID",
    "PermissionRule",
    "PermissionRuleset",
    "Session",
    "SessionFileDiff",
    "SessionShare",
    "SessionSnapshot",
    "SessionStatus",
    "SessionStatusBusy",
    "SessionStatusIdle",
    "SessionStatusRetry",
    "SessionStatusRetryAction",
    "SessionTime",
    "SessionTokenCache",
    "SessionTokens",
    "Todo",
    "UpdateSessionRequest",
]


class ModelID(OpencodeModel):
    """Reference to a model: id + provider + optional variant."""

    id: str
    provider_id: str
    variant: str | None = None


class SessionSnapshot(OpencodeModel):
    """File-change statistics shown in the session summary."""

    additions: float
    deletions: float
    files: float
    diffs: list[dict[str, Any]] | None = None


class SessionTokenCache(OpencodeModel):
    """Token usage split into cache reads and writes."""

    read: float
    write: float


class SessionTokens(OpencodeModel):
    """Cumulative token usage of a session."""

    input: float
    output: float
    reasoning: float
    cache: SessionTokenCache


class SessionShare(OpencodeModel):
    """Published share URL of a session."""

    url: str


class SessionTime(OpencodeModel):
    """Lifecycle timestamps of a session (unix seconds)."""

    created: float
    updated: float
    compacting: float | None = None
    archived: float | None = None


class PermissionRule(OpencodeModel):
    """A single permission rule: allow/deny/ask for a permission pattern."""

    permission: str
    pattern: str
    action: Literal["allow", "deny", "ask"]


PermissionRuleset = list[PermissionRule]


class Session(OpencodeModel):
    """A conversation session on the server."""

    id: str
    slug: str
    project_id: str
    workspace_id: str | None = None
    directory: str
    path: str
    parent_id: str | None = None
    summary: SessionSnapshot | None = None
    cost: float | None = None
    tokens: SessionTokens | None = None
    share: SessionShare | None = None
    title: str
    agent: str | None = None
    model: ModelID | None = None
    version: str
    metadata: dict[str, Any] | None = None
    time: SessionTime
    permission: PermissionRuleset | None = None
    revert: dict[str, Any] | None = None


class CreateSessionRequest(OpencodeModel):
    """Request body for ``POST /session`` (all fields optional)."""

    parent_id: str | None = None
    title: str | None = None
    agent: str | None = None
    model: ModelID | None = None
    metadata: dict[str, Any] | None = None
    permission: PermissionRuleset | None = None
    workspace_id: str | None = None


class UpdateSessionRequest(OpencodeModel):
    """Request body for ``PATCH /session/{id}`` (all fields optional)."""

    title: str | None = None
    metadata: dict[str, Any] | None = None
    permission: PermissionRuleset | None = None
    time: dict[str, float] | None = None


# ---------------------------------------------------------------------------
# Status / todo / message diff (GET /session/status, .../todo, .../diff)
# ---------------------------------------------------------------------------


class SessionStatusIdle(OpencodeModel):
    """Session status: no turn is running."""

    type: Literal["idle"]


class SessionStatusBusy(OpencodeModel):
    """Session status: a turn is currently running."""

    type: Literal["busy"]


class SessionStatusRetryAction(OpencodeModel):
    """Suggested remediation shown alongside a retrying session."""

    reason: str
    provider: str
    title: str
    message: str
    label: str
    link: str | None = None


class SessionStatusRetry(OpencodeModel):
    """Session status: the last turn failed and will be retried."""

    type: Literal["retry"]
    attempt: int
    message: str
    next: int
    action: SessionStatusRetryAction | None = None


#: Discriminated union of the three session states (``type`` tag).
SessionStatus: TypeAlias = Annotated[
    SessionStatusIdle | SessionStatusBusy | SessionStatusRetry,
    pydantic.Field(discriminator="type"),
]


class Todo(OpencodeModel):
    """One task on a session's todo list (``GET /session/{id}/todo``)."""

    content: str
    status: Literal["pending", "in_progress", "completed", "cancelled"]
    priority: Literal["high", "medium", "low"]


class SessionFileDiff(OpencodeModel):
    """One file changed by a session's messages (``GET /session/{id}/diff``).

    Unlike :class:`~opencode_client.models.VcsFileDiff` only the line counts
    are guaranteed; ``file``/``patch``/``status`` may be absent.
    """

    file: str | None = None
    patch: str | None = None
    additions: float
    deletions: float
    status: Literal["added", "deleted", "modified"] | None = None

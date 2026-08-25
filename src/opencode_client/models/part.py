"""Models for message parts.

A message payload (``MessageWithParts``) is the message info plus an
ordered list of :data:`Part` items. This module also defines the
request-side part inputs accepted by the prompt endpoints, and the
shared helper models those parts depend on.
"""

from typing import Annotated, Any, Literal, TypeAlias

import pydantic
from pydantic import Field

from .base import OpencodeModel
from .session import SessionTokenCache

__all__ = [
    "AgentPart",
    "AgentPartInput",
    "AssistantMessageTokens",
    "CompactionPart",
    "FilePart",
    "FilePartInput",
    "FilePartRange",
    "FilePartSource",
    "FilePartSourceFile",
    "FilePartSourceResource",
    "FilePartSourceSymbol",
    "FilePartText",
    "PatchPart",
    "Part",
    "PartBase",
    "PartTime",
    "PromptModel",
    "PromptPart",
    "PromptRequest",
    "ReasoningPart",
    "RetryPart",
    "SnapshotPart",
    "StepFinishPart",
    "StepStartPart",
    "SubtaskModel",
    "SubtaskPartInput",
    "TextPart",
    "TextPartInput",
    "ToolPart",
    "ToolState",
    "ToolStateCompleted",
    "ToolStateError",
    "ToolStatePending",
    "ToolStateRunning",
]


class AssistantMessageTokens(OpencodeModel):
    """Token usage counters of an assistant message (also embedded in step-finish parts)."""

    total: float | None = None
    input: float
    output: float
    reasoning: float
    cache: SessionTokenCache


class PartTime(OpencodeModel):
    """Start/end timestamps of a part (unix seconds)."""

    start: float
    end: float | None = None


class PartBase(OpencodeModel):
    """Fields shared by every part type."""

    id: str
    session_id: str
    message_id: str


class TextPart(PartBase):
    """Free-form text produced by the assistant."""

    type: Literal["text"]
    text: str
    synthetic: bool | None = None
    ignored: bool | None = None
    time: PartTime | None = None
    metadata: dict[str, Any] | None = None


class FilePartText(OpencodeModel):
    """A slice of file content with its byte offsets."""

    value: str
    start: float
    end: float


class FilePartRange(OpencodeModel):
    """Line/column range pointing at the referenced source location."""

    start: dict[str, float]
    end: dict[str, float]


class FilePartSourceFile(OpencodeModel):
    """File part sourced from a whole file."""

    type: Literal["file"]
    text: FilePartText
    path: str


class FilePartSourceSymbol(OpencodeModel):
    """File part sourced from a named symbol inside a file."""

    type: Literal["symbol"]
    text: FilePartText
    path: str
    range: FilePartRange
    name: str
    kind: int


class FilePartSourceResource(OpencodeModel):
    """File part sourced from an external resource URI."""

    type: Literal["resource"]
    text: FilePartText
    client_name: str
    uri: str


FilePartSource: TypeAlias = Annotated[
    FilePartSourceFile | FilePartSourceSymbol | FilePartSourceResource,
    pydantic.Field(discriminator="type"),
]


class FilePart(PartBase):
    """A file attached to a message."""

    type: Literal["file"]
    mime: str
    url: str
    filename: str | None = None
    source: FilePartSource | None = None


class ToolStatePending(OpencodeModel):
    """Tool call accepted but not started."""

    status: Literal["pending"]
    input: dict[str, Any]
    raw: str


class ToolStateRunning(OpencodeModel):
    """Tool call in flight."""

    status: Literal["running"]
    input: dict[str, Any]
    title: str | None = None
    metadata: dict[str, Any] | None = None
    time: PartTime


class ToolStateCompleted(OpencodeModel):
    """Tool call finished successfully; ``output`` carries its result."""

    status: Literal["completed"]
    input: dict[str, Any]
    output: str
    title: str | None = None
    metadata: dict[str, Any] | None = None
    time: dict[str, float]
    attachments: list[dict[str, Any]] | None = None


class ToolStateError(OpencodeModel):
    """Tool call failed; ``error`` carries the reason."""

    status: Literal["error"]
    input: dict[str, Any]
    error: str
    metadata: dict[str, Any] | None = None
    time: dict[str, float]


ToolState: TypeAlias = Annotated[
    ToolStatePending | ToolStateRunning | ToolStateCompleted | ToolStateError,
    pydantic.Field(discriminator="status"),
]


class ToolPart(PartBase):
    """A tool invocation with its lifecycle state."""

    type: Literal["tool"]
    call_id: str
    tool: str
    state: ToolState
    metadata: dict[str, Any] | None = None


class ReasoningPart(PartBase):
    """Chain-of-thought content (extended-thinking models)."""

    type: Literal["reasoning"]
    text: str
    metadata: dict[str, Any] | None = None
    time: PartTime


class SnapshotPart(PartBase):
    """A git snapshot captured for the session."""

    type: Literal["snapshot"]
    snapshot: str


class StepStartPart(PartBase):
    """Marks the start of an agent step."""

    type: Literal["step-start"]
    snapshot: str | None = None


class StepFinishPart(PartBase):
    """Marks the end of an agent step with its cost and token usage."""

    type: Literal["step-finish"]
    reason: str
    snapshot: str | None = None
    cost: float
    tokens: AssistantMessageTokens


class PatchPart(PartBase):
    """A file patch applied during the message."""

    type: Literal["patch"]
    hash: str
    files: list[str]


class AgentPart(PartBase):
    """Delegation to another agent."""

    type: Literal["agent"]
    name: str
    source: dict[str, Any] | None = None


class RetryPart(PartBase):
    """A provider retry attempt and its error."""

    type: Literal["retry"]
    attempt: int
    error: dict[str, Any]
    time: dict[str, float]


class CompactionPart(PartBase):
    """Context-compaction bookkeeping for long sessions."""

    type: Literal["compaction"]
    auto: bool
    overflow: bool | None = None
    # wire field is snake_case, not camelCase
    tail_start_id: str | None = Field(default=None, alias="tail_start_id")


Part: TypeAlias = Annotated[
    TextPart
    | FilePart
    | ToolPart
    | ReasoningPart
    | SnapshotPart
    | StepStartPart
    | StepFinishPart
    | PatchPart
    | AgentPart
    | RetryPart
    | CompactionPart,
    pydantic.Field(discriminator="type"),
]


# ---------------------------------------------------------------------------
# Request-side prompt part inputs (POST /session/{id}/message)
# ---------------------------------------------------------------------------


class TextPartInput(OpencodeModel):
    """Text block of a prompt request."""

    type: Literal["text"]
    text: str
    id: str | None = None
    synthetic: bool | None = None
    ignored: bool | None = None
    time: PartTime | None = None
    metadata: dict[str, Any] | None = None


class AgentPartInput(OpencodeModel):
    """Agent block of a prompt request."""

    type: Literal["agent"]
    name: str
    id: str | None = None
    source: dict[str, Any] | None = None


class FilePartInput(OpencodeModel):
    """File block of a prompt request."""

    type: Literal["file"]
    url: str
    mime: str
    filename: str | None = None
    source: FilePartSource | None = None


class SubtaskModel(OpencodeModel):
    """Model reference for a subtask prompt part."""

    provider_id: str
    model_id: str


class SubtaskPartInput(OpencodeModel):
    """Subtask block: delegate a subgoal to an agent."""

    type: Literal["subtask"]
    prompt: str
    description: str
    agent: str
    model: SubtaskModel
    command: str | None = None


PromptPart: TypeAlias = Annotated[
    TextPartInput | FilePartInput | AgentPartInput | SubtaskPartInput,
    pydantic.Field(discriminator="type"),
]


class PromptModel(OpencodeModel):
    """Model target override for a prompt request."""

    provider_id: str
    model_id: str


class PromptRequest(OpencodeModel):
    """Full request-body shape of the prompt endpoints (assembled by the client)."""

    message_id: str | None = None
    model: PromptModel | None = None
    agent: str | None = None
    no_reply: bool | None = None
    tools: dict[str, bool] | None = None
    system: str | None = None
    variant: str | None = None
    parts: list[PromptPart]

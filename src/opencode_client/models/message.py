"""Models for messages: the info object plus its parts."""

from typing import Annotated, Any, Literal, TypeAlias

import pydantic

from .base import OpencodeModel
from .part import AssistantMessageTokens, Part

__all__ = [
    "AssistantMessage",
    "AssistantMessagePath",
    "Message",
    "MessageTime",
    "MessageWithParts",
    "UserMessage",
    "UserMessageModel",
    "UserMessageSummary",
]


class MessageTime(OpencodeModel):
    """Creation/completion timestamps of a message (unix seconds)."""

    created: float
    completed: float | None = None


class UserMessageModel(OpencodeModel):
    """Provider/model pair recorded on a user message."""

    provider_id: str
    model_id: str
    variant: str | None = None


class UserMessageSummary(OpencodeModel):
    """Optional summary attached to a user message."""

    title: str | None = None
    body: str | None = None
    diffs: list[dict[str, Any]]


class UserMessage(OpencodeModel):
    """A message sent by the user (or an upstream agent)."""

    id: str
    session_id: str
    role: Literal["user"]
    time: MessageTime
    format: dict[str, Any] | None = None
    summary: UserMessageSummary | None = None
    agent: str
    model: UserMessageModel
    system: str | None = None
    tools: dict[str, bool] | None = None
    variant: str | None = None


class AssistantMessagePath(OpencodeModel):
    """Working/root directory the assistant ran in."""

    cwd: str
    root: str


class AssistantMessage(OpencodeModel):
    """A message produced by an assistant agent."""

    id: str
    session_id: str
    role: Literal["assistant"]
    time: MessageTime
    error: dict[str, Any] | None = None
    parent_id: str
    model_id: str
    provider_id: str
    mode: str
    agent: str
    path: AssistantMessagePath
    summary: bool | None = None
    cost: float
    tokens: AssistantMessageTokens
    structured: dict[str, Any] | None = None
    variant: str | None = None
    finish: str | None = None


#: Discriminated union of the two message roles.
Message: TypeAlias = Annotated[UserMessage | AssistantMessage, pydantic.Field(discriminator="role")]


class MessageWithParts(OpencodeModel):
    """A message plus its ordered list of parts (the wire shape of ``GET .../message``)."""

    info: Message
    parts: list[Part]

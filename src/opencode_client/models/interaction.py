"""Models for pending interaction requests: permissions and questions.

These shapes describe requests that block a running turn until the client
answers: a **permission request** asks to allow/deny a tool pattern, and a
**question request** asks the user to pick or type answers to one or more
questions (the interactive-question tool).
"""

from typing import Any

from .base import OpencodeModel

__all__ = [
    "PermissionRequest",
    "PermissionTool",
    "QuestionAnswer",
    "QuestionInfo",
    "QuestionOption",
    "QuestionRequest",
    "QuestionTool",
]

#: One answer to one question: the list of selected option labels.
QuestionAnswer = list[str]


class QuestionOption(OpencodeModel):
    """A selectable answer choice for one question."""

    label: str
    description: str


class QuestionInfo(OpencodeModel):
    """One question to ask, with its available options.

    Args reflect the option-tool wire shape; ``options`` may be empty when the
    question is open-ended (``custom``).
    """

    question: str
    header: str
    options: list[QuestionOption]
    multiple: bool | None = None
    custom: bool | None = None


class QuestionTool(OpencodeModel):
    """Pointer to the tool call that raised the question (message + call id)."""

    message_id: str
    call_id: str


class QuestionRequest(OpencodeModel):
    """A pending question request awaiting user answers."""

    id: str
    session_id: str
    questions: list[QuestionInfo]
    tool: QuestionTool | None = None


class PermissionTool(OpencodeModel):
    """Pointer to the tool call that triggered a permission request."""

    message_id: str
    call_id: str


class PermissionRequest(OpencodeModel):
    """A pending permission request awaiting an allow/deny reply.

    ``permission`` is the permission name (e.g. ``"bash"``), ``patterns`` are
    the concrete patterns being asked about, and ``always`` the scopes that
    would be persisted if answered ``always``.
    """

    id: str
    session_id: str
    permission: str
    patterns: list[str]
    metadata: dict[str, Any]
    always: list[str]
    tool: PermissionTool | None = None

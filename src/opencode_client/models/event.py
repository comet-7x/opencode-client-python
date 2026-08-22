"""The generic event shape delivered over ``GET /event`` (SSE)."""

from typing import Any

from .base import OpencodeModel

__all__ = ["Event"]


class Event(OpencodeModel):
    """A single server event.

    The server emits ~94 event types (``session.updated``,
    ``message.part.updated``, ...). Instead of modelling each one,
    :attr:`properties` stays a free-form dict; branch on ``event.type``.
    """

    id: str | None = None
    type: str
    properties: dict[str, Any] = {}

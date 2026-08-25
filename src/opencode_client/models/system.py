"""Models for server system-info endpoints: /path, /lsp and /log."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .base import OpencodeModel

__all__ = ["LSPStatus", "LogEntry", "ServerPaths"]


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

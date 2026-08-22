"""Models for the /vcs endpoints: repo info, file status and diffs."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .base import OpencodeModel

__all__ = ["VcsFileDiff", "VcsFileStatus", "VcsInfo"]


class VcsInfo(OpencodeModel):
    """Repository info reported by ``GET /vcs`` (branch + default branch).

    Both fields are optional on the wire; ``default_branch`` is snake_case
    while most of the API is camelCase, so it carries an explicit alias to
    stop ``id_alias`` from turning it into ``defaultBranch``.
    """

    branch: str | None = None
    default_branch: str | None = Field(
        default=None, validation_alias="default_branch", serialization_alias="default_branch"
    )


class VcsFileStatus(OpencodeModel):
    """One changed file in ``GET /vcs/status``."""

    file: str
    additions: float
    deletions: float
    status: Literal["added", "deleted", "modified"]


class VcsFileDiff(OpencodeModel):
    """One changed file's unified diff from ``GET /vcs/diff``."""

    file: str
    patch: str
    additions: float
    deletions: float
    status: Literal["added", "deleted", "modified"]

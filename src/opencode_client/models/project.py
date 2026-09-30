"""Models for the /project endpoints: workspaces, icons and directories."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .base import OpencodeModel

__all__ = [
    "Project",
    "ProjectCommands",
    "ProjectDirectory",
    "ProjectIcon",
    "ProjectTime",
    "UpdateProjectRequest",
]


class ProjectIcon(OpencodeModel):
    """Optional icon metadata for a project (URL / emoji override / color)."""

    url: str | None = None
    override: str | None = None
    color: str | None = None


class ProjectCommands(OpencodeModel):
    """Project-level lifecycle commands (e.g. what to run in new worktrees)."""

    start: str | None = None


class ProjectTime(OpencodeModel):
    """Timestamps of a project's lifecycle (server-side epoch millis)."""

    created: int
    updated: int
    initialized: int | None = None


class Project(OpencodeModel):
    """One registered project (a worktree opencode can operate on).

    ``vcs`` is ``"git"`` when the worktree is a git repository, otherwise
    absent.  ``sandboxes`` lists the sandbox environments attached to the
    project.
    """

    id: str
    worktree: str
    time: ProjectTime
    sandboxes: list[str]
    vcs: Literal["git"] | None = None
    name: str | None = None
    icon: ProjectIcon | None = None
    commands: ProjectCommands | None = None


class UpdateProjectRequest(OpencodeModel):
    """Mutable fields for ``PATCH /project/{id}`` — everything is optional."""

    name: str | None = None
    icon: ProjectIcon | None = None
    commands: ProjectCommands | None = None


class ProjectDirectory(OpencodeModel):
    """One directory entry from ``GET /project/{id}/directories``.

    ``strategy`` is optional on the wire; it names how the directory was
    discovered/attached to the project.
    """

    directory: str
    strategy: str | None = Field(default=None)

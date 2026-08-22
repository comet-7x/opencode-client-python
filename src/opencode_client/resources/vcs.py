"""VCS resource: repository info, status, diffs and patch application.

Maps to the ``/vcs*`` endpoints and ships in two flavours:

- :class:`VcsResource` — synchronous, backed by :class:`OpenCodeClient`;
- :class:`AsyncVcsResource` — asynchronous, backed by :class:`AsyncOpenCodeClient`.

``diff_raw`` returns the raw ``text/x-diff`` body as a string rather than a
parsed model (see :func:`_wire.validate_text`).
"""

from __future__ import annotations

from typing import Any, Literal

from ..models import VcsFileDiff, VcsFileStatus, VcsInfo
from ._wire import (
    TYPE_ADAPTERS,
    request_spec,
    validate_response,
    validate_text,
    vcs_apply_body,
    vcs_diff_query,
)
from .base import AsyncResource, Resource

__all__ = ["AsyncVcsResource", "VcsResource"]


class VcsResource(Resource):
    """Synchronous client for the ``/vcs*`` endpoints."""

    def info(self, directory: str | None = None, workspace: str | None = None) -> VcsInfo:
        """Get the current branch and default branch of the repository."""
        response = self._send("GET", "/vcs", **request_spec(directory=directory, workspace=workspace))
        return validate_response(response, TYPE_ADAPTERS.vcs_info)

    def status(self, directory: str | None = None, workspace: str | None = None) -> list[VcsFileStatus]:
        """List changed files (added/modified/deleted) with their change counts."""
        response = self._send("GET", "/vcs/status", **request_spec(directory=directory, workspace=workspace))
        return validate_response(response, TYPE_ADAPTERS.vcs_status)

    def diff(
        self,
        mode: Literal["git", "branch"],
        context: int | None = None,
        directory: str | None = None,
        workspace: str | None = None,
    ) -> list[VcsFileDiff]:
        """Get a structured per-file diff.

        Args:
            mode: Diff base to compare against — ``"git"`` (working tree vs
                index/HEAD) or ``"branch"`` (vs the current branch).
            context: Optional number of context lines.
        """
        query = vcs_diff_query(mode, context)
        response = self._send("GET", "/vcs/diff", **request_spec(directory=directory, workspace=workspace, query=query))
        return validate_response(response, TYPE_ADAPTERS.vcs_diff)

    def diff_raw(self, directory: str | None = None, workspace: str | None = None) -> str:
        """Get the combined raw unified diff as text (``text/x-diff``)."""
        response = self._send("GET", "/vcs/diff/raw", **request_spec(directory=directory, workspace=workspace))
        return validate_text(response)

    def apply(
        self,
        patch: str,
        directory: str | None = None,
        workspace: str | None = None,
    ) -> dict[str, Any]:
        """Apply a unified diff patch to the working tree.

        Args:
            patch: The unified diff patch text.

        Returns:
            The server's apply result document.
        """
        json_body = vcs_apply_body(patch)
        response = self._send(
            "POST", "/vcs/apply", **request_spec(directory=directory, workspace=workspace, json_body=json_body)
        )
        return validate_response(response, TYPE_ADAPTERS.vcs_apply)


class AsyncVcsResource(AsyncResource):
    """Asynchronous client for the ``/vcs*`` endpoints."""

    async def info(self, directory: str | None = None, workspace: str | None = None) -> VcsInfo:
        """Get the current branch and default branch of the repository."""
        response = await self._send("GET", "/vcs", **request_spec(directory=directory, workspace=workspace))
        return validate_response(response, TYPE_ADAPTERS.vcs_info)

    async def status(self, directory: str | None = None, workspace: str | None = None) -> list[VcsFileStatus]:
        """List changed files (added/modified/deleted) with their change counts."""
        response = await self._send("GET", "/vcs/status", **request_spec(directory=directory, workspace=workspace))
        return validate_response(response, TYPE_ADAPTERS.vcs_status)

    async def diff(
        self,
        mode: Literal["git", "branch"],
        context: int | None = None,
        directory: str | None = None,
        workspace: str | None = None,
    ) -> list[VcsFileDiff]:
        """Get a structured per-file diff.

        Args:
            mode: Diff base to compare against — ``"git"`` or ``"branch"``.
            context: Optional number of context lines.
        """
        query = vcs_diff_query(mode, context)
        response = await self._send(
            "GET", "/vcs/diff", **request_spec(directory=directory, workspace=workspace, query=query)
        )
        return validate_response(response, TYPE_ADAPTERS.vcs_diff)

    async def diff_raw(self, directory: str | None = None, workspace: str | None = None) -> str:
        """Get the combined raw unified diff as text (``text/x-diff``)."""
        response = await self._send("GET", "/vcs/diff/raw", **request_spec(directory=directory, workspace=workspace))
        return validate_text(response)

    async def apply(
        self,
        patch: str,
        directory: str | None = None,
        workspace: str | None = None,
    ) -> dict[str, Any]:
        """Apply a unified diff patch to the working tree.

        Args:
            patch: The unified diff patch text.

        Returns:
            The server's apply result document.
        """
        json_body = vcs_apply_body(patch)
        response = await self._send(
            "POST", "/vcs/apply", **request_spec(directory=directory, workspace=workspace, json_body=json_body)
        )
        return validate_response(response, TYPE_ADAPTERS.vcs_apply)

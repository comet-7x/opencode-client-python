"""Projects resource: registered workspaces and their directories.

Maps to the ``/project*`` endpoints and ships in two flavours:

- :class:`ProjectsResource` — synchronous, backed by :class:`OpenCodeClient`;
- :class:`AsyncProjectsResource` — asynchronous, backed by :class:`AsyncOpenCodeClient`.
"""

from __future__ import annotations

import builtins

import httpx

from ..models import Project, ProjectDirectory, UpdateProjectRequest
from ._wire import (
    TYPE_ADAPTERS,
    path_segment,
    request_spec,
    update_project_body,
    validate_response,
)
from .base import AsyncResource, Resource

__all__ = [
    "AsyncProjectsResource",
    "AsyncProjectsResourceWithRawResponse",
    "ProjectsResource",
    "ProjectsResourceWithRawResponse",
]


def _id_path(project_id: str, suffix: str = "") -> str:
    """Build a ``/project/{id}`` sub-path with the id percent-encoded."""
    return f"/project/{path_segment(project_id)}{suffix}"


class ProjectsResource(Resource):
    """Synchronous client for the ``/project*`` endpoints."""

    @property
    def with_raw_response(self) -> ProjectsResourceWithRawResponse:
        """Prefix for the raw-response variants of every method below.

        Each call returns the unprocessed :class:`httpx.Response` instead of
        the parsed model (same retries, same error mapping on non-2xx).
        """
        return ProjectsResourceWithRawResponse(self._client)

    def list(self, directory: str | None = None, workspace: str | None = None) -> list[Project]:
        """List every project known to the server."""
        response = self._send("GET", "/project", **request_spec(directory=directory, workspace=workspace))
        return validate_response(response, TYPE_ADAPTERS.projects)

    def current(self, directory: str | None = None, workspace: str | None = None) -> Project:
        """Get the project the server is currently scoped to."""
        response = self._send("GET", "/project/current", **request_spec(directory=directory, workspace=workspace))
        return validate_response(response, TYPE_ADAPTERS.project)

    def update(
        self,
        project_id: str,
        body: UpdateProjectRequest,
        directory: str | None = None,
        workspace: str | None = None,
    ) -> Project:
        """Update mutable project fields (name/icon/commands).

        Args:
            project_id: The project's ``prj_...`` identifier.
            body: Only the fields to change; everything else is preserved.
        """
        json_body = update_project_body(body)
        response = self._send(
            "PATCH", _id_path(project_id), **request_spec(directory=directory, workspace=workspace, json_body=json_body)
        )
        return validate_response(response, TYPE_ADAPTERS.project)

    def directories(
        self, project_id: str, directory: str | None = None, workspace: str | None = None
    ) -> builtins.list[ProjectDirectory]:
        """List directories attached to a project (and how each was attached)."""
        response = self._send(
            "GET", _id_path(project_id, "/directories"), **request_spec(directory=directory, workspace=workspace)
        )
        return validate_response(response, TYPE_ADAPTERS.project_directories)

    def git_init(self, directory: str | None = None, workspace: str | None = None) -> Project:
        """Initialize a git repository in the scoped worktree; return the project."""
        response = self._send("POST", "/project/git/init", **request_spec(directory=directory, workspace=workspace))
        return validate_response(response, TYPE_ADAPTERS.project)


class AsyncProjectsResource(AsyncResource):
    """Asynchronous client for the ``/project*`` endpoints."""

    @property
    def with_raw_response(self) -> AsyncProjectsResourceWithRawResponse:
        """Prefix for the raw-response variants of every method below.

        Each call returns the unprocessed :class:`httpx.Response` instead of
        the parsed model (same retries, same error mapping on non-2xx).
        """
        return AsyncProjectsResourceWithRawResponse(self._client)

    async def list(self, directory: str | None = None, workspace: str | None = None) -> builtins.list[Project]:
        """List every project known to the server."""
        response = await self._send("GET", "/project", **request_spec(directory=directory, workspace=workspace))
        return validate_response(response, TYPE_ADAPTERS.projects)

    async def current(self, directory: str | None = None, workspace: str | None = None) -> Project:
        """Get the project the server is currently scoped to."""
        response = await self._send("GET", "/project/current", **request_spec(directory=directory, workspace=workspace))
        return validate_response(response, TYPE_ADAPTERS.project)

    async def update(
        self,
        project_id: str,
        body: UpdateProjectRequest,
        directory: str | None = None,
        workspace: str | None = None,
    ) -> Project:
        """Update mutable project fields (name/icon/commands).

        Args:
            project_id: The project's ``prj_...`` identifier.
            body: Only the fields to change; everything else is preserved.
        """
        json_body = update_project_body(body)
        response = await self._send(
            "PATCH",
            _id_path(project_id),
            **request_spec(directory=directory, workspace=workspace, json_body=json_body),
        )
        return validate_response(response, TYPE_ADAPTERS.project)

    async def directories(
        self, project_id: str, directory: str | None = None, workspace: str | None = None
    ) -> builtins.list[ProjectDirectory]:
        """List directories attached to a project (and how each was attached)."""
        response = await self._send(
            "GET", _id_path(project_id, "/directories"), **request_spec(directory=directory, workspace=workspace)
        )
        return validate_response(response, TYPE_ADAPTERS.project_directories)

    async def git_init(self, directory: str | None = None, workspace: str | None = None) -> Project:
        """Initialize a git repository in the scoped worktree; return the project."""
        response = await self._send(
            "POST", "/project/git/init", **request_spec(directory=directory, workspace=workspace)
        )
        return validate_response(response, TYPE_ADAPTERS.project)


class ProjectsResourceWithRawResponse(Resource):
    """Synchronous raw-response view of the ``/project*`` endpoints.

    Mirrors :class:`ProjectsResource` method-for-method but returns the
    unprocessed response instead of the parsed model. Non-2xx still raise
    the same mapped errors; retries are shared.
    """

    def list(self, directory: str | None = None, workspace: str | None = None) -> httpx.Response:
        """List all projects; return the raw response."""
        return self._send("GET", "/project", **request_spec(directory=directory, workspace=workspace))

    def current(self, directory: str | None = None, workspace: str | None = None) -> httpx.Response:
        """Get the current project; return the raw response."""
        return self._send("GET", "/project/current", **request_spec(directory=directory, workspace=workspace))

    def update(
        self,
        project_id: str,
        body: UpdateProjectRequest,
        directory: str | None = None,
        workspace: str | None = None,
    ) -> httpx.Response:
        """Update a project; return the raw response."""
        json_body = update_project_body(body)
        return self._send(
            "PATCH",
            _id_path(project_id),
            **request_spec(directory=directory, workspace=workspace, json_body=json_body),
        )

    def directories(
        self, project_id: str, directory: str | None = None, workspace: str | None = None
    ) -> httpx.Response:
        """List a project's directories; return the raw response."""
        return self._send(
            "GET", _id_path(project_id, "/directories"), **request_spec(directory=directory, workspace=workspace)
        )

    def git_init(self, directory: str | None = None, workspace: str | None = None) -> httpx.Response:
        """Initialize a git repository; return the raw response."""
        return self._send("POST", "/project/git/init", **request_spec(directory=directory, workspace=workspace))


class AsyncProjectsResourceWithRawResponse(AsyncResource):
    """Asynchronous raw-response view of the ``/project*`` endpoints.

    Mirrors :class:`AsyncProjectsResource` method-for-method but returns the
    unprocessed response instead of the parsed model. Non-2xx still raise
    the same mapped errors; retries are shared.
    """

    async def list(self, directory: str | None = None, workspace: str | None = None) -> httpx.Response:
        """List all projects; return the raw response."""
        return await self._send("GET", "/project", **request_spec(directory=directory, workspace=workspace))

    async def current(self, directory: str | None = None, workspace: str | None = None) -> httpx.Response:
        """Get the current project; return the raw response."""
        return await self._send("GET", "/project/current", **request_spec(directory=directory, workspace=workspace))

    async def update(
        self,
        project_id: str,
        body: UpdateProjectRequest,
        directory: str | None = None,
        workspace: str | None = None,
    ) -> httpx.Response:
        """Update a project; return the raw response."""
        json_body = update_project_body(body)
        return await self._send(
            "PATCH",
            _id_path(project_id),
            **request_spec(directory=directory, workspace=workspace, json_body=json_body),
        )

    async def directories(
        self, project_id: str, directory: str | None = None, workspace: str | None = None
    ) -> httpx.Response:
        """List a project's directories; return the raw response."""
        return await self._send(
            "GET", _id_path(project_id, "/directories"), **request_spec(directory=directory, workspace=workspace)
        )

    async def git_init(self, directory: str | None = None, workspace: str | None = None) -> httpx.Response:
        """Initialize a git repository; return the raw response."""
        return await self._send("POST", "/project/git/init", **request_spec(directory=directory, workspace=workspace))

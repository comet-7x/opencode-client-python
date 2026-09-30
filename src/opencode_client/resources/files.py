"""Files resource: filesystem browsing, content reads, search and formatters.

Maps to the ``/file*``, ``/find*`` and ``/formatter`` endpoints (the server
groups them all in its ``fileHandlers``) and ships in two flavours:

- :class:`FilesResource` — synchronous, backed by :class:`OpenCodeClient`;
- :class:`AsyncFilesResource` — asynchronous, backed by :class:`AsyncOpenCodeClient`.

All endpoints are read-only ``GET``s scoped by the usual
``directory``/``workspace`` query params.
"""

from __future__ import annotations

import builtins
from typing import Literal

import httpx

from ..models import (
    FileChange,
    FileContent,
    FileNode,
    FormatterStatus,
    Symbol,
    TextMatch,
)
from ._wire import (
    TYPE_ADAPTERS,
    find_file_query,
    request_spec,
    validate_response,
)
from .base import AsyncResource, Resource

__all__ = [
    "AsyncFilesResource",
    "AsyncFilesResourceWithRawResponse",
    "FilesResource",
    "FilesResourceWithRawResponse",
]


def _path_query(path: str) -> dict[str, str]:
    """Build the required ``path`` query param shared by list/read."""
    return {"path": path}


class FilesResource(Resource):
    """Synchronous client for file browsing, search and formatter status."""

    @property
    def with_raw_response(self) -> FilesResourceWithRawResponse:
        """Prefix for the raw-response variants of every method below.

        Each call returns the unprocessed :class:`httpx.Response` instead of
        the parsed model (same retries, same error mapping on non-2xx).
        """
        return FilesResourceWithRawResponse(self._client)

    def list(self, path: str, directory: str | None = None, workspace: str | None = None) -> builtins.list[FileNode]:
        """List one level of a directory relative to the server's worktree.

        Args:
            path: Directory path to list (``""`` or ``"."`` for the root).
        """
        response = self._send(
            "GET", "/file", **request_spec(directory=directory, workspace=workspace, query=_path_query(path))
        )
        return validate_response(response, TYPE_ADAPTERS.file_nodes)

    def read(self, path: str, directory: str | None = None, workspace: str | None = None) -> FileContent:
        """Read a file; text comes back plain, binary as base64.

        Check :attr:`FileContent.type` to narrow between
        :class:`TextFileContent` and :class:`BinaryFileContent`.
        """
        response = self._send(
            "GET",
            "/file/content",
            **request_spec(directory=directory, workspace=workspace, query=_path_query(path)),
        )
        return validate_response(response, TYPE_ADAPTERS.file_content)

    def status(self, directory: str | None = None, workspace: str | None = None) -> builtins.list[FileChange]:
        """List changed files (added/modified/deleted) with line counts."""
        response = self._send("GET", "/file/status", **request_spec(directory=directory, workspace=workspace))
        return validate_response(response, TYPE_ADAPTERS.file_changes)

    def search_text(
        self, pattern: str, directory: str | None = None, workspace: str | None = None
    ) -> builtins.list[TextMatch]:
        """Ripgrep-style text search across the worktree.

        The server caps results at 10 matches (not configurable).

        Args:
            pattern: Regex pattern to search for.
        """
        response = self._send(
            "GET", "/find", **request_spec(directory=directory, workspace=workspace, query={"pattern": pattern})
        )
        return validate_response(response, TYPE_ADAPTERS.text_matches)

    def search_files(
        self,
        query: str,
        dirs: bool | None = None,
        type: Literal["file", "directory"] | None = None,
        limit: int | None = None,
        directory: str | None = None,
        workspace: str | None = None,
    ) -> builtins.list[str]:
        """Fuzzy-find file paths by name fragment.

        Args:
            query: Filename fragment to match.
            dirs: Whether directories are included in the search.
            type: Restrict results to files or directories.
            limit: Maximum number of paths (server default is 10).
        """
        params = find_file_query(query, dirs, type, limit)
        response = self._send(
            "GET", "/find/file", **request_spec(directory=directory, workspace=workspace, query=params)
        )
        return validate_response(response, TYPE_ADAPTERS.found_paths)

    def search_symbols(
        self, query: str, directory: str | None = None, workspace: str | None = None
    ) -> builtins.list[Symbol]:
        """Search workspace symbols (LSP); ``kind`` is the numeric LSP kind."""
        response = self._send(
            "GET", "/find/symbol", **request_spec(directory=directory, workspace=workspace, query={"query": query})
        )
        return validate_response(response, TYPE_ADAPTERS.symbols)

    def formatter_status(
        self, directory: str | None = None, workspace: str | None = None
    ) -> builtins.list[FormatterStatus]:
        """List registered formatters with their handled extensions."""
        response = self._send("GET", "/formatter", **request_spec(directory=directory, workspace=workspace))
        return validate_response(response, TYPE_ADAPTERS.formatter_statuses)


class AsyncFilesResource(AsyncResource):
    """Asynchronous client for file browsing, search and formatter status."""

    @property
    def with_raw_response(self) -> AsyncFilesResourceWithRawResponse:
        """Prefix for the raw-response variants of every method below.

        Each call returns the unprocessed :class:`httpx.Response` instead of
        the parsed model (same retries, same error mapping on non-2xx).
        """
        return AsyncFilesResourceWithRawResponse(self._client)

    async def list(
        self, path: str, directory: str | None = None, workspace: str | None = None
    ) -> builtins.list[FileNode]:
        """List one level of a directory relative to the server's worktree.

        Args:
            path: Directory path to list (``""`` or ``"."`` for the root).
        """
        response = await self._send(
            "GET", "/file", **request_spec(directory=directory, workspace=workspace, query=_path_query(path))
        )
        return validate_response(response, TYPE_ADAPTERS.file_nodes)

    async def read(self, path: str, directory: str | None = None, workspace: str | None = None) -> FileContent:
        """Read a file; text comes back plain, binary as base64.

        Check :attr:`FileContent.type` to narrow between
        :class:`TextFileContent` and :class:`BinaryFileContent`.
        """
        response = await self._send(
            "GET",
            "/file/content",
            **request_spec(directory=directory, workspace=workspace, query=_path_query(path)),
        )
        return validate_response(response, TYPE_ADAPTERS.file_content)

    async def status(self, directory: str | None = None, workspace: str | None = None) -> builtins.list[FileChange]:
        """List changed files (added/modified/deleted) with line counts."""
        response = await self._send("GET", "/file/status", **request_spec(directory=directory, workspace=workspace))
        return validate_response(response, TYPE_ADAPTERS.file_changes)

    async def search_text(
        self, pattern: str, directory: str | None = None, workspace: str | None = None
    ) -> builtins.list[TextMatch]:
        """Ripgrep-style text search across the worktree.

        The server caps results at 10 matches (not configurable).

        Args:
            pattern: Regex pattern to search for.
        """
        response = await self._send(
            "GET", "/find", **request_spec(directory=directory, workspace=workspace, query={"pattern": pattern})
        )
        return validate_response(response, TYPE_ADAPTERS.text_matches)

    async def search_files(
        self,
        query: str,
        dirs: bool | None = None,
        type: Literal["file", "directory"] | None = None,
        limit: int | None = None,
        directory: str | None = None,
        workspace: str | None = None,
    ) -> builtins.list[str]:
        """Fuzzy-find file paths by name fragment.

        Args:
            query: Filename fragment to match.
            dirs: Whether directories are included in the search.
            type: Restrict results to files or directories.
            limit: Maximum number of paths (server default is 10).
        """
        params = find_file_query(query, dirs, type, limit)
        response = await self._send(
            "GET", "/find/file", **request_spec(directory=directory, workspace=workspace, query=params)
        )
        return validate_response(response, TYPE_ADAPTERS.found_paths)

    async def search_symbols(
        self, query: str, directory: str | None = None, workspace: str | None = None
    ) -> builtins.list[Symbol]:
        """Search workspace symbols (LSP); ``kind`` is the numeric LSP kind."""
        response = await self._send(
            "GET", "/find/symbol", **request_spec(directory=directory, workspace=workspace, query={"query": query})
        )
        return validate_response(response, TYPE_ADAPTERS.symbols)

    async def formatter_status(
        self, directory: str | None = None, workspace: str | None = None
    ) -> builtins.list[FormatterStatus]:
        """List registered formatters with their handled extensions."""
        response = await self._send("GET", "/formatter", **request_spec(directory=directory, workspace=workspace))
        return validate_response(response, TYPE_ADAPTERS.formatter_statuses)


class FilesResourceWithRawResponse(Resource):
    """Synchronous raw-response view of the files-domain endpoints.

    Mirrors :class:`FilesResource` method-for-method but returns the
    unprocessed response instead of the parsed model. Non-2xx still raise
    the same mapped errors; retries are shared.
    """

    def list(self, path: str, directory: str | None = None, workspace: str | None = None) -> httpx.Response:
        """List a directory; return the raw response."""
        return self._send(
            "GET", "/file", **request_spec(directory=directory, workspace=workspace, query=_path_query(path))
        )

    def read(self, path: str, directory: str | None = None, workspace: str | None = None) -> httpx.Response:
        """Read a file; return the raw response."""
        return self._send(
            "GET",
            "/file/content",
            **request_spec(directory=directory, workspace=workspace, query=_path_query(path)),
        )

    def status(self, directory: str | None = None, workspace: str | None = None) -> httpx.Response:
        """List changed files; return the raw response."""
        return self._send("GET", "/file/status", **request_spec(directory=directory, workspace=workspace))

    def search_text(self, pattern: str, directory: str | None = None, workspace: str | None = None) -> httpx.Response:
        """Text-search the worktree; return the raw response."""
        return self._send(
            "GET", "/find", **request_spec(directory=directory, workspace=workspace, query={"pattern": pattern})
        )

    def search_files(
        self,
        query: str,
        dirs: bool | None = None,
        type: Literal["file", "directory"] | None = None,
        limit: int | None = None,
        directory: str | None = None,
        workspace: str | None = None,
    ) -> httpx.Response:
        """Fuzzy-find file paths; return the raw response."""
        params = find_file_query(query, dirs, type, limit)
        return self._send("GET", "/find/file", **request_spec(directory=directory, workspace=workspace, query=params))

    def search_symbols(self, query: str, directory: str | None = None, workspace: str | None = None) -> httpx.Response:
        """Search workspace symbols; return the raw response."""
        return self._send(
            "GET", "/find/symbol", **request_spec(directory=directory, workspace=workspace, query={"query": query})
        )

    def formatter_status(self, directory: str | None = None, workspace: str | None = None) -> httpx.Response:
        """List registered formatters; return the raw response."""
        return self._send("GET", "/formatter", **request_spec(directory=directory, workspace=workspace))


class AsyncFilesResourceWithRawResponse(AsyncResource):
    """Asynchronous raw-response view of the files-domain endpoints.

    Mirrors :class:`AsyncFilesResource` method-for-method but returns the
    unprocessed response instead of the parsed model. Non-2xx still raise
    the same mapped errors; retries are shared.
    """

    async def list(self, path: str, directory: str | None = None, workspace: str | None = None) -> httpx.Response:
        """List a directory; return the raw response."""
        return await self._send(
            "GET", "/file", **request_spec(directory=directory, workspace=workspace, query=_path_query(path))
        )

    async def read(self, path: str, directory: str | None = None, workspace: str | None = None) -> httpx.Response:
        """Read a file; return the raw response."""
        return await self._send(
            "GET",
            "/file/content",
            **request_spec(directory=directory, workspace=workspace, query=_path_query(path)),
        )

    async def status(self, directory: str | None = None, workspace: str | None = None) -> httpx.Response:
        """List changed files; return the raw response."""
        return await self._send("GET", "/file/status", **request_spec(directory=directory, workspace=workspace))

    async def search_text(
        self, pattern: str, directory: str | None = None, workspace: str | None = None
    ) -> httpx.Response:
        """Text-search the worktree; return the raw response."""
        return await self._send(
            "GET", "/find", **request_spec(directory=directory, workspace=workspace, query={"pattern": pattern})
        )

    async def search_files(
        self,
        query: str,
        dirs: bool | None = None,
        type: Literal["file", "directory"] | None = None,
        limit: int | None = None,
        directory: str | None = None,
        workspace: str | None = None,
    ) -> httpx.Response:
        """Fuzzy-find file paths; return the raw response."""
        params = find_file_query(query, dirs, type, limit)
        return await self._send(
            "GET", "/find/file", **request_spec(directory=directory, workspace=workspace, query=params)
        )

    async def search_symbols(
        self, query: str, directory: str | None = None, workspace: str | None = None
    ) -> httpx.Response:
        """Search workspace symbols; return the raw response."""
        return await self._send(
            "GET", "/find/symbol", **request_spec(directory=directory, workspace=workspace, query={"query": query})
        )

    async def formatter_status(self, directory: str | None = None, workspace: str | None = None) -> httpx.Response:
        """List registered formatters; return the raw response."""
        return await self._send("GET", "/formatter", **request_spec(directory=directory, workspace=workspace))

"""Shared plumbing for resource groups.

A *resource* groups the client methods for one area of the API (``sessions``,
``server``). Resources are plain composition: each instance holds its owner
client and reuses ``client.send()`` for transport. There is no inheritance
magic, which keeps groups trivially composable and swappable.

Every resource area ships in two flavours with identical signatures:

- a **sync** resource, whose methods call ``client.send`` directly;
- an **async** resource, whose methods ``await`` the same call.

Request-shaping logic (paths, query params, bodies, parse adapters) is shared
via :mod:`opencode_client.resources._wire`, so the two flavours can never
drift apart in what they send or how they parse.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx

if TYPE_CHECKING:
    from ..client import AsyncOpenCodeClient, OpenCodeClient


def query_params(
    directory: str | None,
    workspace: str | None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a query-string dict, dropping ``None`` values.

    Most endpoints accept optional ``directory``/``workspace`` scoping
    parameters; this keeps their spelling in one place.

    Args:
        directory: Optional ``directory`` scoping value.
        workspace: Optional ``workspace`` scoping value.
        extra: Additional name/value pairs to merge in.

    Returns:
        A dict of query params containing only the supplied values.
    """
    params: dict[str, Any] = {}
    if directory is not None:
        params["directory"] = directory
    if workspace is not None:
        params["workspace"] = workspace
    if extra:
        params.update(extra)
    return params


class Resource:
    """Base for sync API resource groups (composition over inheritance)."""

    def __init__(self, client: OpenCodeClient) -> None:
        self._client = client

    @property
    def client(self) -> OpenCodeClient:
        """:return: the owning client instance."""
        return self._client

    def _send(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        """Forward a raw request to the client transport.

        Args:
            method: HTTP method.
            path: Path relative to the base URL.
            **kwargs: Anything the underlying ``httpx.Client.request`` accepts.

        Raises:
            OpenCodeApiError: On any non-2xx response.
            OpenCodeTransportError: On connection-level failures.
        """
        return self._client.send(method, path, **kwargs)


class AsyncResource:
    """Base for async API resource groups (composition over inheritance)."""

    def __init__(self, client: AsyncOpenCodeClient) -> None:
        self._client = client

    @property
    def client(self) -> AsyncOpenCodeClient:
        """:return: the owning async client instance."""
        return self._client

    async def _send(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        """Forward a raw request to the async client transport.

        Args:
            method: HTTP method.
            path: Path relative to the base URL.
            **kwargs: Anything the underlying ``httpx.AsyncClient.request`` accepts.

        Raises:
            OpenCodeApiError: On any non-2xx response.
            OpenCodeTransportError: On connection-level failures.
        """
        return await self._client.send(method, path, **kwargs)

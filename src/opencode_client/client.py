"""Core HTTP clients for the opencode server (``opencode serve``).

The package ships two clients with an identical API:

- :class:`OpenCodeClient` — synchronous (blocking);
- :class:`AsyncOpenCodeClient` — asynchronous.

Both expose API resource groups:

- ``client.sessions`` — session CRUD, prompt, messages, permissions;
- ``client.server`` — health/config, providers, agents, commands, event stream.

Synchronous usage::

    with OpenCodeClient("http://127.0.0.1:4096") as client:
        print(client.server.health().version)
        session = client.sessions.create()

Asynchronous usage::

    async with AsyncOpenCodeClient("http://127.0.0.1:4096") as client:
        print((await client.server.health()).version)
        session = await client.sessions.create()

The two classes differ only in the transport (blocking vs. ``await``);
path/query/body helpers and response parsing live in :mod:`opencode_client.resources`
and are shared by both.
"""

from __future__ import annotations

import asyncio
import time
from types import TracebackType
from typing import Any

import httpx

from ._types import NOT_GIVEN, NotGiven
from .constants import DEFAULT_CONNECT_TIMEOUT, DEFAULT_MAX_RETRIES, DEFAULT_USER_AGENT
from .errors import OpenCodeServerError, make_api_error, make_transport_error
from .resources.mcp import AsyncMcpResource, McpResource
from .resources.server import AsyncServerResource, ServerResource
from .resources.sessions import AsyncSessionsResource, SessionsResource
from .resources.vcs import AsyncVcsResource, VcsResource

__all__ = ["AsyncOpenCodeClient", "OpenCodeClient"]


def _is_retryable_status(status_code: int) -> bool:
    """Return ``True`` for status codes that benefit from another attempt (429 / 5xx)."""
    return status_code == 429 or status_code >= 500


def _auth(username: str | None, password: str | None) -> httpx.BasicAuth | None:
    """Build Basic auth from a credential pair, or ``None`` when no password is given.

    Args:
        username: Basic-auth username.
        password: Basic-auth password.

    Returns:
        A :class:`httpx.BasicAuth` instance, or ``None`` when ``password`` is ``None``.
    """
    return httpx.BasicAuth(username or "opencode", password) if password is not None else None


def _client_kwargs(
    base_url: str,
    username: str | None,
    password: str | None,
    timeout: float,
    extra: dict[str, Any],
) -> dict[str, Any]:
    """Common httpx client settings shared by the sync and async transports.

    Args:
        base_url: Server base URL.
        username: Basic-auth username (used only with ``password``).
        password: Basic-auth password; omit for unauthenticated servers.
        timeout: Timeout in seconds for connecting and reading.
        extra: Extra settings forwarded to the underlying httpx client.

    Returns:
        The keyword arguments accepted by :class:`httpx.Client` / :class:`httpx.AsyncClient`.
    """
    return {
        "base_url": base_url.rstrip("/"),
        "auth": _auth(username, password),
        "timeout": timeout,
        "headers": {"User-Agent": DEFAULT_USER_AGENT},
        **extra,
    }


def _backoff_seconds(attempt: int, response: httpx.Response | None = None) -> float:
    """Delay before retry ``attempt`` (1-based), honouring ``Retry-After`` when present.

    Exponential backoff: 0.5s, 1s, 2s ... capped at 8s.

    Args:
        attempt: The 1-based retry index (1 = wait before the 2nd attempt).
        response: The failed response (used to read ``Retry-After``).

    Returns:
        Seconds to sleep before the next attempt.
    """
    if response is not None:
        retry_after = response.headers.get("Retry-After")
        if retry_after is not None and retry_after.isdigit():
            return float(retry_after)
    backoff: float = min(0.5 * (2.0 ** (attempt - 1)), 8.0)
    return backoff


class ClientOptions:
    """Constructor settings, kept so :meth:`with_options` can rebuild the client.

    Args:
        base_url: Server base URL.
        username: Basic-auth username (used only with ``password``).
        password: Basic-auth password.
        timeout: Timeout in seconds.
        max_retries: Number of retries for failed (429/5xx/connection) requests.
        extra: Extra kwargs for the underlying httpx client.
    """

    def __init__(
        self,
        base_url: str,
        username: str | None = "opencode",
        password: str | None = None,
        timeout: float = DEFAULT_CONNECT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        **extra: Any,
    ) -> None:
        self.base_url = base_url
        self.username = username
        self.password = password
        self.timeout = timeout
        self.max_retries = max_retries
        self.extra = extra

    def overridden(
        self,
        *,
        base_url: str | NotGiven = NOT_GIVEN,
        timeout: float | NotGiven = NOT_GIVEN,
        max_retries: int | NotGiven = NOT_GIVEN,
    ) -> ClientOptions:
        """Return a copy with any of the given options replaced.

        Use :data:`NOT_GIVEN` to keep the current value; pass an explicit value to override.

        Returns:
            A new :class:`ClientOptions` reflecting the overrides.
        """
        return ClientOptions(
            self.base_url if isinstance(base_url, NotGiven) else base_url,
            username=self.username,
            password=self.password,
            timeout=self.timeout if isinstance(timeout, NotGiven) else timeout,
            max_retries=self.max_retries if isinstance(max_retries, NotGiven) else max_retries,
            **self.extra,
        )


class OpenCodeClient:
    """Synchronous client for one opencode server.

    Performs request retries for transient failures (HTTP 429/5xx and
    connection errors) automatically; see ``max_retries``.

    Args:
        base_url: Server base URL, e.g. ``http://127.0.0.1:4096``.
        username: Basic-auth username; used only when ``password`` is set.
        password: Basic-auth password; omit for unauthenticated servers.
        timeout: Timeout in seconds for connecting and reading.
        max_retries: How many times to retry failed requests (first attempt is free).
        **kwargs: Extra settings forwarded to :class:`httpx.Client`
            (proxies, ssl, headers, ...).

    Example::

        with OpenCodeClient("http://127.0.0.1:4096") as client:
            print(client.server.health().version)
            session = client.sessions.create()
            reply = client.sessions.prompt(session.id, "Hello!")
    """

    def __init__(
        self,
        base_url: str,
        username: str | None = "opencode",
        password: str | None = None,
        timeout: float = DEFAULT_CONNECT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        **kwargs: Any,
    ) -> None:
        self._opts = ClientOptions(base_url, username, password, timeout, max_retries, **kwargs)
        self._http = httpx.Client(**_client_kwargs(base_url, username, password, timeout, kwargs))
        self.sessions = SessionsResource(self)
        self.server = ServerResource(self)
        self.vcs = VcsResource(self)
        self.mcp = McpResource(self)

    @property
    def http(self) -> httpx.Client:
        """The underlying :class:`httpx.Client` (advanced use only)."""
        return self._http

    @property
    def base_url(self) -> str:
        """The effective base URL of this client."""
        return self._opts.base_url

    @property
    def timeout(self) -> float:
        """The effective request timeout in seconds."""
        return self._opts.timeout

    @property
    def max_retries(self) -> int:
        """The effective retry budget."""
        return self._opts.max_retries

    def __enter__(self) -> OpenCodeClient:
        """:return: this client; the transport is already open."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close the underlying HTTP client."""
        self.close()

    def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        self._http.close()

    def with_options(
        self,
        *,
        base_url: str | NotGiven = NOT_GIVEN,
        timeout: float | NotGiven = NOT_GIVEN,
        max_retries: int | NotGiven = NOT_GIVEN,
    ) -> OpenCodeClient:
        """Return a copy of this client with a subset of options overridden.

        Omit an argument (or pass :data:`NOT_GIVEN`) to keep the current value;
        pass an explicit value to override it.
        """
        return OpenCodeClient(
            **_options_to_kwargs(self._opts.overridden(base_url=base_url, timeout=timeout, max_retries=max_retries))
        )

    def send(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        """Send a request with retries, raising mapped errors on failure.

        Args:
            method: HTTP method (``GET``, ``POST``, ...).
            path: Path relative to the base URL.
            **kwargs: Anything :meth:`httpx.Client.request` accepts.

        Raises:
            OpenCodeApiError: Non-2xx status (a subclass chosen for the code).
            OpenCodeTransportError: Connection-level failure.
        """
        attempt = 0
        while True:
            try:
                response = self._http.request(method, path, **kwargs)
            except httpx.HTTPError as exc:
                if attempt < self._opts.max_retries:
                    time.sleep(_backoff_seconds(attempt + 1))
                    attempt += 1
                    continue
                raise make_transport_error(exc) from exc
            if 200 <= response.status_code < 300:
                return response
            if _is_retryable_status(response.status_code) and attempt < self._opts.max_retries:
                time.sleep(_backoff_seconds(attempt + 1, response))
                attempt += 1
                continue
            raise make_api_error(response)
        raise OpenCodeServerError(500, "unreachable")  # pragma: no cover


class AsyncOpenCodeClient:
    """Asynchronous client for one opencode server.

    Performs request retries for transient failures (HTTP 429/5xx and
    connection errors) automatically; see ``max_retries``.

    Args:
        base_url: Server base URL, e.g. ``http://127.0.0.1:4096``.
        username: Basic-auth username; used only when ``password`` is set.
        password: Basic-auth password; omit for unauthenticated servers.
        timeout: Timeout in seconds for connecting and reading.
        max_retries: How many times to retry failed requests (first attempt is free).
        **kwargs: Extra settings forwarded to :class:`httpx.AsyncClient`
            (proxies, ssl, headers, ...).

    Example::

        async with AsyncOpenCodeClient("http://127.0.0.1:4096") as client:
            print((await client.server.health()).version)
            session = await client.sessions.create()
    """

    def __init__(
        self,
        base_url: str,
        username: str | None = "opencode",
        password: str | None = None,
        timeout: float = DEFAULT_CONNECT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        **kwargs: Any,
    ) -> None:
        self._opts = ClientOptions(base_url, username, password, timeout, max_retries, **kwargs)
        self._http = httpx.AsyncClient(**_client_kwargs(base_url, username, password, timeout, kwargs))
        self.sessions = AsyncSessionsResource(self)
        self.server = AsyncServerResource(self)
        self.vcs = AsyncVcsResource(self)
        self.mcp = AsyncMcpResource(self)

    @property
    def http(self) -> httpx.AsyncClient:
        """The underlying :class:`httpx.AsyncClient` (advanced use only)."""
        return self._http

    @property
    def base_url(self) -> str:
        """The effective base URL of this client."""
        return self._opts.base_url

    @property
    def timeout(self) -> float:
        """The effective request timeout in seconds."""
        return self._opts.timeout

    @property
    def max_retries(self) -> int:
        """The effective retry budget."""
        return self._opts.max_retries

    async def __aenter__(self) -> AsyncOpenCodeClient:
        """:return: this client; the transport is already open."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close the underlying HTTP client."""
        await self.close()

    async def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        await self._http.aclose()

    def with_options(
        self,
        *,
        base_url: str | NotGiven = NOT_GIVEN,
        timeout: float | NotGiven = NOT_GIVEN,
        max_retries: int | NotGiven = NOT_GIVEN,
    ) -> AsyncOpenCodeClient:
        """Return a copy of this client with a subset of options overridden.

        Omit an argument (or pass :data:`NOT_GIVEN`) to keep the current value;
        pass an explicit value to override it.
        """
        return AsyncOpenCodeClient(
            **_options_to_kwargs(self._opts.overridden(base_url=base_url, timeout=timeout, max_retries=max_retries))
        )

    async def send(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        """Send a request with retries, raising mapped errors on failure.

        Args:
            method: HTTP method (``GET``, ``POST``, ...).
            path: Path relative to the base URL.
            **kwargs: Anything :meth:`httpx.AsyncClient.request` accepts.

        Raises:
            OpenCodeApiError: Non-2xx status (a subclass chosen for the code).
            OpenCodeTransportError: Connection-level failure.
        """
        attempt = 0
        while True:
            try:
                response = await self._http.request(method, path, **kwargs)
            except httpx.HTTPError as exc:
                if attempt < self._opts.max_retries:
                    await asyncio.sleep(_backoff_seconds(attempt + 1))
                    attempt += 1
                    continue
                raise make_transport_error(exc) from exc
            if 200 <= response.status_code < 300:
                return response
            if _is_retryable_status(response.status_code) and attempt < self._opts.max_retries:
                await asyncio.sleep(_backoff_seconds(attempt + 1, response))
                attempt += 1
                continue
            raise make_api_error(response)
        raise OpenCodeServerError(500, "unreachable")  # pragma: no cover


def _options_to_kwargs(opts: ClientOptions) -> dict[str, Any]:
    """Flatten :class:`ClientOptions` into client constructor kwargs.

    Args:
        opts: The options to flatten.

    Returns:
        A keyword mapping matching the client ``__init__`` signature.
    """
    return {
        "base_url": opts.base_url,
        "username": opts.username,
        "password": opts.password,
        "timeout": opts.timeout,
        "max_retries": opts.max_retries,
        **opts.extra,
    }

"""Request-level retry behaviour: backoff schedule, 429/Retry-After, mapping.

The sync-side happy/sad paths already live in ``test_sync_client.py``; this
module locks the remaining corners and mirrors the whole picture on the async
client so the two transports cannot drift.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Generator

import httpx
import pytest
import respx

from opencode_client import (
    AsyncOpenCodeClient,
    OpenCodeClient,
    OpenCodeRateLimitError,
    OpenCodeServerConnectionError,
    OpenCodeServerError,
    OpenCodeTimeoutError,
)
from opencode_client.client import _backoff_seconds, _is_retryable_status  # pyright: ignore[reportPrivateUsage]

BASE = "http://localhost:4096"


def _healthy() -> httpx.Response:
    return httpx.Response(200, json={"healthy": True, "version": "1.2.3"})


def _unavailable() -> httpx.Response:
    return httpx.Response(503, json={"name": "Service Unavailable", "data": {}})


def _no_sleep(seconds: float) -> None:
    """Collapse the backoff so retry tests run instantly."""


@pytest.fixture
async def client() -> AsyncGenerator[AsyncOpenCodeClient, None]:
    client = AsyncOpenCodeClient(BASE)
    try:
        yield client
    finally:
        await client.close()


@pytest.fixture(autouse=True)
def mock_server() -> Generator[respx.MockRouter, None, None]:
    with respx.mock(base_url=BASE) as router:
        yield router


class TestBackoffSchedule:
    def test_exponential_with_cap(self) -> None:
        assert [round(_backoff_seconds(i), 3) for i in range(1, 5)] == [0.5, 1.0, 2.0, 4.0]
        assert _backoff_seconds(6) == 8.0
        assert _backoff_seconds(99) == 8.0

    def test_retry_after_header_wins(self) -> None:
        response = httpx.Response(429, headers={"Retry-After": "7"})
        assert _backoff_seconds(1, response) == 7.0

    def test_non_numeric_retry_after_falls_back(self) -> None:
        response = httpx.Response(429, headers={"Retry-After": "2026-08-22T00:00:00Z"})
        assert _backoff_seconds(1, response) == 0.5

    def test_retryable_statuses(self) -> None:
        assert all(_is_retryable_status(code) for code in (429, 500, 502, 599))
        assert not any(_is_retryable_status(code) for code in (200, 204, 400, 401, 404, 409, 422))


class TestRetryOnRetryableStatuses:
    def test_5xx_retries_then_succeeds(self, mock_server: respx.MockRouter) -> None:
        route = mock_server.get("/global/health")
        route.side_effect = [_unavailable(), _healthy()]
        with OpenCodeClient(BASE, max_retries=1) as client:
            assert client.server.health().version == "1.2.3"
        assert route.calls.call_count == 2

    def test_502_retries_then_succeeds(self, mock_server: respx.MockRouter) -> None:
        route = mock_server.get("/global/health")
        route.side_effect = [httpx.Response(502, json={}), _healthy()]
        with OpenCodeClient(BASE, max_retries=1) as client:
            client.server.health()
        assert route.calls.call_count == 2

    def test_429_retries_then_succeeds(self, mock_server: respx.MockRouter) -> None:
        route = mock_server.get("/global/health")
        route.side_effect = [httpx.Response(429, json={"name": "Too Many Requests"}), _healthy()]
        with OpenCodeClient(BASE, max_retries=1) as client:
            client.server.health()
        assert route.calls.call_count == 2

    def test_429_exhausted_raises_rate_limit_error(self, mock_server: respx.MockRouter) -> None:
        mock_server.get("/global/health").mock(
            return_value=httpx.Response(429, headers={"Retry-After": "0"}, json={"name": "Too Many Requests"})
        )
        with OpenCodeClient(BASE, max_retries=2) as client:
            with pytest.raises(OpenCodeRateLimitError) as excinfo:
                client.server.health()
        assert excinfo.value.status_code == 429
        assert mock_server.get("/global/health").calls.call_count == 3

    def test_5xx_exhausted_raises_server_error(self, mock_server: respx.MockRouter) -> None:
        mock_server.get("/global/health").mock(return_value=_unavailable())
        with OpenCodeClient(BASE, max_retries=1) as client:
            with pytest.raises(OpenCodeServerError) as excinfo:
                client.server.health()
        assert excinfo.value.status_code == 503
        assert mock_server.get("/global/health").calls.call_count == 2

    def test_retry_budget_zero_never_retries(self, mock_server: respx.MockRouter) -> None:
        mock_server.get("/global/health").mock(return_value=_unavailable())
        with OpenCodeClient(BASE, max_retries=0) as client:
            with pytest.raises(OpenCodeServerError):
                client.server.health()
        assert mock_server.get("/global/health").calls.call_count == 1

    def test_connection_error_retries_then_succeeds(
        self, mock_server: respx.MockRouter, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import opencode_client.client as client_module

        monkeypatch.setattr(client_module.time, "sleep", _no_sleep)
        route = mock_server.get("/global/health")
        route.side_effect = [httpx.ConnectError("reset"), _healthy()]
        with OpenCodeClient(BASE, max_retries=1) as client:
            client.server.health()
        assert route.calls.call_count == 2

    def test_timeout_error_retries_then_succeeds(
        self, mock_server: respx.MockRouter, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import opencode_client.client as client_module

        monkeypatch.setattr(client_module.time, "sleep", _no_sleep)
        route = mock_server.get("/global/health")
        route.side_effect = [httpx.ReadTimeout("slow"), _healthy()]
        with OpenCodeClient(BASE, max_retries=1) as client:
            client.server.health()
        assert route.calls.call_count == 2


class TestAsyncRetryMirrors:
    """Same behaviour through ``AsyncOpenCodeClient``."""

    async def test_429_exhausted_raises_rate_limit_error(
        self, mock_server: respx.MockRouter, client: AsyncOpenCodeClient
    ) -> None:
        mock_server.get("/global/health").mock(
            return_value=httpx.Response(429, headers={"Retry-After": "0"}, json={"name": "Too Many Requests"})
        )
        with pytest.raises(OpenCodeRateLimitError) as excinfo:
            await client.server.health()
        assert excinfo.value.status_code == 429
        assert mock_server.get("/global/health").calls.call_count == 3

    async def test_5xx_retries_then_succeeds(self, mock_server: respx.MockRouter) -> None:
        route = mock_server.get("/global/health")
        route.side_effect = [_unavailable(), _healthy()]
        async with AsyncOpenCodeClient(BASE, max_retries=1) as client:
            assert (await client.server.health()).version == "1.2.3"
        assert route.calls.call_count == 2

    async def test_5xx_exhausted_raises_server_error(self, mock_server: respx.MockRouter) -> None:
        mock_server.get("/global/health").mock(return_value=_unavailable())
        async with AsyncOpenCodeClient(BASE, max_retries=1) as client:
            with pytest.raises(OpenCodeServerError):
                await client.server.health()
        assert mock_server.get("/global/health").calls.call_count == 2

    async def test_non_retryable_404_raises_immediately(
        self, mock_server: respx.MockRouter, client: AsyncOpenCodeClient
    ) -> None:
        mock_server.get("/session/ses_missing").mock(
            return_value=httpx.Response(404, json={"name": "NotFound", "data": {"message": "nope"}})
        )
        from opencode_client import OpenCodeNotFoundError

        with pytest.raises(OpenCodeNotFoundError):
            await client.sessions.get("ses_missing")
        assert mock_server.get("/session/ses_missing").calls.call_count == 1

    async def test_connection_error_wrapped(self, mock_server: respx.MockRouter) -> None:
        mock_server.get("/global/health").mock(side_effect=httpx.ConnectError("gone"))
        async with AsyncOpenCodeClient(BASE, max_retries=0) as client:
            with pytest.raises(OpenCodeServerConnectionError):
                await client.server.health()

    async def test_timeout_error_mapped(self, mock_server: respx.MockRouter) -> None:
        mock_server.get("/global/health").mock(side_effect=httpx.ReadTimeout("slow"))
        async with AsyncOpenCodeClient(BASE, max_retries=0) as client:
            with pytest.raises(OpenCodeTimeoutError):
                await client.server.health()

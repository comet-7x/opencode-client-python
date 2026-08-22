"""Integration tests against a real, running opencode server.

The only tests in the suite that touch the network. They run only when a
server is reachable: ``pytest --live-url http://127.0.0.1:4096`` (optionally
``--live-password <pw>``). Without the flag the probe fixture skips, so the
default run stays offline and hermetic.
"""

from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import Generator
from contextlib import suppress
from typing import Any

import httpx
import pytest

from opencode_client import (
    AsyncOpenCodeClient,
    CreateSessionRequest,
    OpenCodeClient,
    UpdateSessionRequest,
)

LIVE_TITLE = "it-008 live stream probe"


def _no_sleep(seconds: float) -> None:
    """Collapse the backoff so the poisoned-transport retry test runs instantly."""


@pytest.fixture(scope="module")
def live_server(request: pytest.FixtureRequest) -> Generator[dict[str, Any], None, None]:
    """Probe the live server once per module; yield client kwargs when it answers.

    Skips the whole module when no ``--live-url`` is given or the probe fails.
    """
    url = request.config.getoption("live_url")
    if not url:
        pytest.skip("no --live-url given; point it at a running opencode server")
    try:
        probe = httpx.get(f"{url}/global/health", timeout=5.0)
    except httpx.HTTPError as exc:
        pytest.skip(f"live server at {url} is not reachable: {exc}")
    if probe.status_code != 200:
        pytest.skip(f"live server at {url} unhealthy (HTTP {probe.status_code})")
    kwargs: dict[str, Any] = {"base_url": url, "timeout": 15.0, "max_retries": 2}
    password = request.config.getoption("live_password")
    if password:
        kwargs["password"] = password
    yield kwargs


class TestLiveSync:
    def test_health(self, live_server: dict[str, Any]) -> None:
        with OpenCodeClient(**live_server) as client:
            assert client.server.health().healthy is True

    def test_session_lifecycle(self, live_server: dict[str, Any]) -> None:
        with OpenCodeClient(**live_server) as client:
            session = client.sessions.create(body=CreateSessionRequest(title="it-008 live smoke"))
            try:
                assert client.sessions.get(session.id).id == session.id
                assert client.sessions.update(session.id, body=UpdateSessionRequest(title="renamed")).title == "renamed"
                assert session.id in [s.id for s in client.sessions.list_sessions()]
            finally:
                assert client.sessions.delete(session.id) is True

    def test_stream_watches_live_session_events(self, live_server: dict[str, Any]) -> None:
        """The auto-reconnecting stream picks up a session created after it attached."""
        with OpenCodeClient(**live_server) as client:
            received: list[str] = []
            matched = threading.Event()

            def watch() -> None:
                with client.server.stream_events() as stream:
                    for event in stream.iter_events():
                        received.append(event.type)
                        raw: dict[str, Any] | None = event.properties.get("info")
                        if raw is not None and raw.get("title") == LIVE_TITLE:
                            matched.set()
                            return

            thread = threading.Thread(target=watch, daemon=True)
            thread.start()
            time.sleep(1.0)  # let the stream attach before the session is created
            session = client.sessions.create(body=CreateSessionRequest(title=LIVE_TITLE))
            try:
                thread.join(timeout=20)
            finally:
                with suppress(Exception):
                    client.sessions.delete(session.id)
            assert not thread.is_alive(), "stream watch did not terminate in time"
        assert matched.is_set(), f"no {LIVE_TITLE!r} event observed among {received[:20]}..."
        assert "session.created" in received

    def test_retries_over_real_transport(self, live_server: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
        """The first /global/health call is poisoned with a 503; the retry must reach the server."""
        import opencode_client.client as client_module

        monkeypatch.setattr(client_module.time, "sleep", _no_sleep)
        with OpenCodeClient(**live_server) as client:
            real_request = client.http.request
            state = {"poisoned": False}
            request = client.http.build_request("GET", "/global/health")

            def flaky(method: str, path: str, **kwargs: Any) -> httpx.Response:
                if not state["poisoned"] and path == "/global/health":
                    state["poisoned"] = True
                    return httpx.Response(503, json={"name": "injected"}, request=request)
                return real_request(method, path, **kwargs)

            client.http.request = flaky  # type: ignore[assignment]
            assert client.server.health().healthy is True

        assert state["poisoned"] is True  # the retry really took a second attempt


class TestLiveAsync:
    async def test_health_and_stream(self, live_server: dict[str, Any]) -> None:
        async with AsyncOpenCodeClient(**live_server) as client:
            assert (await client.server.health()).healthy is True
            seen: list[str] = []
            matched = asyncio.Event()

            async def watch() -> None:
                """Match the ``session.created`` event for the probe session by title."""
                async with client.server.stream_events() as stream:
                    async for event in stream.aiter_events():
                        seen.append(event.type)
                        raw: dict[str, Any] | None = event.properties.get("info")
                        if event.type == "session.created" and raw is not None and raw.get("title") == LIVE_TITLE:
                            matched.set()
                            return

            listener = asyncio.create_task(watch())
            await asyncio.sleep(1.0)  # let the stream attach before the session is created
            session = await client.sessions.create(body=CreateSessionRequest(title=LIVE_TITLE))
            try:
                await asyncio.wait_for(matched.wait(), timeout=20)
            finally:
                await client.sessions.delete(session.id)
                with suppress(Exception):
                    await listener
            assert "session.created" in seen

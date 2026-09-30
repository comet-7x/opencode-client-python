"""Automatic reconnection of the ``/event`` SSE stream (sync + async).

The reconnect machinery is driven over scripted fake transports — respx
cannot express a mid-stream drop (it consumes side-effect bodies at
route-resolution time) — so every path is covered deterministically.

Script entries, one per connection attempt:

- an ``httpx.HTTPError`` → establishing the connection fails;
- a body ending in an error → the lines are served until the body's error
  fires mid-iteration (a dropped connection — triggers reconnection);
- a plain list of lines → served, then a clean close (EOF — ends the
  iteration, no reconnection).
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Generator, Iterator
from typing import Any, cast

import httpx
import pytest
import respx

from opencode_client import (
    AsyncEventStream,
    AsyncOpenCodeClient,
    Event,
    EventStream,
    OpenCodeClient,
    OpenCodeServerConnectionError,
    OpenCodeTimeoutError,
    OpenCodeTransportError,
)
from opencode_client import sse as sse_module

BASE = "http://opencode.test"

# One scripted connection body: SSE lines (no line endings, httpx strips them),
# optionally terminated by a transport error that fires mid-iteration.
Body = list[str | httpx.HTTPError]
Script = list[Body | httpx.HTTPError]


def _frame(type_: str, **props: Any) -> str:
    """The single ``data:`` line of one JSON event frame."""
    return f"data: {json.dumps({'type': type_, 'properties': props})}"


def _body(type_: str, **props: Any) -> Body:
    """A complete frame: data line + terminating blank line."""
    return [_frame(type_, **props), ""]


def _drop(error: httpx.HTTPError, *frames: Body) -> Body:
    """Serve the framed bodies, then drop the connection with ``error``."""
    lines: Body = []
    for frame in frames:
        lines.extend(frame)
    lines.append(error)
    return lines


class FakeResponse:
    """One scripted ``/event`` connection."""

    def __init__(self, lines: Body) -> None:
        self._lines = lines
        self.closed = False

    def iter_lines(self) -> Iterator[str]:
        for item in self._lines:
            if isinstance(item, httpx.HTTPError):
                raise item
            yield item

    async def aiter_lines(self) -> AsyncIterator[str]:
        for item in self._lines:
            if isinstance(item, httpx.HTTPError):
                raise item
            yield item

    def close(self) -> None:
        self.closed = True

    async def aclose(self) -> None:
        self.closed = True


class _FakeBase:
    """Shared script playback: ``open_count`` connections, last one tracked."""

    def __init__(self, script: Script) -> None:
        self._script = script
        self.current: FakeResponse | None = None
        self.open_count = 0

    def _next(self) -> FakeResponse:
        self.open_count += 1
        entry = self._script[self.open_count - 1]
        if not isinstance(entry, list):
            self.current = None
            raise entry
        response = FakeResponse(entry)
        self.current = response
        return response


class SyncFakes(_FakeBase):
    """``httpx.Client``-shaped fake: blocking ``send(request, stream=...)``."""

    def send(self, request: httpx.Request, *, stream: bool) -> FakeResponse:
        if not stream:
            raise AssertionError("streaming must be requested")
        return self._next()


class AsyncFakes(_FakeBase):
    """``httpx.AsyncClient``-shaped fake: awaiting ``send(request, stream=...)``."""

    async def send(self, request: httpx.Request, *, stream: bool) -> FakeResponse:
        if not stream:
            raise AssertionError("streaming must be requested")
        return self._next()


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Collapse reconnect backoffs to zero; individual tests re-wrap with a spy."""

    def _zero(attempt: int) -> float:
        return 0.0

    monkeypatch.setattr(sse_module, "_reconnect_delay", _zero)


@pytest.fixture
def event_request() -> httpx.Request:
    return httpx.Request("GET", f"{BASE}/event")


async def _collect(stream: AsyncEventStream) -> list[Event]:
    return [event async for event in stream.aiter_events()]


class TestSyncReconnect:
    def test_mid_stream_drop_reconnects(self, event_request: httpx.Request) -> None:
        fakes = SyncFakes([_drop(httpx.ReadError("reset"), _body("first")), _body("second")])
        with EventStream(cast("httpx.Client", fakes), event_request) as stream:
            events = list(stream.iter_events())
        assert [e.type for e in events] == ["first", "second"]
        assert fakes.open_count == 2
        assert fakes.current is not None and fakes.current.closed is True

    def test_budget_zero_raises_on_first_drop(self, event_request: httpx.Request) -> None:
        fakes = SyncFakes([_drop(httpx.ReadError("reset"), _body("first"))])
        with pytest.raises(OpenCodeServerConnectionError) as excinfo:
            with EventStream(cast("httpx.Client", fakes), event_request, max_reconnect_attempts=0) as stream:
                list(stream.iter_events())
        assert excinfo.value.__cause__ is not None
        assert fakes.open_count == 1

    def test_error_exhausted_raises_wrapped_error(self, event_request: httpx.Request) -> None:
        fakes = SyncFakes([_drop(httpx.ReadError("reset"), _body("first")), _drop(httpx.ConnectError("gone"))])
        with pytest.raises(OpenCodeServerConnectionError) as excinfo:
            with EventStream(cast("httpx.Client", fakes), event_request, max_reconnect_attempts=1) as stream:
                list(stream.iter_events())
        assert isinstance(excinfo.value.__cause__, httpx.ConnectError)
        assert fakes.open_count == 2

    def test_timeout_error_maps_to_timeout_subclass(self, event_request: httpx.Request) -> None:
        fakes = SyncFakes([_drop(httpx.ReadTimeout("slow"))])
        with pytest.raises(OpenCodeTimeoutError):
            with EventStream(cast("httpx.Client", fakes), event_request, max_reconnect_attempts=0) as stream:
                list(stream.iter_events())

    def test_connect_failure_wrapped_in_enter(self, event_request: httpx.Request) -> None:
        fakes = SyncFakes([httpx.ConnectError("refused")])
        stream = EventStream(cast("httpx.Client", fakes), event_request)
        with pytest.raises(OpenCodeServerConnectionError):
            stream.__enter__()
        with pytest.raises(RuntimeError):
            stream.iter_lines()

    def test_connect_timeout_wrapped_in_enter(self, event_request: httpx.Request) -> None:
        fakes = SyncFakes([httpx.ConnectTimeout("slow")])
        with pytest.raises(OpenCodeTimeoutError):
            with EventStream(cast("httpx.Client", fakes), event_request):
                pass

    def test_clean_eof_ends_iteration_without_reconnect(self, event_request: httpx.Request) -> None:
        fakes = SyncFakes([_body("a"), [], []])
        with EventStream(cast("httpx.Client", fakes), event_request, max_reconnect_attempts=3) as stream:
            events = list(stream.iter_events())
        assert [e.type for e in events] == ["a"]
        assert fakes.open_count == 1  # never reconnects after a clean close
        assert fakes.current is not None and fakes.current.closed is True

    def test_clean_eof_flushes_leftover_partial_frame(self, event_request: httpx.Request) -> None:
        # Data line without a terminating blank at EOF: emitted on close.
        fakes = SyncFakes([[_frame("tail")]])
        with EventStream(cast("httpx.Client", fakes), event_request) as stream:
            events = list(stream.iter_events())
        assert [e.type for e in events] == ["tail"]

    def test_drop_discards_partial_frame_in_flight(self, event_request: httpx.Request) -> None:
        # The half-frame on the dying connection is dropped, not spliced with
        # the next connection; the reconnected connection delivers its own.
        fakes = SyncFakes([[_frame("split"), httpx.ReadError("reset")], _body("after")])
        with EventStream(cast("httpx.Client", fakes), event_request) as stream:
            events = list(stream.iter_events())
        assert [e.type for e in events] == ["after"]
        assert fakes.open_count == 2

    def test_backoff_schedule_and_budget_reset(
        self, event_request: httpx.Request, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        delays: list[float] = []

        def spy(attempt: int) -> float:
            delays.append(min(0.5 * (2.0 ** (attempt - 1)), 8.0))
            return 0.0

        monkeypatch.setattr(sse_module, "_reconnect_delay", spy)
        # a and b drop after their line (budget resets to attempt 1 each time),
        # then a clean EOF ends the stream.
        script: Script = [
            _drop(httpx.ReadError("r"), _body("a")),
            _drop(httpx.ReadError("r"), _body("b")),
            [],
        ]
        fakes = SyncFakes(script)
        with EventStream(cast("httpx.Client", fakes), event_request, max_reconnect_attempts=3) as stream:
            events = list(stream.iter_events())
        assert [e.type for e in events] == ["a", "b"]
        assert delays == [0.5, 0.5]
        assert fakes.open_count == 3

    def test_exit_closes_connection_when_iteration_raises(self, event_request: httpx.Request) -> None:
        fakes = SyncFakes([_drop(httpx.ReadError("reset"), _body("a"))])
        with pytest.raises(OpenCodeTransportError):
            with EventStream(cast("httpx.Client", fakes), event_request, max_reconnect_attempts=0) as stream:
                iterator = stream.iter_events()
                next(iterator)  # the "a" event
                next(iterator)  # resumes into the drop
        assert fakes.current is not None and fakes.current.closed is True


class TestAsyncReconnect:
    async def test_mid_stream_drop_reconnects(self, event_request: httpx.Request) -> None:
        fakes = AsyncFakes([_drop(httpx.ReadError("reset"), _body("first")), _body("second")])
        async with AsyncEventStream(cast("httpx.AsyncClient", fakes), event_request) as stream:
            events = await _collect(stream)
        assert [e.type for e in events] == ["first", "second"]
        assert fakes.open_count == 2
        assert fakes.current is not None and fakes.current.closed is True

    async def test_budget_zero_raises_on_first_drop(self, event_request: httpx.Request) -> None:
        fakes = AsyncFakes([_drop(httpx.ReadError("reset"), _body("first"))])
        with pytest.raises(OpenCodeServerConnectionError):
            async with AsyncEventStream(
                cast("httpx.AsyncClient", fakes), event_request, max_reconnect_attempts=0
            ) as stream:
                await _collect(stream)
        assert fakes.open_count == 1

    async def test_error_exhausted_raises_wrapped_error(self, event_request: httpx.Request) -> None:
        fakes = AsyncFakes([_drop(httpx.ReadError("reset"), _body("first")), _drop(httpx.ConnectError("gone"))])
        with pytest.raises(OpenCodeServerConnectionError):
            async with AsyncEventStream(
                cast("httpx.AsyncClient", fakes), event_request, max_reconnect_attempts=1
            ) as stream:
                await _collect(stream)
        assert fakes.open_count == 2

    async def test_connect_failure_wrapped_in_aenter(self, event_request: httpx.Request) -> None:
        fakes = AsyncFakes([httpx.ConnectError("refused")])
        with pytest.raises(OpenCodeServerConnectionError):
            async with AsyncEventStream(cast("httpx.AsyncClient", fakes), event_request):
                pass
        assert fakes.current is None

    async def test_connect_timeout_wrapped_in_aenter(self, event_request: httpx.Request) -> None:
        fakes = AsyncFakes([httpx.ConnectTimeout("slow")])
        with pytest.raises(OpenCodeTimeoutError):
            async with AsyncEventStream(cast("httpx.AsyncClient", fakes), event_request):
                pass

    async def test_clean_eof_ends_iteration_without_reconnect(self, event_request: httpx.Request) -> None:
        fakes = AsyncFakes([_body("a"), [], []])
        async with AsyncEventStream(
            cast("httpx.AsyncClient", fakes), event_request, max_reconnect_attempts=3
        ) as stream:
            events = await _collect(stream)
        assert [e.type for e in events] == ["a"]
        assert fakes.open_count == 1

    async def test_drop_discards_partial_frame_in_flight(self, event_request: httpx.Request) -> None:
        fakes = AsyncFakes([[_frame("split"), httpx.ReadError("reset")], _body("after")])
        async with AsyncEventStream(cast("httpx.AsyncClient", fakes), event_request) as stream:
            events = await _collect(stream)
        assert [e.type for e in events] == ["after"]
        assert fakes.open_count == 2

    async def test_exit_closes_connection_when_iteration_raises(self, event_request: httpx.Request) -> None:
        fakes = AsyncFakes([_drop(httpx.ReadError("reset"), _body("a"))])
        with pytest.raises(OpenCodeTransportError):
            async with AsyncEventStream(
                cast("httpx.AsyncClient", fakes), event_request, max_reconnect_attempts=0
            ) as stream:
                iterator = stream.aiter_events()
                await iterator.__anext__()  # the "a" event
                await iterator.__anext__()  # resumes into the drop
        assert fakes.current is not None and fakes.current.closed is True


class TestResourceFactory:
    """The resource entry point wires the stream through to respx-able transports."""

    def test_sync_stream_events_consumes_via_iter_events(self, mock_server: respx.MockRouter) -> None:
        body = b"data: " + json.dumps({"type": "a", "properties": {}}).encode() + b"\n\n"
        mock_server.get("/event").mock(
            return_value=httpx.Response(200, headers={"Content-Type": "text/event-stream"}, content=body)
        )
        with OpenCodeClient(BASE) as client:
            stream = client.server.stream_events(max_reconnect_attempts=1)
            assert isinstance(stream, EventStream)
            with stream:
                events = list(stream.iter_events())
        assert [e.type for e in events] == ["a"]
        assert stream.connections_opened == 1

    async def test_async_stream_events_consumes_via_aiter_events(self, mock_server: respx.MockRouter) -> None:
        body = b"data: " + json.dumps({"type": "a", "properties": {}}).encode() + b"\n\n"
        mock_server.get("/event").mock(
            return_value=httpx.Response(200, headers={"Content-Type": "text/event-stream"}, content=body)
        )
        async with AsyncOpenCodeClient(BASE) as client:
            stream = client.server.stream_events(max_reconnect_attempts=1)
            assert isinstance(stream, AsyncEventStream)
            async with stream:
                events = await _collect(stream)
        assert [e.type for e in events] == ["a"]
        assert stream.connections_opened == 1


@pytest.fixture(autouse=True)
def mock_server() -> Generator[respx.MockRouter, None, None]:
    with respx.mock(base_url=BASE) as router:
        yield router

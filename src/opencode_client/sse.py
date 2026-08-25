"""Server-Sent Events (SSE) helpers.

Classes in this module:

- :class:`SSEDecoder` — a WHATWG ``text/event-stream`` line decoder;
- :class:`AsyncEventStream` — **async** context manager that keeps the long-lived
  ``GET /event`` connection open, with automatic reconnection;
- :class:`EventStream` — the synchronous equivalent.

Reconnection
------------

``/event`` is a long-lived connection and transient drops are a normal
event (server restart, network blip).  Both stream classes therefore
reconnect automatically: when body iteration ends with a *transport error*
the stream pauses with exponential backoff (0.5s … 8s cap), re-sends the
same request, and continues.  Reconnections are bounded by
``max_reconnect_attempts``; **any line received resets the budget**, so a
healthy stream may reconnect indefinitely.  A *clean* close ends the
iteration instead: the server finished sending and nothing more will arrive.

When the budget is exhausted, the failing transport error is re-raised
(wrapped into an :class:`~opencode_client.OpenCodeTransportError` subclass).
A partial frame in flight when a connection drops is discarded — the
opencode server does not replay events, so splicing a half-frame from the
next connection would be silently wrong.

Consuming events needs no manual glue: iterate ``stream.iter_events()``
(sync) or ``stream.aiter_events()`` (async), which wrap the decoder around
the reconnection machinery.  The raw ``iter_lines()`` / ``aiter_lines()``
accessors are still available — they proxy the *current* connection
without reconnecting and are for advanced use only.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator, Iterator
from contextlib import suppress
from types import TracebackType
from typing import Any

import httpx
from pydantic import ValidationError

from .constants import DEFAULT_STREAM_RECONNECT_ATTEMPTS
from .errors import make_transport_error
from .models import Event, typed_event
from .router import AsyncEventRouter, EventRouter


def _reconnect_delay(attempt: int) -> float:
    """Seconds to wait before reconnect attempt ``attempt`` (1-based).

    Exponential backoff: 0.5s, 1s, 2s ... capped at 8s (mirrors the
    request-level retry schedule, kept apart so streams can evolve
    independently).
    """
    return min(0.5 * (2.0 ** (attempt - 1)), 8.0)


class SSEDecoder:
    r"""Incremental SSE decoder conforming to the WHATWG event-stream spec.

    Feed raw lines (from ``httpx.Response.iter_lines()`` / ``aiter_lines()``
    or a file) into :meth:`decode_line`, :meth:`iter_events` or
    :meth:`aiter_events`.

    Behaviour per spec:

    - ``data:`` lines are accumulated; multiple data lines are joined with ``\\n``;
    - ``event:`` lines are collected but the server payload is self-describing
      (``{"type": ..., "properties": ...}``), so only data is parsed;
    - blank lines dispatch the pending event;
    - comment lines (starting with ``:``) are ignored;
    - if the stream ends without a trailing blank line, the pending event is
      flushed on EOF (see :meth:`flush`).
    """

    def __init__(self) -> None:
        self._data: list[str] = []

    def _take_event(self) -> Event | None:
        """Build and clear the pending event, or return ``None`` if nothing is pending.

        Known hot types are upgraded to their typed event subclass (see
        :func:`opencode_client.models.typed_event`); unknown types and
        payloads that no longer validate degrade to the base
        :class:`~opencode_client.models.Event`.
        """
        if not self._data:
            return None
        data = "\n".join(self._data)
        self._data.clear()
        try:
            raw: dict[str, Any] = json.loads(data)
        except ValueError:
            raw = {"type": "message", "properties": {"raw": data}}
        try:
            return typed_event(raw)
        except ValidationError:
            # Frames outside the instance envelope (e.g. /global/event's
            # GlobalEvent wrapper) degrade instead of breaking the stream;
            # the raw document is preserved under properties["raw"].
            return Event(type="unknown", properties={"raw": raw})

    def flush(self) -> Event | None:
        """Dispatch a pending event left without its trailing blank line.

        For callers driving :meth:`decode_line` manually over a stream that
        may end mid-event.
        """
        return self._take_event()

    def clear(self) -> None:
        """Discard the accumulated partial event without emitting it."""
        self._data.clear()

    def decode_line(self, line: str) -> Event | None:
        """Feed one raw line; an event is returned only on a blank-line boundary."""
        if not line:
            return self._take_event()
        if line.startswith(":"):
            return None
        if line.startswith("data:"):
            self._data.append(line[5:].removeprefix(" "))
        return None

    def iter_events(self, lines: Iterator[str]) -> Iterator[Event]:
        """Decode a synchronous line iterator, flushing a trailing partial event."""
        for line in lines:
            event = self.decode_line(line.rstrip("\r"))
            if event is not None:
                yield event
        final = self.flush()
        if final is not None:
            yield final

    async def aiter_events(self, lines: AsyncIterator[str]) -> AsyncIterator[Event]:
        """Decode an asynchronous line iterator, flushing a trailing partial event."""
        async for line in lines:
            event = self.decode_line(line.rstrip("\r"))
            if event is not None:
                yield event
        final = self.flush()
        if final is not None:
            yield final


class AsyncEventStream:
    """Async context manager wrapping the ``/event`` SSE stream with auto-reconnect.

    Usage::

        async with client.server.stream_events() as stream:
            async for event in stream.aiter_events():
                print(event.type)

    The underlying HTTP request is opened on ``__aenter__`` (a failure
    there is wrapped into an
    :class:`~opencode_client.OpenCodeTransportError` subclass) and always
    released on ``__aexit__``, even when the body iteration raised.  A drop
    mid-iteration triggers a reconnect; see the module docstring.

    Args:
        client: The owning transport the streaming request is sent on.
        request: The prebuilt ``GET /event`` request (query params included).
        max_reconnect_attempts: How many reconnects to attempt after a drop
            before giving up; ``None`` uses the package default
            (:data:`~opencode_client.constants.DEFAULT_STREAM_RECONNECT_ATTEMPTS`).
    """

    def __init__(
        self,
        client: httpx.AsyncClient,
        request: httpx.Request,
        max_reconnect_attempts: int | None = None,
    ) -> None:
        self._client = client
        self._request = request
        self._reconnect_budget = (
            DEFAULT_STREAM_RECONNECT_ATTEMPTS if max_reconnect_attempts is None else max_reconnect_attempts
        )
        self._response: httpx.Response | None = None
        self._reconnects_used = 0
        self._connections_opened = 0

    async def __aenter__(self) -> AsyncEventStream:
        """Open the streaming connection; a failure raises a wrapped transport error."""
        try:
            await self._open()
        except httpx.HTTPError as exc:
            await self._release()
            raise make_transport_error(exc) from exc
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Release the streaming connection, if one is open."""
        await self._release()

    @property
    def response(self) -> httpx.Response | None:
        """The currently open HTTP response, or ``None`` when disconnected."""
        return self._response

    @property
    def connections_opened(self) -> int:
        """How many ``/event`` connections were established (initial + reconnects)."""
        return self._connections_opened

    def route(self, session_id: str | None = None) -> AsyncEventRouter:
        """Create a subscription router over this stream.

        The returned :class:`~opencode_client.router.AsyncEventRouter`
        dispatches decoded events to handlers by type; see its docstring
        for the run/stop semantics.  When ``session_id`` is given, only
        events for that session are dispatched.

        Args:
            session_id: Restrict dispatch to this session's events.
        """
        return AsyncEventRouter(self, session_id=session_id)

    def aiter_lines(self) -> AsyncIterator[str]:
        """Yield raw lines from the *current* connection.

        Advanced use: this does **not** reconnect; for transparent
        reconnection iterate :meth:`aiter_events` instead.
        """
        response = self._response
        if response is None:
            raise RuntimeError("AsyncEventStream is not open")
        return response.aiter_lines()

    async def aiter_events(self) -> AsyncIterator[Event]:
        """Yield decoded events, reconnecting transparently after drops.

        Reconnects (with backoff) while reconnects remain in the budget;
        any line received resets the budget.  A transport error after the
        budget is exhausted raises a wrapped
        :class:`~opencode_client.OpenCodeTransportError` subclass.  A clean
        close ends the iteration (emitting a leftover partial frame).
        """
        decoder = SSEDecoder()
        while True:
            response = self._response
            if response is None:
                break
            try:
                async for line in response.aiter_lines():
                    self._reconnects_used = 0
                    event = decoder.decode_line(line.rstrip("\r"))
                    if event is not None:
                        yield event
            except httpx.HTTPError as exc:
                decoder.clear()
                await self._reconnect_or(exc)
            else:
                final = decoder.flush()
                if final is not None:
                    yield final
                break

    async def _open(self) -> None:
        """Open (or re-open) the streaming connection on the own transport."""
        self._response = await self._client.send(self._request, stream=True)
        self._connections_opened += 1

    async def _release(self) -> None:
        """Close the open response (if any); never raises."""
        if self._response is not None:
            with suppress(Exception):
                await self._response.aclose()
            self._response = None

    async def _reconnect_or(self, exc: httpx.HTTPError) -> None:
        """After a dropped body: reconnect within budget or re-raise ``exc``."""
        self._reconnects_used += 1
        if self._reconnects_used > self._reconnect_budget:
            raise make_transport_error(exc) from exc
        await asyncio.sleep(_reconnect_delay(self._reconnects_used))
        await self._reopen()

    async def _reopen(self) -> None:
        """Re-send the request; a failure raises a wrapped transport error."""
        try:
            await self._open()
        except httpx.HTTPError as exc:
            raise make_transport_error(exc) from exc


class EventStream:
    """Synchronous context manager wrapping the ``/event`` SSE stream with auto-reconnect.

    Usage::

        with client.server.stream_events() as stream:
            for event in stream.iter_events():
                print(event.type)

    Behaves exactly like :class:`AsyncEventStream` (same reconnection policy);
    the blocking equivalent of every operation.

    Args:
        client: The owning transport the streaming request is sent on.
        request: The prebuilt ``GET /event`` request (query params included).
        max_reconnect_attempts: How many reconnects to attempt after a drop
            before giving up; ``None`` uses the package default
            (:data:`~opencode_client.constants.DEFAULT_STREAM_RECONNECT_ATTEMPTS`).
    """

    def __init__(
        self,
        client: httpx.Client,
        request: httpx.Request,
        max_reconnect_attempts: int | None = None,
    ) -> None:
        self._client = client
        self._request = request
        self._reconnect_budget = (
            DEFAULT_STREAM_RECONNECT_ATTEMPTS if max_reconnect_attempts is None else max_reconnect_attempts
        )
        self._response: httpx.Response | None = None
        self._reconnects_used = 0
        self._connections_opened = 0

    def __enter__(self) -> EventStream:
        """Open the streaming connection; a failure raises a wrapped transport error."""
        try:
            self._open()
        except httpx.HTTPError as exc:
            self._release()
            raise make_transport_error(exc) from exc
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Release the streaming connection, if one is open."""
        self._release()

    @property
    def response(self) -> httpx.Response | None:
        """The currently open HTTP response, or ``None`` when disconnected."""
        return self._response

    @property
    def connections_opened(self) -> int:
        """How many ``/event`` connections were established (initial + reconnects)."""
        return self._connections_opened

    def route(self, session_id: str | None = None) -> EventRouter:
        """Create a subscription router over this stream.

        The returned :class:`~opencode_client.router.EventRouter`
        dispatches decoded events to handlers by type; see its docstring
        for the run/stop semantics.  When ``session_id`` is given, only
        events for that session are dispatched.

        Args:
            session_id: Restrict dispatch to this session's events.
        """
        return EventRouter(self, session_id=session_id)

    def iter_lines(self) -> Iterator[str]:
        """Yield raw lines from the *current* connection.

        Advanced use: this does **not** reconnect; for transparent
        reconnection iterate :meth:`iter_events` instead.
        """
        response = self._response
        if response is None:
            raise RuntimeError("EventStream is not open")
        return response.iter_lines()

    def iter_events(self) -> Iterator[Event]:
        """Yield decoded events, reconnecting transparently after drops.

        Reconnects (with backoff) while reconnects remain in the budget;
        any line received resets the budget.  A transport error after the
        budget is exhausted raises a wrapped
        :class:`~opencode_client.OpenCodeTransportError` subclass.  A clean
        close ends the iteration (emitting a leftover partial frame).
        """
        decoder = SSEDecoder()
        while True:
            response = self._response
            if response is None:
                break
            try:
                for line in response.iter_lines():
                    self._reconnects_used = 0
                    event = decoder.decode_line(line.rstrip("\r"))
                    if event is not None:
                        yield event
            except httpx.HTTPError as exc:
                decoder.clear()
                self._reconnect_or(exc)
            else:
                final = decoder.flush()
                if final is not None:
                    yield final
                break

    def _open(self) -> None:
        """Open (or re-open) the streaming connection on the own transport."""
        self._response = self._client.send(self._request, stream=True)
        self._connections_opened += 1

    def _release(self) -> None:
        """Close the open response (if any); never raises."""
        if self._response is not None:
            with suppress(Exception):
                self._response.close()
            self._response = None

    def _reconnect_or(self, exc: httpx.HTTPError) -> None:
        """After a dropped body: reconnect within budget or re-raise ``exc``."""
        self._reconnects_used += 1
        if self._reconnects_used > self._reconnect_budget:
            raise make_transport_error(exc) from exc
        time.sleep(_reconnect_delay(self._reconnects_used))
        self._reopen()

    def _reopen(self) -> None:
        """Re-send the request; a failure raises a wrapped transport error."""
        try:
            self._open()
        except httpx.HTTPError as exc:
            raise make_transport_error(exc) from exc

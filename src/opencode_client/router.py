"""Event routing: subscribe to the ``/event`` stream by event type.

Builds on :mod:`opencode_client.sse` (transport, reconnection, decoding) and
:mod:`opencode_client.models.event` (typed payloads): a single reader loop
pulls events off the stream and dispatches them, in arrival order, to every
handler subscribed to their type.  Subscribing by type string (or
:class:`~opencode_client.EventType`) is all a consumer writes — payload
upgrading, session filtering and teardown live here, not in user code::

    async with client.server.stream_events() as stream:
        bus = stream.route(session.id)
        bus.on("message.part.delta", print_delta)
        bus.on("message.part.updated", on_part)
        await bus.run(until="session.idle", timeout=300)

:class:`AsyncEventRouter` (async) wraps an
:class:`~opencode_client.sse.AsyncEventStream`;
:class:`EventRouter` (sync) wraps a
:class:`~opencode_client.sse.EventStream`.
"""

from __future__ import annotations

import asyncio
import inspect
import threading
from collections.abc import Callable
from contextlib import suppress
from typing import Any

from .models import Event, EventType

__all__ = ["AsyncEventRouter", "EventRouter"]

Handler = Callable[[Event], Any]


def _matches(subscription: EventType | str, event: Event) -> bool:
    """Whether a subscription matches an event (enum members equal their raw value)."""
    return event.type == subscription


def _event_session_id(event: Event) -> str | None:
    """The session an event belongs to, or ``None`` for server-level events.

    Typed hot events hoist ``session_id`` from the wire; the base envelope
    carries it under ``properties["sessionID"]``.  Both sources agree in
    normal operation; the hoisted field is checked first so programmatically
    built typed events still filter correctly.
    """
    return getattr(event, "session_id", None) or event.properties.get("sessionID")


class AsyncEventRouter:
    """Async subscription router over an :class:`~opencode_client.sse.AsyncEventStream`.

    Subscribe with :meth:`on`, then run the single reader loop with
    :meth:`run`.  Handlers run sequentially in arrival order — a slow
    handler stalls the others (there is deliberately no concurrency).  A
    handler that raises stops the run and the error propagates.

    Args:
        stream: The open event stream to read from.
        session_id: When given, only events whose payload carries this
            ``sessionID`` are dispatched (others are dropped).
    """

    def __init__(self, stream: Any, *, session_id: str | None = None) -> None:
        self._stream = stream
        self._session_id = session_id
        self._handlers: list[tuple[EventType | str, Handler]] = []

    @property
    def session_id(self) -> str | None:
        """The session this router is scoped to, if any."""
        return self._session_id

    def on(self, event_type: EventType | str, handler: Handler) -> None:
        """Subscribe ``handler`` to one event type.

        Handlers may be sync or async callables.  Several subscriptions may
        target the same type; they run in subscription order.
        """
        self._handlers.append((event_type, handler))

    async def run(
        self,
        *,
        until: EventType | str | None = None,
        timeout: float | None = None,
    ) -> None:
        """Run the reader loop until a stop condition fires.

        Stop conditions, in order of precedence: a handler raises (the
        error propagates), an event of type ``until`` is dispatched, the
        stream ends cleanly, or ``timeout`` seconds elapse (raises
        :class:`asyncio.TimeoutError`).  The event stream is left open —
        closing it is the stream context manager's job.

        Args:
            until: Event type that ends the run, after its handlers ran.
            timeout: Overall wall-clock budget for the run.
        """
        iterator = self._stream.aiter_events()
        body = self._run(iterator, until)
        try:
            if timeout is None:
                await body
            else:
                await asyncio.wait_for(body, timeout)
        finally:
            with suppress(Exception, BaseException):
                await iterator.aclose()

    async def _run(self, iterator: Any, until: EventType | str | None) -> None:
        """Consume events until ``until`` matches or the stream ends cleanly."""
        while True:
            try:
                event: Event = await iterator.__anext__()
            except StopAsyncIteration:
                return
            await self._dispatch(event)
            if until is not None and _matches(until, event):
                return

    async def _dispatch(self, event: Event) -> None:
        """Run every matching handler in subscription order."""
        if self._session_id is not None and _event_session_id(event) != self._session_id:
            return
        for event_type, handler in self._handlers:
            if _matches(event_type, event):
                result = handler(event)
                if inspect.isawaitable(result):
                    await result


class EventRouter:
    """Synchronous subscription router over a sync event stream.

    The blocking twin of :class:`AsyncEventRouter` (same stop conditions,
    sequential dispatch); handlers must be sync callables, and :meth:`run`
    blocks until a stop condition fires.

    Args:
        stream: The open event stream to read from.
        session_id: When given, only events whose payload carries this
            ``sessionID`` are dispatched (others are dropped).
    """

    def __init__(self, stream: Any, *, session_id: str | None = None) -> None:
        self._stream = stream
        self._session_id = session_id
        self._handlers: list[tuple[EventType | str, Handler]] = []

    @property
    def session_id(self) -> str | None:
        """The session this router is scoped to, if any."""
        return self._session_id

    def on(self, event_type: EventType | str, handler: Handler) -> None:
        """Subscribe a *sync* ``handler`` to one event type.

        Raises:
            TypeError: If ``handler`` is a coroutine function.
        """
        if inspect.iscoroutinefunction(handler):
            raise TypeError("EventRouter handlers must be sync callables")
        self._handlers.append((event_type, handler))

    def run(self, *, until: EventType | str | None = None, timeout: float | None = None) -> None:
        """Run the reader loop until a stop condition fires.

        Stop conditions: a handler raises (the error propagates), an event
        of type ``until`` is dispatched, the stream ends cleanly, or
        ``timeout`` seconds elapse (raises :class:`TimeoutError`).  The
        event stream is left open — closing it is the stream context
        manager's job.

        Unlike :meth:`AsyncEventRouter.run`, whose deadline is enforced by
        ``asyncio.wait_for``, the sync reader blocks in a plain generator;
        a real wall-clock budget is enforced by running the loop in a
        watchdog worker thread.  If the deadline fires while blocked on a
        silent stream, that worker thread cannot be interrupted and is left
        as a daemon — it dies with the process, but the socket it holds is
        not released before then.

        Args:
            until: Event type that ends the run, after its handlers ran.
            timeout: Overall wall-clock budget for the run.

        Raises:
            TimeoutError: If ``timeout`` elapses before any other stop condition.
        """
        iterator = self._stream.iter_events()
        try:
            if timeout is None:
                self._loop(iterator, until)
                return
            # A blocking next() cannot be interrupted from another thread,
            # so invert the problem: run the whole loop in a helper thread
            # and enforce the deadline here in the caller's thread.
            failure: list[BaseException] = []
            done = threading.Event()

            def _body() -> None:
                try:
                    self._loop(iterator, until)
                except BaseException as exc:  # noqa: BLE001 - re-raised below
                    failure.append(exc)
                finally:
                    done.set()

            worker = threading.Thread(target=_body, name="opencode-event-router", daemon=True)
            worker.start()
            if not done.wait(timeout):
                raise TimeoutError(f"event router timed out after {timeout}s")
            worker.join()
            if failure:
                raise failure[0]
        finally:
            with suppress(Exception, BaseException):
                iterator.close()

    def _loop(self, iterator: Any, until: EventType | str | None) -> None:
        """Consume events until ``until`` matches or the stream ends cleanly."""
        while True:
            try:
                event = next(iterator)
            except StopIteration:
                return
            self._dispatch(event)
            if until is not None and _matches(until, event):
                return

    def _dispatch(self, event: Event) -> None:
        """Run every matching handler in subscription order."""
        if self._session_id is not None and _event_session_id(event) != self._session_id:
            return
        for event_type, handler in self._handlers:
            if _matches(event_type, event):
                handler(event)

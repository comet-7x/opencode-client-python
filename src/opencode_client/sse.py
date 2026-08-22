"""Server-Sent Events (SSE) helpers.

Three classes here:

- :class:`SSEDecoder` — a WHATWG ``text/event-stream`` line decoder;
- :class:`EventStream` — **async** context manager that keeps the long-lived
  ``GET /event`` connection open and guarantees it is closed;
- :class:`SyncEventStream` — the synchronous equivalent.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Iterator
from types import TracebackType
from typing import Any

import httpx

from .models import Event


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
      flushed on EOF.
    """

    def __init__(self) -> None:
        self._data: list[str] = []

    def _take_event(self) -> Event | None:
        """Build and clear the pending event, or return ``None`` if nothing is pending."""
        if not self._data:
            return None
        data = "\n".join(self._data)
        self._data.clear()
        try:
            raw: dict[str, Any] = json.loads(data)
        except ValueError:
            raw = {"type": "message", "properties": {"raw": data}}
        return Event.model_validate(raw)

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
        final = self._take_event()
        if final is not None:
            yield final

    async def aiter_events(self, lines: AsyncIterator[str]) -> AsyncIterator[Event]:
        """Decode an asynchronous line iterator, flushing a trailing partial event."""
        async for line in lines:
            event = self.decode_line(line.rstrip("\r"))
            if event is not None:
                yield event
        final = self._take_event()
        if final is not None:
            yield final


class EventStream:
    """Async context manager wrapping the ``/event`` SSE stream.

    Usage::

        async with client.server.stream_events() as stream:
            async for event in SSEDecoder().aiter_events(stream.aiter_lines()):
                print(event.type)

    The underlying HTTP response is opened on ``__aenter__`` and always
    closed on ``__aexit__``, even when the body iteration raised.
    """

    def __init__(self, client: httpx.AsyncClient, request: httpx.Request) -> None:
        self._client = client
        self._request = request
        self._response: httpx.Response | None = None

    async def __aenter__(self) -> httpx.Response:
        """Send the streaming request and return the open response."""
        response = await self._client.send(self._request, stream=True)
        self._response = response
        return response

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close the streaming response, if it was opened."""
        if self._response is not None:
            await self._response.aclose()
            self._response = None


class SyncEventStream:
    """Synchronous context manager wrapping the ``/event`` SSE stream.

    Usage::

        with client.server.stream_events() as stream:
            for event in SSEDecoder().iter_events(stream.iter_lines()):
                print(event.type)

    The underlying HTTP response is opened on ``__enter__`` and always closed
    on ``__exit__``, even when the body iteration raised.
    """

    def __init__(self, client: httpx.Client, request: httpx.Request) -> None:
        self._client = client
        self._request = request
        self._response: httpx.Response | None = None

    def __enter__(self) -> httpx.Response:
        """Send the streaming request and return the open response."""
        response = self._client.send(self._request, stream=True)
        self._response = response
        return response

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close the streaming response, if it was opened."""
        if self._response is not None:
            self._response.close()
            self._response = None

"""Typed hot events + the event router (catalog/contract + consumption)."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from typing import Any, cast

import httpx
import pytest

from opencode_client import (
    AsyncEventRouter,
    Event,
    EventRouter,
    EventType,
    MessagePartDeltaEvent,
    MessagePartUpdatedEvent,
    MessageUpdatedEvent,
    PermissionAskedEvent,
    QuestionAskedEvent,
    SessionIdleEvent,
    TextPart,
    typed_event,
)
from opencode_client.models import EVENT_CATALOG
from opencode_client.sse import AsyncEventStream, EventStream, SSEDecoder

PART_RAW = {
    "type": "text",
    "id": "prt_1",
    "sessionID": "ses_1",
    "messageID": "msg_1",
    "text": "hello",
}


def _sse_line(payload: dict[str, Any]) -> list[str]:
    """One complete SSE frame (data line + blank boundary) as raw lines."""
    return [f"data: {json.dumps(payload)}", ""]


class TestEventType:
    def test_str_mixin_equals_raw_value(self) -> None:
        # open set: a member compares equal to its raw string value
        raw: str = "session.idle"
        assert EventType.SESSION_IDLE == raw
        assert raw == EventType.SESSION_IDLE
        assert EventType.MESSAGE_PART_DELTA.value == "message.part.delta"

    def test_open_set_covers_known_surface(self) -> None:
        # one member per known v1 event type from the server's /doc export
        members = {member.value for member in EventType}
        assert len(members) == 57
        assert "session.idle" in members
        assert "message.part.delta" in members
        # sorted for stable reading
        values = [member.value for member in EventType]
        assert values == sorted(values)

    def test_catalog_keys_are_known_types(self) -> None:
        for key in EVENT_CATALOG:
            assert key in {member.value for member in EventType}
        assert set(EVENT_CATALOG) == {
            "message.part.updated",
            "message.part.delta",
            "message.updated",
            "session.idle",
            "permission.asked",
            "question.asked",
        }


class TestTypedEvent:
    def test_part_updated_upgrades_and_types_part(self) -> None:
        raw = {
            "type": "message.part.updated",
            "properties": {"sessionID": "ses_1", "part": PART_RAW, "time": 123},
        }
        event = typed_event(raw)
        assert isinstance(event, MessagePartUpdatedEvent)
        assert event.session_id == "ses_1"
        assert event.time == 123
        assert isinstance(event.part, TextPart)
        assert event.part.text == "hello"

    def test_part_delta_upgrades(self) -> None:
        raw = {
            "type": "message.part.delta",
            "properties": {
                "sessionID": "ses_1",
                "messageID": "msg_1",
                "partID": "prt_1",
                "field": "text",
                "delta": "he",
            },
        }
        event = typed_event(raw)
        assert isinstance(event, MessagePartDeltaEvent)
        assert (event.session_id, event.message_id, event.part_id) == ("ses_1", "msg_1", "prt_1")
        assert (event.field, event.delta) == ("text", "he")

    def test_message_updated_keeps_info_unvalidated(self) -> None:
        raw = {
            "type": "message.updated",
            "properties": {"sessionID": "ses_1", "info": {"role": "user", "id": "msg_1"}},
        }
        event = typed_event(raw)
        assert isinstance(event, MessageUpdatedEvent)
        assert event.session_id == "ses_1"
        assert event.info["role"] == "user"

    def test_session_idle_upgrades(self) -> None:
        event = typed_event({"type": "session.idle", "properties": {"sessionID": "ses_1"}})
        assert isinstance(event, SessionIdleEvent)
        assert event.session_id == "ses_1"

    def test_permission_asked_hoists_request_fields(self) -> None:
        raw = {
            "type": "permission.asked",
            "properties": {
                "id": "per_1",
                "sessionID": "ses_1",
                "permission": "bash",
                "patterns": ["rm *"],
                "metadata": {},
                "always": ["rm"],
                "tool": {"messageID": "msg_1", "callID": "call_1"},
            },
        }
        event = typed_event(raw)
        assert isinstance(event, PermissionAskedEvent)
        assert (event.id, event.session_id, event.permission) == ("per_1", "ses_1", "bash")
        assert event.patterns == ["rm *"]
        assert event.always == ["rm"]
        assert event.tool == {"messageID": "msg_1", "callID": "call_1"}
        assert event.request.permission == "bash"
        assert event.request.patterns == ["rm *"]

    def test_question_asked_exposes_typed_request(self) -> None:
        raw = {
            "type": "question.asked",
            "properties": {
                "id": "que_1",
                "sessionID": "ses_1",
                "questions": [
                    {"question": "Q", "header": "H", "options": [{"label": "a", "description": "d"}]},
                ],
            },
        }
        event = typed_event(raw)
        assert isinstance(event, QuestionAskedEvent)
        assert event.request.questions[0].header == "H"
        assert event.request.questions[0].options[0].label == "a"

    def test_unknown_type_stays_base(self) -> None:
        event = typed_event({"type": "pty.updated", "properties": {"x": 1}})
        assert type(event) is Event
        assert event.properties == {"x": 1}

    def test_broken_hot_payload_degrades_to_base(self) -> None:
        # the server changed its shape: required field missing
        event = typed_event({"type": "session.idle", "properties": {}})
        assert type(event) is Event
        # still readable via the free-form dict
        assert event.properties == {}

    def test_broken_part_payload_degrades_to_base(self) -> None:
        raw = {
            "type": "message.part.updated",
            "properties": {"sessionID": "ses_1", "part": PART_RAW},  # time missing
        }
        assert type(typed_event(raw)) is Event


class TestSSEDecodeHook:
    def test_iter_events_upgrades_hot_and_keeps_unknown(self) -> None:
        decoder = SSEDecoder()
        lines: list[str] = []
        lines += _sse_line(
            {
                "type": "message.part.delta",
                "properties": {"sessionID": "s", "messageID": "m", "partID": "p", "field": "text", "delta": "x"},
            }
        )
        lines += _sse_line({"type": "unknown.event", "properties": {}})
        events = list(decoder.iter_events(iter(lines)))
        assert isinstance(events[0], MessagePartDeltaEvent)
        assert type(events[1]) is Event

    def test_flush_also_upgrades(self) -> None:
        decoder = SSEDecoder()
        raw = json.dumps({"type": "session.idle", "properties": {"sessionID": "s"}})
        decoder.decode_line(f"data: {raw}")  # no trailing blank line yet
        event = decoder.flush()
        assert isinstance(event, SessionIdleEvent)

    def test_non_json_data_stays_base(self) -> None:
        decoder = SSEDecoder()
        events = list(decoder.iter_events(iter(["data: not-json", ""])))
        assert type(events[0]) is Event
        assert events[0].type == "message"


class _FakeAsyncStream:
    def __init__(self, events: list[Event]) -> None:
        self._events = events

    def aiter_events(self) -> Any:
        async def gen() -> Any:
            for event in self._events:
                yield event

        return gen()


class _FakeSyncStream:
    def __init__(self, events: list[Event]) -> None:
        self._events = events

    def iter_events(self) -> Any:
        return iter(self._events)


def _delta(session_id: str, delta: str) -> MessagePartDeltaEvent:
    return MessagePartDeltaEvent(
        type="message.part.delta",
        properties={},
        session_id=session_id,
        message_id="msg_1",
        part_id="prt_1",
        field="text",
        delta=delta,
    )


def _idle(session_id: str) -> SessionIdleEvent:
    return SessionIdleEvent(type="session.idle", properties={"sessionID": session_id}, session_id=session_id)


def _delta_recorder(seen: list[str]) -> Callable[[Event], None]:
    """A handler that appends each part-delta's text, asserting the type upgrade."""

    def handler(event: Event) -> None:
        assert isinstance(event, MessagePartDeltaEvent)
        seen.append(event.delta)

    return handler


class TestAsyncEventRouter:
    async def test_dispatch_in_arrival_order(self) -> None:
        seen: list[str] = []
        router = AsyncEventRouter(
            _FakeAsyncStream([_delta("s1", "a"), _delta("s1", "b"), _idle("s1")]),
        )
        router.on("message.part.delta", _delta_recorder(seen))
        router.on("session.idle", lambda event: seen.append("idle"))
        await router.run()
        assert seen == ["a", "b", "idle"]

    async def test_multiple_subscriptions_same_type_in_order(self) -> None:
        seen: list[str] = []
        router = AsyncEventRouter(_FakeAsyncStream([_delta("s1", "x")]))
        router.on(EventType.MESSAGE_PART_DELTA, lambda event: seen.append("first"))
        router.on("message.part.delta", lambda event: seen.append("second"))
        await router.run()
        assert seen == ["first", "second"]

    async def test_sync_and_async_handlers(self) -> None:
        seen: list[str] = []

        async def on_idle(event: Event) -> None:
            assert isinstance(event, SessionIdleEvent)
            seen.append(f"idle:{event.session_id}")

        router = AsyncEventRouter(_FakeAsyncStream([_delta("s1", "a"), _idle("s1")]))
        router.on("message.part.delta", _delta_recorder(seen))
        router.on("session.idle", on_idle)
        await router.run()
        assert seen == ["a", "idle:s1"]

    async def test_session_filter_drops_other_sessions(self) -> None:
        seen: list[str] = []
        router = AsyncEventRouter(
            _FakeAsyncStream([_delta("s1", "a"), _delta("s2", "b"), _idle("s1")]),
            session_id="s1",
        )
        router.on("message.part.delta", _delta_recorder(seen))
        router.on("session.idle", lambda event: seen.append("idle"))
        await router.run()
        assert seen == ["a", "idle"]

    async def test_session_filter_reads_properties_for_base_events(self) -> None:
        other = Event(type="pty.updated", properties={"sessionID": "s2"})
        seen: list[str] = []
        router = AsyncEventRouter(
            _FakeAsyncStream([other, _delta("s1", "a")]),
            session_id="s1",
        )
        router.on("message.part.delta", _delta_recorder(seen))
        router.on("pty.updated", lambda event: seen.append("pty"))
        await router.run()
        assert seen == ["a"]

    async def test_until_stops_after_handlers_ran(self) -> None:
        seen: list[str] = []
        router = AsyncEventRouter(_FakeAsyncStream([_delta("s1", "a"), _idle("s1"), _delta("s1", "late")]))
        router.on("message.part.delta", _delta_recorder(seen))
        router.on("session.idle", lambda event: seen.append("idle"))
        await router.run(until="session.idle")
        assert seen == ["a", "idle"]

    async def test_clean_eof_ends_run(self) -> None:
        seen: list[str] = []
        router = AsyncEventRouter(_FakeAsyncStream([_delta("s1", "a")]))
        router.on("message.part.delta", _delta_recorder(seen))
        await router.run()
        assert seen == ["a"]

    async def test_handler_error_propagates(self) -> None:
        def boom(event: Event) -> None:
            raise ValueError("handler exploded")

        router = AsyncEventRouter(_FakeAsyncStream([_delta("s1", "a")]))
        router.on("message.part.delta", boom)
        with pytest.raises(ValueError, match="handler exploded"):
            await router.run()

    async def test_timeout_raises_asyncio_timeout(self) -> None:
        class _HangingStream:
            def aiter_events(self) -> Any:
                async def gen() -> Any:
                    await asyncio.sleep(30)
                    yield _idle("s1")

                return gen()

        with pytest.raises(asyncio.TimeoutError):
            await AsyncEventRouter(_HangingStream()).run(timeout=0.01)

    async def test_no_subscriptions_runs_to_eof(self) -> None:
        router = AsyncEventRouter(_FakeAsyncStream([_delta("s1", "a"), _idle("s1")]))
        await router.run()  # must not raise or block


class TestEventRouter:
    def test_dispatch_filter_and_until(self) -> None:
        seen: list[str] = []
        router = EventRouter(
            _FakeSyncStream([_delta("s1", "a"), _delta("s2", "b"), _idle("s1")]),
            session_id="s1",
        )
        router.on("message.part.delta", _delta_recorder(seen))
        router.on("session.idle", lambda event: seen.append("idle"))
        router.run(until="session.idle")
        assert seen == ["a", "idle"]

    def test_clean_eof_ends_run(self) -> None:
        seen: list[str] = []
        router = EventRouter(_FakeSyncStream([_delta("s1", "a")]))
        router.on("message.part.delta", _delta_recorder(seen))
        router.run()
        assert seen == ["a"]

    def test_handler_error_propagates(self) -> None:
        def boom(event: Event) -> None:
            raise RuntimeError("sync boom")

        router = EventRouter(_FakeSyncStream([_delta("s1", "a")]))
        router.on("message.part.delta", boom)
        with pytest.raises(RuntimeError, match="sync boom"):
            router.run()

    def test_timeout_raises_timeout_error(self) -> None:
        import time

        # budget expires at the boundary *between* events (a slow first
        # event would block the read; only gaps are observable)
        class _GappyStream:
            def iter_events(self) -> Any:
                def gen() -> Any:
                    yield _delta("s1", "a")
                    time.sleep(0.1)
                    yield _idle("s1")

                return gen()

        seen: list[str] = []
        router = EventRouter(_GappyStream())
        router.on("message.part.delta", _delta_recorder(seen))
        with pytest.raises(TimeoutError, match="timed out"):
            router.run(timeout=0.02)
        assert seen == ["a"]

    def test_rejects_coroutine_handlers(self) -> None:
        async def handler(event: Event) -> None:
            pass

        router = EventRouter(_FakeSyncStream([]))
        with pytest.raises(TypeError, match="sync callables"):
            router.on("session.idle", handler)


class TestStreamRouteWiring:
    def test_async_stream_route_returns_router(self) -> None:
        stream = AsyncEventStream(
            cast("httpx.AsyncClient", object()),
            httpx.Request("GET", "http://127.0.0.1/event"),
        )
        router = stream.route("ses_1")
        assert isinstance(router, AsyncEventRouter)
        assert router.session_id == "ses_1"
        assert isinstance(stream.route(), AsyncEventRouter)

    def test_sync_stream_route_returns_router(self) -> None:
        stream = EventStream(
            cast("httpx.Client", object()),
            httpx.Request("GET", "http://127.0.0.1/event"),
        )
        router = stream.route("ses_2")
        assert isinstance(router, EventRouter)
        assert router.session_id == "ses_2"
        assert isinstance(stream.route(), EventRouter)

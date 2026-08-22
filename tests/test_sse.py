import json
from collections.abc import AsyncIterator

from opencode_client import Event
from opencode_client.sse import SSEDecoder


class TestSSEDecoder:
    def test_single_event(self) -> None:
        decoder = SSEDecoder()
        payload = {"id": "evt_1", "type": "message.updated", "properties": {"sessionID": "ses_1"}}
        lines = [f"data: {json.dumps(payload)}", ""]
        events = list(decoder.iter_events(iter(lines)))
        assert len(events) == 1
        assert events[0].type == "message.updated"
        assert events[0].properties["sessionID"] == "ses_1"

    def test_event_field_and_multi_data_lines(self) -> None:
        decoder = SSEDecoder()
        lines = [
            "event: ping",
            "data: {",
            'data: "type": "server.connected", "properties": {}}',
            "",
        ]
        events = list(decoder.iter_events(iter(lines)))
        assert len(events) == 1
        assert events[0].type == "server.connected"

    def test_multiple_events_one_chunk(self) -> None:
        decoder = SSEDecoder()
        raw = 'data: {"type": "a", "properties": {}}\n\ndata: {"type": "b", "properties": {}}\n\n'
        events = list(decoder.iter_events(iter(raw.splitlines())))
        assert [e.type for e in events] == ["a", "b"]

    def test_comment_lines_ignored(self) -> None:
        decoder = SSEDecoder()
        raw = ': keep-alive\n\ndata: {"type": "x", "properties": {}}\n\n'
        events = list(decoder.iter_events(iter(raw.splitlines())))
        assert [e.type for e in events] == ["x"]

    def test_flush_partial_event_at_eof(self) -> None:
        decoder = SSEDecoder()
        raw = 'data: {"type": "eof", "properties": {}}\n'
        events = list(decoder.iter_events(iter([raw])))
        assert [e.type for e in events] == ["eof"]

    def test_non_json_data_wrapped(self) -> None:
        decoder = SSEDecoder()
        events = list(decoder.iter_events(iter(["data: not-json", ""])))
        assert len(events) == 1
        assert events[0].type == "message"

    def test_event_model_defaults(self) -> None:
        event = Event.model_validate({"type": "session.created"})
        assert event.properties == {}
        assert event.id is None

    async def test_aiter_events(self) -> None:
        decoder = SSEDecoder()
        lines = [
            'data: {"type": "one", "properties": {}}',
            "",
            'data: {"type": "two", "properties": {}}',
        ]

        async def gen() -> AsyncIterator[str]:
            for line in lines:
                yield line

        events = [e async for e in decoder.aiter_events(gen())]
        assert [e.type for e in events] == ["one", "two"]

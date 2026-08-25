"""Regression tests for the 2026-08-24 code review fixes (IT-012).

Covers: layered default timeouts (H1), idempotency-aware transport retries
(M1), sync router wall-clock timeout (M2), response-validation error
wrapping (M3), ``/session/status`` scope params (L1), path-segment quoting
(L2), Retry-After HTTP-date parsing (L5), and typed-event envelope key
protection (L4).
"""

from __future__ import annotations

import email.utils
import threading
import time
from collections.abc import Iterator

import httpx
import pydantic
import pytest
import respx

from opencode_client import (
    AsyncOpenCodeClient,
    Event,
    EventRouter,
    MessagePartDeltaEvent,
    OpenCodeClient,
    OpenCodeError,
    OpenCodeResponseError,
    OpenCodeTimeoutError,
)
from opencode_client.client import (  # pyright: ignore[reportPrivateUsage]
    _backoff_seconds,  # pyright: ignore[reportPrivateUsage]
    _is_retryable_transport_error,  # pyright: ignore[reportPrivateUsage]
)
from opencode_client.resources._wire import TYPE_ADAPTERS, path_segment, validate_response

BASE = "http://localhost:4096"


def _no_sleep(seconds: float) -> None:
    """Collapse the backoff so retry tests run instantly."""


def _session_payload() -> dict[str, object]:
    return {
        "id": "ses_1",
        "slug": "s",
        "projectID": "prj_1",
        "directory": "/tmp/proj",
        "path": "",
        "title": "t",
        "version": "0.1.0",
        "time": {"created": 1, "updated": 2},
    }


class TestDefaultTimeout:
    def test_sync_default_layers_connect_and_read(self) -> None:
        with OpenCodeClient(BASE) as client:
            timeout = client._http.timeout  # pyright: ignore[reportPrivateUsage]
        assert isinstance(timeout, httpx.Timeout)
        assert timeout.connect == 5.0
        assert timeout.read == 60.0

    @pytest.mark.asyncio
    async def test_async_default_layers_connect_and_read(self) -> None:
        async with AsyncOpenCodeClient(BASE) as client:
            timeout = client._http.timeout  # pyright: ignore[reportPrivateUsage]
        assert isinstance(timeout, httpx.Timeout)
        assert timeout.connect == 5.0
        assert timeout.read == 60.0

    def test_explicit_scalar_applies_to_every_phase(self) -> None:
        with OpenCodeClient(BASE, timeout=10.0) as client:
            timeout = client._http.timeout  # pyright: ignore[reportPrivateUsage]
        assert isinstance(timeout, httpx.Timeout)
        assert timeout.read == 10.0
        assert timeout.connect == 10.0


class TestIdempotencyAwareRetries:
    def test_read_timeout_on_get_is_retryable(self) -> None:
        assert _is_retryable_transport_error("GET", httpx.ReadTimeout("slow"))
        assert _is_retryable_transport_error("DELETE", httpx.ConnectError("refused"))

    def test_read_timeout_on_post_is_not_retryable(self) -> None:
        assert not _is_retryable_transport_error("POST", httpx.ReadTimeout("slow"))
        assert not _is_retryable_transport_error("POST", httpx.WriteError("broken"))

    def test_connect_phase_failure_on_post_is_retryable(self) -> None:
        assert _is_retryable_transport_error("POST", httpx.ConnectError("refused"))
        assert _is_retryable_transport_error("POST", httpx.ConnectTimeout("slow handshake"))

    def _client_with_failures(self, exc: httpx.HTTPError, calls: list[httpx.Request]) -> OpenCodeClient:
        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            raise exc

        return OpenCodeClient(BASE, max_retries=2, transport=httpx.MockTransport(handler))

    def test_post_read_timeout_raises_without_retries(self) -> None:
        calls: list[httpx.Request] = []
        client = self._client_with_failures(httpx.ReadTimeout("slow"), calls)
        with pytest.raises(OpenCodeTimeoutError):
            client.send("POST", "/session/ses_1/prompt", json={})
        assert len(calls) == 1

    def test_post_connect_error_is_retried_then_mapped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import opencode_client.client as client_module

        monkeypatch.setattr(client_module.time, "sleep", _no_sleep)
        calls: list[httpx.Request] = []
        client = self._client_with_failures(httpx.ConnectError("refused"), calls)
        with pytest.raises(OpenCodeError):
            client.send("POST", "/session", json={})
        assert len(calls) == 3

    @pytest.mark.asyncio
    async def test_async_post_read_timeout_raises_without_retries(self) -> None:
        calls: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            raise httpx.ReadTimeout("slow")

        async with AsyncOpenCodeClient(BASE, max_retries=2, transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(OpenCodeTimeoutError):
                await client.send("POST", "/session/ses_1/prompt", json={})
        assert len(calls) == 1


class TestRetryAfterDate:
    def test_delta_seconds_still_wins(self) -> None:
        response = httpx.Response(429, headers={"Retry-After": "7"})
        assert _backoff_seconds(1, response) == 7.0

    def test_http_date_is_parsed(self) -> None:
        header = email.utils.formatdate(time.time() + 30, usegmt=True)
        response = httpx.Response(429, headers={"Retry-After": header})
        delay = _backoff_seconds(1, response)
        assert 25 <= delay <= 30

    def test_garbage_falls_back_to_backoff(self) -> None:
        response = httpx.Response(429, headers={"Retry-After": "soon"})
        assert _backoff_seconds(3, response) == pytest.approx(2.0)


class TestResponseValidationError:
    def test_schema_mismatch_wraps_validation_error(self) -> None:
        response = httpx.Response(200, json=[{"nope": True}])
        with pytest.raises(OpenCodeResponseError) as excinfo:
            validate_response(response, TYPE_ADAPTERS.sessions)
        assert isinstance(excinfo.value.__cause__, pydantic.ValidationError)

    def test_wrapped_error_is_part_of_the_hierarchy(self) -> None:
        response = httpx.Response(200, json=[{"nope": True}])
        with pytest.raises(OpenCodeError):
            validate_response(response, TYPE_ADAPTERS.sessions)


class TestSyncRouterWallClockTimeout:
    def test_silent_stream_times_out_in_wall_clock_time(self) -> None:
        class SilentStream:
            # a generator whose first next() blocks forever, mimicking a
            # silent SSE stream where the old deadline check never fired
            def iter_events(self) -> Iterator[Event]:
                threading.Event().wait()
                yield Event(type="session.idle", properties={})  # pragma: no cover

        router = EventRouter(SilentStream())
        start = time.monotonic()
        with pytest.raises(TimeoutError):
            router.run(timeout=0.2)
        elapsed = time.monotonic() - start
        assert elapsed < 2.0

    def test_active_stream_dispatches_until(self) -> None:
        class FakeStream:
            def iter_events(self) -> Iterator[Event]:
                yield Event(type="session.idle", properties={})

        router = EventRouter(FakeStream())
        seen: list[Event] = []
        router.on("session.idle", seen.append)
        router.run(until="session.idle", timeout=5)
        assert len(seen) == 1


class TestStatusScopeParams:
    def test_status_forwards_directory_and_workspace(self) -> None:
        with respx.mock(base_url=BASE) as router:
            route = router.get("/session/status").mock(return_value=httpx.Response(200, json={}))
            with OpenCodeClient(BASE) as client:
                client.sessions.status(directory="/tmp/proj", workspace="ws")
        params = route.calls.last.request.url.params
        assert params["directory"] == "/tmp/proj"
        assert params["workspace"] == "ws"

    @pytest.mark.asyncio
    async def test_async_status_forwards_scope_params(self) -> None:
        with respx.mock(base_url=BASE) as router:
            route = router.get("/session/status").mock(return_value=httpx.Response(200, json={}))
            async with AsyncOpenCodeClient(BASE) as client:
                await client.sessions.status(directory="/tmp/proj")
        assert route.calls.last.request.url.params["directory"] == "/tmp/proj"


class TestPathSegmentQuoting:
    def test_reserved_characters_are_encoded(self) -> None:
        assert path_segment("a/b") == "a%2Fb"
        assert path_segment("a?b#c") == "a%3Fb%23c"
        assert path_segment("ses_abc") == "ses_abc"

    def test_path_ids_reach_the_wire_encoded(self) -> None:
        with respx.mock(base_url=BASE) as router:
            # the encoded wire path cannot be matched literally, so catch it by prefix
            route = router.get(url__startswith=f"{BASE}/session/ses").mock(
                return_value=httpx.Response(200, json=_session_payload())
            )
            with OpenCodeClient(BASE) as client:
                client.sessions.get("ses/1")
        url = route.calls[0].request.url  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        # httpx's url.path is the decoded form; raw_path keeps the percent-encoding
        assert url.raw_path == b"/session/ses%2F1"  # pyright: ignore[reportUnknownMemberType]


class TestEnvelopeKeyProtection:
    def test_payload_type_cannot_override_envelope_type(self) -> None:
        event = MessagePartDeltaEvent.model_validate(
            {
                "type": "message.part.delta",
                "properties": {
                    "type": "spoofed",
                    "sessionID": "ses_1",
                    "messageID": "msg_1",
                    "partID": "prt_1",
                    "field": "text",
                    "delta": "hi",
                },
            }
        )
        assert event.type == "message.part.delta"
        assert event.session_id == "ses_1"
        # pass-through payload stays intact for consumers that read properties directly
        assert event.properties["type"] == "spoofed"

    def test_payload_id_still_hoists(self) -> None:
        event = MessagePartDeltaEvent.model_validate(
            {
                "id": "evt_1",
                "type": "message.part.delta",
                "properties": {
                    "id": "per_9",
                    "sessionID": "ses_1",
                    "messageID": "msg_1",
                    "partID": "prt_1",
                    "field": "text",
                    "delta": "hi",
                },
            }
        )
        assert event.id == "per_9"

"""Tests for IT-017: the last 11 core-surface endpoints."""

from __future__ import annotations

import json
from collections.abc import Generator
from typing import Any

import httpx
import pytest
import respx

from opencode_client import (
    AsyncOpenCodeClient,
    Event,
    GlobalEvent,
    OpenCodeClient,
    ProviderAuthAuthorization,
    ProviderAuthMethod,
    ProviderAuthPromptSelect,
    ProviderAuthPromptText,
)

BASE = "http://localhost:4096"


def _msg_doc() -> dict[str, Any]:
    return {
        "info": {
            "id": "msg_a",
            "sessionID": "ses_e",
            "role": "assistant",
            "time": {"created": 1, "completed": 2},
            "parentID": "msg_u",
            "modelID": "m",
            "providerID": "p",
            "mode": "build",
            "agent": "build",
            "path": {"cwd": "/tmp", "root": "/tmp"},
            "cost": 0.0,
            "tokens": {"total": 2.0, "input": 1, "output": 1, "reasoning": 0, "cache": {"read": 0, "write": 0}},
            "finish": "stop",
        },
        "parts": [{"id": "prt_t", "sessionID": "ses_e", "messageID": "msg_a", "type": "text", "text": "hi"}],
    }


@pytest.fixture(autouse=True)
def mock_server() -> Generator[respx.MockRouter, None, None]:
    with respx.mock(base_url=BASE) as router:
        yield router


class TestGetMessage:
    def test_sync_get_message(self, mock_server: respx.MockRouter) -> None:
        route = mock_server.get("/session/ses_e/message/msg_a").mock(return_value=httpx.Response(200, json=_msg_doc()))
        with OpenCodeClient(BASE) as client:
            msg = client.sessions.get_message("ses_e", "msg_a")
        assert msg.info.id == "msg_a"
        assert msg.parts[0].type == "text"
        assert route.calls.last.request.url.path == "/session/ses_e/message/msg_a"

    async def test_async_get_message(self, mock_server: respx.MockRouter) -> None:
        mock_server.get("/session/ses_e/message/msg_a").mock(return_value=httpx.Response(200, json=_msg_doc()))
        async with AsyncOpenCodeClient(BASE) as client:
            msg = await client.sessions.get_message("ses_e", "msg_a")
        assert msg.parts[0].id == "prt_t"

    def test_raw_get_message(self, mock_server: respx.MockRouter) -> None:
        mock_server.get("/session/ses_e/message/msg_a").mock(return_value=httpx.Response(200, json=_msg_doc()))
        with OpenCodeClient(BASE) as client:
            response = client.sessions.with_raw_response.get_message("ses_e", "msg_a")
        assert response.json()["parts"][0]["text"] == "hi"


class TestProviderOAuth:
    def _methods_payload(self) -> dict[str, Any]:
        return {
            "anthropic": [
                {"type": "oauth", "label": "Claude OAuth"},
                {
                    "type": "api",
                    "label": "API key",
                    "prompts": [
                        {"type": "text", "key": "apiKey", "message": "Paste key"},
                        {
                            "type": "select",
                            "key": "region",
                            "message": "Pick region",
                            "options": [{"label": "US", "value": "us"}],
                        },
                    ],
                },
            ]
        }

    def test_auth_methods_parse_prompts_union(self, mock_server: respx.MockRouter) -> None:
        route = mock_server.get("/provider/auth").mock(return_value=httpx.Response(200, json=self._methods_payload()))
        with OpenCodeClient(BASE) as client:
            methods = client.auth.provider_auth_methods()
        entry = methods["anthropic"][1]
        assert isinstance(entry, ProviderAuthMethod)
        assert isinstance(entry.prompts[0], ProviderAuthPromptText)
        assert isinstance(entry.prompts[1], ProviderAuthPromptSelect)
        assert entry.prompts[1].options[0]["value"] == "us"
        assert route.calls.last.request.url.path == "/provider/auth"

    def test_start_oauth_serialises_method_and_inputs(self, mock_server: respx.MockRouter) -> None:
        route = mock_server.post("/provider/anthropic/oauth/authorize").mock(
            return_value=httpx.Response(
                200,
                json={"url": "https://auth.example", "method": "code", "instructions": "paste it back"},
            )
        )
        with OpenCodeClient(BASE) as client:
            started = client.auth.start_provider_oauth("anthropic", method=1, inputs={"apiKey": "sk"})
        assert isinstance(started, ProviderAuthAuthorization)
        assert started.method == "code"
        sent = json.loads(route.calls.last.request.content)
        assert sent == {"method": 1, "inputs": {"apiKey": "sk"}}

    def test_complete_oauth(self, mock_server: respx.MockRouter) -> None:
        route = mock_server.post("/provider/anthropic/oauth/callback").mock(return_value=httpx.Response(200, json=True))
        with OpenCodeClient(BASE) as client:
            ok = client.auth.complete_provider_oauth("anthropic", method=1, code="c0de")
        assert ok is True
        sent = json.loads(route.calls.last.request.content)
        assert sent == {"method": 1, "code": "c0de"}

    async def test_async_mirror(self, mock_server: respx.MockRouter) -> None:
        mock_server.get("/provider/auth").mock(return_value=httpx.Response(200, json=self._methods_payload()))
        mock_server.post("/provider/anthropic/oauth/authorize").mock(
            return_value=httpx.Response(200, json={"url": "u", "method": "auto", "instructions": "none"})
        )
        async with AsyncOpenCodeClient(BASE) as client:
            methods = await client.auth.provider_auth_methods()
            started = await client.auth.start_provider_oauth("anthropic", method=0)
        assert "anthropic" in methods
        assert isinstance(started, ProviderAuthAuthorization)


class TestGlobalConfigAndLifecycle:
    def test_get_global_config(self, mock_server: respx.MockRouter) -> None:
        mock_server.get("/global/config").mock(
            return_value=httpx.Response(200, json={"$schema": "https://opencode.ai/config.json"})
        )
        with OpenCodeClient(BASE) as client:
            cfg = client.server.get_global_config()
        assert cfg["$schema"].endswith("config.json")

    def test_update_global_config(self, mock_server: respx.MockRouter) -> None:
        route = mock_server.patch("/global/config").mock(return_value=httpx.Response(200, json={"username": "renamed"}))
        with OpenCodeClient(BASE) as client:
            cfg = client.server.update_global_config({"username": "renamed"})
        assert cfg["username"] == "renamed"
        assert json.loads(route.calls.last.request.content) == {"username": "renamed"}

    def test_dispose_instance(self, mock_server: respx.MockRouter) -> None:
        route = mock_server.post("/instance/dispose").mock(return_value=httpx.Response(200, json=True))
        with OpenCodeClient(BASE) as client:
            assert client.server.dispose_instance() is True
        assert route.calls.last.request.url.path == "/instance/dispose"

    def test_dispose_global_and_upgrade(self, mock_server: respx.MockRouter) -> None:
        dispose_route = mock_server.post("/global/dispose").mock(return_value=httpx.Response(200, json=True))
        upgrade_route = mock_server.post("/global/upgrade").mock(
            return_value=httpx.Response(200, json={"success": True, "version": "1.18.22"})
        )
        with OpenCodeClient(BASE) as client:
            assert client.server.dispose_global() is True
            result = client.server.upgrade_global(target="v1.19.0")
        assert result["success"] is True
        assert json.loads(upgrade_route.calls.last.request.content) == {"target": "v1.19.0"}
        assert dispose_route.calls.last.request.url.path == "/global/dispose"

    async def test_async_mirrors(self, mock_server: respx.MockRouter) -> None:
        mock_server.get("/global/config").mock(return_value=httpx.Response(200, json={}))
        mock_server.post("/instance/dispose").mock(return_value=httpx.Response(200, json=True))
        async with AsyncOpenCodeClient(BASE) as client:
            await client.server.get_global_config()
            disposed = await client.server.dispose_instance()
        assert disposed is True


class TestGlobalEventStream:
    def _sse(self, *events: dict[str, Any]) -> bytes:
        frames = "".join(f"data: {json.dumps(e)}\n\n" for e in events).encode()
        return frames

    def test_sync_stream_parses_global_envelope(self) -> None:
        sse = self._sse(
            {
                "directory": "/tmp/proj",
                "payload": {"id": "evt_1", "type": "session.idle", "properties": {}},
            },
            {
                "project": "prj_1",
                "payload": {"id": "evt_2", "type": "models-dev.refreshed", "properties": {}},
            },
        )
        # stream_events-style tests use a real socket via httpx.MockTransport
        from opencode_client.constants import DEFAULT_MAX_RETRIES

        transport = httpx.MockTransport(lambda request: httpx.Response(200, content=sse))
        from opencode_client import AsyncOpenCodeClient

        async def run() -> list[Event]:
            events: list[Event] = []
            base = AsyncOpenCodeClient(BASE, transport=transport, max_retries=DEFAULT_MAX_RETRIES)
            request = base._http.build_request("GET", "/global/event")  # pyright: ignore[reportPrivateUsage]
            from opencode_client.sse import AsyncEventStream

            async with AsyncEventStream(base._http, request) as stream:  # pyright: ignore[reportPrivateUsage]
                async for event in stream.aiter_events():
                    events.append(event)
                    if len(events) == 2:
                        break
            await base.close()
            return events

        import asyncio

        events = asyncio.run(run())
        # global 信封与实例 Event 形状不同：解码器按"流永不断"降级为
        # type="unknown" 的基类事件，原始文档保留在 properties["raw"]。
        assert [e.type for e in events] == ["unknown", "unknown"]
        envelopes = [GlobalEvent.model_validate(e.properties["raw"]) for e in events]
        assert [envelopes[0].payload_type, envelopes[1].payload_type] == [
            "session.idle",
            "models-dev.refreshed",
        ]
        assert events[0].properties["raw"]["directory"] == "/tmp/proj"
        assert envelopes[0].directory == "/tmp/proj"

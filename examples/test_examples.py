"""respx 驱动的 examples 冒烟：离线跑各教学脚本的 cli() 入口。

每个示例脚本都暴露一个纯 CLI 入口（argparse + ``asyncio.run``），因此这里
直接给 ``sys.argv`` 喂参数、再在 respx mock 下调用它们的 ``cli()``，即可
完整走过一次真实管线而不依赖真实 opencode 服务。
（`streaming` 脚本里的真实 sleep 只有 0.5s，套件仍可秒级跑完。）

数字前缀目录不是 Python 标识符，故用
``importlib.import_module("examples.00_quickstart.quickstart")`` 加载，
而非 `import examples.00_quickstart.quickstart` 这种语法。
"""

from __future__ import annotations

import importlib
import json
import sys
from collections.abc import Generator
from types import ModuleType
from typing import Any

import httpx
import pytest
import respx

BASE = "http://localhost:4096"


def _session_payload(session_id: str = "ses_e") -> dict[str, Any]:
    return {
        "id": session_id,
        "slug": "s",
        "projectID": "prj",
        "directory": "/tmp",
        "path": "",
        "title": "my session",
        "version": "1",
        "time": {"created": 1, "updated": 1},
    }


def _assistant_message(session_id: str = "ses_e") -> dict[str, Any]:
    return {
        "id": "msg_a",
        "sessionID": session_id,
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
    }


TEXT_PART = {"id": "prt_t", "sessionID": "ses_e", "messageID": "msg_a", "type": "text", "text": "pong"}


@pytest.fixture(autouse=True)
def mock_server() -> Generator[respx.MockRouter, None, None]:
    """Mocking of the endpoints that the example scripts touch.

    SSE stream: two text deltas + ``session.idle`` (sessionID matched to the
    session that the script will create).
    """
    with respx.mock(base_url=BASE, assert_all_called=False) as router:
        router.get("/global/health").mock(return_value=httpx.Response(200, json={"healthy": True, "version": "1.0"}))
        router.post("/session").mock(return_value=httpx.Response(200, json=_session_payload()))
        router.delete("/session/ses_e").mock(return_value=httpx.Response(200, json=True))
        # delete_session 在未指定 --session 时会现建一个再删：删除 404 兜底。
        router.route(method="DELETE", path__regex=r"/session/[^/]+").mock(return_value=httpx.Response(200, json=True))
        router.get("/session/ses_e").mock(return_value=httpx.Response(200, json=_session_payload()))
        # list_sessions 会取到的列表（最新在前的语义在真实服务端保证，这里给一条）。
        router.get("/session").mock(return_value=httpx.Response(200, json=[_session_payload()]))
        # A non-existent session: quickstart/error_handling paths expect 404.
        router.get("/session/ses_does_not_exist_0000").mock(
            return_value=httpx.Response(404, json={"name": "NotFound", "data": {"message": "nope"}})
        )
        router.get("/session/ses_missing_a").mock(
            return_value=httpx.Response(404, json={"name": "NotFound", "data": {}})
        )
        router.get("/session/ses_missing_b").mock(
            return_value=httpx.Response(404, json={"name": "NotFound", "data": {}})
        )
        router.post("/session/ses_e/message").mock(
            return_value=httpx.Response(200, json={"info": _assistant_message(), "parts": [TEXT_PART]})
        )
        router.post("/session/ses_e/prompt_async").mock(return_value=httpx.Response(204))
        # Interaction polling: nothing pending.
        router.get("/permission").mock(return_value=httpx.Response(200, json=[]))
        router.get("/question").mock(return_value=httpx.Response(200, json=[]))
        sse = (
            f"data: {json.dumps({'type': 'message.part.delta', 'properties': {'sessionID': 'ses_e', 'field': 'text', 'delta': 'hello '}})}\n\n"
            f"data: {json.dumps({'type': 'message.part.delta', 'properties': {'sessionID': 'ses_e', 'field': 'text', 'delta': 'world'}})}\n\n"
            f"data: {json.dumps({'type': 'session.idle', 'properties': {'sessionID': 'ses_e'}})}\n\n"
        ).encode()
        router.get("/event").mock(
            return_value=httpx.Response(200, headers={"Content-Type": "text/event-stream"}, content=sse)
        )
        yield router


def _load(pkg: str) -> ModuleType:
    """Load an example submodule whose path contains a numeric folder name."""
    return importlib.import_module(f"examples.{pkg}")


def _run_cli(module: ModuleType, *args: str) -> None:
    """Run an example's ``cli()`` with forced argv under the respx mock."""
    sys.argv = [module.__file__, *args]
    module.cli()


class TestExamplesSmoke:
    def test_quickstart(self) -> None:
        mod = _load("00_quickstart.quickstart")
        _run_cli(mod, "--url", BASE)

    def test_quickstart_with_directory(self) -> None:
        # 00 必须演示的 --directory 简写调用路径
        mod = _load("00_quickstart.quickstart")
        _run_cli(mod, "--url", BASE, "--directory", "/tmp/scope")

    def test_create_session(self) -> None:
        mod = _load("01_session_management.create_session")
        _run_cli(mod, "--url", BASE, "--title", "t")

    def test_list_sessions(self) -> None:
        # fixture 里 GET /session 返回一条记录，覆盖“非空”分支与表格渲染。
        mod = _load("01_session_management.list_sessions")
        _run_cli(mod, "--url", BASE)

    def test_delete_session(self) -> None:
        mod = _load("01_session_management.delete_session")
        _run_cli(mod, "--url", BASE, "--session", "ses_e")

    def test_error_handling(self) -> None:
        mod = _load("03_advanced_patterns.error_handling")
        _run_cli(mod, "--url", BASE)

    def test_client_reuse(self) -> None:
        mod = _load("03_advanced_patterns.client_reuse")
        _run_cli(mod, "--url", BASE)

    def test_stream_events(self) -> None:
        mod = _load("03_advanced_patterns.stream_events")
        _run_cli(mod, "--url", BASE)

    def test_interact_moving_session(self) -> None:
        mod = _load("03_advanced_patterns.interact_moving_session")
        _run_cli(mod, "--url", BASE)

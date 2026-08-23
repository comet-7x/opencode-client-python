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


def _session_payload(
    session_id: str = "ses_e", title: str = "my session", share: dict[str, Any] | None = None
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": session_id,
        "slug": "s",
        "projectID": "prj",
        "directory": "/tmp",
        "path": "",
        "title": title,
        "version": "1",
        "time": {"created": 1, "updated": 1},
    }
    if share is not None:
        payload["share"] = share
    return payload


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


def _user_message() -> dict[str, Any]:
    return {
        "id": "msg_u",
        "sessionID": "ses_e",
        "role": "user",
        "time": {"created": 1},
        "agent": "build",
        "model": {"providerID": "p", "modelID": "m"},
    }


def _provider_payload() -> dict[str, Any]:
    model: dict[str, Any] = {
        "id": "mock-model",
        "providerID": "mock-provider",
        "api": {},
        "name": "Mock Model",
        "capabilities": {},
    }
    return {
        "all": [
            {
                "id": "mock-provider",
                "name": "Mock",
                "source": "config",
                "env": [],
                "options": {},
                "models": {"mock-model": model},
            }
        ],
        "default": {"mock-provider": "mock-model"},
        "connected": ["mock-provider"],
    }


def _permission_payload() -> dict[str, Any]:
    return {
        "id": "per_1",
        "sessionID": "ses_e",
        "permission": "bash",
        "patterns": ["echo *"],
        "metadata": {},
        "always": ["*"],
    }


def _question_payload() -> dict[str, Any]:
    return {
        "id": "que_1",
        "sessionID": "ses_e",
        "questions": [
            {
                "question": "Pick one",
                "header": "Pick",
                "options": [
                    {"label": "A", "description": "a"},
                    {"label": "B", "description": "b"},
                ],
            }
        ],
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
        # 所有 DELETE /session/{id}（含 fork 分支的清理）都成功。
        # 末尾 $ 锚定：避免吞掉 /session/{id}/share 这类子路径（unshare 另有精确路由）。
        router.route(method="DELETE", path__regex=r"/session/[^/]+$").mock(return_value=httpx.Response(200, json=True))
        router.get("/session/ses_e").mock(return_value=httpx.Response(200, json=_session_payload()))
        # list_sessions 会取到的列表（最新在前的语义在真实服务端保证，这里给一条）。
        router.get("/session").mock(return_value=httpx.Response(200, json=[_session_payload()]))
        # A non-existent session: quickstart/error_handling/lifecycle paths expect 404.
        router.get("/session/ses_does_not_exist_0000").mock(
            return_value=httpx.Response(404, json={"name": "NotFound", "data": {"message": "nope"}})
        )
        router.get("/session/ses_missing_a").mock(
            return_value=httpx.Response(404, json={"name": "NotFound", "data": {}})
        )
        router.get("/session/ses_missing_b").mock(
            return_value=httpx.Response(404, json={"name": "NotFound", "data": {}})
        )
        # —— session_lifecycle 用到的动词端点（全部落在默认会话 ses_e 上）。
        router.patch("/session/ses_e").mock(return_value=httpx.Response(200, json=_session_payload(title="updated")))
        router.post("/session/ses_e/fork").mock(return_value=httpx.Response(200, json=_session_payload("ses_forked")))
        router.post("/session/ses_e/abort").mock(return_value=httpx.Response(200, json=True))
        router.post("/session/ses_e/share").mock(
            return_value=httpx.Response(200, json=_session_payload(share={"url": "https://share.example/s/e"}))
        )
        router.delete("/session/ses_e/share").mock(return_value=httpx.Response(200, json=_session_payload()))
        router.post("/session/ses_e/summarize").mock(return_value=httpx.Response(200, json=True))
        # 消息列表（最新在前：assistant 在 user 之前）；DELETE .../message/{id} 成功。
        router.get("/session/ses_e/message").mock(
            return_value=httpx.Response(
                200,
                json=[
                    {"info": _assistant_message(), "parts": [TEXT_PART]},
                    {"info": _user_message(), "parts": [TEXT_PART]},
                ],
            )
        )
        router.route(method="DELETE", path__regex=r"/session/[^/]+/message/[^/]+").mock(
            return_value=httpx.Response(200, json=True)
        )
        router.post("/session/ses_e/message").mock(
            return_value=httpx.Response(200, json={"info": _assistant_message(), "parts": [TEXT_PART]})
        )
        router.post("/session/ses_e/prompt_async").mock(return_value=httpx.Response(204))
        # —— discovery（02 explore_server）。
        router.get("/config").mock(return_value=httpx.Response(200, json={"share": {"enabled": True}}))
        router.patch("/config").mock(return_value=httpx.Response(200, json={"share": {"enabled": False}}))
        router.get("/provider").mock(return_value=httpx.Response(200, json=_provider_payload()))
        router.get("/agent").mock(
            return_value=httpx.Response(
                200,
                json=[
                    {
                        "name": "build",
                        "mode": "primary",
                        "options": {},
                        "model": {"providerID": "mock-provider", "modelID": "mock-model"},
                    }
                ],
            )
        )
        router.get("/command").mock(
            return_value=httpx.Response(
                200, json=[{"name": "init", "description": "Init", "template": "init", "hints": []}]
            )
        )
        router.get("/skill").mock(
            return_value=httpx.Response(
                200,
                json=[
                    {
                        "name": "demo-skill",
                        "location": "/skills/demo",
                        "content": "# demo\n\nbody",
                        "description": "demo skill",
                    }
                ],
            )
        )
        # —— vcs（03 vcs_workflow）。
        router.get("/vcs").mock(return_value=httpx.Response(200, json={"branch": "develop", "default_branch": "main"}))
        router.get("/vcs/status").mock(
            return_value=httpx.Response(
                200, json=[{"file": "a.py", "additions": 3, "deletions": 1, "status": "modified"}]
            )
        )
        router.get("/vcs/diff").mock(
            return_value=httpx.Response(
                200,
                json=[
                    {
                        "file": "a.py",
                        "patch": "diff --git a/a.py b/a.py\n+line",
                        "additions": 3,
                        "deletions": 1,
                        "status": "modified",
                    }
                ],
            )
        )
        router.get("/vcs/diff/raw").mock(
            return_value=httpx.Response(
                200, headers={"Content-Type": "text/x-diff"}, content="diff --git a/a.py b/a.py\n+line"
            )
        )
        router.post("/vcs/apply").mock(return_value=httpx.Response(200, json={"success": True}))
        # —— mcp（04 mcp_servers）。
        router.get("/mcp").mock(return_value=httpx.Response(200, json={"docs": {"status": "connected"}}))
        router.post("/mcp").mock(return_value=httpx.Response(200, json={"name": "added", "status": "connected"}))
        # —— 交互轮询（05 interact）：各挂一个 pending，主循环一轮内应答完。
        #     注意 route() 对同 method+path 的多次注册是“追加别名”，最后一次生效，
        #     所以 reply 端点只保留一个 payload（与 loop 消费的 per_1/que_1 匹配）。
        router.get("/permission").mock(return_value=httpx.Response(200, json=[_permission_payload()]))
        router.post("/permission/per_1/reply").mock(return_value=httpx.Response(200, json=True))
        router.get("/question").mock(return_value=httpx.Response(200, json=[_question_payload()]))
        router.post("/question/que_1/reply").mock(return_value=httpx.Response(200, json=True))
        router.post("/question/que_1/reject").mock(return_value=httpx.Response(200, json=True))
        # 会话级权限端点（sessions.respond_permission）。
        router.route(method="POST", path__regex=r"/session/[^/]+/permissions/[^/]+").mock(
            return_value=httpx.Response(200, json=True)
        )
        sse = (
            f"data: {json.dumps({'type': 'message.part.updated', 'properties': {'sessionID': 'ses_e', 'part': {'id': 'prt_t', 'type': 'text', 'text': '', 'messageID': 'msg_a', 'sessionID': 'ses_e'}}})}\n\n"
            f"data: {json.dumps({'type': 'message.part.delta', 'properties': {'sessionID': 'ses_e', 'partID': 'prt_t', 'field': 'text', 'delta': 'hello '}})}\n\n"
            f"data: {json.dumps({'type': 'message.part.delta', 'properties': {'sessionID': 'ses_e', 'partID': 'prt_t', 'field': 'text', 'delta': 'world'}})}\n\n"
            f"data: {json.dumps({'type': 'message.part.updated', 'properties': {'sessionID': 'ses_e', 'part': {'id': 'prt_t', 'type': 'text', 'text': 'hello world', 'messageID': 'msg_a', 'sessionID': 'ses_e'}}})}\n\n"
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

    def test_list_messages(self) -> None:
        mod = _load("01_session_management.list_messages")
        _run_cli(mod, "--url", BASE, "--session", "ses_e")

    def test_session_lifecycle(self) -> None:
        mod = _load("01_session_management.session_lifecycle")
        _run_cli(mod, "--url", BASE)

    def test_explore_server(self) -> None:
        mod = _load("02_discovery_config.explore_server")
        _run_cli(mod, "--url", BASE)

    def test_explore_server_with_config_patch(self) -> None:
        mod = _load("02_discovery_config.explore_server")
        _run_cli(mod, "--url", BASE, "--set-config", '{"share": {"enabled": false}}')

    def test_vcs_workflow(self) -> None:
        mod = _load("03_vcs.vcs_workflow")
        _run_cli(mod, "--url", BASE, "--directory", "/tmp")

    def test_mcp_servers(self) -> None:
        mod = _load("04_mcp.mcp_servers")
        _run_cli(mod, "--url", BASE)

    def test_error_handling(self) -> None:
        mod = _load("05_advanced_patterns.error_handling")
        _run_cli(mod, "--url", BASE)

    def test_client_reuse(self) -> None:
        mod = _load("05_advanced_patterns.client_reuse")
        _run_cli(mod, "--url", BASE)

    def test_stream_events(self) -> None:
        mod = _load("05_advanced_patterns.stream_events")
        _run_cli(mod, "--url", BASE)

    def test_interact_moving_session(self) -> None:
        mod = _load("05_advanced_patterns.interact_moving_session")
        _run_cli(mod, "--url", BASE)

    def test_interact_with_respond_verbs(self) -> None:
        # --respond 额外走 sessions.respond_permission + server.reject_question
        mod = _load("05_advanced_patterns.interact_moving_session")
        _run_cli(mod, "--url", BASE, "--respond")

    def test_raw_response(self) -> None:
        mod = _load("05_advanced_patterns.raw_response")
        _run_cli(mod, "--url", BASE)

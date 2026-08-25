"""respx 驱动的 examples 冒烟：离线跑各教学脚本的 cli() 入口。

每个示例脚本都暴露一个纯 CLI 入口（argparse + ``asyncio.run``），因此这里
直接给 ``sys.argv`` 喂参数、再在 respx mock 下调用它们的 ``cli()``，即可
完整走过一次真实管线而不依赖真实 opencode 服务。
（`streaming` 脚本里的真实 sleep 只有 0.5s，套件仍可秒级跑完。）

目录按功能模块组织（quickstart/sessions/server/events/vcs/mcp/client），
均为合法 Python 标识符，经
``importlib.import_module("examples.quickstart.quickstart")`` 加载。
"""

from __future__ import annotations

import importlib
import json
import sys
from collections.abc import Generator
from pathlib import Path
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


def _part_updated_event(text: str) -> dict[str, Any]:
    """One ``message.part.updated`` SSE event (wire shape: sessionID+part+time, all required)."""
    return {
        "type": "message.part.updated",
        "properties": {
            "sessionID": "ses_e",
            "part": {"id": "prt_t", "type": "text", "text": text, "messageID": "msg_a", "sessionID": "ses_e"},
            "time": 1,
        },
    }


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
        # ses_missing_a 的 404 特例必须先注册（respx 先注册先匹配）。
        router.route(method="DELETE", path__regex=r"/session/ses_missing_a$").mock(
            return_value=httpx.Response(404, json={"name": "NotFound", "data": {"message": "nope"}})
        )
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
                    {
                        "info": _assistant_message(),
                        "parts": [
                            TEXT_PART,
                            # 覆盖 list_messages 的其余 part 分支：tool/reasoning/step-finish
                            {
                                "id": "prt_tool",
                                "sessionID": "ses_e",
                                "messageID": "msg_a",
                                "type": "tool",
                                "callID": "call_1",
                                "tool": "bash",
                                "state": {
                                    "status": "completed",
                                    "input": {"command": "ls"},
                                    "output": "a.py",
                                    "title": "ls",
                                    "time": {"start": 1.0, "end": 2.0},
                                },
                            },
                            {
                                "id": "prt_r",
                                "sessionID": "ses_e",
                                "messageID": "msg_a",
                                "type": "reasoning",
                                "text": "thinking...",
                                "time": {"start": 1, "end": 2},
                            },
                            {
                                "id": "prt_sf",
                                "sessionID": "ses_e",
                                "messageID": "msg_a",
                                "type": "step-finish",
                                "reason": "stop",
                                "cost": 0.5,
                                "tokens": {
                                    "total": 2.0,
                                    "input": 1,
                                    "output": 1,
                                    "reasoning": 0,
                                    "cache": {"read": 0, "write": 0},
                                },
                            },
                        ],
                    },
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
        # —— projects + 系统信息（explore_projects）。
        # explore_projects 的空分支（--directory /empty-scope 时）。
        router.get("/project", params={"directory": "/empty-scope"}).mock(return_value=httpx.Response(200, json=[]))
        router.get("/project/current", params={"directory": "/empty-scope"}).mock(
            return_value=httpx.Response(404, json={"name": "NotFound", "data": {}})
        )
        router.get("/lsp", params={"directory": "/empty-scope"}).mock(return_value=httpx.Response(200, json=[]))

        router.get("/project").mock(
            return_value=httpx.Response(
                200,
                json=[
                    {
                        "id": "prj_1",
                        "worktree": "/tmp/proj",
                        "name": "demo",
                        "vcs": "git",
                        "time": {"created": 1000, "updated": 2000},
                        "sandboxes": [],
                    }
                ],
            )
        )
        router.get("/project/current").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "prj_1",
                    "worktree": "/tmp/proj",
                    "time": {"created": 1000, "updated": 2000},
                    "sandboxes": [],
                },
            )
        )
        router.get("/path").mock(
            return_value=httpx.Response(
                200,
                json={
                    "home": "/home/u",
                    "state": "/s",
                    "config": "/c",
                    "worktree": "/w",
                    "directory": "/d",
                },
            )
        )
        router.get("/lsp").mock(
            return_value=httpx.Response(
                200, json=[{"id": "pyright", "name": "pyright", "root": "/tmp/proj", "status": "connected"}]
            )
        )
        router.post("/log").mock(return_value=httpx.Response(200, json=True))
        router.put(path__regex=r"/auth/[^/]+").mock(return_value=httpx.Response(200, json=True))
        router.delete(path__regex=r"/auth/[^/]+").mock(return_value=httpx.Response(200, json=True))
        # —— mcp（04 mcp_servers）。
        router.get("/mcp").mock(
            return_value=httpx.Response(
                200,
                json={
                    "docs": {"status": "connected"},
                    "search": {"status": "failed", "error": "spawn ENOENT"},
                    "notes": {"status": "disabled"},
                    "authed": {"status": "needs_auth"},
                },
            )
        )
        router.post("/mcp").mock(return_value=httpx.Response(200, json={"name": "added", "status": "connected"}))
        # —— mcp 生命周期（--oauth remote 演示段）。
        router.post("/mcp/remote/auth").mock(
            return_value=httpx.Response(
                200,
                json={"authorizationUrl": "https://auth.example/authorize", "oauthState": "st-1"},
            )
        )
        router.post("/mcp/remote/auth/authenticate").mock(
            return_value=httpx.Response(200, json={"status": "needs_auth"})
        )
        router.post("/mcp/remote/connect").mock(return_value=httpx.Response(200, json=True))
        router.post("/mcp/remote/disconnect").mock(return_value=httpx.Response(200, json=True))
        # --oauth local：演示"服务端拒绝 OAuth"分支（400）与其后的连接管理。
        router.post("/mcp/local/auth").mock(return_value=httpx.Response(400, json={"name": "BadRequest", "data": {}}))
        router.post("/mcp/local/auth/authenticate").mock(return_value=httpx.Response(200, json={"status": "connected"}))
        router.post("/mcp/local/connect").mock(return_value=httpx.Response(200, json=True))
        router.post("/mcp/local/disconnect").mock(return_value=httpx.Response(200, json=True))
        # —— files（browse_files / search_code）。
        # 参数级路由（特例先注册）：空目录分支。
        router.get("/file", params={"path": "emptydir"}).mock(return_value=httpx.Response(200, json=[]))
        router.get("/file").mock(
            return_value=httpx.Response(
                200,
                json=[
                    {"name": "src", "path": "src", "absolute": "/tmp/proj/src", "type": "directory", "ignored": False},
                    {"name": "a.py", "path": "a.py", "absolute": "/tmp/proj/a.py", "type": "file", "ignored": False},
                ],
            )
        )
        # 参数级路由（先于通用路由的特例）：二进制 / 404。
        router.get("/file/content", params={"path": "logo.png"}).mock(
            return_value=httpx.Response(
                200, json={"type": "binary", "content": "aGVsbG8=", "encoding": "base64", "mimeType": "image/png"}
            )
        )
        router.get("/file/content", params={"path": "missing.txt"}).mock(
            return_value=httpx.Response(404, json={"name": "NotFound", "data": {"message": "nope"}})
        )
        router.get("/file/content").mock(
            return_value=httpx.Response(
                200,
                json={
                    "type": "text",
                    "content": "print('hi')\n",
                    # 覆盖 browse_files 的"未保存改动"展示分支
                    "diff": "-old\n+new\n",
                },
            )
        )
        router.get("/file/status").mock(
            return_value=httpx.Response(200, json=[{"path": "a.py", "added": 2, "removed": 1, "status": "modified"}])
        )
        router.get("/formatter").mock(
            return_value=httpx.Response(200, json=[{"name": "ruff", "extensions": [".py"], "enabled": True}])
        )
        # search_code 空命中分支（三个搜索目标都传 zzz 时命中这些特例路由）。
        router.get("/find", params={"pattern": "zzz"}).mock(return_value=httpx.Response(200, json=[]))
        router.get("/find/file", params={"query": "zzz"}).mock(return_value=httpx.Response(200, json=[]))
        router.get("/find/symbol", params={"query": "zzz"}).mock(return_value=httpx.Response(200, json=[]))

        router.get("/find").mock(
            return_value=httpx.Response(
                200,
                json=[
                    {
                        "path": {"text": "a.py"},
                        "lines": {"text": "print('hi')\n"},
                        "line_number": 0,
                        "absolute_offset": 0,
                        "submatches": [{"match": {"text": "hi"}, "start": 7, "end": 9}],
                    }
                ],
            )
        )
        router.get("/find/file").mock(return_value=httpx.Response(200, json=["a.py"]))
        router.get("/find/symbol").mock(
            return_value=httpx.Response(
                200,
                json=[
                    {
                        "name": "main",
                        "kind": 12,
                        "location": {
                            "uri": "file:///tmp/proj/a.py",
                            "range": {
                                "start": {"line": 0, "character": 0},
                                "end": {"line": 0, "character": 4},
                            },
                        },
                    }
                ],
            )
        )
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
        # —— session_state_history（01）。
        router.get("/session/status").mock(
            return_value=httpx.Response(200, json={"ses_e": {"type": "busy"}, "ses_other": {"type": "idle"}})
        )
        router.route(method="GET", path__regex=r"/session/[^/]+/children").mock(
            return_value=httpx.Response(200, json=[_session_payload("ses_child")])
        )
        router.route(method="GET", path__regex=r"/session/[^/]+/todo").mock(
            return_value=httpx.Response(
                200,
                json=[
                    {"content": "create demo.txt", "status": "completed", "priority": "medium"},
                ],
            )
        )
        router.route(method="GET", path__regex=r"/session/[^/]+/diff").mock(
            return_value=httpx.Response(
                200,
                json=[{"file": "demo.txt", "additions": 1, "deletions": 0, "status": "added"}],
            )
        )
        router.route(method="POST", path__regex=r"/session/[^/]+/revert$").mock(
            return_value=httpx.Response(200, json=_session_payload() | {"revert": {"messageID": "msg_a"}})
        )
        router.route(method="POST", path__regex=r"/session/[^/]+/unrevert").mock(
            return_value=httpx.Response(200, json=_session_payload())
        )
        # part.updated 的 wire 形状（/doc 导出）：sessionID + part + time 均必填。
        sse = (
            f"data: {json.dumps(_part_updated_event(''))}\n\n"
            f"data: {json.dumps({'type': 'message.part.delta', 'properties': {'sessionID': 'ses_e', 'partID': 'prt_t', 'field': 'text', 'delta': 'hello '}})}\n\n"
            f"data: {json.dumps({'type': 'message.part.delta', 'properties': {'sessionID': 'ses_e', 'partID': 'prt_t', 'field': 'text', 'delta': 'world'}})}\n\n"
            f"data: {json.dumps(_part_updated_event('hello world'))}\n\n"
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
        mod = _load("quickstart.quickstart")
        _run_cli(mod, "--url", BASE)

    def test_quickstart_with_directory(self) -> None:
        # 00 必须演示的 --directory 简写调用路径
        mod = _load("quickstart.quickstart")
        _run_cli(mod, "--url", BASE, "--directory", "/tmp/scope")

    def test_create_session(self) -> None:
        mod = _load("sessions.create_session")
        _run_cli(mod, "--url", BASE, "--title", "t")

    def test_list_sessions(self) -> None:
        # fixture 里 GET /session 返回一条记录，覆盖“非空”分支与表格渲染。
        mod = _load("sessions.list_sessions")
        _run_cli(mod, "--url", BASE)

    def test_delete_session(self) -> None:
        mod = _load("sessions.delete_session")
        _run_cli(mod, "--url", BASE, "--session", "ses_e")

    def test_delete_missing_session(self) -> None:
        # OpenCodeNotFoundError 分支：删除不存在的会话
        mod = _load("sessions.delete_session")
        _run_cli(mod, "--url", BASE, "--session", "ses_missing_a")

    def test_list_messages(self) -> None:
        mod = _load("sessions.list_messages")
        _run_cli(mod, "--url", BASE, "--session", "ses_e")

    def test_list_messages_auto_latest(self) -> None:
        # 不传 --session：自动取最新会话的分支
        mod = _load("sessions.list_messages")
        _run_cli(mod, "--url", BASE)

    def test_session_lifecycle(self) -> None:
        mod = _load("sessions.session_lifecycle")
        _run_cli(mod, "--url", BASE)

    def test_session_state_history(self) -> None:
        mod = _load("sessions.session_state_history")
        _run_cli(mod, "--url", BASE)

    def test_explore_server(self) -> None:
        mod = _load("server.explore_server")
        _run_cli(mod, "--url", BASE)

    def test_explore_server_with_config_patch(self) -> None:
        mod = _load("server.explore_server")
        _run_cli(mod, "--url", BASE, "--set-config", '{"share": {"enabled": false}}')

    def test_vcs_workflow(self) -> None:
        mod = _load("vcs.vcs_workflow")
        _run_cli(mod, "--url", BASE, "--directory", "/tmp")

    def test_vcs_workflow_save_and_apply(self, tmp_path: Path) -> None:
        # --save 落盘 + --apply 打补丁两个 opt-in 分支
        mod = _load("vcs.vcs_workflow")
        patch_file = tmp_path / "patch.diff"
        patch_file.write_text("diff --git a/a.py b/a.py\n+line\n", encoding="utf-8")
        save_to = tmp_path / "out.diff"
        _run_cli(mod, "--url", BASE, "--directory", "/tmp", "--save", str(save_to), "--apply", str(patch_file))
        assert "diff --git" in save_to.read_text(encoding="utf-8")

    def test_explore_projects_empty_scope(self) -> None:
        # 空项目清单 + current 404 + 空 LSP 三个分支
        mod = _load("projects.explore_projects")
        _run_cli(mod, "--url", BASE, "--directory", "/empty-scope")

    def test_mcp_servers(self) -> None:
        mod = _load("mcp.mcp_servers")
        _run_cli(mod, "--url", BASE)

    def test_mcp_add_server(self) -> None:
        # --name 注册流（local config 组装 + add + 回读 status）
        mod = _load("mcp.mcp_servers")
        _run_cli(mod, "--url", BASE, "--name", "fs", "--command", "npx,-y,@foo/bar")

    def test_mcp_oauth_lifecycle(self) -> None:
        mod = _load("mcp.mcp_servers")
        _run_cli(mod, "--url", BASE, "--oauth", "remote")

    def test_mcp_oauth_rejected(self) -> None:
        # start_oauth 被服务端拒绝（400）的分支 + 其后的 authenticate/connect/disconnect
        mod = _load("mcp.mcp_servers")
        _run_cli(mod, "--url", BASE, "--oauth", "local")

    def test_explore_projects(self) -> None:
        mod = _load("projects.explore_projects")
        _run_cli(mod, "--url", BASE, "--log", "--auth-demo")

    def test_browse_files(self) -> None:
        mod = _load("files.browse_files")
        _run_cli(mod, "--url", BASE, "--path", "src", "--read", "a.py")

    def test_browse_files_binary_and_empty(self) -> None:
        # 二进制判联合分支 + 空目录分支
        mod = _load("files.browse_files")
        _run_cli(mod, "--url", BASE, "--path", "emptydir", "--read", "logo.png")

    def test_browse_files_read_404(self) -> None:
        # OpenCodeApiError 兜底分支：读不存在的文件
        mod = _load("files.browse_files")
        with pytest.raises(SystemExit) as excinfo:
            _run_cli(mod, "--url", BASE, "--read", "missing.txt")
        assert excinfo.value.code == 1

    def test_search_code(self) -> None:
        mod = _load("files.search_code")
        _run_cli(mod, "--url", BASE, "--pattern", "hi", "--find-file", "a", "--symbol", "main")

    def test_search_code_empty_hits(self) -> None:
        # 三个"无命中"展示分支
        mod = _load("files.search_code")
        _run_cli(mod, "--url", BASE, "--pattern", "zzz", "--find-file", "zzz", "--symbol", "zzz")

    def test_search_code_no_args_exits(self) -> None:
        # 不给任何搜索目标：usage 提示 + exit 2
        mod = _load("files.search_code")
        with pytest.raises(SystemExit) as excinfo:
            _run_cli(mod, "--url", BASE)
        assert excinfo.value.code == 2

    def test_error_handling(self) -> None:
        mod = _load("client.error_handling")
        _run_cli(mod, "--url", BASE)

    def test_client_reuse(self) -> None:
        mod = _load("client.client_reuse")
        _run_cli(mod, "--url", BASE)

    def test_stream_events(self) -> None:
        mod = _load("events.stream_events")
        _run_cli(mod, "--url", BASE)

    def test_event_router(self) -> None:
        mod = _load("events.event_router")
        _run_cli(mod, "--url", BASE)

    def test_interact_moving_session(self) -> None:
        mod = _load("sessions.interact_moving_session")
        _run_cli(mod, "--url", BASE)

    def test_interact_with_respond_verbs(self) -> None:
        # --respond 额外走 sessions.respond_permission + server.reject_question
        mod = _load("sessions.interact_moving_session")
        _run_cli(mod, "--url", BASE, "--respond")

    def test_raw_response(self) -> None:
        mod = _load("client.raw_response")
        _run_cli(mod, "--url", BASE)

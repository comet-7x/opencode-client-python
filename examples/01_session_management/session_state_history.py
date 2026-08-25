"""01 session_state_history: observe and rewind a session's state.

Companion to ``session_lifecycle.py`` (verbs) — this one covers the
*observation & history* half of ``client.sessions.*``:

- ``status()``     -> run state of every active session (idle/busy/retry)
- ``children()``   -> subagent/task sessions spawned by this session
- ``list_todos()`` -> the todo list the agent's todo tool wrote
- ``diff()``       -> per-file changes made by the session's messages
- ``revert()`` / ``unrevert()`` -> rewind history to a message, then restore

The session is created fresh and deleted at the end.

Run (from the repo root):

    uv run python -m examples.01_session_management.session_state_history
"""

from __future__ import annotations

import argparse  # --url/--provider/--model
import asyncio  # 事件循环
import sys  # 退出码

from opencode_client import (
    AsyncOpenCodeClient,
    CreateSessionRequest,
    OpenCodeApiError,
    OpenCodeTransportError,
)

BASE_URL = "http://127.0.0.1:4096"


async def main(base_url: str, provider_flag: str | None, model_flag: str | None) -> None:
    """Run every state/history read plus one revert round-trip.

    Args:
        base_url: server base URL.
        provider_flag: 可选，prompt 用的 provider（缺省用 connected 的第一个）。
        model_flag: 可选，prompt 用的 model（缺省由服务端会话默认决定）。
    """
    async with AsyncOpenCodeClient(base_url) as client:
        session = await client.sessions.create(body=CreateSessionRequest(title="01 state/history demo"))
        print(f"== 基线会话 ==\ncreated   : {session.id}")

        try:
            # —— 先造一轮对话，后面的 diff/revert 才有东西可看。
            providers = await client.server.list_providers()
            pid = provider_flag or (providers.connected[0] if providers.connected else None)
            reply = None
            if pid is not None:
                # --model 只在同时知道 provider 时才有意义（wire 是 provider/model 对）。
                model = {"providerID": pid, "modelID": model_flag} if model_flag else None
                reply = await client.sessions.prompt(
                    session.id,
                    "Create a file named demo.txt containing 'hello'.",
                    model=model,
                )
                print(f"prompt    : assistant 回复 {reply.info.id}")
            else:
                print("prompt    : 无可用 provider，跳过（后续观察类调用仍演示）")

            # —— status：所有活跃会话的运行状态（idle/busy/retry 判别联合）。
            status = await client.sessions.status()
            mine = status.get(session.id)
            kind = type(mine).__name__ if mine else "（未在状态表中）"
            print(f"status    : {len(status)} 个会话，本会话 -> {kind}")

            # —— children：本会话派生的子会话（subagent/task），通常为空。
            children = await client.sessions.children(session.id)
            print(f"children  : {len(children)} 个子会话")

            # —— todos：agent 的 todo 工具写下的任务列表。
            todos = await client.sessions.list_todos(session.id)
            for todo in todos:
                print(f"todo      : [{todo.status}] {todo.content}（{todo.priority}）")
            if not todos:
                print("todo      : （空——本轮没有触发 todo 工具）")

            # —— diff：会话消息造成的文件改动（additions/deletions + 可选 patch）。
            diffs = await client.sessions.diff(session.id)
            for item in diffs:
                print(f"diff      : {item.file} +{item.additions}/-{item.deletions} ({item.status})")
            if not diffs:
                print("diff      : （无文件改动）")

            # —— revert / unrevert：把历史回退到某条消息之前，再恢复。
            #    会话忙时服务端返回 409 -> OpenCodeConflictError。
            if reply is not None:
                reverted = await client.sessions.revert(session.id, reply.info.id)
                print(f"revert    : revert 字段={reverted.revert is not None}")
                restored = await client.sessions.unrevert(session.id)
                print(f"unrevert  : revert 字段已清除={restored.revert is None}")
        finally:
            await client.sessions.delete(session.id)
            print(f"cleanup   : 已删除会话 {session.id}")


def cli() -> None:
    """Parse args, run main, translate library errors into exit codes."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=BASE_URL, help="opencode server base URL")
    parser.add_argument("--provider", default=None, help="provider id for prompt (default: first connected)")
    parser.add_argument("--model", default=None, help="model id for prompt (default: session default)")
    args = parser.parse_args()

    try:
        asyncio.run(main(args.url, args.provider, args.model))
    except OpenCodeApiError as exc:
        print(f"[OpenCodeApiError] HTTP {exc.status_code}: {exc.payload}", file=sys.stderr)
        raise SystemExit(1) from exc
    except OpenCodeTransportError as exc:
        print(f"[transport] 无法完成与 {args.url} 的通信：{exc}", file=sys.stderr)
        print("  提示：确认服务已启动，例如 `opencode serve --port 4096`，或用 --url 指定。", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    cli()

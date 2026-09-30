"""session_state_history：观察会话运行状态，回放/恢复它的历史。

与 ``session_lifecycle.py``（动作类动词）互补，本脚本覆盖
``client.sessions.*`` 的**观察与历史**半边：

- ``status()``     → 所有活跃会话的运行状态（idle/busy/retry 判别联合）
- ``children()``   → 本会话派生的子会话（subagent/task）
- ``list_todos()`` → agent 的 todo 工具写下的任务清单
- ``diff()``       → 会话消息造成的 per-file 改动
- ``revert()``/``unrevert()`` → 把历史回退到某条消息之前，再恢复

会话现场新建、结束删除。

运行（仓库根目录）::

    uv run python -m examples.sessions.session_state_history
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from opencode_client import AsyncOpenCodeClient, CreateSessionRequest, OpenCodeApiError, OpenCodeTransportError

BASE_URL = "http://127.0.0.1:4096"


async def main(base_url: str, provider_flag: str | None, model_flag: str | None) -> None:
    """跑一遍全部状态/历史读取，外加一轮 revert 往返。

    Args:
        base_url: 服务地址。
        provider_flag: 可选，prompt 用的 provider（缺省用 connected 的第一个）。
        model_flag: 可选，prompt 用的 model（缺省由服务端会话默认决定）。
    """
    async with AsyncOpenCodeClient(base_url) as client:
        session = await client.sessions.create(body=CreateSessionRequest(title="state/history demo"))
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

            # status：所有活跃会话的运行状态（idle/busy/retry 判别联合）。
            status = await client.sessions.status()
            mine = status.get(session.id)
            kind = type(mine).__name__ if mine else "（未在状态表中）"
            print(f"status    : {len(status)} 个会话，本会话 -> {kind}")

            # children：本会话派生的子会话（subagent/task），通常为空。
            children = await client.sessions.children(session.id)
            print(f"children  : {len(children)} 个子会话")

            # todos：agent 的 todo 工具写下的任务清单。
            todos = await client.sessions.list_todos(session.id)
            for todo in todos:
                print(f"todo      : [{todo.status}] {todo.content}（{todo.priority}）")
            if not todos:
                print("todo      : （空——本轮没有触发 todo 工具）")

            # diff：会话消息造成的文件改动（additions/deletions + 可选 patch）。
            diffs = await client.sessions.diff(session.id)
            for item in diffs:
                print(f"diff      : {item.file} +{item.additions}/-{item.deletions} ({item.status})")
            if not diffs:
                print("diff      : （无文件改动）")

            # revert / unrevert：把历史回退到某条消息之前，再恢复。
            # 会话忙时服务端返回 409 -> OpenCodeConflictError。
            if reply is not None:
                reverted = await client.sessions.revert(session.id, reply.info.id)
                print(f"revert    : revert 字段={reverted.revert is not None}")
                restored = await client.sessions.unrevert(session.id)
                print(f"unrevert  : revert 字段已清除={restored.revert is None}")
        finally:
            await client.sessions.delete(session.id)
            print(f"cleanup   : 已删除会话 {session.id}")


def cli() -> None:
    """解析参数并运行 main。"""
    parser = argparse.ArgumentParser(description="观察会话状态并回放/恢复历史")
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
        print(f"[transport] 无法连接 {args.url}：{exc}", file=sys.stderr)
        print("  提示：确认服务已启动，例如 `opencode serve --port 4096`，或用 --url 指定正确地址。", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    cli()

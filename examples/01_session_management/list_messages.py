"""01 list_messages: render a session's message history (info + parts).

Shows ``sessions.list_messages(session_id)`` — it returns
``MessageWithParts`` items, **newest first**, each with:

- ``info``: a discriminated union of ``UserMessage | AssistantMessage``
  (use ``isinstance`` to narrow before reading role-specific fields);
- ``parts``: the ordered list of typed parts (text/tool/reasoning/...).

Run (from the repo root):

    uv run python -m examples.01_session_management.list_messages
    uv run python -m examples.01_session_management.list_messages --session ses_XXXX --limit 5
    uv run python examples/01_session_management/list_messages.py
"""

from __future__ import annotations

import argparse  # --session/--limit/--url
import asyncio  # 事件循环
import sys  # 退出码

from opencode_client import (
    AssistantMessage,  # 用于 isinstance 收窄联合类型
    AsyncOpenCodeClient,
    OpenCodeApiError,
    OpenCodeTransportError,
    Part,  # parts 列表元素的（联合）类型
)

BASE_URL = "http://127.0.0.1:4096"


def _render_parts(parts: list[Part]) -> None:
    """Print one message's parts as readable one-liners.

    Args:
        parts: the part list of one ``MessageWithParts``.
    """
    for part in parts:
        # parts 是按 type 判别的联合；按 .type 分支，取每种 part 收窄后可用的字段。
        if part.type == "text":
            # 长文本截断，保持屏幕可读
            print(f"  text      : {part.text[:120]!r}")
        elif part.type == "tool":
            # title 只存在于 running/completed 状态，用 getattr 兜底安全读
            print(f"  tool      : {part.tool} [{part.state.status}] {getattr(part.state, 'title', '') or '-'}")
        elif part.type == "reasoning":
            # 推理原文通常不整段打印，仅给长度
            print(f"  reasoning : {len(part.text)} chars")
        elif part.type == "step-finish":
            # 每次工具/步骤结束的汇总：终止原因 + 花费
            print(f"  step-finish: reason={part.reason} cost={part.cost}")
        else:
            # 未来新增的 part 类型不至于让整个脚本崩溃
            print(f"  part      : {part.type}")


async def main(base_url: str, session_id: str | None, limit: int) -> None:
    """Print the message history of one session.

    Args:
        base_url: server base URL.
        session_id: 要展示历史的会话；为 None 时自动取最新的一个。
        limit: 最多取多少条（服务端最新在前）。
    """
    async with AsyncOpenCodeClient(base_url) as client:
        # 没指定会话就取“最新一个”（list_sessions 也是最新在前），让脚本开箱即用。
        target = session_id
        if target is None:
            sessions = await client.sessions.list_sessions(limit=1)
            if not sessions:
                print("服务端还没有任何会话（先跑一次 00_quickstart，或用 --session 指定）。")
                return
            target = sessions[0].id
            print(f"取最新会话：{target}\n")

        # —— 真正的调用：返回该会话的消息，**最新在前**。
        #    limit / before 是可选查询参数（before = 只取该 id 之前更旧的消息）。
        messages = await client.sessions.list_messages(target, limit=limit)
        print(f"--- {target}: {len(messages)} messages（按时间正序展示）---\n")

        # reversed：服务端给的是最新在前，对话习惯从最早读起，故反转展示。
        for msg in reversed(messages):
            info = msg.info  # 联合类型：user 或 assistant
            if isinstance(info, AssistantMessage):
                # 只有 assistant 消息带 finish（终止方式）
                print(f"[assistant] {info.id}  finish={info.finish}")
            else:
                print(f"[user] {info.id}")
            _render_parts(msg.parts)
            print()  # 消息之间空一行


def cli() -> None:
    """Parse args, run main, translate errors into exit codes."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=BASE_URL, help="opencode server base URL")
    parser.add_argument("--session", default=None, help="session id (default: the newest one)")
    parser.add_argument("--limit", type=int, default=50, help="max messages to show")
    args = parser.parse_args()

    try:
        asyncio.run(main(args.url, args.session, args.limit))
    except OpenCodeApiError as exc:
        print(f"[OpenCodeApiError] HTTP {exc.status_code}: {exc.payload}", file=sys.stderr)
        raise SystemExit(1) from exc
    except OpenCodeTransportError as exc:
        print(f"[transport] 无法完成与 {args.url} 的通信：{exc}", file=sys.stderr)
        print("  提示：确认服务已启动，例如 `opencode serve --port 4096`，或用 --url 指定。", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    cli()

"""list_messages：读会话历史——info 与 parts 两层联合类型的渲染。

``sessions.list_messages`` 返回 ``MessageWithParts`` 列表，**最新在前**：

- ``msg.info``  —— user/assistant 的判别联合（isinstance 收窄后才能读
  各自字段，如 ``tokens`` 只在 assistant 上）；
- ``msg.parts`` —— 有序的 part 列表（text/tool/reasoning/...），按 ``type``
  分支渲染。

运行（仓库根目录）::

    uv run python -m examples.sessions.list_messages
    uv run python -m examples.sessions.list_messages --session ses_XXXX --limit 5
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from opencode_client import AssistantMessage, AsyncOpenCodeClient, OpenCodeApiError, OpenCodeTransportError, Part

BASE_URL = "http://127.0.0.1:4096"


def _render_parts(parts: list[Part]) -> None:
    """把一条消息的 parts 渲染成可读行。

    Args:
        parts: 一条 MessageWithParts 的 part 列表。
    """
    for part in parts:
        # Part 是按 type 判别的联合；分支后各类型才有自己的专属字段。
        if part.type == "text":
            print(f"  text       : {part.text[:120]!r}")  # 长文本截断保持可读
        elif part.type == "tool":
            # title 只存在于 running/completed 状态，getattr 兜底安全读。
            title = getattr(part.state, "title", "") or "-"
            print(f"  tool       : {part.tool} [{part.state.status}] {title}")
        elif part.type == "reasoning":
            print(f"  reasoning  : {len(part.text)} chars")  # 推理原文只给长度
        elif part.type == "step-finish":
            print(f"  step-finish: reason={part.reason} cost={part.cost}")
        else:
            # 未来新增的 part 类型不至于让脚本崩溃：打印类型名即可。
            print(f"  part       : {part.type}")


async def main(base_url: str, session_id: str | None, limit: int) -> None:
    """展示一个会话的消息历史。

    Args:
        base_url: 服务地址。
        session_id: 目标会话；None 时自动取最新会话。
        limit: 最多取多少条。
    """
    async with AsyncOpenCodeClient(base_url) as client:
        target = session_id
        if target is None:
            sessions = await client.sessions.list_sessions(limit=1)
            if not sessions:
                print("服务端还没有任何会话（先跑一次 quickstart，或用 --session 指定）。")
                return
            target = sessions[0].id
            print(f"取最新会话：{target}\n")

        messages = await client.sessions.list_messages(target, limit=limit)
        print(f"--- {target}: {len(messages)} messages（服务端最新在前，这里反转为对话顺序展示）---\n")

        for msg in reversed(messages):
            info = msg.info
            if isinstance(info, AssistantMessage):
                print(f"[assistant] {info.id}  finish={info.finish}")
            else:
                print(f"[user] {info.id}")
            _render_parts(msg.parts)
            print()


def cli() -> None:
    """解析参数并运行 main。"""
    parser = argparse.ArgumentParser(description="浏览会话历史")
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
        print(f"[transport] 无法连接 {args.url}：{exc}", file=sys.stderr)
        print("  提示：确认服务已启动，例如 `opencode serve --port 4096`，或用 --url 指定正确地址。", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    cli()

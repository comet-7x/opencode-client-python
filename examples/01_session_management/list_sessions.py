"""01 list_sessions: list sessions, newest first, with optional filters.

Shows ``sessions.list_sessions`` and its query filters (limit, search, ...),
and makes the result ordering explicit: the server returns sessions
**newest first**.

Run (from the repo root):

    uv run python -m examples.01_session_management.list_sessions
    uv run python -m examples.01_session_management.list_sessions --limit 5 --search quick
    uv run python examples/01_session_management/list_sessions.py
"""

from __future__ import annotations

import argparse  # 解析 --limit/--search/--url
import asyncio  # 事件循环
import sys  # 退出码

from opencode_client import (
    AsyncOpenCodeClient,
    OpenCodeApiError,
    OpenCodeTransportError,
    Session,  # 列表里每个元素的类型
)

BASE_URL = "http://127.0.0.1:4096"


def _one_line(s: Session) -> str:
    """Render one session as a single readable table row.

    Args:
        s: A :class:`Session` to summarise.
    """
    model = f"{s.model.provider_id}/{s.model.id}" if s.model else "-"
    # f-string 的 :>6 让更新时间的宽度对齐，肉眼更易扫读。
    return f"{s.id:<24} {s.title!r:<28} {model:<24} updated={s.time.updated:>6}"


async def main(base_url: str, limit: int, search: str | None) -> None:
    """List and print the sessions found on the server.

    Args:
        base_url: server base URL.
        limit: 最多取多少条（服务端按最新在前排序）。
        search: 可选关键词过滤（匹配标题等）。
    """
    async with AsyncOpenCodeClient(base_url) as client:
        # —— 调用。每个过滤参数都是 None 时省略；结果“最新在前”。
        sessions = await client.sessions.list_sessions(limit=limit, search=search)

        # 空列表是合法状态（全新服务器），明确打印而不是留白。
        if not sessions:
            print("没有匹配的会话。")
            return

        # 表头 + 每行一个会话。列宽与 _one_line 保持一致，方便肉眼比较。
        print(f"{'id':<24} {'title':<28} {'model':<24} {'updated':>14}")
        for s in sessions:
            print(_one_line(s))
        print(f"\n共 {len(sessions)} 个会话（limit={limit}, search={search!r}）")


def cli() -> None:
    """Parse args, run main, translate errors into exit codes."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=BASE_URL, help="opencode server base URL")
    parser.add_argument("--limit", type=int, default=20, help="max sessions to show")
    parser.add_argument("--search", default=None, help="filter by keyword (title, ...)")
    args = parser.parse_args()

    try:
        asyncio.run(main(args.url, args.limit, args.search))
    except OpenCodeApiError as exc:
        print(f"[OpenCodeApiError] HTTP {exc.status_code}: {exc.payload}", file=sys.stderr)
        raise SystemExit(1) from exc
    except OpenCodeTransportError as exc:
        print(f"[transport] 无法完成与 {args.url} 的通信：{exc}", file=sys.stderr)
        print("  提示：确认服务已启动，例如 `opencode serve --port 4096`，或用 --url 指定。", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    cli()

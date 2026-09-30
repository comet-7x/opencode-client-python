"""list_sessions：列出会话（最新在前）与过滤参数。

演示 ``sessions.list_sessions`` 的 ``limit`` / ``search`` 过滤，
并明确结果排序语义：服务端**最新在前**。

运行（仓库根目录）::

    uv run python -m examples.sessions.list_sessions
    uv run python -m examples.sessions.list_sessions --limit 5 --search quick
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from opencode_client import AsyncOpenCodeClient, OpenCodeApiError, OpenCodeTransportError, Session

BASE_URL = "http://127.0.0.1:4096"


def _one_line(s: Session) -> str:
    """把一个 Session 渲染成一行表格。

    Args:
        s: 要展示的会话。
    """
    model = f"{s.model.provider_id}/{s.model.id}" if s.model else "-"
    return f"{s.id:<24} {s.title!r:<28} {model:<24} updated={s.time.updated}"


async def main(base_url: str, limit: int, search: str | None) -> None:
    """列出并打印服务端会话。

    Args:
        base_url: 服务地址。
        limit: 最多取多少条。
        search: 可选关键词过滤（匹配标题等）。
    """
    async with AsyncOpenCodeClient(base_url) as client:
        sessions = await client.sessions.list_sessions(limit=limit, search=search)

        # 空列表是合法状态（全新服务器），显式打印而不是留白。
        if not sessions:
            print("没有匹配的会话。")
            return

        print(f"{'id':<24} {'title':<28} {'model':<24} {'updated':>14}")
        for s in sessions:
            print(_one_line(s))
        print(f"\n共 {len(sessions)} 个会话（limit={limit}, search={search!r}；结果最新在前）")


def cli() -> None:
    """解析参数并运行 main。"""
    parser = argparse.ArgumentParser(description="列出服务端会话")
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
        print(f"[transport] 无法连接 {args.url}：{exc}", file=sys.stderr)
        print("  提示：确认服务已启动，例如 `opencode serve --port 4096`，或用 --url 指定正确地址。", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    cli()

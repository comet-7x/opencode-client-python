"""01 delete_session: delete a session by id and confirm the result.

Shows ``sessions.delete`` — what it returns (``True`` on success) and what
happens for a missing session (the server answers 404, which the client
maps to :class:`OpenCodeNotFoundError`, a subclass of
:class:`OpenCodeApiError`).

Run (from the repo root):

    uv run python -m examples.01_session_management.delete_session --session ses_XXXX
    uv run python -m examples.01_session_management.delete_session   # 不带 id：随机删一个自己新建的
    uv run python examples/01_session_management/delete_session.py --url http://127.0.0.1:20001
"""

from __future__ import annotations

import argparse  # --session/--url
import asyncio  # 事件循环
import sys  # 退出码

from opencode_client import (
    AsyncOpenCodeClient,
    CreateSessionRequest,
    OpenCodeApiError,  # 404 会落到它的子类 OpenCodeNotFoundError
    OpenCodeNotFoundError,  # 专门捕获“删的东西不存在”，演示分层异常
    OpenCodeTransportError,
)

BASE_URL = "http://127.0.0.1:4096"


async def main(base_url: str, session_id: str | None) -> None:
    """Delete a session; if none given, create a throwaway one first.

    Args:
        base_url: server base URL.
        session_id: 要删的会话 id；为 None 时先建一个一次性会话再删（演示完整闭环）。
    """
    async with AsyncOpenCodeClient(base_url) as client:
        target_id = session_id
        created_temp = False
        if target_id is None:
            # 没传 id：建一个一次性会话，确保脚本“有东西可删”且自清理。
            temp = await client.sessions.create(body=CreateSessionRequest(title="01 delete throwaway"))
            target_id = temp.id
            created_temp = True
            print(f"未指定 --session，先建了一个一次性会话：{target_id}")

        # —— 真正的删除调用。返回 True = 服务端确认已删。
        try:
            deleted = await client.sessions.delete(target_id)
        except OpenCodeNotFoundError:
            # 分层异常的价值在这里体现：能单独区分“东西不存在”。
            # 注意：它仍是 OpenCodeApiError 的子类，外层还能统一兜底。
            print(f"会话 {target_id} 不存在（服务器返回 404）。")
            return
        print(f"delete -> {deleted}（会话 {target_id} 已删除）")
        print(
            "(删除是不可逆的：会话及其消息历史都会移除；"
            + ("本例删的是刚建的一次性会话。" if created_temp else "请确认你确实要删它。")
        )


def cli() -> None:
    """Parse args, run main, translate errors into exit codes."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=BASE_URL, help="opencode server base URL")
    parser.add_argument("--session", default=None, help="session id to delete (omit to create+delete a throwaway)")
    args = parser.parse_args()

    try:
        asyncio.run(main(args.url, args.session))
    except OpenCodeApiError as exc:
        print(f"[OpenCodeApiError] HTTP {exc.status_code}: {exc.payload}", file=sys.stderr)
        raise SystemExit(1) from exc
    except OpenCodeTransportError as exc:
        print(f"[transport] 无法完成与 {args.url} 的通信：{exc}", file=sys.stderr)
        print("  提示：确认服务已启动，例如 `opencode serve --port 4096`，或用 --url 指定。", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    cli()

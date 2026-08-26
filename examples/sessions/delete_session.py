"""delete_session：按 id 删除会话，观察返回值与 404 的异常映射。

演示 ``sessions.delete``：成功返回 ``True``；删除不存在的会话时服务端回
404，客户端把它映射成 :class:`OpenCodeNotFoundError`（:class:`OpenCodeApiError`
的子类）——分层异常让你能单独区分"东西不存在"。

运行（仓库根目录）::

    uv run python -m examples.sessions.delete_session --session ses_XXXX
    uv run python -m examples.sessions.delete_session   # 不带 id：自建一个一次性会话再删
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from opencode_client import (
    AsyncOpenCodeClient,
    CreateSessionRequest,
    OpenCodeApiError,
    OpenCodeNotFoundError,
    OpenCodeTransportError,
)

BASE_URL = "http://127.0.0.1:4096"


async def main(base_url: str, session_id: str | None) -> None:
    """删除指定会话；不给 id 就先建一个一次性会话（保证有东西可删、且自清理）。

    Args:
        base_url: 服务地址。
        session_id: 要删的会话 id；None 时走"建了就删"的完整闭环。
    """
    async with AsyncOpenCodeClient(base_url) as client:
        target_id = session_id
        created_temp = False
        if target_id is None:
            temp = await client.sessions.create(body=CreateSessionRequest(title="delete throwaway"))
            target_id = temp.id
            created_temp = True
            print(f"未指定 --session，先建了一个一次性会话：{target_id}")

        try:
            deleted = await client.sessions.delete(target_id)
        except OpenCodeNotFoundError:
            # 具体子类先捕获：404 是业务里可预期的正常分支，单独给话术。
            # 它仍是 OpenCodeApiError 的子类，外层还能统一兜底。
            print(f"会话 {target_id} 不存在（服务器返回 404）。")
            return
        print(f"delete -> {deleted}（会话 {target_id} 已删除）")
        tail = "本例删的是刚建的一次性会话。" if created_temp else "请确认你确实要删它。"
        print(f"(删除不可逆：会话及其消息历史一并移除；{tail}")


def cli() -> None:
    """解析参数并运行 main。"""
    parser = argparse.ArgumentParser(description="删除一个会话")
    parser.add_argument("--url", default=BASE_URL, help="opencode server base URL")
    parser.add_argument("--session", default=None, help="session id to delete (omit to create+delete a throwaway)")
    args = parser.parse_args()

    try:
        asyncio.run(main(args.url, args.session))
    except OpenCodeApiError as exc:
        print(f"[OpenCodeApiError] HTTP {exc.status_code}: {exc.payload}", file=sys.stderr)
        raise SystemExit(1) from exc
    except OpenCodeTransportError as exc:
        print(f"[transport] 无法连接 {args.url}：{exc}", file=sys.stderr)
        print("  提示：确认服务已启动，例如 `opencode serve --port 4096`，或用 --url 指定正确地址。", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    cli()

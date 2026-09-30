"""quickstart（sync）：与 async 版完全对等的同步客户端流程。

``OpenCodeClient``（同步）与 ``AsyncOpenCodeClient``（异步）方法签名一一对应，
仅去掉 ``async/await``；资源分组（``client.server.*`` / ``client.sessions.*``）、
模型、错误分层、重试策略全部共享。适合脚本、CLI 工具等没有事件循环的场景。

运行（仓库根目录）::

    uv run python -m examples.quickstart.quickstart_sync
    uv run python -m examples.quickstart.quickstart_sync --url http://127.0.0.1:20001
"""

from __future__ import annotations

import argparse
import sys

from opencode_client import (
    AssistantMessage,
    CreateSessionRequest,
    OpenCodeApiError,
    OpenCodeClient,
    OpenCodeTransportError,
    TextPart,
)

BASE_URL = "http://127.0.0.1:4096"


def main(base_url: str) -> None:
    """同步版一问一答：健康检查 → 建会话 → prompt → 打印 → 删除。

    Args:
        base_url: 服务地址，如 ``http://127.0.0.1:4096``。
    """
    # 普通上下文管理器即可，无需 asyncio；退出时自动关闭底层连接池。
    with OpenCodeClient(base_url) as client:
        health = client.server.health()  # 没有 await——这是 sync 与 async 唯一的写法差别
        print(f"health: opencode {health.version}")

        session = client.sessions.create(body=CreateSessionRequest(title="quickstart (sync)"))
        print(f"created session: {session.id}")
        try:
            # prompt() 阻塞到助手答完才返回最终 MessageWithParts；
            # 回答是 part 列表，文本部分在 TextPart.text。
            reply = client.sessions.prompt(session.id, "Reply with exactly one word: pong")
            for part in reply.parts:
                if isinstance(part, TextPart):
                    print(f"assistant: {part.text.strip()}")

            # info 是 user/assistant 的联合类型；tokens 只在 assistant 上，先收窄再读。
            if isinstance(reply.info, AssistantMessage):
                print(f"tokens: {reply.info.tokens.total}")
        finally:
            # 无论成功失败都清理，不在服务端留垃圾会话。
            client.sessions.delete(session.id)
            print("deleted session")


def cli() -> None:
    """解析参数并运行 main；错误处理与 async 版一致。"""
    parser = argparse.ArgumentParser(description="opencode-client 最简入门（sync 版）")
    parser.add_argument("--url", default=BASE_URL, help="opencode server base URL")
    args = parser.parse_args()

    try:
        main(args.url)
    except OpenCodeApiError as exc:
        print(f"[OpenCodeApiError] HTTP {exc.status_code}: {exc.payload}", file=sys.stderr)
        raise SystemExit(1) from exc
    except OpenCodeTransportError as exc:
        print(f"[transport] 无法连接 {args.url}：{exc}", file=sys.stderr)
        print("  提示：确认服务已启动，例如 `opencode serve --port 4096`，或用 --url 指定正确地址。", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    cli()

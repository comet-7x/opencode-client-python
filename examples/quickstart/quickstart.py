"""quickstart（async）：健康检查 → 建会话 → 一问一答 → 清理。

从"一个运行中的 opencode 服务"到"拿到一句回答"的最短路径。
同步客户端的同款流程见同目录 ``quickstart_sync.py``——两者 API 完全对等，
仅 async 侧多 ``await``。

运行（仓库根目录）::

    uv run python -m examples.quickstart.quickstart
    uv run python examples/quickstart/quickstart.py
    uv run python examples/quickstart/quickstart.py --url http://127.0.0.1:20001
    uv run python examples/quickstart/quickstart.py --directory /path/to/project
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from opencode_client import (
    AssistantMessage,
    AsyncOpenCodeClient,
    CreateSessionRequest,
    OpenCodeApiError,
    OpenCodeTransportError,
    TextPart,
)

BASE_URL = "http://127.0.0.1:4096"


async def main(
    base_url: str, directory: str | None = None, provider_id: str | None = None, model_id: str | None = None
) -> None:
    """连上服务、建会话、发一句 prompt、打印回答，最后删除会话。

    Args:
        base_url: 服务地址，如 ``http://127.0.0.1:4096``。
        directory: 可选作用域，把会话钉在某个项目目录上。
        provider_id: 与 model_id 成对传入时钉住模型，否则用服务端默认。
        model_id: 同上。
    """
    # `async with` 保证退出时关闭底层连接池，中途抛异常也不会泄漏连接。
    async with AsyncOpenCodeClient(base_url) as client:
        # 第 1 步：health() 是最小的连通性探针，顺带拿服务端版本号。
        health = await client.server.health()
        print(f"health: opencode {health.version}")

        # 第 2 步：建会话。请求体走 body=（字段全可选），directory 是请求级 query 参数、平铺在外层。
        session = await client.sessions.create(
            body=CreateSessionRequest(title="quickstart demo"),
            directory=directory,
        )
        print(f"created session: {session.id}")

        try:
            # 第 3 步：prompt() 阻塞到助手答完才返回最终 MessageWithParts
            # （区别于 prompt_async 的 fire-and-forget）。纯文本会自动包成 text part。
            model = {"providerID": provider_id, "modelID": model_id} if provider_id and model_id else None
            reply = await client.sessions.prompt(session.id, "Reply with exactly one word: pong", model=model)

            # 第 4 步：回答被拆成 text/tool/reasoning 等 part，只取文本部分。
            for part in reply.parts:
                if isinstance(part, TextPart):
                    print(f"assistant: {part.text.strip()}")

            # 消息头在 reply.info 上，是 user/assistant 的联合类型；
            # tokens 只存在于 assistant 消息，先 isinstance 收窄再读。
            if isinstance(reply.info, AssistantMessage):
                print(f"tokens: {reply.info.tokens.total}")
        finally:
            # 无论成功失败都清理，不在服务端留垃圾会话。
            await client.sessions.delete(session.id)
            print("deleted session")


def cli() -> None:
    """解析参数并运行 main；把库异常翻译成可读的退出码。"""
    parser = argparse.ArgumentParser(description="opencode-client 最简入门（async 版）")
    parser.add_argument("--url", default=BASE_URL, help="opencode server base URL")
    parser.add_argument("--directory", default=None, help="scope the session to a project directory")
    parser.add_argument("--provider", default=None, help="pin a provider id")
    parser.add_argument("--model", default=None, help="pin a model id")
    args = parser.parse_args()

    try:
        asyncio.run(main(args.url, args.directory, args.provider, args.model))
    except OpenCodeApiError as exc:
        print(f"[OpenCodeApiError] HTTP {exc.status_code}: {exc.payload}", file=sys.stderr)
        raise SystemExit(1) from exc
    except OpenCodeTransportError as exc:
        print(f"[transport] 无法连接 {args.url}：{exc}", file=sys.stderr)
        print("  提示：确认服务已启动，例如 `opencode serve --port 4096`，或用 --url 指定正确地址。", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    cli()

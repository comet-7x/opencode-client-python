"""raw_response：with_raw_response 裸响应视图——拿到未加工的 httpx.Response。

正常调用返回解析好的模型（Session/Health/...）；需要看**线上原样**时——
响应头、精确状态码、未经模型重塑的 body——给任意方法加 ``with_raw_response``
前缀::

    session = await client.sessions.get(sid)                # -> Session
    raw     = await client.sessions.with_raw_response.get(sid)  # -> httpx.Response

不变的部分（共享同一传输层）：同样的 method/path/query/body、同样的重试
策略、非 2xx 仍抛同样的分层异常——raw 视图只改"成功时给你什么"。
``stream_events`` 没有 raw 变体。

运行（仓库根目录）::

    uv run python -m examples.client.raw_response
    uv run python -m examples.client.raw_response --url http://127.0.0.1:20001
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from opencode_client import (
    AsyncOpenCodeClient,
    OpenCodeApiError,
    OpenCodeNotFoundError,
    OpenCodeTransportError,
    Session,
)

BASE_URL = "http://127.0.0.1:4096"


async def main(base_url: str) -> None:
    """在相同端点上对比解析视图与裸响应视图。

    Args:
        base_url: 服务地址。
    """
    async with AsyncOpenCodeClient(base_url, timeout=30.0) as client:
        # —— 1) 同一端点，两种视图。参数完全一致（directory 等照常透传）。
        session = await client.sessions.get("ses_e")
        print(f"[parsed]  Session(id={session.id!r}, title={session.title!r})")

        raw = await client.sessions.with_raw_response.get("ses_e")
        print(f"[raw]     {raw.status_code} {raw.request.method} {raw.request.url.path}")
        # 头是 raw 视图的独占收益：探测限流/追踪信息（不存在时跳过）。
        for header in ("content-type", "x-request-id", "retry-after"):
            if header in raw.headers:
                print(f"[raw]     header {header}: {raw.headers[header]}")
        # body 想怎么用怎么用：也可以自己喂给模型校验（等价于库替你做的事）。
        parsed_from_raw = Session.model_validate(raw.json())
        if parsed_from_raw.id != session.id:
            raise AssertionError("raw body 解析结果应与正常视图一致")
        print(f"[raw]     自行解析后 id 一致: {parsed_from_raw.id!r}")

        # —— 2) 轻量端点同样适用：直接看到原始 body。
        health_raw = await client.server.with_raw_response.health()
        body = health_raw.json()
        print(f"[raw]     /global/health -> {health_raw.status_code}, body={body!r}")

        # —— 3) 关键保证：404 在 raw 视图下依旧抛 OpenCodeNotFoundError，
        #     而不是把错误响应交到你手里。
        try:
            await client.sessions.with_raw_response.get("ses_does_not_exist_0000")
            raise AssertionError("404 应当抛出异常，而不是返回响应")
        except OpenCodeNotFoundError as exc:
            print(f"[raw]     404 仍映射为 {type(exc).__name__} (status={exc.status_code})")


def cli() -> None:
    """解析参数并运行 main。"""
    parser = argparse.ArgumentParser(description="with_raw_response 裸响应视图演示")
    parser.add_argument("--url", default=BASE_URL, help="opencode server base URL")
    args = parser.parse_args()

    try:
        asyncio.run(main(args.url))
    except OpenCodeApiError as exc:
        print(f"[OpenCodeApiError] HTTP {exc.status_code}: {exc.payload}", file=sys.stderr)
        raise SystemExit(1) from exc
    except OpenCodeTransportError as exc:
        print(f"[transport] 无法连接 {args.url}：{exc}", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    cli()

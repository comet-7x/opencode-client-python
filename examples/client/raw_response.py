"""05 raw_response: the with_raw_response view — the unprocessed httpx.Response.

Normally every client method hands you a parsed model (``Session``, ``Health``,
...). Sometimes you need what the wire actually said: response **headers**,
the exact **status code**, or the **body before** our models reshape it.

Each resource exposes a ``with_raw_response`` prefix whose methods mirror the
parsed ones one-for-one but return the raw :class:`httpx.Response`::

    session = await client.sessions.get(sid)            # -> Session (parsed)
    raw = await client.sessions.with_raw_response.get(sid)  # -> httpx.Response

What stays the same (they share the same transport):
- identical wire: same method/path/query/body as the parsed call;
- same retry policy (429/5xx/connection errors, exponential backoff);
- same error mapping: non-2xx still raises the layered ``OpenCode*Error``
  hierarchy — ``with_raw_response`` only changes what you get on SUCCESS.

Use cases: reading server headers (rate limits, request ids), forwarding an
upstream response as-is, or debugging a payload our models normalise away.

Run (from the repo root):

    uv run python -m examples.events.raw_response
    uv run python examples/client/raw_response.py --url http://127.0.0.1:20001
"""

from __future__ import annotations

import argparse  # --url
import asyncio  # 事件循环
import sys  # 退出码

from opencode_client import (
    AsyncOpenCodeClient,
    OpenCodeApiError,
    OpenCodeNotFoundError,
    OpenCodeTransportError,
    Session,
)

BASE_URL = "http://127.0.0.1:4096"


async def main(base_url: str) -> None:
    """Contrast the parsed view with the raw view on the same endpoints.

    Args:
        base_url: server base URL.
    """
    async with AsyncOpenCodeClient(base_url, timeout=30.0) as client:
        # —— 1) 同一个端点，两种视图。
        #    正常视图：库替你解析成 Session 模型，字段按 camelCase -> snake_case 映射。
        session = await client.sessions.get("ses_e")
        print(f"[parsed]  Session(id={session.id!r}, title={session.title!r})")

        # raw 视图：原样的 httpx.Response —— 状态码、头、body 都在你手里。
        # 参数与正常视图完全一致（directory/workspace 等原样透传）。
        raw = await client.sessions.with_raw_response.get("ses_e")
        print(f"[raw]     {raw.status_code} {raw.request.method} {raw.request.url.path}")
        # 头是 raw 视图的独占收益：比如探测服务端限流/追踪信息（不存在时跳过）。
        for header in ("content-type", "x-request-id", "retry-after"):
            if header in raw.headers:
                print(f"[raw]     header {header}: {raw.headers[header]}")
        # body 想怎么用怎么用：这里仍可以用模型校验（等价于库替你做的事）。
        parsed_from_raw = Session.model_validate(raw.json())
        assert parsed_from_raw.id == session.id, "raw body 应与正常视图解析结果一致"
        print(f"[raw]     自己解析后 id 一致: {parsed_from_raw.id!r}")

        # —— 2) 轻量端点：health 也能 raw，直接看到原始 body。
        health_raw = await client.server.with_raw_response.health()
        print(f"[raw]     /global/health -> {health_raw.status_code}, body={health_raw.json()!r}")

        # —— 3) 关键保证：raw 视图只改“成功时给你什么”，不改“失败时抛什么”。
        #    404 依旧映射成 OpenCodeNotFoundError（而不是返回 404 响应）。
        try:
            await client.sessions.with_raw_response.get("ses_does_not_exist_0000")
            raise AssertionError("404 应当抛出异常，而不是返回响应")
        except OpenCodeNotFoundError as exc:
            print(f"[raw]     404 仍映射为 {type(exc).__name__} (status={exc.status_code})")


def cli() -> None:
    """Parse args, run main, translate errors into exit codes."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=BASE_URL, help="opencode server base URL")
    args = parser.parse_args()

    try:
        asyncio.run(main(args.url))
    except OpenCodeApiError as exc:
        print(f"[OpenCodeApiError] HTTP {exc.status_code}: {exc.payload}", file=sys.stderr)
        raise SystemExit(1) from exc
    except OpenCodeTransportError as exc:
        print(f"[transport] 无法完成与 {args.url} 的通信：{exc}", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    cli()

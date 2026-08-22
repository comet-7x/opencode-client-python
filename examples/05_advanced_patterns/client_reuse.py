"""05 client_reuse: build the client ONCE and reuse it, with tuning knobs.

Teaches two related things:

1. **Reuse** — ``AsyncOpenCodeClient`` wraps an ``httpx`` connection pool.
   Creating a fresh client per call re-opens the pool and re-negotiates the
   connection every time; the right pattern is one client per process
   (here, one per ``async with`` block), then many calls through it.
2. **Tuning** — ``timeout=`` / ``max_retries=`` control read timeout and the
   429/5xx/connection-error retry budget; ``client.with_options(...)``
   derives a new client that overrides only the values you pass (backed by
   the ``NOT_GIVEN`` sentinel), so two clients can share a server but
   behave differently.

Run (from the repo root):

    uv run python -m examples.05_advanced_patterns.client_reuse
    uv run python examples/05_advanced_patterns/client_reuse.py --url http://127.0.0.1:20001
"""

from __future__ import annotations

import argparse  # --url
import asyncio  # 事件循环
import sys  # 退出码
import time  # 计时：对比“复用连接”与多次请求的耗时差异

from opencode_client import (
    AsyncOpenCodeClient,
    OpenCodeApiError,
    OpenCodeTransportError,
)

BASE_URL = "http://127.0.0.1:4096"


async def main(base_url: str) -> None:
    """Drive several calls through ONE client, then derive a tuned copy.

    Args:
        base_url: server base URL.
    """
    # —— 关键点 1：只建一个 client，作用域内复用。
    #    参数：
    #      timeout=30.0   读超时（秒）：单次请求等多久没收到完整响应算超时；
    #                     建连超时同理。默认只有 5s，真实 prompt 往往更久，故调大。
    #      max_retries=3  重试预算：429/5xx/连接错误最多再试几次（指数退避 + 认 Retry-After）。
    #    注意构造本身不建连；连接池在 `async with` 进入时才打开，退出时关闭。
    async with AsyncOpenCodeClient(base_url, timeout=30.0, max_retries=3) as client:
        # 计时：同一个连接池上连续做 3 次轻量调用。
        # 第二次起通常更快（TCP+TLS 已复用、无握手），这是“复用 client”的直接收益。
        calls = 3
        timings: list[float] = []
        for i in range(1, calls + 1):
            t0 = time.perf_counter()  # 高精度墙钟，只测“这一次 await”
            health = await client.server.health()  # 每次都是真实请求，但走同一个池
            timings.append(time.perf_counter() - t0)
            print(f"call {i}: health ok (version={health.version})  took {timings[-1]:.3f}s")

        # 简单观察结论（网络抖动下也可能不单调，这只是量级演示，不作断言）。
        print(f"\n同池连续 {calls} 次调用耗时: " + ", ".join(f"{t:.3f}s" for t in timings))
        print("(复用一个连接池，避免每次调用都重新建连/握手)\n")

        # —— 关键点 2：with_options() 派生新配置。
        #    只覆盖 timeout，其余（base_url/username/password/max_retries）原样保留；
        #    未显式传入的参数走 NOT_GIVEN 哨兵，代表“别动我的值”。
        #    派生出的 fast_client 是一个独立 client，需要自己管理生命周期。
        fast_client = client.with_options(timeout=2.0)  # 例如：探活/轮询用短超时
        async with fast_client:
            h2 = await fast_client.server.health()
            print(f"派生 client (timeout=2.0s) 也正常: version={h2.version}")
        print("(派生 client 已关闭；原 client 仍在作用域内，继续可用)")

        # —— 关键点 3：复用不只是“能跑”，还要能“干净退出”。
        #    退出 before 再发一次请求，证明状态仍健康；随后 `async with` 收尾关池。
        h3 = await client.server.health()
        print(f"收尾检查: version={h3.version}（连接池即将随 with 退出而关闭）")


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
        # timeout 调大后仍然报这类错误，多半是服务彻底不可达（而不是单次慢）。
        print(f"[transport] 无法完成与 {args.url} 的通信：{exc}", file=sys.stderr)
        print("  提示：确认服务已启动；若只是慢，可再调大 timeout=。", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    cli()

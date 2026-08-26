"""client_reuse：复用客户端、超时/重试预算、with_options 派生配置。

生产环境的三件套：

- **复用**——``AsyncOpenCodeClient`` 内部是一个 httpx 连接池；每次新建
  client 都要重新建池、重新握手。正确姿势是一个进程/作用域建一个，
  多次调用共享；
- **调参**——``timeout=`` 控制建连与读超时（默认仅 5s，真实 prompt 往往
  更久）；``max_retries=`` 控制 429/5xx/连接错误的重试预算（指数退避
  0.5s→8s，尊重 Retry-After）；
- **派生**——``client.with_options(...)`` 返回新 client，只覆盖传入的项
  （未传的保持原值，基于 NOT_GIVEN 哨兵），适合"同一服务器、不同超时"。

运行（仓库根目录）::

    uv run python -m examples.client.client_reuse
    uv run python -m examples.client.client_reuse --url http://127.0.0.1:20001
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time

from opencode_client import AsyncOpenCodeClient, OpenCodeApiError, OpenCodeTransportError

BASE_URL = "http://127.0.0.1:4096"


async def main(base_url: str) -> None:
    """用一个 client 跑多次调用并计时，再派生一个短超时副本验证隔离性。

    Args:
        base_url: 服务地址。
    """
    async with AsyncOpenCodeClient(base_url, timeout=30.0, max_retries=3) as client:
        # 同一连接池上连续轻量调用；第二次起通常更快（连接已复用、无握手）。
        # 网络抖动下耗时不保证单调，这里只演示量级差异。
        calls = 3
        timings: list[float] = []
        for i in range(1, calls + 1):
            t0 = time.perf_counter()
            health = await client.server.health()
            timings.append(time.perf_counter() - t0)
            print(f"call {i}: health ok (version={health.version})  took {timings[-1]:.3f}s")
        joined = ", ".join(f"{t:.3f}s" for t in timings)
        print(f"\n同池连续 {calls} 次调用耗时: {joined}\n")

        # with_options 派生：只覆盖 timeout；派生出的 client 生命周期独立管理。
        fast_client = client.with_options(timeout=2.0)  # 例如探活/轮询用短超时
        async with fast_client:
            h2 = await fast_client.server.health()
            print(f"派生 client (timeout=2.0s) 也正常: version={h2.version}")
        print("(派生 client 已关闭；原 client 仍在作用域内，继续可用)\n")

        h3 = await client.server.health()
        print(f"收尾检查: version={h3.version}（连接池即将随 async with 退出而关闭）")


def cli() -> None:
    """解析参数并运行 main。"""
    parser = argparse.ArgumentParser(description="客户端复用、超时/重试与 with_options 派生")
    parser.add_argument("--url", default=BASE_URL, help="opencode server base URL")
    args = parser.parse_args()

    try:
        asyncio.run(main(args.url))
    except OpenCodeApiError as exc:
        print(f"[OpenCodeApiError] HTTP {exc.status_code}: {exc.payload}", file=sys.stderr)
        raise SystemExit(1) from exc
    except OpenCodeTransportError as exc:
        # 调大 timeout 后仍报这类错误，多半是服务彻底不可达而不是单次慢。
        print(f"[transport] 无法连接 {args.url}：{exc}", file=sys.stderr)
        print("  提示：确认服务已启动；若只是慢，可再调大 timeout=。", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    cli()

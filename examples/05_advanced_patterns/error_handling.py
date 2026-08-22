"""05 error_handling: catch OpenCodeApiError and degrade instead of crashing.

Real programs should not dump a traceback to end users when the server says
"not found". This script shows the exception hierarchy and the
catch-specific-first / catch-base-last pattern, then wraps a small batch of
operations so one failure doesn't kill the rest (graceful degradation with
fallbacks).

Run (from the repo root):

    uv run python -m examples.05_advanced_patterns.error_handling
    uv run python examples/05_advanced_patterns/error_handling.py --url http://127.0.0.1:20001
"""

from __future__ import annotations

import argparse  # --url
import asyncio  # 事件循环
import sys  # 退出码

from opencode_client import (
    AsyncOpenCodeClient,
    CreateSessionRequest,
    OpenCodeApiError,  # 所有“服务端给了非 2xx 响应”异常的公共基类
    OpenCodeNotFoundError,  # 404 的专用子类
    OpenCodeRateLimitError,  # 429，仅在此演示“族谱存在”，未必触发
    OpenCodeTransportError,  # 另一族：没拿到 HTTP 响应（连不上/超时）
)

BASE_URL = "http://127.0.0.1:4096"


async def fetch_or_fallback(
    client: AsyncOpenCodeClient,
    session_id: str,
) -> str:
    """Get a session's title, or a readable fallback string on any API error.

    这是“降级”的最小形状：把“可能失败”的调用包进 try，
    任何非 2xx 都不往外抛，而是返回一个可被上层继续使用的结果。

    Args:
        client: 已打开的连接。
        session_id: 要取标题的会话 id。

    Returns:
        会话标题；失败时返回形如 ``“<fallback: HTTP 404>”`` 的字符串。
    """
    try:
        session = await client.sessions.get(session_id)
        return session.title
    except OpenCodeNotFoundError:
        # 先捕获“最具体”的子类：404 是业务里能预期的正常情况（删过/expired）。
        # 注意它也是 OpenCodeApiError 的实例，但这里我们想给它单独的话术。
        return "<fallback: 会话不存在(404)>"
    except OpenCodeRateLimitError as exc:
        # 再捕获次具体的：429 通常值得提示“被限流/可稍后重试”。
        # exc.status_code / exc.payload 是基类统一携带的两个属性，任何子类都能读。
        return f"<fallback: 限流({exc.status_code})，稍后再试>"
    except OpenCodeApiError as exc:
        # 最后兜底到基类：其余 4xx/5xx 用统一话术。
        # 这里故意只把 status_code 与 payload 摘要给用户，不暴露内部 traceback。
        return f"<fallback: HTTP {exc.status_code} {exc.payload!r:.60}>"


async def main(base_url: str) -> None:
    """Demonstrate layered catching and a resilient batch.

    Args:
        base_url: server base URL.
    """
    async with AsyncOpenCodeClient(base_url) as client:
        # —— 演示 1：一个“必然 404”的 id，走 fetch_or_fallback 的降级路径。
        print("== 单个失败如何降级 ==")
        missing = "ses_does_not_exist_0000"
        title = await fetch_or_fallback(client, missing)
        print(f"GET {missing!r} -> {title}")
        print("（没有抛异常、没有堆栈：上层拿到的仍是可处理的字符串）\n")

        # —— 演示 2：批量操作，一个失败不拖垮整批。
        #    先建一个真会话 + 一个不存在的 id，混在同一批里处理。
        print("== 批量里单个失败不阻断其他 ==")
        real = await client.sessions.create(body=CreateSessionRequest(title="03 error-handling demo"))
        batch = [real.id, "ses_missing_a", "ses_missing_b"]
        results: list[tuple[str, str]] = []
        for sid in batch:
            results.append((sid, await fetch_or_fallback(client, sid)))
            # 关键点：循环 body 里不再 try/except —— 降级已下沉到 fetch_or_fallback，
            # 所以这里照常继续下一条，这就是“优雅降级”的意义。
        for sid, res in results:
            print(f"  {sid} -> {res}")
        await client.sessions.delete(real.id)  # 清理刚建的真会话

        print("\n== 捕获顺序为什么这样写 ==")
        print("先 OpenCodeNotFoundError / OpenCodeRateLimitError，后 OpenCodeApiError：")
        print("Python 按代码顺序匹配 except 子句，具体子类必须在基类 *之前*，")
        print("否则基类会先命中，具体子类的分支永远不会执行。")


def cli() -> None:
    """Parse args, run main, translate errors into exit codes.

    注意最外层只兜 TransportError：这里的业务错误都已在 main 内部降级处理，
    能漏到外层的只剩“根本连不上服务”这类环境问题。
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=BASE_URL, help="opencode server base URL")
    args = parser.parse_args()

    try:
        asyncio.run(main(args.url))
    except OpenCodeTransportError as exc:
        print(f"[transport] 无法完成与 {args.url} 的通信：{exc}", file=sys.stderr)
        print("  提示：确认服务已启动，例如 `opencode serve --port 4096`，或用 --url 指定。", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    cli()

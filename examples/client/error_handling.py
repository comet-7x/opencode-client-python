"""error_handling：分层异常的捕获顺序与优雅降级。

真实程序不该在服务端说"not found"时把堆栈糊给用户。本脚本演示：

- 异常族谱：``OpenCodeApiError``（带 status_code/payload）按状态码细分成
  404/401/403/409/422/429/5xx 子类；``OpenCodeTransportError``（连不上/超时，
  根本没拿到 HTTP 响应）是另一族；
- 捕获顺序：**先具体子类，后基类**——except 子句按代码顺序匹配，基类在前
  会吞掉所有子类分支；
- 降级模式：把"可能失败"的调用包成返回可读 fallback 的函数，批量操作里
  单个失败不拖垮整批。

运行（仓库根目录）::

    uv run python -m examples.client.error_handling            # 故意 404，看降级路径
    uv run python -m examples.client.error_handling --url http://127.0.0.1:20001
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
    OpenCodeRateLimitError,
    OpenCodeTransportError,
)

BASE_URL = "http://127.0.0.1:4096"


async def fetch_title_or_fallback(client: AsyncOpenCodeClient, session_id: str) -> str:
    """取会话标题；任何 API 错误都降级为可读字符串而不外抛。

    Args:
        client: 已打开的客户端。
        session_id: 目标会话 id。

    Returns:
        会话标题；失败时返回形如 ``<fallback: HTTP 404>`` 的字符串。
    """
    try:
        session = await client.sessions.get(session_id)
        return session.title
    except OpenCodeNotFoundError:
        # 最具体的先捕获：404 是业务里可预期的正常情况（删过/过期）。
        return "<fallback: 会话不存在(404)>"
    except OpenCodeRateLimitError as exc:
        # 429 值得单独话术：被限流，可稍后重试。
        return f"<fallback: 限流({exc.status_code})，稍后再试>"
    except OpenCodeApiError as exc:
        # 最后兜底到基类：其余 4xx/5xx 统一话术。
        # status_code/payload 是基类统一携带的属性，任何子类都能读。
        return f"<fallback: HTTP {exc.status_code} {exc.payload!r:.60}>"


async def main(base_url: str) -> None:
    """演示分层捕获与批处理降级。

    Args:
        base_url: 服务地址。
    """
    async with AsyncOpenCodeClient(base_url) as client:
        print("== 单个失败如何降级 ==")
        missing = "ses_does_not_exist_0000"
        title = await fetch_title_or_fallback(client, missing)
        print(f"GET {missing!r} -> {title}")
        print("（没有抛异常、没有堆栈：上层拿到的仍是可处理的字符串）\n")

        print("== 批量里单个失败不阻断其他 ==")
        real = await client.sessions.create(body=CreateSessionRequest(title="error handling demo"))
        try:
            batch = [real.id, "ses_missing_a", "ses_missing_b"]
            for sid in batch:
                # 循环体里不再 try/except——降级已下沉到 fetch_title_or_fallback。
                result = await fetch_title_or_fallback(client, sid)
                print(f"  {sid} -> {result}")
        finally:
            await client.sessions.delete(real.id)

        print("\n== 捕获顺序为什么这样写 ==")
        print("先 OpenCodeNotFoundError / OpenCodeRateLimitError，后 OpenCodeApiError：")
        print("Python 按代码顺序匹配 except 子句，具体子类必须在基类之前。")


def cli() -> None:
    """解析参数并运行 main。

    业务错误已在 main 内部降级，能漏到这里的只剩连不上服务这类环境问题。
    """
    parser = argparse.ArgumentParser(description="异常分层与降级演示")
    parser.add_argument("--url", default=BASE_URL, help="opencode server base URL")
    args = parser.parse_args()

    try:
        asyncio.run(main(args.url))
    except OpenCodeTransportError as exc:
        print(f"[transport] 无法连接 {args.url}：{exc}", file=sys.stderr)
        print("  提示：确认服务已启动，例如 `opencode serve --port 4096`，或用 --url 指定正确地址。", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    cli()

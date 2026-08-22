"""00_quickstart: health check -> create session -> one prompt -> print reply.

The shortest path from "a running opencode server" to "getting an answer".
Every line is commented; read the sibling README.md for the why.

Run (either form, from the repo root):

    uv run python -m examples.00_quickstart.quickstart
    uv run python examples/00_quickstart/quickstart.py
    uv run python examples/00_quickstart/quickstart.py --url http://127.0.0.1:20001
    uv run python examples/00_quickstart/quickstart.py --directory /path/to/project
"""

from __future__ import annotations

import argparse  # CLI 参数解析：让用户能传 --url / --directory / --provider / --model
import asyncio  # 事件循环：async 网络请求必须跑在一个事件循环里
import sys  # 退出码：示例脚本用非零码表达"业务失败"，便于 shell 判断

# 只从包根 import 公开符号 —— 这是对外推荐姿势（见仓库 AGENTS.md「导出规则」）
from opencode_client import (
    AssistantMessage,  # 助手消息模型，用来判断 reply.info 的具体类型
    AsyncOpenCodeClient,  # 异步客户端：本示例所有网络调用都走它
    CreateSessionRequest,  # 建会话的请求体（title/agent/model 等，字段全可选）
    OpenCodeApiError,  # 服务端返回非 2xx 时抛出的分层异常基类
    OpenCodeTransportError,  # 连接失败/超时等“没拿到 HTTP 响应”的异常基类
    TextPart,  # 回答里承载文本的 part 类型
)

BASE_URL = "http://127.0.0.1:4096"  # 默认服务地址，可用 --url 覆盖


async def main(
    base_url: str,
    directory: str | None = None,  # 可选作用域：把会话钉在某个项目目录上
    provider_id: str | None = None,  # 可选：钉住 provider（不传用服务端默认）
    model_id: str | None = None,  # 可选：钉住 model
) -> None:
    """Connect, create a session, ask one question, print the answer, clean up.

    Args:
        base_url: opencode server URL, e.g. ``http://127.0.0.1:4096``.
        directory: Optional project directory to scope the session to.
        provider_id: Optional provider id to pin for the prompt.
        model_id: Optional model id to pin for the prompt.
    """
    # `async with` 让客户端成为上下文管理器：
    # 进入时建立底层 HTTP 连接池，退出时自动 close —— 哪怕中途抛异常也不泄漏连接。
    async with AsyncOpenCodeClient(base_url) as client:
        # —— 第 1 步：健康检查。最小的连通性探针，确认服务在跑、协议对得上。
        #     health() 返回 Health，.version 是服务端版本号。
        health = await client.server.health()
        print(f"health: opencode {health.version}")

        # —— 第 2 步：创建会话。
        # 这里是用户要求演示的“简写”：不拼 agent/model 等复杂 body，
        # 只带一个标题 + 作用域参数 —— 即 create(body=..., directory=...)。
        # 请求体统一走 body 参数（不传 body 则完全用服务端默认）。
        session = await client.sessions.create(
            body=CreateSessionRequest(title="quickstart demo"),  # 会话标题（list_sessions 里可见）
            directory=directory,  # 作用域：None 时服务端用默认目录
        )
        print(f"created session: {session.id}")

        # 会话用完了必须在 finally 里删掉，避免在服务端留下垃圾会话。
        try:
            # —— 第 3 步：发 prompt。
            # prompt() 是“同步式”调用：发出请求后一直等，直到助手完整答完才返回
            # 最终的 MessageWithParts（区别于 prompt_async 的 fire-and-forget）。
            # model 只在同时给了 provider 和 model 时才构造；否则用服务端默认。
            model = {"providerID": provider_id, "modelID": model_id} if provider_id and model_id else None
            reply = await client.sessions.prompt(
                session.id,  # 往哪个会话发
                "Reply with exactly one word: pong",  # 问题本体（纯文本会被自动包成 text part）
                model=model,
            )

            # —— 第 4 步：读取回答。
            # reply.parts 是“分块列表”：一次回答可能被拆成 text / tool / reasoning 等多种 part。
            # 我们只关心文本部分，所以逐个判断类型，取 TextPart 的 .text。
            for part in reply.parts:
                if isinstance(part, TextPart):  # 只有文本 part 才有 .text 属性
                    print(f"assistant: {part.text.strip()}")

            # 附带展示：回复的消息头（role/tokens 等）在 reply.info 上。
            # info 是一个联合类型（user/assistant 消息），assistant 才有 tokens。
            if isinstance(reply.info, AssistantMessage):
                print(f"tokens: {reply.info.tokens.total}")
        finally:
            # —— 第 5 步：清理。无论上面成功还是抛错，都尝试删除会话。
            # delete 返回 True 表示服务端确认删除成功。
            await client.sessions.delete(session.id)
            print("deleted session")


def cli() -> None:
    """Parse CLI arguments and run :func:`main` with error handling.

    这里统一演示 ``OpenCodeApiError`` 的捕获：它是所有“服务端给了非 2xx 响应”
    的异常的公共基类，再往下有 404→OpenCodeNotFoundError、429→OpenCodeRateLimitError、
    5xx→OpenCodeServerError 等子类可进一步细化。示例里我们只兜底到基类，
    打印可读信息并以非零码退出；连接/超时类错误（OpenCodeTransportError 子类）
    属于另一分支，单独提示“检查服务是否已启动”。
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=BASE_URL, help="opencode server base URL")
    parser.add_argument("--directory", default=None, help="scope the session to a project directory")
    parser.add_argument("--provider", default=None, help="pin a provider id")
    parser.add_argument("--model", default=None, help="pin a model id")
    args = parser.parse_args()

    try:
        # asyncio.run 负责创建并运行事件循环，main 是入口协程。
        asyncio.run(main(args.url, args.directory, args.provider, args.model))
    except OpenCodeApiError as exc:
        # 服务端可达但业务上拒绝/出错（404、409、422、429、5xx…）。
        # exc.status_code 是 HTTP 状态码，exc.payload 是解析后的错误体。
        # 用 `raise ... from exc` 建立异常链，保留原始 traceback 供调试。
        print(f"[OpenCodeApiError] HTTP {exc.status_code}: {exc.payload}", file=sys.stderr)
        raise SystemExit(1) from exc
    except Exception as exc:  # 含 OpenCodeTransportError（连不上/超时）及未预期错误
        # 这一层兜底最常见的原因是“服务没起”，给一行明确提示，
        # 其余未预期错误直接抛出带 traceback，方便定位。
        if isinstance(exc, OpenCodeTransportError):
            print(f"[transport] 无法完成与 {args.url} 的通信：{exc}", file=sys.stderr)
            print(
                "  提示：确认服务已启动，例如 `opencode serve --port 4096`，或用 --url 指定正确地址。", file=sys.stderr
            )
            raise SystemExit(2) from exc
        raise


if __name__ == "__main__":
    cli()

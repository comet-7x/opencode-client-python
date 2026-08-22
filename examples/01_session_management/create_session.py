"""01 create_session: create a session with various parameters and show the result.

Shows the full parameter surface of ``sessions.create`` (title, agent,
model, metadata, directory scoping) and prints every field of the returned
``Session`` so you can see what the server actually stored.

Run (from the repo root):

    uv run python -m examples.01_session_management.create_session
    uv run python -m examples.01_session_management.create_session --title 我的会话 --provider anthropic --model claude-x
    uv run python examples/01_session_management/create_session.py --url http://127.0.0.1:20001
"""

from __future__ import annotations

import argparse  # 解析 --title/--provider/--model/--directory/--url
import asyncio  # 事件循环
import sys  # 非零退出码表达失败

from opencode_client import (  # 只从包根 import 公开符号
    AsyncOpenCodeClient,
    CreateSessionRequest,  # 建会话的请求体模型（全部字段可选）
    ModelID,  # “pin 一个模型”用的 id 结构：provider_id + id
    OpenCodeApiError,  # 服务端非 2xx 的异常基类
    OpenCodeTransportError,  # 连不上/超时的异常基类
)

BASE_URL = "http://127.0.0.1:4096"


async def main(
    base_url: str,
    title: str,
    agent: str | None,
    provider_id: str | None,
    model_id: str | None,
    directory: str | None,
) -> None:
    """Create one session and print the returned ``Session`` field by field.

    Args:
        base_url: server base URL.
        title: 会话标题（必填，便于在列表里辨认）。
        agent: 可选，钉住一个 agent（build/plan/...）。
        provider_id: 与 model_id 成对出现时，钉住模型。
        model_id: 与 provider_id 成对出现时，钉住模型。
        directory: 可选作用域，把会话钉在某个项目目录。
    """
    async with AsyncOpenCodeClient(base_url) as client:  # 上下文管理器保证连接池必关
        # —— 组装请求体：只有用户给了 provider+model 时才钉模型。
        #    CreateSessionRequest 字段全是可选的；不传 body= 则用服务端默认。
        body = CreateSessionRequest(
            title=title,  # 会回显在 list_sessions 里
            model=ModelID(id=model_id, provider_id=provider_id) if provider_id and model_id else None,
            agent=agent or None,  # argparse 的默认 "" 归一成 None
        )

        # —— 真正的调用。
        #    directory 是“请求级作用域参数”（query 参数），不是 body 字段；
        #    所以它平铺在 create() 的 kwargs 上，而不是塞进 body。
        session = await client.sessions.create(body=body, directory=directory)

        # —— 逐个字段打印，说明每个字段是什么。
        #    库已把 wire 的 camelCase/大写ID 映射成 snake_case（见 models/base.py 的 id_alias），
        #    所以这里直接读属性，不用关心 sessionID 这种线上格式。
        print("== 创建的 Session ==")
        print(f"id          : {session.id}")  # 服务端生成的会话 id，后续所有调用都用它
        print(f"slug        : {session.slug}")  # 短别名，用于分享链接
        print(f"title       : {session.title!r}")
        print(f"directory   : {session.directory}")  # 会话绑定的工作目录
        print(f"project_id  : {session.project_id}")  # 所属项目
        print(f"workspace_id: {session.workspace_id}")  # 工作区（可为 None）
        print(f"agent       : {session.agent}")  # 会话默认 agent
        print(
            f"model       : "
            + (f"{session.model.provider_id}/{session.model.id}" if session.model else "（服务端默认）")
        )
        print(f"version     : {session.version}")  # 创建时的服务端版本
        print(f"created     : {session.time.created}  updated: {session.time.updated}")

        print(f"\nsession 已创建：{session.id}（本脚本不删除它；删除示例见 delete_session.py）")


def cli() -> None:
    """Parse args, run main, and translate library errors into exit codes."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=BASE_URL, help="opencode server base URL")
    parser.add_argument("--title", default="01 create demo", help="session title")
    parser.add_argument("--agent", default="", help="pin an agent name")
    parser.add_argument("--provider", default="", help="pin a provider id (with --model)")
    parser.add_argument("--model", default="", help="pin a model id (with --provider)")
    parser.add_argument("--directory", default=None, help="scope the session to a project directory")
    args = parser.parse_args()

    try:
        asyncio.run(
            main(
                base_url=args.url,
                title=args.title,
                agent=args.agent,
                provider_id=args.provider,
                model_id=args.model,
                directory=args.directory,
            )
        )
    except OpenCodeApiError as exc:
        print(f"[OpenCodeApiError] HTTP {exc.status_code}: {exc.payload}", file=sys.stderr)
        raise SystemExit(1) from exc
    except OpenCodeTransportError as exc:
        print(f"[transport] 无法完成与 {args.url} 的通信：{exc}", file=sys.stderr)
        print("  提示：确认服务已启动，例如 `opencode serve --port 4096`，或用 --url 指定。", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    cli()

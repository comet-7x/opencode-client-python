"""create_session：创建会话的完整参数面与返回字段一览。

演示 ``sessions.create`` 的三种姿势：不带 body 全默认、带 ``CreateSessionRequest``
钉标题/agent/模型、用 ``directory`` 作用域参数绑定项目目录；并逐个打印返回的
``Session`` 字段，看清服务端到底存了什么。

运行（仓库根目录）::

    uv run python -m examples.sessions.create_session
    uv run python -m examples.sessions.create_session --title 我的会话 --provider anthropic --model claude-x
    uv run python examples/sessions/create_session.py
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from opencode_client import (
    AsyncOpenCodeClient,
    CreateSessionRequest,
    ModelID,
    OpenCodeApiError,
    OpenCodeTransportError,
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
    """按给定参数创建一个会话并逐字段打印。

    Args:
        base_url: 服务地址。
        title: 会话标题（列表里靠它辨认）。
        agent: 可选，钉住一个 agent（build/plan/...）。
        provider_id: 与 model_id 成对出现时钉住模型。
        model_id: 同上。
        directory: 可选作用域，把会话钉在某个项目目录。
    """
    async with AsyncOpenCodeClient(base_url) as client:
        # 请求体字段全可选；只有用户同时给了 provider+model 才构造 ModelID 钉模型。
        # agent 的 argparse 默认 "" 归一成 None。
        body = CreateSessionRequest(
            title=title,
            model=ModelID(id=model_id, provider_id=provider_id) if provider_id and model_id else None,
            agent=agent or None,
        )
        # directory/workspace 是"请求级作用域参数"（query 参数），平铺在方法 kwargs 上而非塞进 body。
        session = await client.sessions.create(body=body, directory=directory)

        # 库已把 wire 的 camelCase/大写 ID（sessionID、projectID…）映射成 snake_case，
        # 直接读属性即可，无需关心线上格式。
        print("== 创建的 Session ==")
        print(f"id          : {session.id}")
        print(f"slug        : {session.slug}")
        print(f"title       : {session.title!r}")
        print(f"directory   : {session.directory}")
        print(f"project_id  : {session.project_id}")
        print(f"workspace_id: {session.workspace_id}")
        print(f"agent       : {session.agent}")
        model = f"{session.model.provider_id}/{session.model.id}" if session.model else "（服务端默认）"
        print(f"model       : {model}")
        print(f"version     : {session.version}")
        print(f"time        : created={session.time.created} updated={session.time.updated}")

        print(f"\nsession 已创建：{session.id}（本脚本不删除它；删除示例见 delete_session.py）")


def cli() -> None:
    """解析参数并运行 main。"""
    parser = argparse.ArgumentParser(description="创建一个会话并打印其全部字段")
    parser.add_argument("--url", default=BASE_URL, help="opencode server base URL")
    parser.add_argument("--title", default="create demo", help="session title")
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
        print(f"[transport] 无法连接 {args.url}：{exc}", file=sys.stderr)
        print("  提示：确认服务已启动，例如 `opencode serve --port 4096`，或用 --url 指定正确地址。", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    cli()

"""prompt_options：``sessions.prompt`` 的完整参数面。

quickstart 只用了 prompt 的最简形态（纯文本）；本脚本把其余参数逐个点亮：

- ``model=PromptModel(...)``   → 钉住 provider/model（从 list_providers 动态探测，不硬编码）
- ``system=``                  → 本次请求的 system 覆盖
- ``tools=``                   → 按名字开/关工具（``--disable-tool`` 时演示）
- ``agent=``                   → 指定 agent（``--agent`` 时演示，如内置的 build）
- 多轮连续对话                 → 同一会话内第二轮能记住第一轮内容
- ``no_reply=True``            → 只写入用户消息、不触发回答（作为后续 turn 的上下文）

运行（仓库根目录）::

    uv run python -m examples.sessions.prompt_options
    uv run python -m examples.sessions.prompt_options --provider anthropic --model claude-x
    uv run python -m examples.sessions.prompt_options --disable-tool bash
    uv run python -m examples.sessions.prompt_options --agent plan
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from opencode_client import (
    AsyncOpenCodeClient,
    CreateSessionRequest,
    MessageWithParts,
    OpenCodeApiError,
    OpenCodeTransportError,
    PromptModel,
    TextPart,
)

BASE_URL = "http://127.0.0.1:4096"


def _print_reply(reply: MessageWithParts, label: str) -> None:
    """打印一次回复的文本部分与消息角色。

    Args:
        reply: prompt 返回的消息（info + parts）。
        label: 展示用标签。
    """
    texts = [p.text for p in reply.parts if isinstance(p, TextPart)]
    answer = " ".join(texts)
    print(f"[{label}] role={reply.info.role}  answer={answer!r}")


async def main(
    base_url: str,
    provider_id: str | None,
    model_id: str | None,
    agent: str | None,
    disable_tool: str | None,
) -> None:
    """在同一会话里发多轮 prompt，逐个演示可选参数。

    Args:
        base_url: 服务地址。
        provider_id: 可选钉住的 provider（缺省动态探测第一个 connected）。
        model_id: 可选钉住的 model（缺省用该 provider 的默认模型）。
        agent: 可选，指定 agent 名（如 build/plan）。
        disable_tool: 可选，演示 tools= 关掉一个工具（传工具名，如 bash）。
    """
    async with AsyncOpenCodeClient(base_url) as client:
        # —— 动态挑模型：provider/model 名随部署变化，权威来源是 /provider 端点，
        #    connected 列出"真能出 token"的 provider，default 是其默认模型映射。
        providers = await client.server.list_providers()
        pid = provider_id or (providers.connected[0] if providers.connected else None)
        mid = model_id
        if pid and not mid:
            known = {p.id: p for p in providers.all}
            mid = providers.default.get(pid) or (next(iter(known[pid].models), None) if pid in known else None)
        model = PromptModel(provider_id=pid, model_id=mid) if pid and mid else None
        target = f"{pid}/{mid}" if model else "（服务端默认）"
        print(f"使用模型: {target}")

        session = await client.sessions.create(body=CreateSessionRequest(title="prompt options demo"))
        try:
            # —— 1) model + system：一句话约束 + 钉模型。system 只影响本次请求。
            reply = await client.sessions.prompt(
                session.id,
                "Reply with exactly one word: pong",
                model=model,
                system="Answer in one short sentence.",
            )
            _print_reply(reply, "model+system")

            # —— 2) 多轮：同一 session 自带历史，第二轮能引用第一轮。
            reply = await client.sessions.prompt(session.id, "What word did I ask you to reply with?", model=model)
            _print_reply(reply, "multi-turn")

            # —— 3) no_reply=True：消息入库但不触发回答，返回的是这条 user 消息；
            #     用途是预置上下文（比如先塞一段背景资料再正式提问）。
            reply = await client.sessions.prompt(
                session.id,
                "(context only, do not answer) My favorite color is blue.",
                model=model,
                no_reply=True,
            )
            print(f"[no_reply] 已写入 user 消息 {reply.info.id}，服务端不应作答")

            # —— 4) agent / tools：默认关着，避免依赖特定环境；需要时用参数点亮。
            if disable_tool:
                reply = await client.sessions.prompt(
                    session.id, "List files here without running any command.", model=model, tools={disable_tool: False}
                )
                _print_reply(reply, f"tools[{disable_tool}=False]")
            if agent:
                reply = await client.sessions.prompt(session.id, "Say hi.", model=model, agent=agent)
                _print_reply(reply, f"agent={agent}")
        finally:
            await client.sessions.delete(session.id)
            print("deleted session")


def cli() -> None:
    """解析参数并运行 main。"""
    parser = argparse.ArgumentParser(description="prompt() 的完整参数面演示")
    parser.add_argument("--url", default=BASE_URL, help="opencode server base URL")
    parser.add_argument("--provider", default=None, help="pin a provider id")
    parser.add_argument("--model", default=None, help="pin a model id")
    parser.add_argument("--agent", default=None, help="run one prompt as this agent (e.g. build)")
    parser.add_argument("--disable-tool", default=None, help="run one prompt with this tool disabled (e.g. bash)")
    args = parser.parse_args()

    try:
        asyncio.run(main(args.url, args.provider, args.model, args.agent, args.disable_tool))
    except OpenCodeApiError as exc:
        print(f"[OpenCodeApiError] HTTP {exc.status_code}: {exc.payload}", file=sys.stderr)
        raise SystemExit(1) from exc
    except OpenCodeTransportError as exc:
        print(f"[transport] 无法连接 {args.url}：{exc}", file=sys.stderr)
        print("  提示：确认服务已启动，例如 `opencode serve --port 4096`，或用 --url 指定正确地址。", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    cli()

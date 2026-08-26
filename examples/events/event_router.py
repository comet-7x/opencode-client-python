"""event_router：按类型订阅 /event——三行 on() 替代整个 if/elif 监听循环。

与 ``stream_events.py`` 同一件事（实时看一轮对话），但监听端从"80 行
``if event.type == ...`` + 手挖 properties 字典"收敛为三个订阅：

- **热事件自动类型化**——高频事件到达时已是类型化子类：
  ``message.part.updated`` 带 ``event.part: Part``（判别联合）、
  ``message.part.delta`` 带 ``event.part_id``/``event.field``/``event.delta``
  属性。未知类型与解析失败一律回落基类 Event，流永不断；
- **EventRouter**——``stream.route(session_id)`` 把全局广播收窄到单会话，
  handler 按到达顺序分发；``run(until="session.idle", timeout=...)`` 统一
  收口（idle / handler 抛错 / 超时 / 干净 EOF）。

运行（仓库根目录）::

    uv run python -m examples.events.event_router
    uv run python -m examples.events.event_router --provider anthropic --model claude-x
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from opencode_client import (
    AsyncOpenCodeClient,
    CreateSessionRequest,
    Event,
    MessagePartDeltaEvent,
    MessagePartUpdatedEvent,
    OpenCodeApiError,
    OpenCodeTransportError,
    ToolPart,
)

BASE_URL = "http://127.0.0.1:4096"
ATTACH_DELAY_SECONDS = 0.5  # 先让 run 把 /event 连接建好，再发 prompt
MAX_TURN_SECONDS = 300.0  # run 的兜底超时


async def main(base_url: str, provider_id: str | None = None, model_id: str | None = None) -> None:
    """发一个 prompt，用事件路由器渲染整轮对话直到 idle。

    Args:
        base_url: 服务地址。
        provider_id: 可选钉住 provider（与 model_id 成对生效）。
        model_id: 同上。
    """
    async with AsyncOpenCodeClient(base_url) as client:
        session = await client.sessions.create(body=CreateSessionRequest(title="event router demo"))
        try:
            async with client.server.stream_events() as stream:
                # route(session_id)：会话过滤下沉到路由层，handler 不再需要手动比对 sessionID。
                bus = stream.route(session.id)

                part_types: dict[str, str] = {}  # partID -> part.type（从 updated 事件学习）

                def on_part(event: Event) -> None:
                    """记录 part 类型；工具 part 额外打印状态迁移。"""
                    if not isinstance(event, MessagePartUpdatedEvent):
                        return
                    # isinstance 收窄后 event.part 是 Part 联合而非 dict。
                    part_types[event.part.id] = event.part.type
                    if isinstance(event.part, ToolPart):
                        print(f"\n[tool] {event.part.tool} -> {event.part.state.status}", flush=True)

                def on_delta(event: Event) -> None:
                    """打印正文/思考的增量文本。"""
                    if not isinstance(event, MessagePartDeltaEvent):
                        return
                    # delta 的 field 对思考/正文都是 "text"，仍靠 partID 映射分流。
                    ptype = part_types.get(event.part_id, "")
                    if ptype in ("text", "reasoning"):
                        prefix = "[思考] " if ptype == "reasoning" else ""
                        print(f"{prefix}{event.delta}", end="\n", flush=True)

                async def on_idle(event: Event) -> None:
                    """turn 结束信号。"""
                    print("\nturn 结束（session.idle）。", flush=True)

                bus.on("message.part.updated", on_part)
                bus.on("message.part.delta", on_delta)
                bus.on("session.idle", on_idle)

                # run 在 idle/handler 抛错/超时/干净 EOF 时收口；handler 可以是 sync 或 async。
                listener = asyncio.create_task(bus.run(until="session.idle", timeout=MAX_TURN_SECONDS))
                await asyncio.sleep(ATTACH_DELAY_SECONDS)

                model = {"providerID": provider_id, "modelID": model_id} if provider_id and model_id else None
                await client.sessions.prompt_async(session.id, "Count from one to five.", model=model)
                await listener
        finally:
            await client.sessions.delete(session.id)


def cli() -> None:
    """解析参数并运行 main。"""
    parser = argparse.ArgumentParser(description="按类型订阅 /event 并实时渲染一轮对话")
    parser.add_argument("--url", default=BASE_URL, help="opencode server base URL")
    parser.add_argument("--provider", default=None, help="pin a provider id (with --model)")
    parser.add_argument("--model", default=None, help="pin a model id (with --provider)")
    args = parser.parse_args()

    try:
        asyncio.run(main(args.url, args.provider, args.model))
    except OpenCodeApiError as exc:
        print(f"[OpenCodeApiError] HTTP {exc.status_code}: {exc.payload}", file=sys.stderr)
        raise SystemExit(1) from exc
    except OpenCodeTransportError as exc:
        print(f"[transport] 无法连接 {args.url}：{exc}", file=sys.stderr)
        print("  提示：确认服务已启动（事件流同样依赖它），或用 --url 指定正确地址。", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    cli()

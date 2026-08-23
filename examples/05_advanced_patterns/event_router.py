"""05 event_router: subscribe to /event by type — no if/elif, no dict digging.

The same job as ``stream_events.py`` (watch a turn live), but the listener
collapses from an 80-line ``if event.type == ...`` loop over
``event.properties`` into three ``bus.on(...)`` subscriptions.  Two things do
the work:

- **typed hot events** — frequently consumed event types arrive as typed
  subclasses, not dicts: ``message.part.updated`` carries
  ``event.part: Part`` (a discriminated union), ``message.part.delta`` carries
  ``event.part_id`` / ``event.field`` / ``event.delta`` fields.  Unknown
  types still arrive as the base :class:`Event`, so the stream never breaks;
- **the event router** — ``stream.route(session_id)`` filters the global
  broadcast down to one session and dispatches events to your handlers in
  arrival order; ``run(until=...)`` ends the run when the session goes idle
  (or a handler raises, or the timeout fires).

The ``partID -> type`` mapping trick from ``stream_events.py`` is still
needed (the server sends ``field: "text"`` for *both* reasoning and text
deltas), but it now runs inside a two-line handler instead of an 80-line loop.

Run (from the repo root):

    uv run python -m examples.05_advanced_patterns.event_router
    uv run python examples/05_advanced_patterns/event_router.py --provider anthropic --model claude-x
"""

from __future__ import annotations

import argparse  # --url/--provider/--model
import asyncio  # 并发两个任务：run 监听器 & 发 prompt
import sys  # 退出码

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
ATTACH_DELAY_SECONDS = 0.5  # 给 run 一点时间先把 /event 连接建好，再发 prompt
MAX_TURN_SECONDS = 300.0  # run 的兜底超时：turn 永远不 idle 时不挂死


async def main(base_url: str, provider_id: str | None = None, model_id: str | None = None) -> None:
    """Send a prompt and let the event router render the turn until idle.

    Args:
        base_url: server base URL.
        provider_id: 可选，钉住 provider（与 model_id 成对生效，否则用默认）。
        model_id: 可选，钉住 model。
    """
    async with AsyncOpenCodeClient(base_url) as client:
        session = await client.sessions.create(body=CreateSessionRequest(title="05 event router demo"))
        try:
            async with client.server.stream_events() as stream:
                # route(session_id)：全局广播自动收窄到本会话，handler 不再
                # 需要手动 if properties["sessionID"] != ...: continue。
                bus = stream.route(session.id)

                part_types: dict[str, str] = {}  # partID -> part.type（从 updated 事件学习）

                def on_part(event: Event) -> None:
                    # 热事件自动类型化：isinstance 收窄后 event.part 是 Part，
                    # 不是 dict——不需要 props.get("part", {}).get(...) 挖字典。
                    if not isinstance(event, MessagePartUpdatedEvent):
                        return
                    part_types[event.part.id] = event.part.type
                    if isinstance(event.part, ToolPart):
                        print(f"\n[tool] {event.part.tool} -> {event.part.state.status}", flush=True)

                def on_delta(event: Event) -> None:
                    if not isinstance(event, MessagePartDeltaEvent):
                        return
                    # delta 的 field 对思考/正文都是 "text"，仍靠 partID 映射分流。
                    ptype = part_types.get(event.part_id, "")
                    if ptype in ("text", "reasoning"):
                        prefix = "[思考] " if ptype == "reasoning" else ""
                        print(f"{prefix}{event.delta}", end="", flush=True)

                async def on_idle(event: Event) -> None:
                    print("\nturn 结束（session.idle）。", flush=True)

                # 三行订阅 = stream_events.py 里整个 if/elif 监听循环。
                bus.on("message.part.updated", on_part)
                bus.on("message.part.delta", on_delta)
                bus.on("session.idle", on_idle)

                # run 在 session.idle / handler 抛错 / 超时 / 干净 EOF 时收口。
                listener = asyncio.create_task(bus.run(until="session.idle", timeout=MAX_TURN_SECONDS))
                await asyncio.sleep(ATTACH_DELAY_SECONDS)

                model = {"providerID": provider_id, "modelID": model_id} if provider_id and model_id else None
                await client.sessions.prompt_async(session.id, "Count from one to five.", model=model)
                await listener
        finally:
            await client.sessions.delete(session.id)


def cli() -> None:
    """Parse args, run main, translate errors into exit codes."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=BASE_URL, help="opencode server base URL")
    parser.add_argument("--provider", default=None, help="pin a provider id")
    parser.add_argument("--model", default=None, help="pin a model id")
    args = parser.parse_args()

    try:
        asyncio.run(main(args.url, args.provider, args.model))
    except OpenCodeApiError as exc:
        print(f"[OpenCodeApiError] HTTP {exc.status_code}: {exc.payload}", file=sys.stderr)
        raise SystemExit(1) from exc
    except OpenCodeTransportError as exc:
        print(f"[transport] 无法完成与 {args.url} 的通信：{exc}", file=sys.stderr)
        print("  提示：确认服务已启动（事件流同样依赖它），或用 --url 指定。", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    cli()

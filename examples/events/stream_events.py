"""stream_events：裸流消费 /event——prompt_async + aiter_events 实时渲染。

``sessions.prompt`` 会阻塞到整个 turn 结束；要看**过程**（增量文本、思考、
工具状态），用 ``prompt_async`` 先发出去，再从 ``server.stream_events()``
的 SSE 流里读细粒度事件，直到该会话发出 ``session.idle`` 收尾信号。

本脚本演示"裸流"姿势：直接 ``aiter_events()`` 迭代基类 Event、手动按
``type`` 分支。按类型订阅 + 类型化 payload 的进阶姿势见同目录
``event_router.py``。

协议要点：``message.part.delta`` 的 ``field`` 对思考/正文都是 "text"，无法
直接区分；必须先用 ``message.part.updated``（properties.part 是完整 part，
含 type）建立 partID → 类型的映射。时序有保证：part 先 updated 后才有 delta。

运行（仓库根目录）::

    uv run python -m examples.events.stream_events
    uv run python -m examples.events.stream_events --provider anthropic --model claude-x
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from opencode_client import AsyncOpenCodeClient, CreateSessionRequest, OpenCodeApiError, OpenCodeTransportError

BASE_URL = "http://127.0.0.1:4096"
ATTACH_DELAY_SECONDS = 0.5  # 监听任务先把 /event 连接建好再发 prompt，避免漏掉前缀事件
MAX_LISTEN_SECONDS = 300.0  # 兜底超时：防止流因某种原因永远等不到 idle


async def listen_until_idle(client: AsyncOpenCodeClient, session_id: str) -> int:
    """读 /event 直到本会话 idle；区分并渲染思考/正文/工具三类事件。

    Args:
        client: 已打开的客户端。
        session_id: 只关心这个会话的事件（/event 是全服务器广播）。

    Returns:
        收到的事件条数。
    """
    count = 0
    part_types: dict[str, str] = {}  # partID -> part.type（从 updated 事件学习）
    tool_status: dict[str, str] = {}  # 每个 tool part 最近一次状态（只打印变化）
    thinking: set[str] = set()  # 正在输出思考块的 partID

    # stream_events() 返回 AsyncEventStream（async 上下文管理器），退出时必关连接。
    # max_reconnect_attempts=0 是演示场景的选择：idle 之后服务端可能关流，
    # 不想让监听协程在空连接上按 0.5s→8s 无限退避重连；生产环境去掉该参数即可。
    async with client.server.stream_events(max_reconnect_attempts=0) as stream:
        # aiter_events() 负责行解码 -> Event 对象；传输层断流会自动重连。
        async for event in stream.aiter_events():
            count += 1
            props = event.properties
            if props.get("sessionID") != session_id:
                continue  # 全局广播，先过滤出本会话

            handled = False
            if event.type == "message.part.updated":
                part = props.get("part", {})
                pid, ptype = part.get("id"), part.get("type")
                if pid:
                    part_types[pid] = ptype
                if ptype == "tool":
                    status = part.get("state", {}).get("status")
                    if tool_status.get(pid) != status:
                        tool_status[pid] = status
                        tool_name = part.get("tool")
                        print(f"\n[tool] {tool_name} -> {status}", flush=True)
                elif ptype == "reasoning":
                    # 空 text = 刚创建（开块）；带 text 的 updated = 推理结束（合块）。
                    if not part.get("text") and pid not in thinking:
                        thinking.add(pid)
                        print("\n--- 思考开始 ---", flush=True)
                    elif part.get("text") and pid in thinking:
                        thinking.discard(pid)
                        print("--- 思考结束 ---\n", flush=True)
                handled = True
            elif event.type == "message.part.delta":
                # delta 按 partID 分流到思考/正文（field 两者都是 "text"）。
                ptype = part_types.get(props.get("partID", ""), "")
                if props.get("field") == "text" and ptype in ("text", "reasoning"):
                    print(props.get("delta", ""), end="", flush=True)
                    handled = True

            if not handled:
                print(f"[event] {event.type}", flush=True)
            if event.type == "session.idle":
                print("\nturn 结束。", flush=True)
                return count
    return count  # 流被干净关闭（EOF）时兜底返回


async def main(base_url: str, provider_id: str | None = None, model_id: str | None = None) -> None:
    """发一个 prompt 并实时流式渲染它的全部事件，直到会话 idle。

    Args:
        base_url: 服务地址。
        provider_id: 可选钉住 provider（与 model_id 成对生效）。
        model_id: 同上。
    """
    async with AsyncOpenCodeClient(base_url) as client:
        session = await client.sessions.create(body=CreateSessionRequest(title="stream demo"))
        try:
            # 监听与发 prompt 必须并发：监听要先建好连接，prompt 才开始产生事件；
            # 串行的话（先发再连流）会漏掉前缀。
            listener_task = asyncio.create_task(listen_until_idle(client, session.id))
            await asyncio.sleep(ATTACH_DELAY_SECONDS)

            model = {"providerID": provider_id, "modelID": model_id} if provider_id and model_id else None
            await client.sessions.prompt_async(session.id, "Count from one to five.", model=model)

            done, _pending = await asyncio.wait({listener_task}, timeout=MAX_LISTEN_SECONDS)
            if listener_task not in done:
                listener_task.cancel()
                print("\n(超出等待上限，未观测到 session.idle)")
            else:
                await listener_task  # 把任务内部异常传播到这里统一处理
        finally:
            await client.sessions.delete(session.id)


def cli() -> None:
    """解析参数并运行 main。"""
    parser = argparse.ArgumentParser(description="裸流消费 /event 并实时渲染一轮对话")
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

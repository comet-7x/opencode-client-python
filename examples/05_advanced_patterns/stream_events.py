"""05 stream_events: watch a prompt live over the SSE event stream.

The difference vs ``sessions.prompt`` (which blocks until the whole turn
finishes): ``prompt_async`` fires the prompt and returns immediately, and we
read the server's ``/event`` stream for the fine-grained updates — including
incremental text deltas, tool states, and the ``session.idle`` end-of-turn
signal.

The stream is an :class:`EventStream` context manager; consume it with
``aiter_events()`` which decodes lines into :class:`Event` objects and
**reconnects automatically** after transient drops (see the package ``sse``
module). No manual ``SSEDecoder`` plumbing is needed.

Run (from the repo root):

    uv run python -m examples.05_advanced_patterns.stream_events
    uv run python examples/05_advanced_patterns/stream_events.py --provider anthropic --model claude-x
"""

from __future__ import annotations

import argparse  # --url/--provider/--model
import asyncio  # 事件循环 + 并发两个“任务”：监听流 & 发 prompt
import sys  # 退出码

from opencode_client import (
    AsyncOpenCodeClient,
    CreateSessionRequest,
    OpenCodeApiError,
    OpenCodeTransportError,
)

BASE_URL = "http://127.0.0.1:4096"
ATTACH_DELAY_SECONDS = 0.5  # 给“监听任务”一点时间先把 /event 连接建好，再发 prompt
MAX_LISTEN_SECONDS = 300.0  # 兜底超时：防止流因某种原因永远等不到 idle


async def listen_until_idle(client: AsyncOpenCodeClient, session_id: str) -> int:
    """Read the ``/event`` stream until this session reports ``session.idle``.

    Args:
        client: 已打开的客户端（用于发起流连接）。
        session_id: 只关心这个会话的事件（/event 是全服务器广播）。

    Returns:
        收到的事件条数（便于外层做简单校验）。
    """
    count = 0
    # stream_events() 返回 EventStream，是 async 上下文管理器：
    # 退出时一定关闭底层连接，即使中间抛了错。
    #
    # max_reconnect_attempts=0：本例只消费“一次连接”。生产环境若希望
    # “断流自动续上”，把这个参数去掉（默认 0.5s→8s 指数退避重连，收数据即重置
    # 预算，参见包内 sse 模块）。这里显式传 0，是怕服务端在 idle 之后直接关流，
    # 导致监听协程在空连接上按 0.5s/1s/2s 无限重连。
    async with client.server.stream_events(max_reconnect_attempts=0) as stream:
        # aiter_events() 负责：行解码 -> Event 对象；以及断流后的自动重连。
        # 我们只在这里“读并打印”，结束条件交给外层（idle）。
        async for event in stream.aiter_events():
            count += 1
            # 服务器把 ~94 种事件统一成 {type, properties}，这里按 type 分支。
            if event.type == "message.part.delta":
                # 增量文本：只打印 field==text 的 delta，end="" 让它拼接成一句。
                props = event.properties
                if props.get("field") == "text":
                    print(props.get("delta", ""), end="", flush=True)
            else:
                # 其他事件类型用一行摘要，避免刷屏。
                print(f"\n[event] {event.type}")
            # —— 结束信号：该会话进入 idle，说明本轮 turn（含所有工具调用）已结束。
            #    /event 是全局广播，必须用 sessionID 过滤，否则会误判别的会话结束。
            if event.type == "session.idle" and event.properties.get("sessionID") == session_id:
                return count
    return count  # 流被干净关闭（EOF）时兜底返回


async def main(base_url: str, provider_id: str | None = None, model_id: str | None = None) -> None:
    """Send a prompt and stream its events until the session goes idle.

    Args:
        base_url: server base URL.
        provider_id: 可选，钉住 provider（与 model_id 成对生效，否则用默认）。
        model_id: 可选，钉住 model。
    """
    async with AsyncOpenCodeClient(base_url) as client:
        session = await client.sessions.create(body=CreateSessionRequest(title="03 stream demo"))
        try:
            # —— 关键点：两个并发“协程任务”。
            #   1) listen_until_idle：持续读 /event 并把增量打到屏幕；
            #   2) 外层：发 prompt 并等监听器结束。
            # 为什么用 create_task 而不是直接在主流程里读流？
            #   因为“监听”和“发 prompt”是并发的：监听必须先跑起来（把连接建好），
            #   prompt 才能开始产生事件；若串行，就得先发 prompt 再连流，会漏掉前缀。
            listener_task = asyncio.create_task(listen_until_idle(client, session.id))
            # 给监听器一点时间完成 /event 连接（经验值；过大只会拖慢启动）。
            await asyncio.sleep(ATTACH_DELAY_SECONDS)

            # —— fire-and-forget 发 prompt：立刻返回，不等 turn 完成。
            #    真正的“完成”由监听器里的 session.idle 判定。
            model = {"providerID": provider_id, "modelID": model_id} if provider_id and model_id else None
            await client.sessions.prompt_async(session.id, "Count from one to five.", model=model)

            # —— 等监听器收尾；加一个全局兜底超时，防止 idle 永远不来而挂死。
            done, _pending = await asyncio.wait({listener_task}, timeout=MAX_LISTEN_SECONDS)
            if listener_task not in done:
                # 超时：显式取消并说明原因，而不是静默泄漏这个任务。
                listener_task.cancel()
                print("\n(超出等待上限，未观测到 session.idle)")
            else:
                await listener_task  # 把任务内部异常（若有）传播到此处统一处理
            print("\nturn 完成。")
        finally:
            # 无论成功/超时/异常，都清理会话。
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

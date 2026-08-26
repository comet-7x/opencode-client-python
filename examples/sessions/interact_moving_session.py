"""interact_moving_session：权限/问答自动应答，让一轮对话无人值守走完。

有些 turn 需要"人在回路"：agent 请求**工具权限**或抛出**追问**，turn 会
阻塞到被应答。本脚本把应答自动化——

1. ``prompt_async`` 发出 prompt；
2. 监听 /event 等该会话的 ``session.idle`` 收尾信号；
3. 同时轮询 ``server.list_permissions`` / ``server.list_questions`` 并逐个应答。

安全默认：权限一律 **reject**（绝不自动放行工具）；``--allow`` 才改为 once 放行。
``--respond`` 额外演示另外两个动词：``sessions.respond_permission``
（会话级端点）与 ``server.reject_question``（整题拒绝）。

运行（仓库根目录）::

    uv run python -m examples.sessions.interact_moving_session
    uv run python -m examples.sessions.interact_moving_session --allow
    uv run python -m examples.sessions.interact_moving_session --respond
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from opencode_client import AsyncOpenCodeClient, CreateSessionRequest, OpenCodeApiError, OpenCodeTransportError

BASE_URL = "http://127.0.0.1:4096"
POLL_SECONDS = 0.5  # 轮询间隔：够及时又不打爆服务端
MAX_WAIT_SECONDS = 180.0  # 整个 turn 的兜底超时


async def watch_until_idle(client: AsyncOpenCodeClient, session_id: str, idle: asyncio.Event) -> int:
    """后台读 /event，渲染增量输出；本会话 idle 时置位信号量。

    与 stream_events.py 同一套分流：思考增量 / 正文增量 / 工具状态迁移
    （part 类型靠 message.part.updated 的 properties.part 学习，delta 的
    field 对思考和正文都是 "text"，无法直接区分）。

    Args:
        client: 已打开的客户端。
        session_id: 只对该会话的 idle 敏感（/event 是全局广播）。
        idle: 信号量，主循环靠它知道 turn 结束了。

    Returns:
        收到的事件条数。
    """
    count = 0
    part_types: dict[str, str] = {}  # partID -> part.type
    tool_status: dict[str, str] = {}  # 每个 tool part 最近一次状态（只打印变化）
    thinking: set[str] = set()  # 正在输出思考块的 partID
    # 演示场景不自动重连（idle 后服务端可能关流，避免监听协程无限退避重连）；
    # 生产用法见 events/stream_events.py 注释。
    async with client.server.stream_events(max_reconnect_attempts=0) as stream:
        async for event in stream.aiter_events():  # 自动解码 + 断流自动重连
            count += 1
            props = event.properties
            if props.get("sessionID") != session_id:
                continue
            if event.type == "message.part.updated":
                part = props.get("part", {})
                pid, ptype = part.get("id"), part.get("type")
                if pid:
                    part_types[pid] = ptype
                if ptype == "tool":
                    status = part.get("state", {}).get("status")
                    if tool_status.get(pid) != status:
                        tool_status[pid] = status
                        print(f"[tool] {part.get('tool')} -> {status}", flush=True)
                elif ptype == "reasoning":
                    # 空 text = 刚创建（开块）；带上 text 的收尾 updated = 合块。
                    if not part.get("text") and pid not in thinking:
                        thinking.add(pid)
                        print("--- 思考开始 ---", flush=True)
                    elif part.get("text") and pid in thinking:
                        thinking.discard(pid)
                        print("--- 思考结束 ---", flush=True)
            elif event.type == "message.part.delta" and props.get("field") == "text":
                # 按 partID 分流：reasoning 的思考增量 / text 的正文增量。
                if part_types.get(props.get("partID", "")) in ("text", "reasoning"):
                    print(props.get("delta", ""), end="", flush=True)
            # pending 请求出现的事件；实际应答由轮询循环完成。
            elif event.type in ("permission.asked", "question.asked"):
                print(f"[interaction] {event.type}", flush=True)
            if event.type == "session.idle":
                idle.set()  # 通知主循环：turn 结束，停止轮询
                return count
    return count


async def answer_pending(client: AsyncOpenCodeClient, *, allow: bool) -> int:
    """把当前所有 pending 的权限/追问各应答一次（幂等：答过的不会再出现在列表里）。

    Args:
        client: 已打开的客户端。
        allow: True 用 once 批准工具权限；False 用 reject 拒绝（安全默认）。

    Returns:
        本轮应答数量。
    """
    answered = 0
    # —— 权限请求：阻塞式，不回应 turn 就会一直卡着。
    for perm in await client.server.list_permissions():
        decision = "once" if allow else "reject"  # 安全侧：默认拒绝，绝不无脑批准工具
        patterns = ", ".join(perm.patterns)
        print(f"permission {perm.id} ({perm.permission}: {patterns}) -> {decision}")
        await client.server.reply_permission(perm.id, decision)
        answered += 1
    # —— 追问请求：带选项的下拉题。这里演示"选第一个选项"的最低成本应答；
    #     真实产品里应把问题渲染给用户手动选；answers 是"每题一组 label"的二维数组。
    for question in await client.server.list_questions():
        options = question.questions[0].options
        answers = [[options[0].label]] if options else [[""]]
        text = question.questions[0].question
        print(f"question {question.id}: {text!r} -> {answers}")
        await client.server.reply_question(question.id, answers)
        answered += 1
    return answered


async def demo_remaining_verbs(client: AsyncOpenCodeClient) -> None:
    """演示主循环没用到的那两个交互动词（有 pending 请求时才触发）。

    Args:
        client: 已打开的客户端。
    """
    # sessions.respond_permission 与 server.reply_permission 等效，
    # 但路径挂在 /session/{id}/permissions/{pid} 下——适合只知道会话 id 的场景。
    permissions = await client.server.list_permissions()
    if permissions:
        perm = permissions[0]
        ok = await client.sessions.respond_permission(perm.session_id, perm.id, "reject")
        print(f"respond_permission: 会话 {perm.session_id} 的 {perm.id} -> reject = {ok}")
    else:
        print("respond_permission: 当前没有 pending 权限请求，跳过（跑一个会触发工具的 turn 再试）")

    # server.reject_question：不逐题作答，直接拒绝整个 question 请求。
    questions = await client.server.list_questions()
    if questions:
        ok = await client.server.reject_question(questions[0].id)
        print(f"reject_question: {questions[0].id} -> rejected = {ok}")
    else:
        print("reject_question: 当前没有 pending 问题请求，跳过")


async def run_turn(client: AsyncOpenCodeClient, *, allow: bool, model: dict[str, str] | None) -> int:
    """跑一轮 prompt 到结束，期间持续应答它的权限/追问。

    Args:
        client: 已打开的客户端。
        allow: 是否自动批准权限。
        model: 可选 ``{"providerID":..., "modelID":...}``。

    Returns:
        总共应答的交互数量。
    """
    session = await client.sessions.create(body=CreateSessionRequest(title="interact demo"))
    idle = asyncio.Event()
    total_answered = 0
    try:
        watcher = asyncio.create_task(watch_until_idle(client, session.id, idle))
        await asyncio.sleep(0.5)  # 同 stream_events.py：先让流连接建好再发 prompt，避免漏前缀
        # 这个 prompt 会触发文件列表工具 → 服务端发权限请求 → 轮询循环去应答。
        await client.sessions.prompt_async(session.id, "List the files in the current directory.", model=model)

        # —— 主循环：在 idle 或整体超时之前，持续清空 pending 交互。
        idle_task = asyncio.create_task(idle.wait())
        deadline = asyncio.create_task(asyncio.sleep(MAX_WAIT_SECONDS))
        try:
            while True:
                # 无条件先轮询一轮：快速 turn 的 idle 可能被监听流抢先消费，
                # 若只在"未 idle"时轮询，pending 交互就会永远得不到应答。
                total_answered += await answer_pending(client, allow=allow)
                if idle.is_set():
                    break
                # 任一子任务完成即醒（FIRST_COMPLETED），最多睡 POLL_SECONDS。
                done, _ = await asyncio.wait(
                    {idle_task, deadline}, timeout=POLL_SECONDS, return_when=asyncio.FIRST_COMPLETED
                )
                if deadline in done and not idle.is_set():
                    print(f"(整体超时 {MAX_WAIT_SECONDS}s 仍未 idle)")
                    break
        finally:
            # 三个子任务都显式 cancel 再回收：deadline 是长 sleep，
            # 不取消的话 gather 会干等它跑满整个超时。
            watcher.cancel()
            idle_task.cancel()
            deadline.cancel()
            await asyncio.gather(watcher, idle_task, deadline, return_exceptions=True)

        print(f"\nturn 结束，共应答 {total_answered} 个交互。")
        return total_answered
    finally:
        await client.sessions.delete(session.id)


async def main(base_url: str, allow: bool, respond: bool, provider_id: str | None, model_id: str | None) -> None:
    """打开客户端并完整跑一轮带交互应答的对话。

    Args:
        base_url: 服务地址。
        allow: 是否自动批准工具权限。
        respond: 是否额外演示 respond_permission / reject_question。
        provider_id: 可选 provider。
        model_id: 可选 model。
    """
    model = {"providerID": provider_id, "modelID": model_id} if provider_id and model_id else None
    async with AsyncOpenCodeClient(base_url) as client:
        await run_turn(client, allow=allow, model=model)
        if respond:
            print("\n== 其余两个交互动词 ==")
            await demo_remaining_verbs(client)


def cli() -> None:
    """解析参数并运行 main。"""
    parser = argparse.ArgumentParser(description="权限/问答自动应答循环")
    parser.add_argument("--url", default=BASE_URL, help="opencode server base URL")
    parser.add_argument("--allow", action="store_true", help="auto-approve tool permissions (default: reject)")
    parser.add_argument("--respond", action="store_true", help="also demo respond_permission / reject_question")
    parser.add_argument("--provider", default=None, help="pin a provider id")
    parser.add_argument("--model", default=None, help="pin a model id")
    args = parser.parse_args()

    try:
        asyncio.run(main(args.url, args.allow, args.respond, args.provider, args.model))
    except OpenCodeApiError as exc:
        print(f"[OpenCodeApiError] HTTP {exc.status_code}: {exc.payload}", file=sys.stderr)
        raise SystemExit(1) from exc
    except OpenCodeTransportError as exc:
        print(f"[transport] 无法连接 {args.url}：{exc}", file=sys.stderr)
        print("  提示：确认服务已启动，例如 `opencode serve --port 4096`，或用 --url 指定正确地址。", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    cli()

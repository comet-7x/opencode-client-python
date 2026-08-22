"""05 interact_moving_session: keep a turn moving by answering its requests.

Some prompts need a human in the loop: the agent asks for **tool permission**
(``permission.updated``) or poses a follow-up **question** (``question.updated``),
and the turn blocks until answered. This script automates that loop so a turn
runs unattended:

- start a ``prompt_async``;
- watch the ``/event`` stream for the ``session.idle`` end-of-turn signal;
- meanwhile poll ``server.list_permissions`` / ``server.list_questions`` and
  answer each pending request.

With ``--respond`` the script additionally demos the two remaining interaction
verbs on a pre-existing pending request pair: ``sessions.respond_permission``
(the session-scoped endpoint) and ``server.reject_question``.

Safety default: permissions are answered **reject** (never auto-grant a tool).
Pass ``--allow`` to auto-approve with ``once`` instead.

Run (from the repo root):

    uv run python -m examples.05_advanced_patterns.interact_moving_session
    uv run python -m examples.05_advanced_patterns.interact_moving_session --allow
    uv run python -m examples.05_advanced_patterns.interact_moving_session --respond
"""

from __future__ import annotations

import argparse  # --url/--allow/--provider/--model
import asyncio  # 并发：监听流 / 等 idle / 轮询交互 三者一起跑
import sys  # 退出码

from opencode_client import (
    AsyncOpenCodeClient,
    CreateSessionRequest,
    OpenCodeApiError,
    OpenCodeTransportError,
)

BASE_URL = "http://127.0.0.1:4096"
POLL_SECONDS = 0.5  # 交互轮询间隔：够及时，又不至于打爆服务端
MAX_WAIT_SECONDS = 180.0  # 整个 turn 的兜底超时


async def watch_until_idle(client: AsyncOpenCodeClient, session_id: str, idle: asyncio.Event) -> int:
    """Read /event until this session reports idle; flip the ``idle`` event.

    Args:
        client: 已打开的客户端。
        session_id: 只对这一会话的 idle 敏感（/event 是全局广播）。
        idle: 信号量，主循环靠它知道 turn 结束了。

    Returns:
        收到的事件条数。
    """
    count = 0
    # 同 stream_events.py：演示场景下明确“不自动重连”（idle 后服务端可能关流，
    # 避免监听协程在空连接上无限退避重连）；生产用法见该文件注释。
    async with client.server.stream_events(max_reconnect_attempts=0) as stream:
        async for event in stream.aiter_events():  # 自动解码 + 断流自动重连
            count += 1
            # 只把“交互类”事件单独标注，其余统一成一行普通事件。
            label = "interaction" if event.type in ("permission.updated", "question.updated") else "event"
            print(f"[{label}] {event.type}")
            if event.type == "session.idle" and event.properties.get("sessionID") == session_id:
                idle.set()  # 通知主循环：turn 结束，停止轮询
                return count
    return count


async def answer_pending(client: AsyncOpenCodeClient, *, allow: bool) -> int:
    """Answer every currently-pending permission/question once each.

    幂等：对同一批请求重复调用是安全的（应答过的不再出现在 list 里）。

    Args:
        client: 已打开的客户端。
        allow: True 用 ``once`` 批准工具权限；False 用 ``reject`` 拒绝（安全默认）。

    Returns:
        本轮应答的交互数量。
    """
    answered = 0
    # —— 权限请求：阻塞式，不回应 turn 就会一直卡着。
    for perm in await client.server.list_permissions():
        decision = "once" if allow else "reject"  # 安全侧：默认拒绝，绝不无脑批准工具
        print(f"permission {perm.id} ({perm.permission}: {', '.join(perm.patterns)}) -> {decision}")
        await client.server.reply_permission(perm.id, decision)
        answered += 1
    # —— 追问请求：带选项的下拉题。这里演示“选第一个选项”的最低成本应答。
    #     真实产品里应把问题渲染给用户手动选；answers 是“每题一组 label”的二维数组。
    for question in await client.server.list_questions():
        options = question.questions[0].options
        answers = [[options[0].label]] if options else [[""]]
        print(f"question {question.id}: {question.questions[0].question!r} -> {answers}")
        await client.server.reply_question(question.id, answers)
        answered += 1
    return answered


async def demo_remaining_verbs(client: AsyncOpenCodeClient) -> None:
    """Demo the two interaction verbs the polling loop above doesn't use.

    The main loop answers requests via the server-scoped endpoints
    (``server.reply_permission`` / ``server.reply_question``). opencode also
    exposes a session-scoped permission endpoint (``sessions.respond_permission``)
    and a question rejection endpoint (``server.reject_question``); this
    function drives both against a real pending request when one happens to
    exist.

    Args:
        client: 已打开的客户端。
    """
    # —— sessions.respond_permission：与 server.reply_permission 效果相同，
    #    但路径挂在 /session/{id}/permissions/{pid} 下，适合"我只知道会话 id"的场景。
    permissions = await client.server.list_permissions()
    if permissions:
        perm = permissions[0]
        ok = await client.sessions.respond_permission(perm.session_id, perm.id, "reject")
        print(f"respond_permission: 会话 {perm.session_id} 的 {perm.id} -> reject = {ok}")
    else:
        print("respond_permission: 当前没有 pending 权限请求，跳过（跑一个会触发工具的 turn 再试）")

    # —— server.reject_question：不回答、直接拒绝整个 question 请求
    #    （区别于 reply_question：逐题给答案）。
    questions = await client.server.list_questions()
    if questions:
        ok = await client.server.reject_question(questions[0].id)
        print(f"reject_question: {questions[0].id} -> rejected = {ok}")
    else:
        print("reject_question: 当前没有 pending 问题请求，跳过")


async def run_turn(client: AsyncOpenCodeClient, *, allow: bool, model: dict[str, str] | None) -> int:
    """Run one prompt to completion, answering whatever it asks for.

    Args:
        client: 已打开的客户端。
        allow: 是否自动批准权限（见 :func:`answer_pending`）。
        model: 可选 ``{"providerID":..., "modelID":...}``。

    Returns:
        总共应答的交互数量。
    """
    session = await client.sessions.create(body=CreateSessionRequest(title="03 interact demo"))
    idle = asyncio.Event()
    total_answered = 0
    try:
        # 监听流作为独立任务，在 background 把 idle 信号送进来。
        watcher = asyncio.create_task(watch_until_idle(client, session.id, idle))
        await asyncio.sleep(0.5)  # 等连接建立（同 stream_events.py 的时序原因）
        await client.sessions.prompt_async(session.id, "List the files in the current directory.", model=model)

        # —— 主循环：在“turn 结束(idle)”或“整体超时”之前，持续应答 pending 交互。
        idle_task = asyncio.create_task(idle.wait())  # wait() 本身是协程，包成任务参与 wait
        deadline = asyncio.create_task(asyncio.sleep(MAX_WAIT_SECONDS))  # 兜底闹钟
        try:
            while not idle.is_set():
                total_answered += await answer_pending(client, allow=allow)
                # 睡 POLL_SECONDS，或更早就绪（idle 到了 / 超期了）就醒。
                # return_when=FIRST_COMPLETED：任一完成即返回，done/pending 分开。
                done, _ = await asyncio.wait(
                    {idle_task, deadline}, timeout=POLL_SECONDS, return_when=asyncio.FIRST_COMPLETED
                )
                if deadline in done and not idle.is_set():
                    print(f"(整体超时 {MAX_WAIT_SECONDS}s 仍未 idle)")
                    break
        finally:
            # 三个子任务都显式 cancel 再 gather 回收：
            # deadline 是 180s 的 sleep，若不取消，gather 会干等它跑满整个超时。
            watcher.cancel()
            idle_task.cancel()
            deadline.cancel()
            # cancel 后的 await/gather 抛出 CancelledError，return_exceptions=True 吃掉。
            await asyncio.gather(watcher, idle_task, deadline, return_exceptions=True)
        print(f"\nturn 结束，共应答 {total_answered} 个交互。")
        return total_answered
    finally:
        await client.sessions.delete(session.id)  # 清理会话


async def main(base_url: str, allow: bool, respond: bool, provider_id: str | None, model_id: str | None) -> None:
    """Open the client and run one interactive turn.

    Args:
        base_url: server base URL.
        allow: 是否自动批准工具权限。
        respond: 是否额外演示 respond_permission / reject_question 两个动词。
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
    """Parse args, run main, translate errors into exit codes."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=BASE_URL, help="opencode server base URL")
    parser.add_argument("--allow", action="store_true", help="auto-approve tool permissions")
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
        print(f"[transport] 无法完成与 {args.url} 的通信：{exc}", file=sys.stderr)
        print("  提示：确认服务已启动，或用 --url 指定。", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    cli()

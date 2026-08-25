"""01 session_lifecycle: every session verb after create/list/delete.

Companion to ``create_session.py`` / ``list_sessions.py`` / ``delete_session.py``:
this one walks the remaining ``client.sessions.*`` verbs on a single
throwaway session so you can see each call and its return value:

- ``update()``          -> PATCH title/metadata, see the returned Session
- ``get()``             -> fetch one session back by id
- ``fork()``            -> branch a new session off it (optionally at a message)
- ``abort()``           -> stop a running turn (safe on an idle session too)
- ``share()``/``unshare()`` -> publish / withdraw the share URL
- ``summarize()``       -> ask the server to summarize with a chosen model
- ``delete_message()``  -> drop a single message from the history

All created artifacts (session + fork) are deleted again at the end.

Run (from the repo root):

    uv run python -m examples.sessions.session_lifecycle
    uv run python -m examples.sessions.session_lifecycle --provider anthropic --model claude-x
"""

from __future__ import annotations

import argparse  # --url/--provider/--model
import asyncio  # 事件循环
import sys  # 退出码

from opencode_client import (
    AsyncOpenCodeClient,
    CreateSessionRequest,
    OpenCodeApiError,
    OpenCodeNotFoundError,  # get 不存在的会话时演示用
    OpenCodeTransportError,
    UpdateSessionRequest,
)

BASE_URL = "http://127.0.0.1:4096"


async def _share_guarded(client: AsyncOpenCodeClient, session_id: str) -> None:
    """Call share() then unshare(), tolerating deployments without sharing.

    Some opencode deployments run without a share gateway; the endpoints then
    answer with a non-2xx. We surface that as a warning instead of aborting
    the whole demo.

    Args:
        client: 已打开的客户端。
        session_id: 目标会话。
    """
    try:
        shared = await client.sessions.share(session_id)
    except OpenCodeApiError as exc:
        print(f"（share 不可用，HTTP {exc.status_code}：本部署可能未启用分享网关，跳过）")
        return
    # share 成功后，Session.share 里带上公开 URL（SessionShare.url）。
    print(f"share     : {shared.share.url if shared.share else '（未返回 URL）'}")
    unshared = await client.sessions.unshare(session_id)
    print(f"unshare   : share 字段已清空 = {unshared.share is None}")


async def main(base_url: str, provider_id: str | None, model_id: str | None) -> None:
    """Run every lifecycle verb once on a throwaway session.

    Args:
        base_url: server base URL.
        provider_id: 可选，summarize 用的 provider（缺省用 connected 的第一个）。
        model_id: 可选，summarize 用的 model（缺省用该 provider 的默认模型）。
    """
    async with AsyncOpenCodeClient(base_url) as client:
        session = await client.sessions.create(body=CreateSessionRequest(title="01 lifecycle demo"))
        print(f"== 基线会话 ==\ncreated   : {session.id}  title={session.title!r}")

        try:
            # —— update：PATCH 语义，只改传入的字段；返回更新后的完整 Session。
            updated = await client.sessions.update(
                session.id, body=UpdateSessionRequest(title="01 lifecycle renamed", metadata={"tag": "demo"})
            )
            print(f"update    : title={updated.title!r}  metadata={updated.metadata}")

            # —— get：按 id 取回单个会话（与 list 的区别：单个、无过滤参数）。
            fetched = await client.sessions.get(session.id)
            print(f"get       : {fetched.id} == {session.id} -> {fetched.id == session.id}")

            # —— get 的失败面：404 落到 OpenCodeNotFoundError（OpenCodeApiError 子类）。
            try:
                await client.sessions.get("ses_does_not_exist_0000")
            except OpenCodeNotFoundError as exc:
                print(f"get 404   : 捕获 OpenCodeNotFoundError（status={exc.status_code}）")

            # —— fork：从当前状态分叉出一个新会话（不带 message_id 即 fork 最新态）。
            #    fork 出来的会话是独立实体：继续对话互不影响。
            branch = await client.sessions.fork(session.id)
            print(f"fork      : 新会话 {branch.id}  title={branch.title!r}")

            # —— abort：中止进行中的 turn；对空闲会话调用是安全无副作用的。
            aborted = await client.sessions.abort(session.id)
            print(f"abort     : {aborted}")

            # —— share / unshare（部分部署未启用，见 _share_guarded）。
            await _share_guarded(client, session.id)

            # —— summarize：让服务端用指定模型生成会话摘要，写回 Session.summary。
            #    模型从 list_providers 动态选，不硬编码（环境不同名字会变）。
            providers = await client.server.list_providers()
            pid = provider_id or (providers.connected[0] if providers.connected else None)
            if pid and pid in {p.id: p for p in providers.all}:
                provider = next(p for p in providers.all if p.id == pid)
                mid = model_id or (providers.default.get(pid) or next(iter(provider.models), None))
                if mid:
                    done = await client.sessions.summarize(session.id, pid, mid)
                    print(f"summarize : {done}（provider={pid} model={mid}）")
                else:
                    print("summarize : 该 provider 没有可用模型，跳过")
            else:
                print(f"summarize : 无法确定 provider（connected={providers.connected}），跳过")

            # —— delete_message：删掉会话里某一条消息。
            #    先用 prompt 造一条 user+assistant 消息，再删掉 user 那条。
            reply = await client.sessions.prompt(session.id, "Hi, this message will be deleted.")
            # list_messages 最新在前；刚发的 user 消息是倒数第二条（最后一条是 assistant）。
            messages = await client.sessions.list_messages(session.id)
            user_message = next(m for m in messages if m.info.role == "user")
            deleted = await client.sessions.delete_message(session.id, user_message.info.id)
            print(f"delete_msg: 删除 {user_message.info.id} -> {deleted}（回复 {reply.info.id} 保留）")

            # —— 收尾：把 fork 出来的分支也删掉，不留垃圾。
            await client.sessions.delete(branch.id)
            print(f"cleanup   : 已删除 fork 分支 {branch.id}")
        finally:
            # 无论中间哪一步失败，主会话都清掉。
            await client.sessions.delete(session.id)
            print(f"cleanup   : 已删除主会话 {session.id}")


def cli() -> None:
    """Parse args, run main, translate library errors into exit codes."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=BASE_URL, help="opencode server base URL")
    parser.add_argument("--provider", default=None, help="provider id for summarize (default: first connected)")
    parser.add_argument("--model", default=None, help="model id for summarize (default: provider default)")
    args = parser.parse_args()

    try:
        asyncio.run(main(args.url, args.provider, args.model))
    except OpenCodeApiError as exc:
        print(f"[OpenCodeApiError] HTTP {exc.status_code}: {exc.payload}", file=sys.stderr)
        raise SystemExit(1) from exc
    except OpenCodeTransportError as exc:
        print(f"[transport] 无法完成与 {args.url} 的通信：{exc}", file=sys.stderr)
        print("  提示：确认服务已启动，例如 `opencode serve --port 4096`，或用 --url 指定。", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    cli()

"""session_lifecycle：CRUD 之外的全部会话动词，在一个临时会话上走完。

与 create/list/delete 三个单动词脚本互补，本脚本在同一个一次性会话上依次
演示其余 ``client.sessions.*`` 动词及各自返回值：

- ``update()``           → PATCH 标题/metadata（只改传入的字段）
- ``get()``              → 按 id 取回单个会话；404 映射为 OpenCodeNotFoundError
- ``fork()``             → 从当前状态分叉出新会话（可指定 message_id 定点分叉）
- ``abort()``            → 中止进行中的 turn（对空闲会话调用是安全无副作用的）
- ``share()``/``unshare()`` → 发布 / 撤回分享链接（部分部署未启用分享网关）
- ``summarize()``        → 让服务端用指定模型生成会话摘要
- ``delete_message()``   → 删除单条消息（会话保留）
- ``shell()``/``command()``/``init()`` → prompt 的三个变体入口
- ``update_part()``/``delete_part()``  → 消息内 part 的编辑与删除

所有创建的产物（主会话 + fork 分支）最后都会删除。

运行（仓库根目录）::

    uv run python -m examples.sessions.session_lifecycle
    uv run python -m examples.sessions.session_lifecycle --provider anthropic --model claude-x
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from opencode_client import (
    AsyncOpenCodeClient,
    CreateSessionRequest,
    OpenCodeApiError,
    OpenCodeNotFoundError,
    OpenCodeTransportError,
    TextPart,
    UpdateSessionRequest,
)

BASE_URL = "http://127.0.0.1:4096"


async def _share_guarded(client: AsyncOpenCodeClient, session_id: str) -> None:
    """调用 share/unshare，容忍未启用分享网关的部署。

    部署可以不配 share 网关，此时端点回非 2xx；这里降级成警告而不是中断整个演示。

    Args:
        client: 已打开的客户端。
        session_id: 目标会话。
    """
    try:
        shared = await client.sessions.share(session_id)
    except OpenCodeApiError as exc:
        print(f"（share 不可用，HTTP {exc.status_code}：本部署可能未启用分享网关，跳过）")
        return
    # 分享成功后，公开 URL 在 Session.share.url 上。
    url = shared.share.url if shared.share else "（未返回 URL）"
    print(f"share     : {url}")
    unshared = await client.sessions.unshare(session_id)
    print(f"unshare   : share 字段已清空 = {unshared.share is None}")


async def main(base_url: str, provider_id: str | None, model_id: str | None) -> None:
    """在一个临时会话上把每个生命周期动词各跑一次。

    Args:
        base_url: 服务地址。
        provider_id: 可选，summarize/init 用的 provider（缺省用 connected 的第一个）。
        model_id: 可选，summarize/init 用的 model（缺省用该 provider 的默认模型）。
    """
    async with AsyncOpenCodeClient(base_url) as client:
        session = await client.sessions.create(body=CreateSessionRequest(title="lifecycle demo"))
        print(f"== 基线会话 ==\ncreated   : {session.id}  title={session.title!r}")

        try:
            # PATCH 语义：只覆盖传入字段，返回更新后的完整 Session。
            updated = await client.sessions.update(
                session.id, body=UpdateSessionRequest(title="lifecycle renamed", metadata={"tag": "demo"})
            )
            print(f"update    : title={updated.title!r}  metadata={updated.metadata}")

            fetched = await client.sessions.get(session.id)
            print(f"get       : {fetched.id}（== 创建的 id：{fetched.id == session.id}）")

            # get 的失败面：不存在的 id 回 404，映射为具体子类。
            try:
                await client.sessions.get("ses_does_not_exist_0000")
            except OpenCodeNotFoundError as exc:
                print(f"get 404   : 捕获 OpenCodeNotFoundError（status={exc.status_code}）")

            # fork 出来的会话是独立实体：继续对话互不影响；不带 message_id 即 fork 最新态。
            branch = await client.sessions.fork(session.id)
            print(f"fork      : 新会话 {branch.id}  title={branch.title!r}")

            aborted = await client.sessions.abort(session.id)
            print(f"abort     : {aborted}")

            await _share_guarded(client, session.id)

            # summarize 需要指定模型。provider/model 名随环境变化，
            # 权威来源是 list_providers().connected + default 映射，不要硬编码。
            providers = await client.server.list_providers()
            pid = provider_id or (providers.connected[0] if providers.connected else None)
            mid: str | None = None
            known = {p.id: p for p in providers.all}
            if pid in known:
                mid = model_id or (providers.default.get(pid) or next(iter(known[pid].models), None))
                if mid:
                    done = await client.sessions.summarize(session.id, pid, mid)
                    print(f"summarize : {done}（provider={pid} model={mid}）")
                else:
                    print("summarize : 该 provider 没有可用模型，跳过")
            else:
                print(f"summarize : 无法确定 provider（connected={providers.connected}），跳过")

            # delete_message：先用 prompt 造一条 user+assistant 消息，再删掉 user 那条。
            # list_messages 最新在前：刚发的 user 消息是倒数第二条（最后一条是 assistant）。
            reply = await client.sessions.prompt(session.id, "Hi, this message will be deleted.")
            messages = await client.sessions.list_messages(session.id)
            user_message = next(m for m in messages if m.info.role == "user")
            deleted = await client.sessions.delete_message(session.id, user_message.info.id)
            print(f"delete_msg: 删除 {user_message.info.id} -> {deleted}（回复 {reply.info.id} 保留）")

            # prompt 的三个变体端点：command（斜杠命令）/ shell（直接跑命令）/
            # init（让 agent 生成 AGENTS.md）。它们与 prompt 共享会话，只是输入形态不同；
            # shell 最直观：不经过模型，直接把命令结果喂进上下文。
            shelled = await client.sessions.shell(session.id, "echo shell-demo", agent="build")
            print(f"shell     : assistant 回复 {shelled.info.id}")
            commanded = await client.sessions.command(session.id, "test", "demo arguments")
            print(f"command   : assistant 回复 {commanded.info.id}")

            # init 需要指定 provider/model 对（写 worktree，演示调用形态）。
            if pid and mid:
                inited = await client.sessions.init(session.id, pid, mid, reply.info.id)
                print(f"init      : {inited}")
            else:
                print("init      : 无法确定 provider/model，跳过")

            # part 编辑：改完再删 assistant 回复里的第一个 text part。
            # PATCH /part 的 body 是完整的 Part 形状（响应侧模型，含三元组 id）。
            parts = next(m for m in messages if m.info.role == "assistant").parts
            text_part = next(p for p in parts if isinstance(p, TextPart))
            edited = await client.sessions.update_part(
                session.id,
                reply.info.id,
                text_part.id,
                TextPart(
                    id=text_part.id,
                    session_id=session.id,
                    message_id=reply.info.id,
                    type="text",
                    text="[edited by update_part demo]",
                ),
            )
            print(f"update_part: {edited.id} -> ok")
            removed = await client.sessions.delete_part(session.id, reply.info.id, text_part.id)
            print(f"delete_part: {text_part.id} -> {removed}")

            await client.sessions.delete(branch.id)
            print(f"cleanup   : 已删除 fork 分支 {branch.id}")
        finally:
            # 无论中间哪一步失败，主会话都清掉。
            await client.sessions.delete(session.id)
            print(f"cleanup   : 已删除主会话 {session.id}")


def cli() -> None:
    """解析参数并运行 main。"""
    parser = argparse.ArgumentParser(description="在一个临时会话上走完全部会话动词")
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
        print(f"[transport] 无法连接 {args.url}：{exc}", file=sys.stderr)
        print("  提示：确认服务已启动，例如 `opencode serve --port 4096`，或用 --url 指定正确地址。", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    cli()

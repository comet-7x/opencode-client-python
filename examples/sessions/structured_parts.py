"""structured_parts：prompt 的 parts 列表形式——一条消息多个内容块。

``prompt()`` 的第一个参数除了纯文本，还接受 ``list[PromptPart]``：按顺序
组装成 wire 上的 ``parts`` 数组，一条消息里可以混排多种块。四种输入块：

- :class:`TextPartInput`    —— 文本段（本脚本默认演示）
- :class:`FilePartInput`    —— 文件附件（url/mime 原样透传给服务端；``--file-url`` 演示）
- :class:`SubtaskPartInput` —— 子任务委派（需指定 agent+model；``--subtask`` 演示）

文件/子任务依赖具体环境（文件 URL 语义、可用 agent/model），所以默认只跑
纯文本组合，其余用参数点亮。

运行（仓库根目录）::

    uv run python -m examples.sessions.structured_parts
    uv run python -m examples.sessions.structured_parts --file-url file:///tmp/a.txt --mime text/plain
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from opencode_client import (
    AsyncOpenCodeClient,
    CreateSessionRequest,
    FilePartInput,
    OpenCodeApiError,
    OpenCodeTransportError,
    PromptPart,  # 四种输入块的判别联合（type 判别键：text|file|agent|subtask）
    SubtaskModel,
    SubtaskPartInput,
    TextPart,
    TextPartInput,
)

BASE_URL = "http://127.0.0.1:4096"


async def main(
    base_url: str,
    file_url: str | None,
    mime: str | None,
    subtask_agent: str | None,
) -> None:
    """用 parts 列表发一条多块消息并打印回答。

    Args:
        base_url: 服务地址。
        file_url: 可选，追加一个 FilePartInput（url 原样透传）。
        mime: file_url 对应的 MIME 类型。
        subtask_agent: 可选，追加一个 SubtaskPartInput（委派给该 agent）；
            子任务的模型从 list_providers 动态探测。
    """
    # 纯文本 prompt(str) 就是"自动包成一个 TextPartInput"的语法糖，
    # 需要多块/附件/委派时才需要显式列表。
    parts: list[PromptPart] = [
        TextPartInput(type="text", text="Here comes a multi-part message."),
        TextPartInput(type="text", text="Summarize everything above in five words."),
    ]

    async with AsyncOpenCodeClient(base_url) as client:
        if file_url and mime:
            parts.append(FilePartInput(type="file", url=file_url, mime=mime))
        if subtask_agent:
            # 子任务必须指定模型：动态探测，不硬编码名字。
            providers = await client.server.list_providers()
            pid = providers.connected[0] if providers.connected else None
            if pid is None:
                print("没有 connected 的 provider，无法构造 subtask（跳过该块）。")
            else:
                known = {p.id: p for p in providers.all}
                mid = providers.default.get(pid) or next(iter(known[pid].models))
                parts.append(
                    SubtaskPartInput(
                        type="subtask",
                        prompt="List the top-level files of this project.",
                        description="顶层文件扫描",
                        agent=subtask_agent,
                        model=SubtaskModel(provider_id=pid, model_id=mid),
                    )
                )

        session = await client.sessions.create(body=CreateSessionRequest(title="structured parts demo"))
        try:
            reply = await client.sessions.prompt(session.id, parts)
            print(f"sent {len(parts)} part(s), role={reply.info.role}")
            for part in reply.parts:
                if isinstance(part, TextPart):
                    print(f"assistant text: {part.text[:120]!r}")
        finally:
            await client.sessions.delete(session.id)
            print("deleted session")


def cli() -> None:
    """解析参数并运行 main。"""
    parser = argparse.ArgumentParser(description="parts 列表形式的 prompt 演示")
    parser.add_argument("--url", default=BASE_URL, help="opencode server base URL")
    parser.add_argument("--file-url", default=None, help="append a file part with this url (passed through as-is)")
    parser.add_argument("--mime", default=None, help="mime type for --file-url (e.g. text/plain)")
    parser.add_argument("--subtask", dest="subtask_agent", default=None, help="append a subtask part run by this agent")
    args = parser.parse_args()

    if bool(args.file_url) != bool(args.mime):
        parser.error("--file-url 与 --mime 必须成对给出")

    try:
        asyncio.run(main(args.url, args.file_url, args.mime, args.subtask_agent))
    except OpenCodeApiError as exc:
        print(f"[OpenCodeApiError] HTTP {exc.status_code}: {exc.payload}", file=sys.stderr)
        raise SystemExit(1) from exc
    except OpenCodeTransportError as exc:
        print(f"[transport] 无法连接 {args.url}：{exc}", file=sys.stderr)
        print("  提示：确认服务已启动，例如 `opencode serve --port 4096`，或用 --url 指定正确地址。", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    cli()

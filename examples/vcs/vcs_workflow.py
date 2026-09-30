"""vcs_workflow：通过服务端查看并修补工作区改动。

``client.vcs.*`` 让 opencode 服务端替你操作项目仓库的版本状态——客户端与
仓库同机时，它提供一个统一的编程入口："改了什么 → 看细节 → 落补丁"：

- ``vcs.info()``         → 当前分支 + 默认分支
- ``vcs.status()``       → 改动文件列表（增删行数）
- ``vcs.diff(mode=...)`` → 结构化 per-file diff（VcsFileDiff）
- ``vcs.diff_raw()``     → 整段 unified diff 纯文本（可落盘/转发）
- ``vcs.apply(patch)``   → 应用一个 unified diff（唯一写操作，藏在 --apply 后面）

运行（仓库根目录）::

    uv run python -m examples.vcs.vcs_workflow
    uv run python -m examples.vcs.vcs_workflow --directory /path/to/repo --mode branch
    uv run python -m examples.vcs.vcs_workflow --save /tmp/diff.txt
    uv run python -m examples.vcs.vcs_workflow --apply /tmp/patch.txt
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from typing import Literal, cast

from opencode_client import (
    AsyncOpenCodeClient,
    OpenCodeApiError,
    OpenCodeTransportError,
    VcsFileDiff,
    VcsFileStatus,
    VcsInfo,
)

BASE_URL = "http://127.0.0.1:4096"


def _print_info(info: VcsInfo) -> None:
    """打印分支状态。

    Args:
        info: GET /vcs 解析结果。
    """
    print("== VCS Info ==")
    # 两个字段在 wire 上都可选：非 git 仓库时服务端可能回空。
    branch = info.branch or "（未检出/非 git）"
    default_branch = info.default_branch or "（未知）"
    print(f"branch          : {branch}")
    print(f"default_branch  : {default_branch}")


def _print_status(statuses: list[VcsFileStatus]) -> None:
    """打印改动文件表。

    Args:
        statuses: GET /vcs/status 解析结果。
    """
    print("\n== VCS Status ==")
    if not statuses:
        print("（工作区干净，无改动）")
        return
    print(f"{'status':<10} {'+':>5} {'-':>5}  file")
    for status in statuses:
        print(f"{status.status:<10} {int(status.additions):>5} {int(status.deletions):>5}  {status.file}")


def _print_diffs(diffs: list[VcsFileDiff], limit: int) -> None:
    """打印结构化 diff，单文件 patch 截断展示。

    Args:
        diffs: GET /vcs/diff 解析结果。
        limit: 每文件 patch 最多显示的字符数。
    """
    print("\n== VCS Diff (structured) ==")
    if not diffs:
        print("（无可展示的 diff）")
        return
    for diff in diffs:
        snippet = diff.patch[:limit].replace("\n", "\\n")
        print(f"- {diff.file}  +{int(diff.additions)} -{int(diff.deletions)}  [{diff.status}]")
        print(f"    {snippet}{'…' if len(diff.patch) > limit else ''}")


async def main(
    base_url: str,
    directory: str,
    mode: Literal["git", "branch"],
    context: int,
    save_to: str | None,
    patch_file: str | None,
) -> None:
    """按 info → status → diff → diff_raw 顺序走一遍，可选应用补丁。

    Args:
        base_url: 服务地址。
        directory: 项目目录绝对路径（vcs 端点靠 directory query 参数定位仓库）。
        mode: diff 基准，git=工作区 vs HEAD，branch=vs 当前分支。
        context: diff 上下文行数（0 = 用服务端默认）。
        save_to: 给了就把 diff_raw 全文写进该文件。
        patch_file: 给了就把该文件内容作为 unified diff 提交给 apply。
    """
    async with AsyncOpenCodeClient(base_url) as client:
        _print_info(await client.vcs.info(directory=directory))
        _print_status(await client.vcs.status(directory=directory))
        _print_diffs(await client.vcs.diff(mode=mode, context=context or None, directory=directory), limit=200)

        raw = await client.vcs.diff_raw(directory=directory)
        print(f"\n== VCS Diff (raw) ==  {len(raw)} chars")
        if raw:
            print(raw[:400] + ("…" if len(raw) > 400 else ""))
        else:
            print("（空 diff）")
        if save_to is not None:
            with open(save_to, "w", encoding="utf-8") as fh:
                fh.write(raw)
            print(f"完整 raw diff 已写入 {save_to}")

        # apply 会真实改动工作区，所以做成显式开关、只应用用户给的补丁文件。
        if patch_file is not None:
            with open(patch_file, encoding="utf-8") as fh:
                patch = fh.read()
            result = await client.vcs.apply(patch, directory=directory)
            # 返回结构随服务端版本演进，原样打印不做强类型。
            print("\n== VCS Apply result ==\n" + json.dumps(result, ensure_ascii=False, indent=2))


def cli() -> None:
    """解析参数并运行 main。"""
    parser = argparse.ArgumentParser(description="查看并修补工作区改动")
    parser.add_argument("--url", default=BASE_URL, help="opencode server base URL")
    parser.add_argument("--directory", default=os.getcwd(), help="absolute path of the project repo (default: cwd)")
    parser.add_argument("--mode", choices=["git", "branch"], default="git", help="diff base")
    parser.add_argument("--context", type=int, default=0, help="diff context lines (0 = server default)")
    parser.add_argument("--save", dest="save_to", default=None, help="write the raw diff to this file")
    parser.add_argument(
        "--apply", dest="patch_file", default=None, help="apply this unified-diff file to the working tree"
    )
    args = parser.parse_args()

    # argparse 的 choices 只能收窄到 str；choices 已保证合法值，cast 还原字面量联合。
    mode = cast(Literal["git", "branch"], args.mode)

    try:
        asyncio.run(main(args.url, args.directory, mode, args.context, args.save_to, args.patch_file))
    except OpenCodeApiError as exc:
        print(f"[OpenCodeApiError] HTTP {exc.status_code}: {exc.payload}", file=sys.stderr)
        raise SystemExit(1) from exc
    except OpenCodeTransportError as exc:
        print(f"[transport] 无法连接 {args.url}：{exc}", file=sys.stderr)
        print("  提示：确认服务已启动，例如 `opencode serve --port 4096`，或用 --url 指定正确地址。", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    cli()

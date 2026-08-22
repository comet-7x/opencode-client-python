"""03 vcs_workflow: inspect and patch the working tree through the server.

The ``client.vcs.*`` endpoints let a remote server operate on a project's
version-control state — useful when the client and the repo live on the same
machine but you want one programmatic surface for "what changed, show me,
apply this patch". This script walks the whole domain in order:

- ``vcs.info()``        -> current branch + default branch
- ``vcs.status()``      -> changed files with add/del counts
- ``vcs.diff(mode=...)``-> structured per-file diffs (``VcsFileDiff``)
- ``vcs.diff_raw()``    -> the combined unified diff as plain text
- ``vcs.apply(patch)``  -> apply a unified diff to the working tree (opt-in)

Run (from the repo root):

    uv run python -m examples.03_vcs.vcs_workflow
    uv run python -m examples.03_vcs.vcs_workflow --directory /path/to/repo --mode branch
    uv run python -m examples.03_vcs.vcs_workflow --save diff.txt
    uv run python -m examples.03_vcs.vcs_workflow --apply patch.txt
"""

from __future__ import annotations

import argparse  # --url/--directory/--mode/--save/--apply
import asyncio  # 事件循环
import json  # 打印 apply 结果 dict
import os  # 默认把作用域设为当前目录
import sys  # 退出码
from typing import Literal, cast  # diff 基准是二选一的字面量联合；cast 收窄 argparse 的 str

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
    """Print the repo's branch state.

    Args:
        info: the parsed ``GET /vcs`` document.
    """
    print("== VCS Info ==")
    # 两个字段在 wire 上都是可选（非 git 仓库时服务端可能回空）。
    print(f"branch          : {info.branch or '（未检出/非 git）'}")
    print(f"default_branch  : {info.default_branch or '（未知）'}")


def _print_status(statuses: list[VcsFileStatus]) -> None:
    """Print changed files as a compact table.

    Args:
        statuses: the parsed ``GET /vcs/status`` list.
    """
    print("\n== VCS Status ==")
    if not statuses:
        print("（工作区干净，无改动）")
        return
    # 列宽：文件路径可能很长，只固定状态与增删列。
    print(f"{'status':<10} {'+':>5} {'-':>5}  file")
    for status in statuses:
        print(f"{status.status:<10} {int(status.additions):>5} {int(status.deletions):>5}  {status.file}")


def _print_diffs(diffs: list[VcsFileDiff], limit: int) -> None:
    """Print the structured diff, truncating each patch for readability.

    Args:
        diffs: the parsed ``GET /vcs/diff`` list.
        limit: max patch characters to show per file (full text via --save/diff_raw).
    """
    print("\n== VCS Diff (structured) ==")
    if not diffs:
        print("（无可展示的 diff）")
        return
    for diff in diffs:
        # patch 是单文件的 unified diff 文本；完整文本看 diff_raw / --save。
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
    """Walk info -> status -> diff -> diff_raw, optionally apply a patch.

    Args:
        base_url: server base URL.
        directory: 项目目录的绝对路径（vcs 端点靠 query 参数 directory 定位仓库）。
        mode: diff 基准，``"git"``（工作区 vs HEAD）或 ``"branch"``（vs 当前分支）。
        context: diff 上下文行数（0 = 不传，用服务端默认）。
        save_to: 给了就把 diff_raw 的完整文本写进这个文件。
        patch_file: 给了就把该文件内容当作 unified diff 提交给 vcs.apply。
    """
    async with AsyncOpenCodeClient(base_url) as client:
        _print_info(await client.vcs.info(directory=directory))
        _print_status(await client.vcs.status(directory=directory))
        # context 传 None 表示"用服务端默认"，所以 0 归一成 None。
        _print_diffs(await client.vcs.diff(mode=mode, context=context or None, directory=directory), limit=200)

        # —— diff_raw：同一份 diff 的"原始文本"形态（text/x-diff），适合直接落盘/转发。
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

        # —— apply：真正改动工作区，所以做成显式开关，且只应用用户给的补丁文件。
        if patch_file is not None:
            with open(patch_file, encoding="utf-8") as fh:
                patch = fh.read()
            result = await client.vcs.apply(patch, directory=directory)
            # 结果结构随服务端版本演进，这里原样打印不做强类型。
            print("\n== VCS Apply result ==\n" + json.dumps(result, ensure_ascii=False, indent=2))


def cli() -> None:
    """Parse args, run main, translate library errors into exit codes."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=BASE_URL, help="opencode server base URL")
    parser.add_argument("--directory", default=os.getcwd(), help="absolute path of the project repo (default: cwd)")
    parser.add_argument("--mode", choices=["git", "branch"], default="git", help="diff base")
    parser.add_argument("--context", type=int, default=0, help="diff context lines (0 = server default)")
    parser.add_argument("--save", dest="save_to", default=None, help="write the raw diff to this file")
    parser.add_argument(
        "--apply", dest="patch_file", default=None, help="apply this unified-diff file to the working tree"
    )
    args = parser.parse_args()

    # argparse 只能把 choices 收窄到 str；用 cast 还原成字面量联合（choices 已保证合法值）。
    mode = cast(Literal["git", "branch"], args.mode)

    try:
        asyncio.run(main(args.url, args.directory, mode, args.context, args.save_to, args.patch_file))
    except OpenCodeApiError as exc:
        print(f"[OpenCodeApiError] HTTP {exc.status_code}: {exc.payload}", file=sys.stderr)
        raise SystemExit(1) from exc
    except OpenCodeTransportError as exc:
        print(f"[transport] 无法完成与 {args.url} 的通信：{exc}", file=sys.stderr)
        print("  提示：确认服务已启动，例如 `opencode serve --port 4096`，或用 --url 指定。", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    cli()

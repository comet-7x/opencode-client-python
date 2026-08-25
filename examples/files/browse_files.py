"""files/browse_files: 浏览服务端工作区的文件系统。

``client.files.*`` 让远端的 opencode 服务替你读文件——客户端和项目不在
同一台机器时，这就是你的"ls + cat"。本脚本按顺序走一遍浏览面：

- ``files.list(path)``          -> 目录树一层（``FileNode``）
- ``files.read(path)``          -> 读单个文件（text/binary 判联合）
- ``files.status()``            -> git 视角的增删改清单
- ``files.formatter_status()``  -> 已注册的 formatter

Run (from the repo root):

    uv run python -m examples.files.browse_files
    uv run python -m examples.files.browse_files --directory /path/to/project --path src
    uv run python -m examples.files.browse_files --read README.md
"""

from __future__ import annotations

import argparse  # --url/--directory/--path/--read
import asyncio  # 事件循环
import os  # 默认把作用域设为当前目录
import sys  # 退出码

from opencode_client import (
    AsyncOpenCodeClient,
    FileNode,
    OpenCodeApiError,
    OpenCodeTransportError,
)

BASE_URL = "http://127.0.0.1:4096"


def _print_nodes(nodes: list[FileNode], path: str) -> None:
    """打印目录列表：目录在前、带类型标记。

    Args:
        nodes: 解析后的 ``GET /file`` 结果。
        path: 被列出的目录（仅用于标题展示）。
    """
    print(f"== Files in '{path or '.'}' ==")
    # 目录排前面、同类按名字排序，读起来更像 `ls`。
    ordered = sorted(nodes, key=lambda n: (n.type != "directory", n.name))
    for node in ordered:
        mark = "d" if node.type == "directory" else "-"
        ignored = "  (ignored)" if node.ignored else ""
        print(f"{mark}  {node.name}{ignored}")
    if not nodes:
        print("（空目录）")


async def read_one(base_url: str, directory: str, path: str) -> None:
    """读单个文件并按判联合分支展示文本/二进制两种形态。

    Args:
        base_url: server base URL。
        directory: 项目目录绝对路径。
        path: 要读取的相对路径。
    """
    async with AsyncOpenCodeClient(base_url) as client:
        content = await client.files.read(path, directory=directory)
    # 判联合按 type 字面量收窄：text 是纯文本，binary 是 base64。
    if content.type == "text":
        preview = content.content[:400]
        print(f"== {path} (text, {len(content.content)} chars) ==")
        print(preview + ("…" if len(content.content) > 400 else ""))
        if content.diff:
            print(f"-- 未保存的改动 diff（前 200 字符）--\n{content.diff[:200]}")
    else:
        print(f"== {path} (binary, {content.encoding}, mime={content.mime_type or 'unknown'}) ==")
        print(f"{len(content.content)} base64 chars")


async def main(base_url: str, directory: str, path: str, read_path: str | None) -> None:
    """走 list -> status -> formatter，可选读单文件。

    Args:
        base_url: server base URL。
        directory: 项目目录绝对路径（query 参数 directory 定位工作区）。
        path: 要列出的子目录（"" 表示根）。
        read_path: 给了就额外演示 files.read。
    """
    async with AsyncOpenCodeClient(base_url) as client:
        _print_nodes(await client.files.list(path, directory=directory), path)

        changes = await client.files.status(directory=directory)
        print("\n== File Status (git 视角) ==")
        if not changes:
            print("（无改动）")
        for change in changes:
            print(f"{change.status:<9} +{change.added:<4} -{change.removed:<4} {change.path}")

        formatters = await client.files.formatter_status(directory=directory)
        print("\n== Formatters ==")
        for fmt in formatters:
            exts = ", ".join(fmt.extensions) or "-"
            state = "enabled" if fmt.enabled else "disabled"
            print(f"{fmt.name:<12} [{state}] {exts}")

    # —— read 单独开一个 client 演示：真实程序里应该复用同一个 client。
    if read_path is not None:
        await read_one(base_url, directory, read_path)


def cli() -> None:
    """Parse args, run main, translate library errors into exit codes."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=BASE_URL, help="opencode server base URL")
    parser.add_argument("--directory", default=os.getcwd(), help="absolute path of the project (default: cwd)")
    parser.add_argument("--path", default="", help="sub-directory to list ('' = worktree root)")
    parser.add_argument("--read", dest="read_path", default=None, help="also read this file via files.read")
    args = parser.parse_args()

    try:
        asyncio.run(main(args.url, args.directory, args.path, args.read_path))
    except OpenCodeApiError as exc:
        print(f"[OpenCodeApiError] HTTP {exc.status_code}: {exc.payload}", file=sys.stderr)
        raise SystemExit(1) from exc
    except OpenCodeTransportError as exc:
        print(f"[transport] 无法完成与 {args.url} 的通信：{exc}", file=sys.stderr)
        print("  提示：确认服务已启动，例如 `opencode serve --port 4096`，或用 --url 指定。", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    cli()

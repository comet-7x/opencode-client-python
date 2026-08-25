"""files/search_code: 在服务端工作区里找东西（文本/文件名/符号）。

三组"找"的端点，对应三种日常检索：

- ``files.search_text(pattern)``    -> ripgrep 文本搜索（带行号与子匹配）
- ``files.search_files(query)``     -> 按文件名模糊找路径
- ``files.search_symbols(query)``   -> LSP 工作区符号（函数/类/方法…）

Run (from the repo root):

    uv run python -m examples.files.search_code --pattern "TODO"
    uv run python -m examples.files.search_code --pattern "def main" --find-file workflow --symbol main
"""

from __future__ import annotations

import argparse  # --url/--directory/--pattern/--find-file/--symbol
import asyncio  # 事件循环
import os  # 默认把作用域设为当前目录
import sys  # 退出码

from opencode_client import (
    AsyncOpenCodeClient,
    OpenCodeApiError,
    OpenCodeTransportError,
    Symbol,
    TextMatch,
)

BASE_URL = "http://127.0.0.1:4096"


def _print_matches(matches: list[TextMatch], pattern: str) -> None:
    """打印文本命中：行号 + 命中行（截断到一行可读宽度）。

    Args:
        matches: 解析后的 ``GET /find`` 结果。
        pattern: 搜索用的正则（仅用于标题展示）。
    """
    print(f"== Text matches for /{pattern}/ ==")
    if not matches:
        print("（无命中；注意服务端把结果上限写死为 10 条）")
        return
    for match in matches:
        line = match.lines.text.rstrip("\n")
        snippet = line[:120] + ("…" if len(line) > 120 else "")
        # submatch 是行内的精确命中区间，可以用来做高亮/跳转。
        spans = ", ".join(f"[{s.start}:{s.end}]{s.match.text!r}" for s in match.submatches)
        print(f"{match.path.text}:{match.line_number + 1}: {snippet}")
        print(f"          submatches -> {spans}")


def _print_symbols(symbols: list[Symbol]) -> None:
    """打印 LSP 符号：kind 数字原样给出，uri 带 行:列 定位。

    Args:
        symbols: 解析后的 ``GET /find/symbol`` 结果。
    """
    print("\n== Symbols ==")
    if not symbols:
        print("（无结果；需要服务端有语言服务器支持对应文件类型）")
        return
    for symbol in symbols:
        start = symbol.location.range.start
        print(f"{symbol.name:<24} kind={symbol.kind:<3} {symbol.location.uri}:{start.line + 1}:{start.character}")


async def main(
    base_url: str,
    directory: str,
    pattern: str | None,
    find_file: str | None,
    symbol_query: str | None,
    limit: int,
) -> None:
    """按需跑三类搜索：给了哪个参数就跑哪一类。

    Args:
        base_url: server base URL。
        directory: 项目目录绝对路径（query 参数 directory 定位工作区）。
        pattern: 文本搜索正则（None = 跳过文本搜索）。
        find_file: 文件名片段（None = 跳过文件名搜索）。
        symbol_query: 符号查询串（None = 跳过符号搜索）。
        limit: 文件名搜索的最大条数（服务端默认 10）。
    """
    async with AsyncOpenCodeClient(base_url) as client:
        if pattern is not None:
            _print_matches(await client.files.search_text(pattern, directory=directory), pattern)

        if find_file is not None:
            paths = await client.files.search_files(find_file, limit=limit, directory=directory)
            print(f"\n== Files matching '{find_file}' ==")
            for path in paths or ["（无命中）"]:
                print(path)

        if symbol_query is not None:
            _print_symbols(await client.files.search_symbols(symbol_query, directory=directory))


def cli() -> None:
    """Parse args, run main, translate library errors into exit codes."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=BASE_URL, help="opencode server base URL")
    parser.add_argument("--directory", default=os.getcwd(), help="absolute path of the project (default: cwd)")
    parser.add_argument("--pattern", default=None, help="regex to grep the worktree (enables text search)")
    parser.add_argument("--find-file", dest="find_file", default=None, help="filename fragment to fuzzy-find")
    parser.add_argument("--symbol", dest="symbol", default=None, help="workspace symbol query (LSP)")
    parser.add_argument("--limit", type=int, default=10, help="max entries for --find-file (server default 10)")
    args = parser.parse_args()

    if args.pattern is None and args.find_file is None and args.symbol is None:
        parser.print_help()
        print("\n至少给一个搜索目标：--pattern / --find-file / --symbol", file=sys.stderr)
        raise SystemExit(2)

    try:
        asyncio.run(main(args.url, args.directory, args.pattern, args.find_file, args.symbol, args.limit))
    except OpenCodeApiError as exc:
        print(f"[OpenCodeApiError] HTTP {exc.status_code}: {exc.payload}", file=sys.stderr)
        raise SystemExit(1) from exc
    except OpenCodeTransportError as exc:
        print(f"[transport] 无法完成与 {args.url} 的通信：{exc}", file=sys.stderr)
        print("  提示：确认服务已启动，例如 `opencode serve --port 4096`，或用 --url 指定。", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    cli()

"""04 mcp_servers: list MCP server states and register a new one.

``client.mcp.*`` covers the ``/mcp`` endpoints. ``status()`` returns a
``name -> MCPStatus`` map — a discriminated union of five lifecycle states
(``connected`` / ``disabled`` / ``failed`` / ``needs_auth`` /
``needs_client_registration``). ``add()`` registers a new server with either a
local stdio command or a remote URL. The connect/disconnect/auth flows are
out of scope for the client library; this script shows the two supported verbs.

Run (from the repo root):

    uv run python -m examples.04_mcp.mcp_servers
    uv run python -m examples.04_mcp.mcp_servers --directory /path/to/project
    uv run python -m examples.04_mcp.mcp_servers --name everything --command npx,-y,@modelcontextprotocol/server-everything
    uv run python -m examples.04_mcp.mcp_servers --name remote --remote-url https://mcp.example.com/sse
"""

from __future__ import annotations

import argparse  # --url/--directory/--name/--command/--remote-url
import asyncio  # 事件循环
import json  # 打印 add 结果 dict
import sys  # 退出码

from opencode_client import (
    AsyncOpenCodeClient,
    McpLocalConfig,
    McpRemoteConfig,
    MCPStatus,
    MCPStatusConnected,
    MCPStatusFailed,
    OpenCodeApiError,
    OpenCodeTransportError,
)

BASE_URL = "http://127.0.0.1:4096"


def _print_status(statuses: dict[str, MCPStatus]) -> None:
    """Render the name -> MCPStatus map, narrowing each union member.

    Args:
        statuses: the parsed ``GET /mcp`` document.
    """
    print("== MCP Servers ==")
    if not statuses:
        print("（服务端没有配置任何 MCP server）")
        return
    for name, status in statuses.items():
        # MCPStatus 是五个兄弟模型构成的判别联合（判别键 status）。
        # 用 isinstance 收窄后，failed 才能安全读 .error；其余分支只打印状态。
        if isinstance(status, MCPStatusConnected):
            print(f"- {name}: connected")
        elif isinstance(status, MCPStatusFailed):
            # error 只在 failed / needs_client_registration 上有值
            print(f"- {name}: failed  ({status.error or '无错误详情'})")
        else:
            # disabled / needs_auth / needs_client_registration：状态本身已说明一切
            print(f"- {name}: {status.status}")


async def main(
    base_url: str, directory: str | None, name: str | None, command: str | None, remote_url: str | None
) -> None:
    """Show MCP status; with --name, register a new server then re-check.

    Args:
        base_url: server base URL.
        directory: 可选作用域（MCP 配置按项目目录隔离时用）。
        name: 给了就注册新 server（配 --command 或 --remote-url 二选一）。
        command: stdio 命令，逗号分隔（如 ``npx,-y,@foo/bar``）。
        remote_url: HTTP/SSE 远程地址。
    """
    async with AsyncOpenCodeClient(base_url) as client:
        _print_status(await client.mcp.status(directory=directory))

        if name is None:
            return
        # —— 组装请求侧 config：两种形态都是判别联合（判别键 type）。
        #    McpLocalConfig 起本地子进程；McpRemoteConfig 连远程端点。
        if command is not None:
            config: McpLocalConfig | McpRemoteConfig = McpLocalConfig(
                type="local",
                command=command.split(","),  # wire 上是 argv 数组，这里用逗号当分隔符
            )
        elif remote_url is not None:
            config = McpRemoteConfig(type="remote", url=remote_url)
        else:
            print("给了 --name 就必须配 --command 或 --remote-url 之一。", file=sys.stderr)
            raise SystemExit(2)

        # add 的返回是"注册后的状态文档"（dict，结构随服务端演进）。
        result = await client.mcp.add(name, config, directory=directory)
        print(f"\n== add({name!r}) result ==\n" + json.dumps(result, ensure_ascii=False, indent=2))

        # —— 注册完立刻回读一次 status，确认新 server 出现在名单里（可能还是
        #    needs_auth/failed，取决于它能不能立刻连上）。
        print("\n== status after add ==")
        _print_status(await client.mcp.status(directory=directory))


def cli() -> None:
    """Parse args, run main, translate library errors into exit codes."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=BASE_URL, help="opencode server base URL")
    parser.add_argument("--directory", default=None, help="scope to a project directory")
    parser.add_argument("--name", default=None, help="register a new MCP server under this name")
    parser.add_argument("--command", default=None, help="stdio command, comma-separated argv (e.g. npx,-y,@foo/bar)")
    parser.add_argument("--remote-url", default=None, help="remote HTTP/SSE endpoint URL")
    args = parser.parse_args()

    try:
        asyncio.run(main(args.url, args.directory, args.name, args.command, args.remote_url))
    except OpenCodeApiError as exc:
        print(f"[OpenCodeApiError] HTTP {exc.status_code}: {exc.payload}", file=sys.stderr)
        raise SystemExit(1) from exc
    except OpenCodeTransportError as exc:
        print(f"[transport] 无法完成与 {args.url} 的通信：{exc}", file=sys.stderr)
        print("  提示：确认服务已启动，例如 `opencode serve --port 4096`，或用 --url 指定。", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    cli()

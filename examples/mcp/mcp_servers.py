"""mcp_servers：MCP 服务器状态一览、注册与生命周期管理。

``client.mcp.*`` 覆盖整个 ``/mcp`` 端点族。``status()`` 返回
``name -> MCPStatus`` 映射——五个生命周期状态的判别联合（connected/disabled/
failed/needs_auth/needs_client_registration）。``add()`` 注册新 server，
config 是 local stdio 命令或远程 URL 两种形态。需要 OAuth 的远程 server，
用 ``--oauth`` 对一台已注册的 server 演示完整生命周期：

- ``start_oauth(name)``  → 拿到 authorizationUrl（真实流程交给用户浏览器打开）
- ``authenticate(name)`` → 无头流（服务端能自己完成的场景）
- ``connect/disconnect`` → 手动拉起/断开连接

运行（仓库根目录）::

    uv run python -m examples.mcp.mcp_servers
    uv run python -m examples.mcp.mcp_servers --directory /path/to/project
    uv run python -m examples.mcp.mcp_servers --name everything --command npx,-y,@modelcontextprotocol/server-everything
    uv run python -m examples.mcp.mcp_servers --name remote --remote-url https://mcp.example.com/sse
    uv run python -m examples.mcp.mcp_servers --oauth remote   # 演示 OAuth + 连接管理（不真正完成认证）
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

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
    """渲染 name -> MCPStatus 映射，逐个收窄联合成员。

    Args:
        statuses: GET /mcp 解析结果。
    """
    print("== MCP Servers ==")
    if not statuses:
        print("（服务端没有配置任何 MCP server）")
        return
    for name, status in statuses.items():
        if isinstance(status, MCPStatusConnected):
            print(f"- {name}: connected")
        elif isinstance(status, MCPStatusFailed):
            # error 只在 failed / needs_client_registration 上有值。
            error = status.error or "无错误详情"
            print(f"- {name}: failed  ({error})")
        else:
            # disabled / needs_auth / needs_client_registration：状态本身已说明一切。
            print(f"- {name}: {status.status}")


async def main(
    base_url: str,
    directory: str | None,
    name: str | None,
    command: str | None,
    remote_url: str | None,
    oauth_name: str | None,
) -> None:
    """展示 MCP 状态；给 --name 时注册新 server 再回读确认。

    Args:
        base_url: 服务地址。
        directory: 可选作用域（MCP 配置按项目目录隔离时用）。
        name: 注册新 server 的名字（需配 --command 或 --remote-url 二选一）。
        command: stdio 命令，逗号分隔（如 npx,-y,@foo/bar）。
        remote_url: HTTP/SSE 远程地址。
        oauth_name: 给了就对这台已注册的 server 演示 OAuth/连接生命周期。
    """
    async with AsyncOpenCodeClient(base_url) as client:
        _print_status(await client.mcp.status(directory=directory))

        # —— 注册新 server：--name 必须配 --command 或 --remote-url 之一。
        if name is not None:
            # 请求侧 config 是判别联合（type 判别键）：
            # McpLocalConfig 起本地子进程；McpRemoteConfig 连远程端点；
            # wire 包装 {"name":..., "config":...} 由库处理。
            if command is not None:
                config: McpLocalConfig | McpRemoteConfig = McpLocalConfig(
                    type="local",
                    command=command.split(","),  # wire 上是 argv 数组
                )
            elif remote_url is not None:
                config = McpRemoteConfig(type="remote", url=remote_url)
            else:
                print("给了 --name 就必须配 --command 或 --remote-url 之一。", file=sys.stderr)
                raise SystemExit(2)

            result = await client.mcp.add(name, config, directory=directory)
            print(f"\n== add({name!r}) result ==\n" + json.dumps(result, ensure_ascii=False, indent=2))

            # 回读闭环：新 server 可能还在 needs_auth/failed——这是正常的初始状态。
            print("\n== status after add ==")
            _print_status(await client.mcp.status(directory=directory))

    # —— OAuth / 连接生命周期：针对已注册 server 演示（默认跳过）。
    #    真实浏览器流是：start_oauth 拿 URL -> 用户在浏览器授权 -> 服务端回调带
    #    code -> complete_oauth 用 code 换 token。脚本只演示到"拿到 URL"为止；
    #    无头流 authenticate 由支持的服务端自行完成认证。
    if oauth_name is not None:
        async with AsyncOpenCodeClient(base_url) as client:
            try:
                started = await client.mcp.start_oauth(oauth_name, directory=directory)
                print(f"\n== start_oauth({oauth_name!r}) ==")
                print(f"authorization_url : {started.authorization_url}")
                print(f"oauth_state       : {started.oauth_state}")
                print("（把 authorization_url 交给用户浏览器打开；拿到回调 code 后")
                print("  用 client.mcp.complete_oauth(name, code) 完成认证。）")
            except OpenCodeApiError as exc:
                # 服务端对不支持 OAuth 的 server 会直接报错——这正是要演示的分支之一。
                print(f"\n== start_oauth({oauth_name!r}) 被拒绝：HTTP {exc.status_code} {exc.payload}")

            status = await client.mcp.authenticate(oauth_name, directory=directory)
            print(f"\n== authenticate({oauth_name!r}) -> {status.status}")

            connected = await client.mcp.connect(oauth_name, directory=directory)
            print(f"connect({oauth_name!r}) -> {connected}")
            disconnected = await client.mcp.disconnect(oauth_name, directory=directory)
            print(f"disconnect({oauth_name!r}) -> {disconnected}")

            # 凭证管理：演示移除（真实场景里移除前应确认，这里仅展示调用形态）。
            removed = await client.mcp.remove_oauth(oauth_name, directory=directory)
            print(f"remove_oauth({oauth_name!r}) -> {removed}")


def cli() -> None:
    """解析参数并运行 main。"""
    parser = argparse.ArgumentParser(description="查看 MCP 状态、注册新 server 并演示生命周期")
    parser.add_argument("--url", default=BASE_URL, help="opencode server base URL")
    parser.add_argument("--directory", default=None, help="scope to a project directory")
    parser.add_argument("--name", default=None, help="register a new MCP server under this name")
    parser.add_argument("--command", default=None, help="stdio command, comma-separated argv (e.g. npx,-y,@foo/bar)")
    parser.add_argument("--remote-url", default=None, help="remote HTTP/SSE endpoint URL")
    parser.add_argument(
        "--oauth", dest="oauth", default=None, help="demo OAuth/connect lifecycle for this registered server"
    )
    args = parser.parse_args()

    try:
        asyncio.run(main(args.url, args.directory, args.name, args.command, args.remote_url, args.oauth))
    except OpenCodeApiError as exc:
        print(f"[OpenCodeApiError] HTTP {exc.status_code}: {exc.payload}", file=sys.stderr)
        raise SystemExit(1) from exc
    except OpenCodeTransportError as exc:
        print(f"[transport] 无法连接 {args.url}：{exc}", file=sys.stderr)
        print("  提示：确认服务已启动，例如 `opencode serve --port 4096`，或用 --url 指定正确地址。", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    cli()

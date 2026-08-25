"""projects/explore_projects: 查看服务端的项目面与系统信息。

opencode 把每个可操作的工作区登记为 **project**。本脚本把项目域与
server 域的系统信息端点串起来，回答三个问题：

- 管了哪些项目？现在在哪个里面？        -> ``client.projects.*``
- 服务端眼里的目录布局长什么样？        -> ``client.server.get_paths()``
- 挂了哪些语言服务器？                  -> ``client.server.lsp_status()``

可选演示：
- ``--log``：往服务端日志里写一条（远程调试用）
- ``--auth-demo``：写入再删除一条假凭证（演示 PUT/DELETE /auth 往返，
  **不会**碰真实 provider 的凭证）

Run (from the repo root):

    uv run python -m examples.projects.explore_projects
    uv run python -m examples.projects.explore_projects --directory /path/to/project
    uv run python -m examples.projects.explore_projects --log
    uv run python -m examples.projects.explore_projects --auth-demo
"""

from __future__ import annotations

import argparse  # --url/--directory/--log/--auth-demo
import asyncio  # 事件循环
import os  # 默认把作用域设为当前目录
import sys  # 退出码

from opencode_client import (
    ApiKeyCredentials,
    AsyncOpenCodeClient,
    OpenCodeApiError,
    OpenCodeTransportError,
    Project,
)

BASE_URL = "http://127.0.0.1:4096"


def _print_projects(projects: list[Project], current_id: str | None) -> None:
    """打印项目清单，标出当前作用域所在的项目。

    Args:
        projects: 解析后的 ``GET /project`` 列表。
        current_id: 当前项目 id（用于打标记；拿不到时为 None）。
    """
    print("== Projects ==")
    if not projects:
        print("（服务端还没有任何项目记录）")
        return
    for project in projects:
        mark = "*" if project.id == current_id else " "
        vcs = f" [{project.vcs}]" if project.vcs else ""
        name = project.name or "（未命名）"
        print(f"{mark} {project.id}  {name}{vcs}")
        print(f"      worktree: {project.worktree}")


async def main(base_url: str, directory: str | None, write_log: bool, auth_demo: bool) -> None:
    """走 projects -> paths -> lsp 三步；可选演示写日志与凭证往返。

    Args:
        base_url: server base URL。
        directory: 可选作用域（影响 current/paths/lsp 的定位）。
        write_log: 给了就往服务端日志写一条。
        auth_demo: 给了就做一次"写入假凭证 -> 删除"的往返演示。
    """
    async with AsyncOpenCodeClient(base_url) as client:
        projects = await client.projects.list(directory=directory)
        try:
            current = await client.projects.current(directory=directory)
            _print_projects(projects, current.id)
        except OpenCodeApiError:
            # 没有 scoped 项目时 current 可能 404——只列清单即可。
            _print_projects(projects, None)

        paths = await client.server.get_paths(directory=directory)
        print("\n== Server Paths ==")
        for field in ("home", "state", "config", "worktree", "directory"):
            print(f"{field:<10}: {getattr(paths, field)}")

        servers = await client.server.lsp_status(directory=directory)
        print("\n== LSP Servers ==")
        if not servers:
            print("（未挂载语言服务器）")
        for server in servers:
            print(f"- {server.name}: {server.status}  root={server.root}")

        if write_log:
            ok = await client.server.write_log(
                service="explore_projects",
                level="info",
                message="hello from opencode-client",
                extra={"source": "example"},
                directory=directory,
            )
            print(f"\n== write_log -> {ok}（去服务端机器上翻它的日志文件验证）")

        # 凭证端点只有写/删没有读，所以用一次性假 provider 做"写入->删除"
        # 往返；不传 --auth-demo 就完全不碰 /auth。
        if auth_demo:
            credentials = ApiKeyCredentials(type="api", key="sk-demo-not-real")
            created = await client.auth.set_credentials("_demo_provider_", credentials)
            removed = await client.auth.remove_credentials("_demo_provider_")
            print(f"\n== auth roundtrip -> set={created} remove={removed}")


def cli() -> None:
    """Parse args, run main, translate library errors into exit codes."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=BASE_URL, help="opencode server base URL")
    parser.add_argument("--directory", default=os.getcwd(), help="scope to a project directory")
    parser.add_argument("--log", action="store_true", help="also write an entry into the server log")
    parser.add_argument(
        "--auth-demo", dest="auth_demo", action="store_true", help="demo set/remove credentials roundtrip"
    )
    args = parser.parse_args()

    try:
        asyncio.run(main(args.url, args.directory, args.log, args.auth_demo))
    except OpenCodeApiError as exc:
        print(f"[OpenCodeApiError] HTTP {exc.status_code}: {exc.payload}", file=sys.stderr)
        raise SystemExit(1) from exc
    except OpenCodeTransportError as exc:
        print(f"[transport] 无法完成与 {args.url} 的通信：{exc}", file=sys.stderr)
        print("  提示：确认服务已启动，例如 `opencode serve --port 4096`，或用 --url 指定。", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    cli()

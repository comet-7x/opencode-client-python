"""explore_server：一次摸清新服务——发现端点全览。

接手一个陌生（或刚启动的）opencode 服务时，先程序化"摸清家底"：

- ``server.health()``         → 活着吗、什么版本
- ``server.get_config()``     → 生效的服务端配置（原始 dict，库刻意不建模）
- ``server.list_providers()`` → provider 目录 + 默认模型 + connected 子集
- ``server.list_agents()``    → agent 定义（mode/model/permission 规则）
- ``server.list_commands()``  → 斜杠命令（内置 / MCP 工具 / 技能）
- ``server.list_skills()``    → 技能（位置 + 正文）
- （可选）``server.update_config()`` → PATCH 一处配置并回读

除 ``--set-config`` 外全部只读。

运行（仓库根目录）::

    uv run python -m examples.server.explore_server
    uv run python -m examples.server.explore_server --directory /path/to/project
    uv run python -m examples.server.explore_server --set-config '{"share": {"enabled": false}}'
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any

from opencode_client import (
    Agent,
    AsyncOpenCodeClient,
    Command,
    OpenCodeApiError,
    OpenCodeTransportError,
    ProviderList,
    Skill,
)

BASE_URL = "http://127.0.0.1:4096"


def _print_providers(providers: ProviderList) -> None:
    """渲染 provider 目录：connected 在前，再列每个 provider 与默认模型。

    Args:
        providers: GET /provider 解析结果。
    """
    print("\n== Providers ==")
    # connected 是"已连上、能真正出 token"的 provider id 列表——挑模型的权威依据。
    connected = ", ".join(providers.connected) if providers.connected else "（无）"
    print(f"connected : {connected}")
    print(f"default   : {json.dumps(providers.default, ensure_ascii=False)}")
    for provider in providers.all:
        model_ids = ", ".join(provider.models) or "（无）"
        print(f"- {provider.id} [{provider.source}]  name={provider.name!r}  models: {model_ids}")


def _print_agents(agents: list[Agent]) -> None:
    """渲染 agent 定义。

    Args:
        agents: GET /agent 解析结果。
    """
    print("\n== Agents ==")
    for agent in agents:
        model = f"{agent.model['providerID']}/{agent.model['modelID']}" if agent.model else "（继承默认）"
        rules = len(agent.permission) if agent.permission else 0
        print(
            f"- {agent.name}  mode={agent.mode}  model={model}  temperature={agent.temperature}  permission_rules={rules}"
        )


def _print_commands(commands: list[Command]) -> None:
    """渲染斜杠命令并标注来源。

    Args:
        commands: GET /command 解析结果。
    """
    print("\n== Commands ==")
    for command in commands:
        # source 标记来源：command（内置）/ mcp（工具）/ skill（技能）。
        desc = (command.description or "")[:80]
        print(f"- /{command.name}  [{command.source or 'command'}]  {desc}")


def _print_skills(skills: list[Skill]) -> None:
    """渲染技能列表（正文截断）。

    Args:
        skills: GET /skill 解析结果。
    """
    print("\n== Skills ==")
    for skill in skills:
        first_line = skill.content.strip().splitlines()[0] if skill.content.strip() else ""
        print(f"- {skill.name}  location={skill.location}  body={len(skill.content)} chars  {first_line[:60]}")


async def main(base_url: str, directory: str | None, set_config: str | None) -> None:
    """跑一遍全部发现端点，打印人类可读的调查报告。

    Args:
        base_url: 服务地址。
        directory: 可选作用域；传了之后各发现端点都限定到该项目目录。
        set_config: 可选 JSON；给了就 PATCH 进 config 并打印更新后的文档。
    """
    async with AsyncOpenCodeClient(base_url) as client:
        health = await client.server.health()
        print(f"== Health ==\nhealthy: {health.healthy}  version: {health.version}")

        # config 返回原始 dict：配置结构演进快，库不做强类型建模。
        config: dict[str, Any] = await client.server.get_config()
        print("\n== Config ==\n" + json.dumps(config, ensure_ascii=False, indent=2))

        _print_providers(await client.server.list_providers(directory=directory))
        _print_agents(await client.server.list_agents(directory=directory))
        _print_commands(await client.server.list_commands(directory=directory))
        _print_skills(await client.server.list_skills(directory=directory))

        if set_config is not None:
            patch = json.loads(set_config)
            updated = await client.server.update_config(patch, directory=directory)
            print("\n== Config after update ==\n" + json.dumps(updated, ensure_ascii=False, indent=2))
            print("（提示：改动写回了服务端配置；如需还原，重新跑 --set-config 传回旧值。）")


def cli() -> None:
    """解析参数并运行 main。"""
    parser = argparse.ArgumentParser(description="服务发现与配置一览")
    parser.add_argument("--url", default=BASE_URL, help="opencode server base URL")
    parser.add_argument("--directory", default=None, help="scope discovery calls to a project directory")
    parser.add_argument(
        "--set-config",
        default=None,
        help='JSON to PATCH into the server config, e.g. \'{"share": {"enabled": false}}\'',
    )
    args = parser.parse_args()

    try:
        asyncio.run(main(args.url, args.directory, args.set_config))
    except OpenCodeApiError as exc:
        print(f"[OpenCodeApiError] HTTP {exc.status_code}: {exc.payload}", file=sys.stderr)
        raise SystemExit(1) from exc
    except OpenCodeTransportError as exc:
        print(f"[transport] 无法连接 {args.url}：{exc}", file=sys.stderr)
        print("  提示：确认服务已启动，例如 `opencode serve --port 4096`，或用 --url 指定正确地址。", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    cli()

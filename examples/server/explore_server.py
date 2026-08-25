"""02 explore_server: survey what a running opencode server offers.

Before driving sessions you usually want to know the landscape: which
providers are connected, which models each exposes, which agents/commands/
skills are configured, and what the effective server config looks like.
This script makes the "read-only discovery" calls in one pass:

- ``server.health()``            -> is it up, which version
- ``server.get_config()``        -> effective config document (raw dict)
- ``server.list_providers()``    -> providers, default models, connected subset
- ``server.list_agents()``       -> agent definitions (mode/model/permissions)
- ``server.list_commands()``     -> slash commands (built-in / mcp / skill)
- ``server.list_skills()``       -> skills with location + body
- (opt-in) ``server.update_config()`` -> PATCH a config key and print the result

Everything here is read-only except ``--set-config``.

Run (from the repo root):

    uv run python -m examples.server.explore_server
    uv run python -m examples.server.explore_server --directory /path/to/project
    uv run python -m examples.server.explore_server --set-config '{"share": {"enabled": false}}'
"""

from __future__ import annotations

import argparse  # --url/--directory/--set-config
import asyncio  # 事件循环
import json  # 打印原始 dict 用的序列化
import sys  # 退出码

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
    """Render the provider directory: connected first, then all with defaults.

    Args:
        providers: the parsed ``GET /provider`` document.
    """
    print("\n== Providers ==")
    # connected 是“已连上、能真正出 token 的” provider id 列表（看 env/config 是否齐了）。
    print(f"connected : {', '.join(providers.connected) if providers.connected else '（无）'}")
    # default 是 provider_id -> model_id 的“默认模型”映射。
    print(f"default   : {json.dumps(providers.default, ensure_ascii=False)}")
    for provider in providers.all:
        # models 是 id -> Model 的映射；这里只列 id，避免把每个模型的能力表刷屏。
        model_ids = ", ".join(provider.models) or "（无）"
        print(f"- {provider.id} [{provider.source}]  name={provider.name!r}  models: {model_ids}")


def _print_agents(agents: list[Agent]) -> None:
    """Render agent definitions (name, mode, model, sampling, permission count).

    Args:
        agents: the parsed ``GET /agent`` list.
    """
    print("\n== Agents ==")
    for agent in agents:
        # model 是 wire 上的 {"providerID":..., "modelID":...}，这里原样展示。
        model = f"{agent.model['providerID']}/{agent.model['modelID']}" if agent.model else "（继承默认）"
        # permission 是规则列表（PermissionRule: permission/pattern/action）。
        rules = len(agent.permission) if agent.permission else 0
        print(
            f"- {agent.name}  mode={agent.mode}  model={model}  "
            f"temperature={agent.temperature}  permission_rules={rules}"
        )


def _print_commands(commands: list[Command]) -> None:
    """Render slash commands, tagged by where they came from.

    Args:
        commands: the parsed ``GET /command`` list.
    """
    print("\n== Commands ==")
    for command in commands:
        # source 标记来源：command（内置）/ mcp（工具）/ skill（技能）。
        desc = (command.description or "")[:80]
        print(f"- /{command.name}  [{command.source or 'command'}]  {desc}")


def _print_skills(skills: list[Skill]) -> None:
    """Render skills with their on-disk location (body is truncated).

    Args:
        skills: the parsed ``GET /skill`` list.
    """
    print("\n== Skills ==")
    for skill in skills:
        # content 是技能正文，可能很长，只给长度 + 首行。
        first_line = skill.content.strip().splitlines()[0] if skill.content.strip() else ""
        print(f"- {skill.name}  location={skill.location}  body={len(skill.content)} chars  {first_line[:60]}")


async def main(base_url: str, directory: str | None, set_config: str | None) -> None:
    """Make every discovery call and print a human-readable survey.

    Args:
        base_url: server base URL.
        directory: 可选作用域；传了之后 discovery 端点都限定到该项目目录。
        set_config: 可选，一段 JSON；给了就 PATCH 进 config 并打印更新后的文档。
    """
    async with AsyncOpenCodeClient(base_url) as client:
        # —— health：最轻的探活，顺带拿到 server 版本。
        health = await client.server.health()
        print(f"== Health ==\nhealthy: {health.healthy}  version: {health.version}")

        # —— config：生效的服务端配置。
        #    返回的是原始 dict（服务端配置结构会演进，库不强行建模）；
        #    想改配置就用 --set-config 走 update_config。
        config = await client.server.get_config()
        print("\n== Config ==\n" + json.dumps(config, ensure_ascii=False, indent=2))

        _print_providers(await client.server.list_providers(directory=directory))
        _print_agents(await client.server.list_agents(directory=directory))
        _print_commands(await client.server.list_commands(directory=directory))
        _print_skills(await client.server.list_skills(directory=directory))

        # —— update_config（可选）：演示“改一处再读回”的闭环。
        #    body 是裸 dict，PATCH 语义：只覆盖你给的键。
        if set_config is not None:
            patch = json.loads(set_config)  # 用户给的就是 JSON，解析失败直接抛（json.JSONDecodeError）
            updated = await client.server.update_config(patch, directory=directory)
            print("\n== Config after update ==\n" + json.dumps(updated, ensure_ascii=False, indent=2))
            print("（提示：改动写回了服务端配置；如需还原，重新跑 --set-config 传回旧值。）")


def cli() -> None:
    """Parse args, run main, translate library errors into exit codes."""
    parser = argparse.ArgumentParser(description=__doc__)
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
        print(f"[transport] 无法完成与 {args.url} 的通信：{exc}", file=sys.stderr)
        print("  提示：确认服务已启动，例如 `opencode serve --port 4096`，或用 --url 指定。", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    cli()

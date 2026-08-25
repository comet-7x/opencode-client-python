# server — 服务级端点（发现与配置）

## 本文件夹讲什么

接到一个陌生（或刚启动的）opencode 服务，动手开会话之前通常先"摸清家底"：
哪些 provider 连着、默认模型是什么、有哪些 agent / 命令 / 技能、配置长什么样。
本组脚本把 `client.server.*` 的**只读发现端点**一次跑齐：

| 脚本 | 演示的调用 | 看什么 |
|---|---|---|
| `explore_server.py` | `server.health()` / `get_config()` / `list_providers()` / `list_agents()` / `list_commands()` / `list_skills()`（+ 可选 `update_config()`） | 每个发现端点返回什么结构；`--directory` 作用域怎么用 |

## 适用场景

- 第一次连一个服务，想程序化地了解它的能力（别硬编码 provider/model 名——
  服务端环境不同，名字会变，用 `list_providers().connected` 探测）；
- 写上层产品（如 CI 里的自动摘要任务）需要动态挑模型/agent；
- 想确认 `directory` 这类作用域参数如何影响发现结果
  （同一个 server 服务多个项目目录时，配置/agent 可能按目录不同）。

## 前置条件

- `make install` 后位于本仓库环境；
- 运行中的 `opencode serve`（默认 `http://127.0.0.1:4096`）。

## 运行

```sh
uv run python -m examples.02_discovery_config.explore_server
uv run python -m examples.02_discovery_config.explore_server --directory ~/code/myproj
uv run python -m examples.02_discovery_config.explore_server --set-config '{"share": {"enabled": false}}'
```

均支持 `--url` 指定服务地址，`--help` 查看全部参数。

## 代码里有什么

- 六个发现端点全在同一个 `async with` 里顺序调用——发现调用彼此独立，
  没有状态依赖，一个连接复用即可（复用收益见 05）；
- `get_config()`/`update_config()` 返回的是**原始 dict**（服务端配置结构
  演进快，库刻意不建模），用 `json.dumps` 原样展示；
- `list_providers()` 的 `connected` 是判断"哪些 provider 真能出 token"
  的权威来源；`default` 是 provider→model 的默认映射；
- `update_config` 是 PATCH 语义：只覆盖传入的键，改完脚本会提示如何还原。

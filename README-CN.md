# opencode-client

[opencode](https://opencode.ai) 服务的轻量级 Python 客户端。连接一个运行中的
`opencode serve` 进程，以编程方式驱动它：管理会话、发送提示、查看消息、应答
权限/追问、查看版本控制状态、管理 MCP 服务器、消费实时事件流——**同步**与
**异步**两套客户端共享同一套 API。

- **类型化响应**：每个端点的返回值都解析成 pydantic v2 模型（服务端的
  camelCase / 大写 `ID` 线上字段自动映射为 `snake_case` 属性）。
- **有韧性**：429 / 5xx / 连接错误自动重试（指数退避，遵守 `Retry-After`），
  分层异常体系让你只捕获真正关心的那一层。
- **实时流**：`/event` SSE 端点封装成可迭代对象，内建自动重连（断流退避重试；
  干净 EOF 结束迭代）。
- **同步/异步对等**：`OpenCodeClient` 与 `AsyncOpenCodeClient` 方法签名完全
  一致，异步版只是多了 `await`。
- **刻意轻量**：无代码生成、无重型运行时——几个小模块包在 `httpx` 之上。

> 🇺🇸 English documentation: [README.md](README.md)

## 环境要求

- Python **>= 3.11**
- 一个运行中的 `opencode serve` 进程（见[本地服务（Docker）](#本地服务docker)）

## 安装

包尚未发布到 PyPI，从本仓库安装：

```sh
git clone https://github.com/comet-7x/opencode-client-python.git
cd opencode-client-python
pip install .            # 或：uv pip install .
```

开发用途（测试、linter、类型检查）：

```sh
make install             # = uv sync，可编辑安装 + 开发工具
```

## 快速上手

### 异步

```python
import asyncio
from opencode_client import AsyncOpenCodeClient


async def main() -> None:
    async with AsyncOpenCodeClient("http://127.0.0.1:4096") as client:
        print((await client.server.health()).version)
        session = await client.sessions.create()
        reply = await client.sessions.prompt(session.id, "你好！")
        print([p.text for p in reply.parts if p.type == "text"])


asyncio.run(main())
```

### 同步

```python
from opencode_client import OpenCodeClient

with OpenCodeClient("http://127.0.0.1:4096") as client:
    print(client.server.health().version)
    session = client.sessions.create()
    reply = client.sessions.prompt(session.id, "你好！")
```

客户端选项：`base_url`（必填）、`username` / `password`（Basic 认证，可选）、
`timeout`（秒，默认 5）、`max_retries`（默认 2）。用 `client.with_options(...)`
可以基于现有 client 派生一个只覆盖指定项的新 client。

## 资源分组

API 按端点域挂在客户端下分组：

| 分组 | 方法 |
|---|---|
| `client.sessions.*` | `list_sessions` `create` `get` `update` `delete` `fork` `abort` `share` `unshare` `summarize` `respond_permission` `list_messages` `prompt` `prompt_async` `delete_message` |
| `client.server.*` | `health` `get_config` `update_config` `list_providers` `list_agents` `list_commands` `list_skills` `list_permissions` `reply_permission` `list_questions` `reply_question` `reject_question` `stream_events` |
| `client.vcs.*` | `info` `status` `diff` `diff_raw` `apply` |
| `client.mcp.*` | `status` `add` |

多数方法都接受可选的 `directory` / `workspace` 作用域查询参数（平铺关键字参数）。

## 错误处理

非 2xx 响应从统一异常树抛出，根为 `OpenCodeError`：

```
OpenCodeError
├── OpenCodeApiError            （带 status_code + payload）
│   ├── OpenCodeAuthenticationError   (401)
│   ├── OpenCodePermissionError       (403)
│   ├── OpenCodeNotFoundError         (404)
│   ├── OpenCodeConflictError         (409)
│   ├── OpenCodeUnprocessableEntityError (422)
│   ├── OpenCodeRateLimitError        (429)
│   └── OpenCodeServerError           (5xx)
└── OpenCodeTransportError        （根本没拿到 HTTP 响应）
    ├── OpenCodeServerConnectionError
    └── OpenCodeTimeoutError
```

```python
from opencode_client import OpenCodeApiError, OpenCodeNotFoundError, OpenCodeTransportError

try:
    session = await client.sessions.get("ses_missing")
except OpenCodeNotFoundError as exc:
    print(f"不存在：{exc.status_code}")
except OpenCodeApiError as exc:
    print(exc.status_code, exc.payload)
except OpenCodeTransportError as exc:
    print("服务不可达：", exc)
```

瞬时失败（429 / 5xx / 连接错误）会先自动重试 `max_retries` 次（指数退避），
耗尽后才抛出异常。

## 事件流（SSE）

`server.stream_events()` 以上下文管理器方式打开 `/event` 流，迭代解码后的
`Event` 对象，断流自动重连：

```python
async with client.server.stream_events() as stream:
    async for event in stream.aiter_events():
        print(event.type, event.properties)
        if event.type == "session.idle":
            break
```

重连语义：只有**传输错误**触发重试（指数退避 0.5 s → 8 s，预算
`max_reconnect_attempts`，收到任意行即重置预算）；干净 EOF 结束迭代。
`prompt_async` + `stream_events` 是实时观察一个 turn 的标准姿势。

## 裸响应视图

每个方法默认返回解析好的模型。若需要**响应头、精确状态码、或模型映射前的
原始 body**，用 `with_raw_response` 前缀——签名、重试、非 2xx 的错误映射
与正常视图完全一致，只是成功时返回未处理的 `httpx.Response`：

```python
raw = await client.sessions.with_raw_response.get(session_id)
print(raw.status_code, raw.headers["content-type"])
session = Session.model_validate(raw.json())  # 需要的话自己解析
```

四个资源域（`sessions` / `server` / `vcs` / `mcp`）都有；
`stream_events` 没有 raw 变体（它返回事件流，不是一次性响应）。

## 本地服务（Docker）

需要一个运行中的 `opencode serve`。服务声明在
[docker-compose.yml](docker-compose.yml)，下面的 Makefile 目标是 `docker compose`
的薄包装（默认端口 **20001**，镜像 `ghcr.io/anomalyco/opencode:1.18.21`，
最新版本见 <https://github.com/anomalyco/opencode/pkgs/container/opencode>）。
覆盖 `OC_IMAGE` / `OC_PORT` / `OC_HOST` 可写进本地 `.env`（`cp .env.template .env`），
也可临时前置环境变量（`OC_PORT=20002 docker compose up -d`）：

```sh
make docker-pull        # 拉取官方镜像
make docker-run         # 后台启动 API 服务
make docker-health      # curl /global/health 探活
make docker-logs        # 查看日志排查
make docker-stop        # 停止并移除容器（配置持久化在 ~/.config/opencode，不受影响）
make docker-tui         # 临时容器里跑交互式 TUI
```

`docker-run` 会把仓库挂到 `/app`、把 `~/.config/opencode` 挂进容器，provider /
模型配置直接复用。镜像拉取慢时，把域名换成镜像代理即可（不改 Docker 全局
配置），拉完 `docker tag` 还原官方名：

```sh
docker pull ghcr.nju.edu.cn/anomalyco/opencode:1.18.21     # 或 ghcr.m.daocloud.io/...
docker tag  ghcr.nju.edu.cn/anomalyco/opencode:1.18.21 ghcr.io/anomalyco/opencode:1.18.21
```

> **macOS 注意**：如果模型后端（如 vLLM）跑在宿主机，容器内不能用
> `127.0.0.1` 访问它，要用 `http://host.docker.internal:8000/v1`——写到
> `~/.config/opencode/opencode.json` 里 provider 的 `baseURL`。

服务探活后，客户端（以及所有示例/测试）指向它即可：

```sh
uv run python -m examples.00_quickstart.quickstart --url http://127.0.0.1:20001
uv run pytest --live-url http://127.0.0.1:20001   # 可选的真实服务集成测试
```

## 示例

可直接运行、带逐行注释的场景化示例，入口见
[examples/README.md](examples/README.md)：

| 目录 | 主题 |
|---|---|
| `00_quickstart/` | 最简入门（含 `directory` 简写） |
| `01_session_management/` | 会话增删改查 + 全生命周期动词 + 消息历史 |
| `02_discovery_config/` | 健康检查、配置、providers、agents、commands、skills |
| `03_vcs/` | 仓库信息 / 状态 / diff / 原始 diff / 打补丁 |
| `04_mcp/` | MCP 服务器状态 + 注册 |
| `05_advanced_patterns/` | 客户端复用、异常处理、实时流、交互循环、裸响应视图 |

所有脚本都在测试套件里用 `respx` 离线驱动，`uv run pytest` 无需真实服务即可验证。

## 开发

```sh
make install            # uv sync
make test               # pytest（离线）
make lint               # ruff check
make format             # ruff format
make types              # mypy + pyright（strict）
make check              # 全量门禁：format-check + lint + types + test
```

目录布局：`src/opencode_client/`（包本体）、`tests/`（pytest + respx）、
`examples/`（示例）、`temp/`（参考 SDK，已排除在工具链外）。
面向协作者的约定见 [AGENTS.md](AGENTS.md)。

## 许可证

[MIT](https://opensource.org/licenses/MIT)

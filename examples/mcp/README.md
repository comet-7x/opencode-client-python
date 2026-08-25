# mcp — MCP 服务器管理

## 本文件夹讲什么

`client.mcp.*` 对应 `/mcp` 端点，管理 opencode 背后的 MCP（Model Context
Protocol）服务器。本组脚本覆盖两个动词：

| 脚本 | 演示的调用 | 看什么 |
|---|---|---|
| `mcp_servers.py` | `mcp.status()` / `mcp.add(name, config)` | status 的判别联合怎么收窄；local/remote 两种 config 怎么传；注册后回读状态 |

## 适用场景

- 程序化检查"哪些 MCP server 真的连上了"（`status` 里 `connected` 才算数，
  `needs_auth`/`failed` 都不可用）；
- 给新项目批量注册 MCP server（CI 初始化、多环境部署）；
- 理解请求侧 `McpConfig` 的判别联合：`McpLocalConfig`（stdio 子进程）vs
  `McpRemoteConfig`（HTTP/SSE 远程），判别键都是 `type`。

## 前置条件

- `make install` 后位于本仓库环境；
- 运行中的 `opencode serve`（默认 `http://127.0.0.1:4096`）；
- `--name` 注册时：本地形态需 `--command`（如 `npx,-y,@modelcontextprotocol/server-everything`），
  远程形态需 `--remote-url`。

## 运行

```sh
# 只看现有 MCP server 状态
uv run python -m examples.04_mcp.mcp_servers

# 注册一个本地 stdio server（会实际起子进程，需对应包可用）
uv run python -m examples.04_mcp.mcp_servers \
    --name everything --command "npx,-y,@modelcontextprotocol/server-everything"

# 注册一个远程 server
uv run python -m examples.04_mcp.mcp_servers --name remote --remote-url https://mcp.example.com/sse
```

均支持 `--url` 指定服务地址，`--directory` 按项目目录作用域，`--help` 查看全部参数。

## 代码里有什么

- `status()` 返回 `dict[name, MCPStatus]`；`MCPStatus` 是**五个兄弟模型**的
  判别联合（`connected`/`disabled`/`failed`/`needs_auth`/
  `needs_client_registration`），用 `isinstance` 收窄后才能安全读
  `failed.error` 这类分支字段；
- `add()` 的 config 参数同样是判别联合（`type: local | remote`），
  库替你处理 wire 上的 `{"name": ..., "config": {...}}` 包装；
- `add` 返回注册后的状态文档（dict，原样打印）；脚本注册完会**回读 status**
  闭环确认——新 server 可能还在 `needs_auth`/`failed`，这是正常的初始状态；
- connect/disconnect/auth 交互流不在本库范围（见 `resources/mcp.py` 文档）。

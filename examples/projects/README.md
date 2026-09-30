# projects — 项目面与系统信息

## 本文件夹讲什么

opencode 把每个可操作的工作区登记为 **project**；围绕它的还有服务端
自身的系统信息（目录布局、语言服务器）。一个脚本串起这些"我在哪、
管着什么"的问题：

| 端点组 | 内容 |
|---|---|
| `client.projects.*` | `list` / `current` / `update` / `directories` / `git_init`——项目清单、当前作用域、改名/图标/启动命令、附属目录、一键 git init |
| `client.server.get_paths()` | 服务端眼里的 home/state/config/worktree/directory |
| `client.server.lsp_status()` | 挂载的语言服务器及连接状态 |
| `client.server.write_log(...)` | 往**服务端**的日志写一条（远程调试时留痕） |
| `client.auth.set/remove_credentials(...)` | provider 凭证管理（PUT/DELETE，全局无作用域） |

## 适用场景

- 多项目管理：列出所有工作区、确认当前作用域、给项目补 name/icon/start 命令；
- 远程排障：在客户端侧把调试信息直接写进服务端日志；
- 凭证自动化：脚本化设置/轮换 provider 的 API key 或 OAuth token。

## wire 形状的坑（库已处理）

- `Project.time.initialized` 可选而 created/updated 必填；
- `/auth` 的凭证是 **type 判联合三兄弟**（oauth/api/wellknown），其中
  oauth 的 `account_id` 在 wire 上是**小写 Id**（`accountId`）——全 API
  大写 ID 惯例下的特例，模型里用了显式 alias；
- 凭证端点没有"读取"，只有写入/删除。

## 前置条件

- `make install` 后位于本仓库环境；运行中的 `opencode serve`（默认 4096）；
- 全部演示只读或可逆（`--auth-demo` 用假 provider 名做往返，不碰真实凭证）。

## 运行

```sh
uv run python -m examples.projects.explore_projects
uv run python -m examples.projects.explore_projects --log
uv run python -m examples.projects.explore_projects --auth-demo
```

均支持 `--url` 与 `--directory`，`--help` 查看全部参数。

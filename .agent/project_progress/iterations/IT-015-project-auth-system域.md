# IT-015 — project/auth 域 + 系统信息端点

日期：2026-08-24
宏观：M5 之后的功能扩张；BOARD「余下端点」第一批（跳过 TUI/PTY/experimental/api）

## 范围（10 端点，均已对照 OpenAPI 核实）

### 新域 `client.projects.*`（5）

| 方法 | wire | 返回 |
|---|---|---|
| `list()` | `GET /project` | `list[Project]` |
| `current()` | `GET /project/current` | `Project` |
| `update(project_id, body)` | `PATCH /project/{id}` | `Project` |
| `directories(project_id)` | `GET /project/{id}/directories` | `list[ProjectDirectory]` |
| `git_init()` | `POST /project/git/init` | `Project` |

`Project`：id/worktree 必填，vcs(`"git"`)/name/icon/commands/time/sandboxes
可选；`time.created/updated` 必填、initialized 可选。
`UpdateProjectRequest`：name/icon/commands 全可选。

### 新域 `client.auth.*`（2）

| 方法 | wire | 返回 |
|---|---|---|
| `set_credentials(provider_id, credentials)` | `PUT /auth/{providerID}` | `bool` |
| `remove_credentials(provider_id)` | `DELETE /auth/{providerID}` | `bool` |

`Auth` 是 type 判联合三兄弟：`oauth`(refresh/access/expires 必填 +
accountId/enterpriseUrl)、`api`(key + metadata)、`wellknown`(key/token)。
Python 名：`OAuthCredentials`/`ApiKeyCredentials`/`WellKnownCredentials`，
联合别名 `AuthCredentials`。注意 `/auth` **无** directory/workspace 参数
（provider 凭证是全局的）；providerID 路径参数走 path_segment。

### server 域补系统信息（3）

| 方法 | wire | 返回 |
|---|---|---|
| `get_paths()` | `GET /path` | `ServerPaths`（home/state/config/worktree/directory 全必填；wire 名 `Path`，避让 pathlib 语义改名） |
| `lsp_status()` | `GET /lsp` | `list[LSPStatus]`（id/name/root/status connected\|error） |
| `write_log(...)` | `POST /log` | `bool`（body: service?/level? debug-info-error-warn/message?/extra?） |

新模型统一放 `models/system.py`：`ServerPaths`、`LSPStatus`；
project 实体放 `models/project.py`；auth 三兄弟放 `models/auth.py`。

## 任务

- [x] 模型三文件（project/auth/system）+ 三处导出注册
- [x] `_wire.py`：TypeAdapters ×7 + `log_body`/`update_project_body` 助手
- [x] `resources/projects.py`、`resources/auth.py` 四类镜像；
      server.py 加 3 方法×4 类；client 挂载 `projects`/`auth`
- [x] 测试：`tests/test_projects_auth.py`（全端点 sync+async+404+raw 抽查）
- [x] 示例：`examples/projects/`（explore_projects.py）；
      auth 凭证演示并入其中（默认只读不写）
- [x] 文档：README 双语表、AGENTS.md 结构树、examples README 同步
- [x] `make check` 全绿；IT-015/BOARD 归档

## 决策记录

- 不做 TUI/PTY（交互 opencode 自身界面，程序化场景少）、不做
  experimental//api（不稳定面）、sync（多工作区同步，等真实需求）。
- `write_log` 归入 server 域而非独立 log 域（单端点不值得开域）。


## 完成记录

2026-08-24 完成：

- **模型三文件**：`models/project.py`（Project/ProjectIcon/ProjectCommands/
  ProjectTime/UpdateProjectRequest/ProjectDirectory）、`models/auth.py`
  （OAuthCredentials/ApiKeyCredentials/WellKnownCredentials + AuthCredentials
  判联合）、`models/system.py`（ServerPaths/LSPStatus/LogEntry）。
- **wire**：7 个 TypeAdapter + `update_project_body`/`log_body`/
  `credentials_body` 助手。
- **资源**：projects/auth 新域四类镜像；server 域补 get_paths/lsp_status/
  write_log ×4 类；client 挂载 `client.projects`/`client.auth`。
- **测试**：tests/test_projects_auth.py 15 项（判联合序列化、部分更新
  wire 形状、路径编码、404、raw 抽查）；raw 镜像锁 DOMAINS 扩到 7 域。
- **示例**：examples/projects/explore_projects.py（项目/paths/LSP 一屏 +
  --log/--auth-demo 可选演示）+ README；冒烟 fixture 补 8 条路由，+1 用例。
- **文档**：README 双语表、AGENTS.md 结构树（models/resources/examples
  三处）、examples README 同步。
- 结果：**`make check` 全绿（262 passed / 5 skipped，+20）**。

### 踩坑

- **id_alias 大写 ID 规则的例外再现**：oauth 凭证的 wire 字段是
  `accountId`（小写 Id），而 id_alias 生成大写 `accountID`——与 McpOAuthConfig
  同款问题，用显式 validation/serialization alias 解决。新模型凡是
  `*_id` 结尾的可选字段都要先查 OpenAPI 确认大小写。
- models/__init__.py 的 `__all__` 漏登记会被 ruff F401 抓到（import 了但
  未再导出）——三处注册（子模块 import / models.__all__ / 包根两处）
  缺一不可。

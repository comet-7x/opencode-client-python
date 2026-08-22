# AGENTS.md

## 项目简介

这是一个 Python 客户端库，用于连接 opencode 服务器（opencode 作为服务层运行），
封装其 REST API：会话管理（创建/聊天/中止）、消息、事件流等。

参考仓库（官方 opencode Python SDK，代码可借鉴/移植）：

- `temp/repositories/opencode-sdk-python`

## 代码结构（src 布局）

```
src/opencode_client/
  __init__.py          # 对外导出的唯一入口（公开 API 全部从这导）
  client.py            # OpenCodeClient(sync)/AsyncOpenCodeClient(async)：传输/重试 + 资源分组入口
  errors.py            # OpenCodeError 分层异常 + make_api_error/make_transport_error
  constants.py         # 默认超时、重试次数、User-Agent 等常量
  _types.py            # NOT_GIVEN 哨兵（with_options 精确 override 用）
  sse.py               # SSEDecoder（行协议解码）+ EventStream/SyncEventStream（流连接上下文管理器）
  models/              # pydantic 模型，按业务实体拆文件，__init__ 统一 re-export
    base.py            #   OpencodeModel 基类 + id_alias 生成器（camelCase/大写ID 映射）
    session.py         #   Session / 请求体 / PermissionRule / ModelID ...
    message.py         #   Message(role 判联合) / MessageWithParts
    part.py            #   Part(type 判联合, 11 种) / ToolState / 请求侧 PromptPart
    discover.py        #   Health / Agent / Provider / Command（发现类端点）
    event.py           #   Event（SSE 事件泛型）
    interaction.py     #   PermissionRequest / QuestionRequest 等（pending 交互请求）
  resources/           # API 资源层：按端点域分组，组合持有 client（非继承），每域 sync/async 双类
    base.py            #   Resource(sync)/AsyncResource 基类 + query_params 助手
    _wire.py           #   共享 wire 纯函数（request_spec/prompt_body/validate_response/各 body）
    sessions.py        #   SessionsResource/AsyncSessionsResource（/session 全套 CRUD/prompt/messages/permission）
    server.py          #   ServerResource/AsyncServerResource（health/config/provider/agent/command + permission/question 交互 + event）
tests/                 # pytest + respx 测试（test_client.py 等）
examples/              # 教学示例（quickstart/stream_events/browse_history），
                       #   带 test_examples.py 用 respx 驱动 main() 做离线冒烟
temp/repositories/     # 参考用第三方仓库（不参与构建，已排除在 lint/typecheck 外）
.agent/                # 多 Agent 共享区（OpenCode / Claude Code / Codex 共用）
  AGENTS.md            #   本文件真实位置；根目录 AGENTS.md/CLAUDE.md 是指向它的 symlink
  project_progress/    #   宏观/微观进度管理（BOARD.md 看板 + ROADMAP + 迭代文件）
  learning_log/        #   学习笔记 + opencode_rest_api.json（OpenAPI 3.1 完整服务端文档）
  skills/              #   共享技能源（.claude/skills、.opencode/skill symlink 到这）
  plugins/             #   共享插件源（.opencode/plugin symlink 到这）
```

## 多 Agent 共享布局

- **本文件的真实位置是 `.agent/AGENTS.md`**。根目录的 `AGENTS.md` 与 `CLAUDE.md`
  都是指向它的 symlink，供不同 Coding Agent 的默认入口自动发现；
  修改项目指令时只编辑本文件，不要动根目录 symlink。
- 技能/插件写一份、全 Agent 生效：内容放 `.agent/skills/<name>/SKILL.md` 与
  `.agent/plugins/`，经 symlink（`.claude/skills`、`.opencode/skill`、`.opencode/plugin`）接入。
- 进度文档与 API 资料同样收敛在 `.agent/` 内（见「项目进度」「API 文档来源」）。

### 目录规范（如何扩展）

- **加新端点**：先查 API 文档确认路径/参数/schema；按所属域放进已有资源
 （session 相关 → `resources/sessions.py`，server 级 → `resources/server.py`）；
 需要新域时新建 `resources/<域>.py`（`class XxxResource(Resource)` +
 `class AsyncXxxResource(AsyncResource)` 双类），并在 `client.py` 里
 `self.xxx = XxxResource(self)` / `AsyncXxxResource(self)`、在 `resources/__init__.py` 导出。
 **wire 细节一律走 `_wire.py` 纯函数，双类方法体只写「send + validate」。**
- **加新模型**：按实体放进 `models/<实体>.py`，继承 `OpencodeModel`，
 并在 `models/__init__.py` 的 import 列表 + `__all__` 注册。
- 模型与资源解耦：资源层只依赖 `models` 的公开名，不 import 子模块路径
 （`from ..models import Session`，不要 `from ..models.session import ...`）。

## 注释风格

### docstring（必须）

- **每个模块、每个类、每个公开函数/方法都必须有 docstring**（ruff `D` 规则强制，
  仅 `tests/`、`examples/` 豁免）。
- 风格：**Google 风格**。第一行一句话摘要（≤120 列），空行后正文；
  有参数写 `Args:`、有返回值写 `Returns:`、会抛异常写 `Raises:`。
- 私有方法（`_` 前缀）不强制，但非显然逻辑建议写。

### 代码内注释（克制）

- 只解释 **why**，不复述代码在做什么。
- 典型场景：绕过某个限制/怪癖（如 `# wire field is snake_case, not camelCase`）、
  非显然的时序（如 `# let the stream attach before the turn starts`）。
- 注释用英文，与现有代码保持一致。

## 导出规则

- **对外 API 唯一入口是包根**：用户代码只写 `from opencode_client import X`。
- `opencode_client/__init__.py` 的 import 列表与 `__all__` 必须同步维护；
  新增公开符号时两处都要加（ruff F401 会查未再导入项）。
- **子包可被用户直接 import 的只有 `models`**（`from opencode_client.models import ...`
  合法，方便按实体取模型）；`client`/`errors`/`sse`/`constants` 也可 import，
  但 `resources/*`、`models/*` 的具体子模块属于**实现细节，禁止在对外文档/示例中引用**。
- `examples/`、`tests/` 一律从包根或 `opencode_client.models` import，
  示范正确姿势。

## API 文档来源

- **以 `.agent/learning_log/get_opencode_api/opencode_rest_api.json` 为准**（opencode serve 的
  `/doc` 端点导出的 OpenAPI 3.1，170+ 端点），新增端点先查该文件确认路径/查询参数/
  请求体/响应 schema。
- 参考仓库 `temp/repositories/opencode-sdk-python` 是旧版本 Stainless 生成代码，
  仅作风格参考，字段可能与最新 API 不一致。
- 服务端 wire 格式为 camelCase，且 ID 类字段是大写 `ID` 后缀（`sessionID`、
  `providerID`），不是 `sessionId`。`models/base.py` 的 `id_alias` 生成器统一处理。

## 常用命令

Makefile 提供等价别名（`make help` 查看；CI/提交前用 `make check` 一次跑完门禁），
底层仍由 uv 驱动，手写 uv 命令同样有效：

```sh
# 安装（Python >= 3.11，建议 uv）
make install            # = uv sync（或 pip install -e ".[dev]"）

# 测试
make test               # = uv run pytest

# lint / 格式化
make lint               # = uv run ruff check .
make format             # = uv run ruff format .

# 类型检查（pyright strict + mypy 都要过，src 和 tests 一起查）
make types              # = uv run pyright + uv run mypy src/ tests/

# 全量门禁 / 清理
make check              # format-check + lint + types + test
make clean              # 清理构建产物与工具缓存（不动 .venv）
```

## 约定

- Python >= 3.11，使用现代语法（`X | None`、`list[T]` 等）。
- HTTP 客户端用 `httpx.AsyncClient`，所有 API 方法为 async。
- 数据模型用 pydantic v2（继承 `OpencodeModel`，`model_dump`/`model_validate`），
  字段映射规则见 `models/base.py` 的 `id_alias`（camelCase + 大写 `ID`），
  个别特例用显式 `Field(alias=...)`。
- 客户端保持轻量：响应解析统一走模块级 `TypeAdapter` 常量（资源文件顶部），
  请求方法参数平铺（`directory`/`workspace` 等 query 参数直接作为关键字参数）。
- API 按端点域分组：会话/消息/权限走 `client.sessions.*`，
  server 级（health/config/provider/agent/command/event）走 `client.server.*`。
- 双客户端对等：**`OpenCodeClient`（sync）与 `AsyncOpenCodeClient`（async）方法签名完全一致**，
  仅 async 侧多 `await`。新增端点必须同时实现双类。
- wire 逻辑（路径/query/body 组装、`TypeAdapter` 解析）必须放在 `resources/_wire.py`
  的共享纯函数里，资源类只做"发送 + 调共享函数"，禁止在资源里写裸 dict 拼装。
- 错误：非 2xx 按状态码抛分层异常（404→`OpenCodeNotFoundError`、429→`OpenCodeRateLimitError`、
  5xx→`OpenCodeServerError`，基类 `OpenCodeApiError`）；连接/超时抛
  `OpenCodeTransportError` 子类。映射逻辑只在 `errors.make_api_error`/`make_transport_error`。
- 429/5xx/连接错误自动重试（`max_retries`，指数退避 + `Retry-After`）；
  `with_options(...)` 用 `NOT_GIVEN` 哨兵精确 override 配置。
- 事件流（`/event`）是 SSE：async `client.server.stream_events()` 返回 `EventStream`
  （`aiter_lines`），sync 返回 `SyncEventStream`（`iter_lines`）；
  统一用 `SSEDecoder`（`aiter_events`/`iter_events`）解析为 `Event`
  （`type` + `properties: dict`，v1 事件不建模 94 个具体类型）。
- 不要修改 `temp/` 下的参考仓库。
- 从官方 SDK 移植代码时：参考仓库是 Stainless 生成的重型代码（`_client.py`、
  `_resource.py`、generated types），本项目保持轻量手写风格，只挑选需要的部分，
  不要整体拷贝生成目录。
- 提交前确保 `ruff check`、`ruff format --check`、`pyright`、`mypy`、`pytest` 全部通过。

## 项目进度（必读）

进度唯一事实来源在 `.agent/project_progress/`，规则见其 README：

- **开始工作前**：先读 `.agent/project_progress/BOARD.md`（任务看板），确认当前宏观阶段/微观迭代。
- **完成工作后**：更新对应 `.agent/project_progress/iterations/IT-XXX-*.md` 的任务状态，并同步 `BOARD.md`；
  跨阶段决策与发版信息写入 `.agent/project_progress/macro/ROADMAP.md`。

```
BOARD.md              # 任务看板：当前宏观阶段 + 微观迭代 + 阻塞项（随时看、随时更新）
macro/ROADMAP.md      # 宏观：里程碑总览 + 关键决策/发版记录
iterations/IT-XXX-*.md # 微观：每个迭代一个文件，目标 + 可勾选任务 + 完成记录
```

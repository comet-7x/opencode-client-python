# 宏观路线图：opencode-client（Python 服务层客户端）

> 项目定位：轻量 Python 客户端，连接 `opencode serve` 服务层；代码风格参考官方 SDK
> （`temp/repositories/opencode-sdk-python`），API 以
> `.agent/learning_log/get_opencode_api/opencode_rest_api.json`（170+ 端点）为准。

## 里程碑总览

| 里程碑 | 内容 | 状态 |
|---|---|---|
| M1 奠基 | 项目结构（src 布局）、pyproject、质量工具链（ruff/mypy/pyright/pytest）、AGENTS.md | ✅ 完成（IT-001）|
| M2 核心功能 | 会话/消息/事件流核心链路 + 真实服务端到端验证 | ✅ 完成（IT-002）|
| M3 功能扩张 | 按使用场景补齐端点：权限/问答交互（IT-005 ✅）、vcs/skill/MCP 基础（IT-006 ✅）、余下候选 share/MCP 连接流等；工程化：地基 IT-003 ✅ + sync/async 对等 IT-004 ✅ | 🔵 进行中 |
| M4 测试强化 | 关键路径补充集成测试、事件流断连重连验证、边界用例 | ⬜ 未开始 |
| M5 发布准备 | README 使用文档、CHANGELOG、版本号策略、打包验证（sdist+wheel）| ⬜ 未开始 |

## 关键记录

### 2026-08-22 — IT-006 vcs / summary / skill / MCP 基础端点
- 9 端点（sync/async 对等）：`client.vcs.*`（info/status/diff/diff_raw/apply，
  diff 的 `mode` 收紧为 `Literal["git","branch"]`）、`client.server.list_skills`、
  `client.mcp.status/add`；`summarize` 双类早已存在，本轮补齐测试
- 新模型：`models/vcs.py`（VcsInfo/VcsFileStatus/VcsFileDiff）、`models/mcp.py`
  （MCPStatus 5 路 `status` 判联合 + McpLocal/McpRemote `type` 判联合 +
  McpOAuthConfig）、discover += Skill
- wire 三处 alias 特例（均活服务/spec 核实）：`default_branch` snake_case、
  `clientId`/`clientSecret` 小写 d、`VcsInfo` 全字段 nullable；`validate_text`
  处理 `GET /vcs/diff/raw` 的 `text/x-diff` 非 JSON 响应
- 测试基建：`tests/conftest.py` session 级 fixture 清除环境代理变量
  （本机 SOCKS 代理会让 httpx 构造即报错；库保留 trust_env 行为，测试自隔离）
- 验证：全门禁绿（pytest **68 passed**）；真实服务 9 端点 sync+async 冒烟通过
  （apply 有写副作用，仅 respx 覆盖）
- 后续另开迭代（一迭代一主题）：IT-007 `with_raw_response`、IT-008 M4 集成/断连重连

### 2026-08-22 — 仓库工程化（.gitignore + Makefile + develop 分支）
- `.agent/` 多 Agent 共享布局：指令/进度/学习日志收敛其中，根目录
  `AGENTS.md`/`CLAUDE.md` 及 `.claude/skills`、`.opencode/skill|plugin` symlink 接线
- `.gitignore` 建立（`.venv`/`dist`/工具缓存/`temp/` 参考仓库均排除）
- Makefile 常用命令别名：`make install/test/lint/format/types/check/clean`
  （`make check` = format-check + lint + types + test 全门禁）
- 首次推送 `origin/develop`：5 批按类别提交（脚手架/核心/测试/示例/共享配置），
  symlink 以 mode 120000 正确入库

### 2026-08-22 — IT-005 permission/question 交互闭环
- 5 个交互端点（server 级，归 ServerResource 双类）：`list_permissions`/`reply_permission`
  （once/always/reject + message）、`list_questions`/`reply_question`（answers=每题一组 label）/
  `reject_question`
- 新模型 `models/interaction.py`：`PermissionRequest`/`QuestionRequest`/`QuestionInfo`/
  `QuestionOption`/工具指针等（`sessionID`/`callID` 走 id_alias）
- 教学 `examples/respond_interactions.py`：prompt_async + SSE 监听 + 轮询自动应答
  （默认安全侧 permission=reject）→ `session.idle` 收尾
- 验证：全门禁绿（pytest 45 passed）；真实服务 list 双端调通 + 示例实跑到 session.idle
- schema 依据 opencode_rest_api.json 逐字段核实（permission reply 枚举 once/always/reject；
  question answers 为 `list[list[str]]` 顺序对齐 questions）

### 2026-08-22 — IT-004 同步客户端 + 官方 SDK 优势吸收
- **双客户端**：`OpenCodeClient`(sync) / `AsyncOpenCodeClient`(async)，API 完全对等，
  命名对齐官方 SDK；wire/query/body/parse 全部抽到 `resources/_wire.py` 纯函数共享，
  sync/async 只差 `await`（轻量方案，不照搬官方 8000 行生成代码 + 每域双类）
- **吸收官方长板**：分层异常（404→`OpenCodeNotFoundError`、429→`RateLimit`、5xx→`Server`、
  timeout/connection 独立基类）、`NOT_GIVEN` 哨兵（`with_options` 精确 override）、
  自动重试（429/5xx/连接错误，指数退避 + `Retry-After`）、`with_options` 派生
- 同步 SSE：`SyncEventStream` 与 async `EventStream` 对等
- **破坏性变更（0.1.0 未发布，接受）**：原 async `OpenCodeClient` → `AsyncOpenCodeClient`；
  examples/tests 全量迁移
- 未做（待决）：`with_raw_response`（返回原始 httpx.Response）
- 全门禁绿：ruff / format / mypy(21 文件) / pyright strict / **pytest 34 passed**
- 真实服务双端冒烟通过（v1.18.18 @ 127.0.0.1:20001）：sync + async 各自
  health/agents/create/prompt("pong")/history/fork/abort/delete 全通过，404 正确分层抛出
- 环境备忘：provider 名会漂移（`steins-middleware-vllm`），smoke 脚本用
  `list_providers().connected` 探测，不硬编码

### 2026-08-22 — IT-003 工程化重构完成
- 目录升级为可扩展库结构：`errors.py`/`constants.py`/`models/`（base/session/message/part/discover/event）
  /`resources/`（sessions/server，组合式资源层）；API 由扁平改为 `client.sessions.*`/`client.server.*`
  分组风格（对齐官方 SDK，0.1.0 未发布故接受破坏性变更）
- `examples/` 教学示例（quickstart/stream_events/browse_history）+ respx 离线冒烟
- AGENTS.md 补：注释风格（Google docstring + 克制注释）、docstring 强制（ruff `D`）、
  导出规则（包根唯一入口 + `models` 可选子包入口）、目录规范与扩展点
- 全门禁绿：ruff(+D) / format / mypy(18 文件) / pyright strict / pytest 23 passed
- 真实服务冒烟通过（v1.18.18，SSE 14 deltas，pong，examples 实跑）

### 2026-08-21 — M1 完成
- pyproject.toml（hatchling、Python >= 3.11、dev 依赖组）
- src 布局：`src/opencode_client/` + `py.typed`
- 质量门禁：`ruff check` / `ruff format` / `pyright strict` / `mypy` / `pytest` 全绿
- 修正 starter 中 pydantic v1 风格代码（`ConfigDict`、`_tag` 字段、`X | None` 语法）

### 2026-08-22 — M2 完成（真实服务验证通过，opencode v1.18.1 @ 127.0.0.1:20001）
- 模型层 `models.py`：Session/Message(discriminated union)/Part(11 种)/ToolState/Agent/Provider 等
- **wire 格式关键约定**：camelCase + 大写 ID（`sessionID`），由 `_id_alias` 生成器统一处理
- `sse.py`：WHATWG SSE 行协议解码器；`client.py`：session 全套 CRUD、prompt/prompt_async、
  `stream_events()`（EventStream 异步上下文管理器）、health/config/providers/agents/commands/respond_permission
- 端到端验证：建会话 → prompt(Qwen3.8-27B) → SSE 92 deltas + session.idle → 历史/abort/fork/delete 全部成功
- 修复：`prompt(model=)` 支持 dict；`MessageWithParts.parts` 由弱类型改为 `list[Part]`
- 已知环境问题：本机 uv python 3.12.13 缺 `collections.abc.AsyncContextManager`（疑似坏构建）；
  PyPI 网络间歇 TLS 失败（影响 `uv build`）

## 发版记录

（暂无）

## 待决事项

- [ ] M3 第一批端点优先级：权限/问答交互（permission/question）是否第一优先？
- [ ] 是否补 `with_raw_response`（官方长板，IT-004 未含）？
- [x] 是否需要 sync 客户端 → **IT-004 已交付**（双客户端对等）
- [ ] 发布渠道：PyPI 还是内部私有源？

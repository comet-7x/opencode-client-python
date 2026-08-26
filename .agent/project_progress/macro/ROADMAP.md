# 宏观路线图：opencode-client（Python 服务层客户端）

> 项目定位：轻量 Python 客户端，连接 `opencode serve` 服务层；代码风格参考官方 SDK
> （`temp/repositories/opencode-sdk-python`），API 以
> `.agent/learning_log/get_opencode_api/opencode_rest_api.json`（170+ 端点）为准。

## 里程碑总览

| 里程碑 | 内容 | 状态 |
|---|---|---|
| M1 奠基 | 项目结构（src 布局）、pyproject、质量工具链（ruff/mypy/pyright/pytest）、AGENTS.md | ✅ 完成（IT-001）|
| M2 核心功能 | 会话/消息/事件流核心链路 + 真实服务端到端验证 | ✅ 完成（IT-002）|
| M3 功能扩张 | 按使用场景补齐端点：权限/问答交互（IT-005）、vcs/skill/MCP 基础（IT-006）；工程化：地基 IT-003 + sync/async 对等 IT-004（余下候选 share/MCP 连接流留后续） | ✅ 完成 |
| M4 测试强化 | 关键路径补充集成测试、事件流断连重连验证（含自动重连实现）、边界用例 | ✅ 完成（IT-007）|
| M5 发布准备 | README 使用文档、CHANGELOG、版本号策略、打包验证（sdist+wheel）| ⬜ 未开始 |

## 关键记录

### 2026-08-24 — IT-011 session 域补全（11 端点 ×4 类）
- sessions 15 → **26 方法**：`status`/`children`/`list_todos`/`diff`/
  `revert`/`unrevert`/`init`/`command`/`shell`/`delete_part`/`update_part`，
  sync/async/raw×2 四类逐字镜像（raw 一致性锁自动通过）。
- 新模型：`SessionStatus`（idle/busy/retry 判联合）、`Todo`、
  `SessionFileDiff`（仅 additions/deletions 必填，与 VcsFileDiff 的差异点）。
- wire 差异核实（服务端 groups/session.ts + handlers/session.ts）：
  `command.model` 是 `"provider/model"` 字符串、`shell.model` 保持对象且
  agent 必填、`update_part` 服务端校验三 ID 与路径一致否则 400；
  revert/unrevert/shell 的 busy → 409 → 现有 `OpenCodeConflictError` 直接命中。
- 测试 +16（`tests/test_sessions_extra.py`）+ examples 冒烟 +1
  （`01_session_management/session_state_history.py`）；结果：**192 passed /
  5 skipped**，全门禁绿。
- 踩坑：`Part` 判联合不能 `model_validate`（用具体子类构造）；respx 未发送
  的 query key 不在 params dict 里（断言 `not in` 而非 `is None`）。
- 另：删除 client.py send() 两处不可达的 `raise ... # pragma: no cover`
  兜底（mypy/pyright 均可证明 while True 不 fall-through），连带清理未用 import。

### 2026-08-23 — IT-010 事件 Router + 类型化热事件
- **契约层**（`models/event.py`）：`EventType`（`StrEnum` 开放集，57 成员，
  种子 = 服务端 `/doc` 导出的 v1 事件面）；6 热事件子类复用现有模型
  （`MessagePartUpdatedEvent.part → Part` 判别联合 /
  `PermissionAskedEvent.request → PermissionRequest` /
  `QuestionAskedEvent.request → QuestionRequest`）；`_TypedEvent` 的
  before 校验器把 `properties` 提升到顶层；`typed_event()` 升级未知类型
  直通、payload 解析失败降级基类（流永不断）。
- **消费层**（`router.py` 新文件，包根）：`AsyncEventRouter`/`EventRouter`，
  `stream.route(session_id)` 进 `sse.py`；单读者顺序分发（保 part 创建先于
  delta 的时序）、多订阅、`until`/`timeout`/错误传播/干净 EOF 四路收口；
  裸流 `aiter_events()` 原样保留（加法式）。
- **权威源修正**（设计 §12）：事件面以 `/doc` 导出的 OpenAPI 为准——
  "94 种"系误传（实为 57 个 v1 事件）；`permission.updated`/
  `question.updated` 不存在，实为 `permission.asked`/`question.asked`；
  `packages/schema/src/v1` 只定义 16 个、生成 SDK 有漂移。
- 关键坑：`Part` 必须运行时导入（`TYPE_CHECKING` 下 pydantic 延迟注解
  解析报错）；pyright strict 的 lambda 参数收窄 / StrEnum 字面量收窄 /
  dict spread partial-unknown 返回各有处理。
- 结果：`make check` 全绿，**174 passed / 5 skipped**（新增
  `tests/test_event_router.py` 32 项）。引用设计的流式消费将建在 Router 上。

### 2026-08-22 — Docker 统一管理本地服务 + 双语 README
- 决策：**不自建 `opencode serve` 进程，统一 Docker 管理**。Makefile 新增
  `docker-pull/run/tui/stop/logs/health` 目标（`OC_IMAGE`/`OC_PORT` 可覆盖，
  默认 `ghcr.io/anomalyco/opencode:1.18.21` : 20001）；`docker-run` 挂
  `./`→`/app`、`~/.config/opencode`→容器，provider 配置持久化复用。
- 镜像拉取慢用**域名代理**（不改全局 Docker 配置）：`ghcr.io` →
  `ghcr.nju.edu.cn`（南大）/ `ghcr.m.daocloud.io`（DaoCloud），拉完
  `docker tag` 还原官方名，后续命令统一。
- Mac 坑：容器访问宿主机 vLLM 须用 `host.docker.internal`，不能 `127.0.0.1`。
- 探活端点为 `/global/health`（OpenAPI 里另有 `/api/health`，客户端库用前者；
  笔记中的 `/health` 不是真实路径）。
- 新增 `README.md`（英，默认）/ `README-CN.md`（中）：安装、快速上手、资源分组表、
  异常树、事件流语义、Docker 服务、示例导航、开发命令。

### 2026-08-22 — examples 全模块补齐（02/03/04 新域 + 01 生命周期 + 05 交互补全）
- 背景：盘点发现 37 个公开方法仅 ~15 有示例，vcs/mcp 两域零覆盖。
- 目录重排：03_advanced_patterns → **05**；新增 **02_discovery_config**
  （health/config/providers/agents/commands/skills + update_config）、
  **03_vcs**（info/status/diff/diff_raw/apply）、**04_mcp**（status/add）。
- 01 新增 `session_lifecycle.py`：update/get/fork/abort/share/unshare/
  summarize/delete_message 一次走完（含 404 演示、share 未启用时降级、
  summarize 动态选 connected provider）；05 interact 加 `--respond` 演示
  `sessions.respond_permission` 与 `server.reject_question`。
- 测试：fixture 扩展全部新端点路由，冒烟 9 → **16 例**（含 list_messages
  此前漏测）。踩坑：respx 同 method+path 多次注册是别名覆盖（后者优先）；
  宽泛 DELETE regex 会吞 /session/{id}/share（需 `$` 锚定）；
  argparse `choices` 只能收窄到 str，传 `Literal` 参数要 `cast`。
- 结果：`make check` 绿，120 passed / 5 skipped。覆盖率：sessions 15/15、
  server 13/13、vcs 5/5、mcp 2/2（client 级 with_options 在 05）。

### 2026-08-22 — conftest 收敛：删除根目录 conftest.py
- 根目录 `conftest.py`（仅注册 `--live-url`/`--live-password`）删除，选项注册并入
  `tests/conftest.py`。实测（pytest 9.1.1）IT-007 时「子目录 conftest 的选项钩子
  不生效」的结论过严：只要调用会收集到 tests/（`make test`、裸 `pytest`、
  `pytest tests/`），子目录 conftest 的 `pytest_addoption` 都生效；唯一不识别的
  是 `pytest examples/ --live-url ...`，该组合无意义（examples 全 respx 离线 mock）。
- 连带修复：根 conftest 被删后 pytest 不再自动把项目根加入 sys.path，
  `examples` 包无法 import → pyproject 加 `pythonpath = ["."]`（pytest 内置 ini
  选项，不依赖任何 conftest 位置）。
- 结果：`make check` 绿，113 passed / 5 skipped。

### 2026-08-22 — examples 按场景重构为编号目录
- 平铺脚本（quickstart/stream_events/browse_history/respond_interactions）迁移为
  `00_quickstart/`、`01_session_management/`、`03_advanced_patterns/`，每目录
  README.md（适用场景 + 前置条件）+ 完整可运行脚本；总入口 `examples/README.md`。
- 新增示例：client_reuse（复用收益 + with_options override）、error_handling
  （分层异常处理）、interact_moving_session（权限+问答交互闭环，asyncio 并发监听）。
- `test_examples.py` 重写：importlib 加载编号包（数字前缀目录靠 PEP 420 命名空间包），
  respx 驱动各脚本 `cli()` 离线冒烟 9 例。
- 踩坑：`sessions.create()` 无 title 平铺参数，须传 `body=CreateSessionRequest(...)`；
  asyncio 子任务（deadline sleep）不 cancel 就 gather 会挂满整个超时。
- 结果：`make check` 绿，113 passed / 5 skipped。

### 2026-08-22 — IT-007 M4 测试强化（SSE 自动重连 + 全测试补全）
- **SSE 自动重连（新能力）**：`stream.iter_events()`/`aiter_events()` 内建重连；
  仅**传输错误**触发（0.5s→8s 指数退避，预算 `DEFAULT_STREAM_RECONNECT_ATTEMPTS=5`，
  收任意行重置预算，耗尽抛 `OpenCodeTransportError` 子类）；**干净 EOF 结束迭代**
  （冲刷残留半帧）；在途半帧丢弃（服务端不做 `Last-Event-ID` 重放，跨连接拼接
  会产幽灵事件）。消费 API 上移到流上，`iter_lines`/`aiter_lines`/`SSEDecoder`
  保留向后兼容。语义教训：初版把 EOF 也当断流，空流脚本下无限重连（跑飞 bug）。
- **请求级重试补全**：429 + `Retry-After`（数值用之/非数值回退）、5xx 指数退避、
  预算 0、耗尽→`OpenCodeRateLimitError`/`OpenCodeServerError` 映射，sync+async 镜像
  （`tests/test_retries.py` 18 例）。
- **真实 server 集成（新）**：`pytest --live-url <url> [--live-password <pw>]`
  （选项钩子注册在 `tests/conftest.py`，见下方 2026-08-22 conftest 迁移记录）；
  无开关自动 skip，离线门禁不受影响。
  覆盖 health、session CRUD、活事件流看到 `session.created`、真实传输注入 503
  验证重试。
- **测试基建**：重连测试用脚本化假传输（respx 无法表达 mid-stream drop——
  路由解析期即消费 side_effect）；`_reconnect_delay` 模块级单点供 spy。
- 结果：`make check` 绿，离线 **107 passed / 5 skipped**；真实服务
  （v1.18.18，127.0.0.1:20001）live 套件 **5/5 passed**。
- M3/M4 完成；下一里程碑 M5 发布准备。

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
- 后续另开迭代（一迭代一主题）：IT-007 M4 集成/断连重连、IT-009 `with_raw_response`

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
- 同步 SSE：`EventStream` 与 async `AsyncEventStream` 对等
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
  `stream_events()`（AsyncEventStream 异步上下文管理器）、health/config/providers/agents/commands/respond_permission
- 端到端验证：建会话 → prompt(Qwen3.8-27B) → SSE 92 deltas + session.idle → 历史/abort/fork/delete 全部成功
- 修复：`prompt(model=)` 支持 dict；`MessageWithParts.parts` 由弱类型改为 `list[Part]`
- 已知环境问题：本机 uv python 3.12.13 缺 `collections.abc.AsyncContextManager`（疑似坏构建）；
  PyPI 网络间歇 TLS 失败（影响 `uv build`）

## 发版记录

### v0.1.0 — 2026-08-22（本地 dist + git tag）
- 发布形式：`uv build` 产出 `dist/opencode_client-0.1.0-py3-none-any.whl` +
  sdist，打 tag `v0.1.0`；**未发 PyPI**。
- 发布件：MIT LICENSE + CHANGELOG + 双语 README；sdist 经 pyproject
  include/exclude 收紧（不含 `.agent`/`.opencode`/`.claude`/`temp`）。
- 功能面：双客户端（sync/async 对等）、37 个公开方法（sessions/server/vcs/mcp）、
  SSE 自动重连、请求级重试（429 Retry-After/5xx/连接错误）、分层异常、
  pydantic 类型化响应（camelCase/大写ID → snake_case）。
- **PyPI 阻塞**：`opencode-client` 名称已被第三方占用（v0.1.1）；
  后续发布需换名（可用：`opencode-client-python` 等）+ token。

## 待决事项

- [ ] M3 第一批端点优先级：权限/问答交互（permission/question）是否第一优先？
- [x] 是否补 `with_raw_response`（官方长板，IT-004 未含）→ **IT-009 已交付**
      （2026-08-23，官方同款代理前缀形态 + 镜像一致性锁）
- [x] 是否需要 sync 客户端 → **IT-004 已交付**（双客户端对等）
- [x] 发布渠道 → **v0.1.0 走本地 dist + git tag**（用户拍板）；PyPI 后续
      （需先解决名称占用：`opencode-client` 已被第三方用掉，换 `opencode-client-python` 之类）
- [x] 事件 Router + 类型化热事件 → **IT-010 已交付**（2026-08-23）；
      全量类型化 deferred，触发式排期（功能需求 / 事件遥测频次报告，
      见 `temp/docs/event-router-design.md` §9）

## v0.1.0 之后增量（随下次发版带出）

- IT-009 `with_raw_response` 裸响应视图：4 资源域 × sync/async 共 8 个
  `*WithRawResponse` 代理（成功返回未解析 `httpx.Response`；重试/错误映射
  与正常视图共享；`stream_events` 无 raw 变体），`tests/test_raw_response.py`
  镜像一致性锁 + 示例 `05_advanced_patterns/raw_response.py`。
- IT-010 事件 Router + 类型化热事件：`EventType` 开放集（57）+ 6 热事件
  类型化子类（降级兜底不破坏流）+ `AsyncEventRouter`/`EventRouter`
  （`stream.route(sid)` 订阅/顺序分发/`until` 终止）。

## v0.2.0 增量（IT-011 ~ IT-017，2026-08-24，随下次发版带出）

- **功能面**：session 域补全 11 端点（status/children/todo/diff/revert/
  init/command/shell/part 编辑）→ files 域新资源域（7 端点）→ mcp 域补全
  （OAuth 流 + connect/disconnect，共 8 方法）→ projects/auth 新域 +
  系统信息端点（10 端点）→ 核心面收尾 11 端点。**核心资源域 100%**
  （69/69 公开方法均有示例演示），目标面 80/105 = 76%
  （详见 `api_coverage.md`）；剩余 tui/pty/sync 为有意延后批次。
- **质量**：全仓库 code review 11 项修复（分层默认超时、重试幂等感知、
  sync Router 真实墙钟超时、`OpenCodeResponseError` 错误分层等，
  见 IT-012）；覆盖率工具链（src ~92%，`make test` 带 90% 门禁）。
- **验证体系**：live 单测 11 用例（`--live-url` opt-in）+ 全端点扫描工具
  `temp/live_sweep.py`（70 项检查对真实 opencode 1.18.22 全过、零模型漂移；
  不入库）。examples 按功能模块重组并实现 API 面全覆盖，顺带修两个示例 bug
  （mcp_servers --oauth 不可达、interact 轮询竞态）。

### 待决

- [x] 发版就绪评估 → **已达标并完成本地发版**（2026-08-24）：
  包名定名 **`opencode-client-python`**（`opencode-client` 被第三方占用；
  导入名 `opencode_client` 不变），版本 **v0.2.0**——dist 已构建、tag 已打。
  PyPI 上传待用户配置 token 后执行 `uv publish`。
  CHANGELOG `[0.2.0] - 2026-08-24` 底稿即本次发布说明。
- [ ] tui/pty/sync 批次是否排期（需求驱动）

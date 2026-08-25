# Code Review 报告 — 2026-08-24

> 由结构化报告 [`code_review_2026-08-24.json`](./code_review_2026-08-24.json) 转换生成。
> **✅ 全部 11 项已由 IT-012 修复**（2026-08-24，`make check` 全绿：214 passed / ruff / mypy / pyright）。

## 元信息

| 项 | 值 |
|---|---|
| 审阅日期 | 2026-08-24 |
| 审阅范围 | 全仓库：`src/opencode_client` 全部模块 + `tests` + `examples` |
| 参考资料 | `.agent/AGENTS.md`、`.agent/project_progress/`、`.agent/learning_log/opencode_rest_api.json`、`temp/repositories/opencode` 官方源码 |
| 基线 commit | `f344ecd` feat: session 域补全 11 端点（IT-011） |
| 门禁现状（审阅时） | pytest **192 passed, 5 skipped** · ruff ✅ · mypy ✅ (38 files) |

## 总览

**共 11 个问题**：

| 严重程度 | 数量 | 徽章 |
|---|---:|---|
| 🔴 High | 1 | 默认配置下即触发的功能性缺陷 |
| 🟠 Medium | 3 | 特定但现实条件下行为错误 / 双端不一致 / 设计缺口 |
| 🟡 Low | 6 | 覆盖缺口、健壮性、约定偏差 |
| ⚪ Info | 1 | 改进建议，非缺陷 |

> **总体评估**：架构质量高——wire 纯函数收敛、raw-response 镜像锁测试、错误分层与重试策略清晰。核心风险集中在**默认超时与阻塞式 prompt 的交互**上（并连带触发重复请求）；其余为一致性/健壮性小问题。

### 问题速览

| ID | 级别 | 标题 | 主要文件 | 状态 |
|---|---|---|---|---|
| [H1](#h1) | 🔴 High | 默认 timeout=5s 使阻塞式 prompt 必然失败，重试还会重复发送请求 | `client.py:196`、`constants.py` | ✅ IT-012 |
| [M1](#m1) | 🟠 Medium | 传输层重试不区分幂等性，非幂等 POST 可能被执行两次 | `client.py:272-288` | ✅ IT-012 |
| [M2](#m2) | 🟠 Medium | sync EventRouter.run(timeout) 静默流会超过 deadline 永久阻塞 | `router.py:184-198` | ✅ IT-012 |
| [M3](#m3) | 🟠 Medium | pydantic.ValidationError 绕过 OpenCodeError 异常体系 | `_wire.py:149` | ✅ IT-012 |
| [L1](#l1) | 🟡 Low | `/session/status` 缺 directory/workspace 参数 | `sessions.py` ×4 处 | ✅ IT-012 |
| [L2](#l2) | 🟡 Low | 路径参数未 URL 编码 | `sessions.py:121` 等 | ✅ IT-012 |
| [L3](#l3) | 🟡 Low | 重试路径响应未关闭，连接缓慢泄漏 | `client.py:282-288` | ✅ IT-012 |
| [L4](#l4) | 🟡 Low | `_hoist_properties` payload 可覆盖信封 `type` 键 | `event.py:138-147` | ✅ IT-012 |
| [L5](#l5) | 🟡 Low | HTTP-date 形式的 Retry-After 被忽略 | `client.py:108-111` | ✅ IT-012 |
| [L6](#l6) | 🟡 Low | examples 中文注释违反「注释用英文」约定 | `examples/*` | ✅ IT-012（豁免） |
| [I1](#i1) | ⚪ Info | `stream_events` 返回类型标注为 Any | `server.py:188-211` | ✅ IT-012 |

---

## 🔴 High

### <a id="h1"></a>H1. 默认 timeout=5s 使阻塞式 prompt/command/init 在真实 LLM 延迟下必然失败，且重试会重复发送请求

- **分类**：bug / 默认配置不可用
- **位置**：`src/opencode_client/client.py:196`、`src/opencode_client/constants.py:9`、`src/opencode_client/constants.py:12`
- **状态**：✅ 已修复（IT-012：默认改用分层 `httpx.Timeout(read=60, connect=5)`）

**描述**：构造器把 `DEFAULT_CONNECT_TIMEOUT=5.0` 作为标量传给 httpx（connect/read/write/pool 全为 5s）。`sessions.prompt()/command()/shell()/init()` 是阻塞式调用：服务端要等整轮 LLM 结束才返回（见官方源码 `packages/opencode/src/server/routes/instance/httpapi/handlers/session.ts` 的 prompt handler）。真实 turn 普遍超过 5 秒，ReadTimeout 被当作可重试传输错误自动重试 POST，同一 prompt 最多发送 `max_retries+1` 次，最终抛 `OpenCodeTimeoutError`。`examples/00_quickstart/quickstart.py` 用默认 client 调阻塞 prompt，对真实服务器在典型延迟下即复现。`constants.DEFAULT_READ_TIMEOUT`(60s) 已定义但全仓库无引用。

**触发条件**：任何一次 LLM turn 超过 5 秒（常态），无需特殊环境。

**影响**：旗舰 API 在默认配置下不可用；且每次超时重试都会在服务端产生重复 user message / 重复 turn。

**建议修复**：
- 默认读超时改用 `DEFAULT_READ_TIMEOUT`（或对阻塞类长调用单独放宽）
- 连接错误/读超时的重试建议只对幂等方法默认开启
- 补一条针对超时阈值的阻塞调用 live 测试

---

## 🟠 Medium

### <a id="m1"></a>M1. 传输层重试不区分方法幂等性，非幂等 POST 可能被服务端执行两次

- **分类**：bug-risk / 重试语义
- **位置**：`src/opencode_client/client.py:272-288`、`src/opencode_client/client.py:394-410`
- **状态**：✅ 已修复（IT-012：`_is_retryable_transport_error` 按 method + 失败阶段区分）

**描述**：`send()` 对 `httpx.HTTPError`（ConnectError/ReadTimeout/WriteError 等）一律重试。若请求已到达服务端后才断连（读超时是最常见形态），重试会对 prompt/shell/vcs.apply/config.patch 等非幂等操作产生重复副作用。prompt 支持 `message_id` 幂等但属可选参数，默认路径无保护。

**触发条件**：请求已被服务端接收后发生网络层失败（慢链路、代理抖动、服务重启瞬间）。

**影响**：重复 turn / 重复打补丁 / 配置被写两次。

**建议修复**：至少在文档标注；更好做法是按 method 区分默认重试策略，或在 `send()` 层自动生成并透传 `message_id`。

### <a id="m2"></a>M2. `EventRouter(sync).run(timeout)` 只在事件边界检查超时，静默流会无限期阻塞超过 deadline

- **分类**：行为不一致 / sync-async 对等
- **位置**：`src/opencode_client/router.py:184-198`
- **状态**：✅ 已修复（IT-012：worker 线程跑读循环 + 主线程墙钟 deadline，与 async 对齐）

**描述**：同步 `run()` 用 `time.monotonic()` 比对 deadline，但只有 `next(iterator)` 返回后才检查。若服务器长时间不发事件（空闲流、session 卡住），阻塞中的 `next()` 无法被打断，timeout 形同虚设。异步孪生用 `asyncio.wait_for` 包 `__anext__`，是真实墙钟超时。docstring 虽写明 *checked at each event boundary*，但两个 Router 公开语义不一致。

**触发条件**：sync `EventRouter` + 订阅后事件稀疏/停滞（恰是 timeout 想兜底的场景）。

**影响**：调用方以为有超时保护，实际可能永久挂起线程。

**建议修复**：在文档显著位置标注该限制；或用看门狗线程/socket 层超时实现真实 deadline。

### <a id="m3"></a>M3. 响应模型校验失败的 `pydantic.ValidationError` 绕过 `OpenCodeError` 异常体系

- **分类**：错误分层缺口
- **位置**：`src/opencode_client/resources/_wire.py:149`、`src/opencode_client/models/interaction.py:83-84`
- **状态**：✅ 已修复（IT-012：新增 `OpenCodeResponseError` + `make_response_error`，包根导出）

**描述**：`validate_response` 直接 `adapter.validate_python(...)`，schema 漂移时抛裸 `pydantic.ValidationError`——它不是 `OpenCodeError` 子类，调用方 `except OpenCodeError` 接不住，与 `errors.py` 模块 docstring 声称覆盖本包一切错误的表述矛盾。现实触发面不小：`PermissionRequest.metadata/always` 是必填字段，服务端任一版本省略它们会让 `list_permissions` 整个端点炸掉而非单条降级。

**触发条件**：服务端 schema 变化或字段缺失（跨版本使用常见）。

**影响**：异常处理契约失效；单条数据问题放大成整个端点不可用。

**建议修复**：把 `ValidationError` 包装进 `OpenCodeError` 家族（如新增 `OpenCodeResponseError`），或把强约束字段改为可选+默认。

---

## 🟡 Low

### <a id="l1"></a>L1. `GET /session/status` 未暴露 API 支持的 directory/workspace 查询参数

- **分类**：API 覆盖缺口
- **位置**：`src/opencode_client/resources/sessions.py:206-209` 及另外三处镜像（`:706-709`、`:1167-1169`、`:1546-1548`）
- **状态**：✅ 已修复（IT-012：四处镜像类补参）

**描述**：`.agent/learning_log` 的 OpenAPI（`paths./session/status.get.parameters`）确认该端点接受 directory/workspace 查询参数；其余 session 方法都暴露了这对参数，唯独 status 的四个镜像类没有。

**触发条件**：多项目/多 workspace 场景想按目录过滤状态时。
**影响**：功能缺口，需绕道 `client.http` 手拼请求。
**建议修复**：四处同步补参（注意 `test_raw_response.py` 镜像锁也要更新）。

### <a id="l2"></a>L2. 路径参数未做 URL 编码，直接 f-string 内插进 path

- **分类**：健壮性
- **位置**：`src/opencode_client/resources/sessions.py:121`、`resources/server.py:127`、`resources/vcs.py:74`
- **状态**：✅ 已修复（IT-012：`_wire.path_segment()` 助手，全部内插点替换）

**描述**：所有 `{id}` 类路径参数未 quote。当前 id 都是服务端生成的安全 token（`ses_`/`msg_`/`per_`/`que_` 前缀），实际风险低；但这是公开 API，用户传入含 `/ ? # %` 的字符串会产生错误请求路径或静默匹配到别的资源段。

**触发条件**：用户自供的非标准 id 字符串。
**影响**：错误请求，非注入级风险。
**建议修复**：统一经 `urllib.parse.quote(id, safe='')` 处理（可放 `_wire.py` 助手函数）。

### <a id="l3"></a>L3. 重试路径丢弃的可重试响应未关闭，连接池缓慢泄漏

- **分类**：资源泄漏
- **位置**：`src/opencode_client/client.py:282-288`、`client.py:404-410`
- **状态**：✅ 已修复（IT-012：重试 continue 前 close/aclose）

**描述**：429/5xx 触发重试时旧 response 既未 read 也未 close 即被丢弃；httpx 中未消费完的响应会一直占连接直到 GC。单次调用最多漏 `max_retries` 个连接，量级小但高频重试场景会累积。

**触发条件**：长时间运行且持续收到可重试状态码的进程。
**影响**：连接池占用累积（低概率）。
**建议修复**：continue 前 `response.close()`（或 `read()` 以复用连接）。

### <a id="l4"></a>L4. `_TypedEvent._hoist_properties` 让 payload 键无条件覆盖信封键，包括 `type`

- **分类**：潜在 bug / 边界
- **位置**：`src/opencode_client/models/event.py:138-147`
- **状态**：✅ 已修复（IT-012：payload 的 `type`/`properties` 不再覆盖信封键）

**描述**：`merged.update(payload)` 无排除名单。若某热事件的 properties 中出现同名 `type` 字段（服务端演进完全可能），合并后会在 catalog 分发前改掉 `event.type` / 子类判别字段。当前 6 个热事件 payload 均不含 `type`，暂未触发。

**触发条件**：未来服务端在 properties 中加入 `type` 同名字段。
**影响**：事件误分类（降级到基类无害，误改 type 会误导分发）。
**建议修复**：update 前 pop 掉 payload 中的信封保留键（`type`/`id`），或反向合并（信封键优先）。

### <a id="l5"></a>L5. Retry-After 只识别秒数格式，HTTP-date 格式被静默忽略

- **分类**：规范符合性
- **位置**：`src/opencode_client/client.py:108-111`
- **状态**：✅ 已修复（IT-012：`_retry_after_seconds` 兼容 RFC 7231 两种格式）

**描述**：`retry_after.isdigit()` 为假时直接回落指数退避。RFC 7231 允许 Retry-After 为 HTTP-date；opencode 服务端目前返回秒数所以未触发，但经中间层/反代时可能遇到 date 格式，导致退避不足。

**触发条件**：上游返回 HTTP-date 形式的 Retry-After。
**影响**：退避间隔不当，重试仍失败的概率升高。
**建议修复**：isdigit 失败时尝试 `email.utils.parsedate_to_datetime` 解析并换算剩余秒数。

### <a id="l6"></a>L6. `examples/` 内大量中文行内注释，违反 AGENTS.md「注释用英文」约定

- **分类**：约定偏差
- **位置**：`examples/05_advanced_patterns/event_router.py:46`、`examples/00_quickstart/quickstart.py:58` 等
- **状态**：✅ 已解决（用户拍板：AGENTS.md 显式豁免 examples 教学注释）

**描述**：AGENTS.md 明确规定代码内注释统一用英文；多个示例文件的教学行内注释为中文（ruff 不查 examples，门禁未拦截）。

**触发条件**：约定审查；不影响运行。
**影响**：与项目规范不一致；若示例被用户复制进代码库会扩散该风格。
**建议修复**：统一翻译为英文，或在 AGENTS.md 中显式豁免 examples 的教学注释语言。

---

## ⚪ Info

### <a id="i1"></a>I1. `stream_events` 返回类型标注为 `Any`，丢失了 `EventStream`/`AsyncEventStream` 的静态类型

- **分类**：类型质量
- **位置**：`src/opencode_client/resources/server.py:188-211`、`server.py:361-384`
- **状态**：✅ 已修复（IT-012：`TYPE_CHECKING` import 精确标注返回类型）

**描述**：两个 `stream_events` 的返回注解是 `Any`（应为 `EventStream` / `AsyncEventStream`）。运行时用局部 import 规避循环依赖，但静态侧可以用 `TYPE_CHECKING` import 精确标注；当前用户 IDE 无法补全 `iter_events`/`aiter_events`/`route`。

**触发条件**：所有使用 `stream_events` 的调用方。
**影响**：DX/类型安全损失，非缺陷。
**建议修复**：顶部加 `if TYPE_CHECKING: from ..sse import ...`，返回值改为精确类型。

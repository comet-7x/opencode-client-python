# IT-012 — Code Review 问题修复（11 项）

日期：2026-08-24
宏观：M5 之后的质量加固；来源：全仓库 code review（报告已迁至本地 `temp/code_review/`，不入库）

## 背景

2026-08-24 全仓库审阅（参照 AGENTS.md / OpenAPI / 官方源码）产出 11 个问题：
1 High / 3 Medium / 6 Low / 1 Info。门禁（pytest 192 passed、ruff/mypy 绿）
全部通过，问题集中在门禁覆盖之外的行为层面：默认超时与阻塞式 prompt 的
交互、重试幂等性、双端超时语义一致性、错误分层缺口等。

## 目标

按严重程度逐条修复 review 报告中的问题，`make check` 保持全绿，
High/Medium 各补对应回归测试。

## 任务

### 🔴 High

- [x] **H1 默认超时不可用**：新增 `constants.DEFAULT_TIMEOUT`
      （`httpx.Timeout(read=60, connect=5)`）作为构造器默认值；标量
      timeout 经 `_normalize_timeout` 归一；`with_options(timeout=X)`
      显式传参仍是全相位标量语义
- [x] **M1 重试幂等性**：`_is_retryable_transport_error(method, exc)`——
      幂等方法（GET/HEAD/OPTIONS/TRACE/PUT/DELETE）照常重试；非幂等
      方法仅在连接期失败（ConnectError/ConnectTimeout，请求确定未到达）
      时重试，ReadTimeout 直接抛出不再重发

### 🟠 Medium

- [x] **M2 sync Router timeout 失效**：`EventRouter.run(timeout)` 改为
      worker 线程跑读循环 + 主线程 `Event.wait(deadline)` 实现真实墙钟
      超时（与 async 孪生对齐）；docstring 写明 deadline 触发时阻塞中的
      daemon worker 无法中断的残留限制；补静默流超时测试
- [x] **M3 ValidationError 绕过异常体系**：新增 `OpenCodeResponseError`
      （携带 `validation_error` 属性）+ `errors.make_response_error` 工厂；
      `_wire.validate_response` 包装 pydantic ValidationError；包根导出

### 🟡 Low

- [x] **L1 `/session/status` 补参**：四处镜像类加 directory/workspace
- [x] **L2 路径参数 URL 编码**：`_wire.path_segment()`（`quote(safe="")`），
      sessions/server 全部 `{id}` 内插点替换（104 处）
- [x] **L3 重试响应泄漏**：429/5xx 重试 continue 前 close/aclose 旧响应
- [x] **L4 信封键保护**：`_hoist_properties` 中 payload 的
      `type`/`properties` 键不再覆盖信封（`id` 仍按原语义由 payload 胜出）
- [x] **L5 Retry-After HTTP-date**：新增 `_retry_after_seconds`，isdigit
      失败走 `email.utils.parsedate_to_datetime` 换算剩余秒数
- [x] **L6 examples 中文注释**：AGENTS.md「注释风格」显式豁免 examples
      教学注释（用户拍板）

### ⚪ Info

- [x] **I1 stream_events 类型标注**：`TYPE_CHECKING` import，返回值精确
      标注 `EventStream`/`AsyncEventStream`

## 收口

- [x] `make check` 全绿：**214 passed / 5 skipped**（+22 回归测试）、
      ruff / mypy (39 files) / pyright strict 全过
- [x] review JSON/MD 报告中各条目标记修复状态
- [x] BOARD.md 同步归档

## 完成记录

2026-08-24 完成：

- **client.py**：`DEFAULT_TIMEOUT` 分层超时（connect=5/read=60）为默认，
  H1 的「prompt >5s 必炸 + 重试重复发送」双问题同时消解；`send()` 双类
  加幂等感知重试与响应关闭；`_retry_after_seconds` 支持 RFC 7231 两种格式。
- **router.py**：sync `run(timeout)` 用 worker 线程 + `done.wait(timeout)`
  收口，静默流也能按墙钟抛 `TimeoutError`；handler 抛错/until/干净 EOF
  语义不变（异常经 failure 列表跨线程重放）。
- **errors.py / _wire.py**：`OpenCodeResponseError` 进家族树，schema 漂移
  时 `except OpenCodeError` 可兜底；顺带在测试中实证（空 body 打 Session
  adapter 即触发）。
- **回归测试** `tests/test_review_fixes.py` 22 项：默认分层超时×3、幂等
  重试×6（MockTransport 计数断言 POST ReadTimeout 只发一次）、HTTP-date×3、
  响应校验包装×2、sync router 静默流/活跃流×2、status 补参×2、路径编码×2、
  信封键保护×2。
- 结果：**`make check` 全绿（214 passed / 5 skipped）**。

### 踩坑

- 测试假流的 `iter_events` 若不含 `yield` 就是普通函数——构造迭代器时在
  主线程同步死循环（旧实现的 bug 形态恰好被复刻）；必须写成 generator。
- httpx 的 `url.path` 返回**解码后**路径，断言 percent-encoding 要用
  `url.raw_path`（bytes）。
- respx 字面量路由匹配不了含 `%2F` 的已编码 path，用 `url__startswith` 兜。
- pyright strict 下 parenthesized import 的 `# pyright: ignore` 注释要放在
  每个名字所在行才生效（报告定位到名字行而非 import 行）。

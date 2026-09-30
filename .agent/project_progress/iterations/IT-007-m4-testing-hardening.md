# IT-007 — M4 测试强化：SSE 自动重连 + 请求重试/集成测试补全

日期：2026-08-22
宏观：M4 测试强化（关键路径集成、断连重连、边界用例）

## 背景

M3 结束时的现状盘点：

- **请求级重试已实现**（`client.send`：429/5xx/连接错误 → 指数退避 + `Retry-After`，
  耗尽后按状态码/传输错误映射分层异常），但只测了 5xx 路径和异常包装，
  429/`Retry-After` 语义、耗尽→具体异常子类映射、async 侧镜像均无测试。
- **SSE 事件流无自动重连**：`stream_events()` 开一条连接，断流即终止。
  M4 的"断连重连"用户拍板为"先加功能再全测"。

## 目标

1. `EventStream`/`SyncEventStream` 支持连接断开后自动重连（指数退避，
   预算 = `max_reconnect_attempts`，收到任意行即重置预算），对外的
   `iter_events()`/`aiter_events()` 在内建重连上持续产出事件；
2. 请求级重试行为全部有测试锁定（sync + async：429、`Retry-After`、
   5xx 退避、连接错误、超时、耗尽→具体异常子类映射）；
3. 新增可选真实 server 集成测试（无服务自动 skip）。

## 任务

- [x] `sse.py`：`EventStream`/`SyncEventStream` 自动重连
      （`max_reconnect_attempts` 默认 `DEFAULT_STREAM_RECONNECT_ATTEMPTS=5`，
      退避 0.5s→8s cap；**仅传输错误触发重连**，干净 EOF 结束迭代
      （冲刷末尾残留半帧）；丢弃在途半帧不拼接下一连接；
      耗尽预算后抛 `make_transport_error` 包装异常；
      保留 `iter_lines`/`aiter_lines` 直通做向后兼容）
- [x] `constants.py`：`DEFAULT_STREAM_RECONNECT_ATTEMPTS`
- [x] `resources/server.py` + `examples/stream_events.py`：文档/用法切到
      `stream.aiter_events()`/`stream.iter_events()` 新姿势
- [x] 测试：`tests/test_stream_reconnect.py`（脚本化假传输驱动 sync+async，21 例：
      中途断开重连、预算 0/耗尽/重置、EOF 语义、半帧丢弃、
      连接/超时错误包装、`__enter__`/`__aenter__` 失败、退出必关连接、
      退避序列 spy）
- [x] 测试：`tests/test_retries.py`（18 例：退避表/cap/`Retry-After` 数值与非数值、
      429+5xx 重试成功与耗尽→`OpenCodeRateLimitError`/`OpenCodeServerError`、
      预算 0、连接/超时错误重试，async 全镜像）
- [x] 测试：`tests/test_live_server.py`（根 `conftest.py` 注册 `--live-url`/
      `--live-password`，无服务自动 skip；health、session CRUD、
      活事件流看到 `session.created`、真实传输上注入 503 验证重试）
- [x] 迁移 `test_client.py`/`test_sync_client.py` 端到端流测试到 `aiter_events()`/
      `iter_events()`（示例用法同步）
- [x] `make check` 全绿（107 passed, 5 skipped 离线）+ 真实服务 live 套件全过
- [x] 归档：BOARD/ROADMAP/AGENTS.md 同步

## 设计决策

- **仅传输错误重连，干净 EOF 终止**：`/event` 是长连接，但服务端 *故意* 关闭
  body（干净 EOF）是合法结束信号；把 EOF 也当断流会在"服务端发完就关"的
  场景下无限重连（验证过会跑飞）。故：传输错误（`httpx.HTTPError`）→
  预算内指数退避重连；干净 EOF → 冲刷残留半帧后结束迭代。
- **断流 ≠ 终止**：预算耗尽前指数退避重连（0.5s…8s cap）；**收到任意行
  即重置预算**，健康流可无限重连。耗尽后抛 `make_transport_error` 包装的
  `OpenCodeTimeoutError`/`OpenCodeServerConnectionError`（保留 `__cause__`）。
- **丢弃在途半帧**：连接断开时未闭合的 data 帧直接丢弃，不用下一连接的行
  拼接——opencode 不实现 `Last-Event-ID` 重放，跨连接拼接会产事件序列外的
  幽灵事件（拼接内容也无法被服务端重放保证）。
- **消费 API 上移到流上**：`stream.iter_events()`/`aiter_events()` 内建
  解码 + 重连，替代旧 `SSEDecoder().iter_events(stream.iter_lines())` 手工粘合。
  旧的 `iter_lines`/`aiter_lines` 直通保留（不重连，文档标注 advanced），
  `SSEDecoder` 公开不变——对外是新增 API，无破坏性。
- **测试缝**：respx 在路由解析时即消费 side_effect（验证过：自定义 content
  迭代器中途抛错无法表达 mid-stream drop），故重连测试用脚本化假传输
  （`send(request, *, stream=True)` + 响应 `iter_lines/aiter_lines/close/aclose`），
  `EventStream` 构造参数类型即 `httpx.Client`——假传输直接 duck-type 顶替，
  pyright/mypy strict 下仅需显式 `cast`。退避时长走模块级 `_reconnect_delay`
  单点，autouse fixture 置 0，退避序列用 spy 断言。
- **live 测试默认离线**：`pytest_addoption` 必须放在根 `conftest.py`
  （子目录 conftest 的选项钩子不生效）；无 `--live-url` 时整模块
  `pytest.skip`，默认 `make check` 不触网、CI 可复现。

## 完成记录

- 2026-08-22：实现 + 测试全部落地。
- 离线：`make check` 绿，**107 passed / 5 skipped**（5 个 live 用例跳过）。
- 真实服务（`--live-url http://127.0.0.1:20001`，opencode v1.18.18）：
  `tests/test_live_server.py` **5 passed**——含活事件流经重连层看到
  `session.created`、真实传输注入 503 后重试成功。
- 语义修正记录：初版把"干净 EOF 也重连"实现后在空流脚本下无限重连，
  且跨连接半帧拼接与服务端不重放矛盾，遂定为上文 Option A 语义。
- 勘误（2026-08-22）：上文「选项钩子必须放根 conftest.py」结论过严，已实测修正
  并删除根 conftest（选项注册并入 tests/conftest.py + pyproject `pythonpath=["."]`），
  详见 ROADMAP 同名记录。

# IT-009 — with_raw_response：原始 httpx.Response 视图

日期：2026-08-23
宏观：M5 之后的功能补全（原占号，M4/M5 完成后顺延为此号）

## 背景

官方 SDK 的每个资源方法都有一个 `.with_raw_response` 前缀变体，返回**原始
响应对象**而非解析后的模型，用途：读响应头、拿原始 body、做自定义解析、
调试。本库 `_send` 本就返回 `httpx.Response`（解析发生在方法末行的
`validate_response`），所以 raw 变体 = 正常方法去掉最后一行解析、直接返回
`_send` 的结果。

## 目标

1. 4 个资源（sessions/server/vcs/mcp）的 sync + async 双类都提供
   `with_raw_response` 代理，方法面与资源方法**一一对应**、返回
   `httpx.Response`；
2. 语义对齐官方：非 2xx **仍按分层异常抛**、仍走重试（复用 `_send`），
   仅成功路径返回原始响应；
3. 测试锁定：raw 视图与正常视图的**方法面镜像一致**（防止双类/双视图漂移），
   + 行为测试（headers/status/原始 body 透传、4xx 仍抛）；
4. 文档（README EN/ZH + AGENTS.md 约定）+ 一个 05 示例。

## 范围

- **纳入**：`with_raw_response` 代理前缀（官方同款形态，用户拍板）；
  server 侧 12 个方法（**不含 `stream_events`**——它返回 EventStream，
  非 `_send` 路径，raw 语义不适用）。
- **不纳入**：`with_streaming_response`（流式，另说）；`share` 实跑 /
  MCP connect-auth 流（另两个占号）；版本号/再发布。

## 任务

- [x] `resources/sessions.py`：`SessionsResourceWithRawResponse` +
      `AsyncSessionsResourceWithRawResponse`（15 方法）+ 双类
      `with_raw_response` 属性
- [x] `resources/server.py`：`ServerResourceWithRawResponse` +
      `AsyncServerResourceWithRawResponse`（12 方法，不含 stream_events）
      + 属性
- [x] `resources/vcs.py`：双 raw 类（5 方法）+ 属性
- [x] `resources/mcp.py`：双 raw 类（2 方法）+ 属性
- [x] `tests/test_raw_response.py`：方法面镜像一致性（4 域 × sync/async ×
      raw 三向对齐）+ 行为（原始 body/headers/status、4xx 仍抛）
- [x] `examples/05_advanced_patterns/raw_response.py` + README
- [x] `README.md` / `README-CN.md` / `AGENTS.md` 约定
- [x] `make check` 绿 + 提交 + BOARD/ROADMAP 归档

## 完成记录

2026-08-23 完成：

- 4 个资源域 × sync/async 共 8 个 raw 代理类，方法面与正常视图一一对应
  （34 方法镜像；server 域按设计排除 `stream_events`）；
- 实现方式：raw 类复用同一 `_send`（重试/错误映射零重复），只去掉末尾
  `validate_response` 解析行，直接返回 `httpx.Response`；
- `resources/__init__.py` 导出 8 个 raw 类；对外 API 仅经
  `<resource>.with_raw_response` 属性触达（测试亦只用包根入口）；
- `tests/test_raw_response.py` 21 项：镜像一致性锁（方法名 + 参数顺序
  三向对齐）+ 行为（raw 返回 `httpx.Response`、wire 与正常视图逐字节一致、
  4xx/5xx 仍抛分层异常、重试共享、`prompt_async` raw 变体返回响应而正常
  视图返回 `None`、server 无 `stream_events` raw 变体）；
- 示例 `05_advanced_patterns/raw_response.py`（解析 vs 裸响应对比 +
  404 仍抛演示）+ 各 README/AGENTS.md 同步；
- `make check` 全绿（142 passed / 5 skipped）。

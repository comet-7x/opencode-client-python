# 03_advanced_patterns — 进阶模式

## 本文件夹讲什么

真实应用里比"发一句话"多出的那些工程问题。四个脚本各演示一类：

| 脚本 | 模式 | 关键点 |
|---|---|---|
| `client_reuse.py` | **复用 Client + 超时配置** | 一个连接池跑多次调用 vs 每次都新建；`timeout=`/`max_retries=` 参数；`with_options()` 派生新配置而不动原 client |
| `error_handling.py` | **异常捕获与降级** | `OpenCodeApiError` 的分层族谱（404/429/5xx 各有子类）；怎么捕获后降级而不是崩溃；`status_code`/`payload` 怎么用 |
| `stream_events.py` | **事件流 + 流式增量** | `prompt_async`（fire-and-forget）+ `stream_events()` 的 `aiter_events()`；断流自动重连 |
| `interact_moving_session.py` | **权限/问答交互循环** | 轮询 `list_permissions`/`list_questions` 并应答，让一个会要权限的 turn 走完到 `session.idle` |

## 适用场景

- 写服务/批处理任务，需要控制**超时**与**重试**（`client_reuse.py`）；
- 面向用户的程序，需要**优雅降级**而不是把异常堆栈糊用户脸上（`error_handling.py`）；
- 需要**实时**看到模型输出/工具调用，而不是干等 turn 结束（`stream_events.py`）；
- 自动化要**无人值守**地推进 turn：自动批准/拒绝权限与回答追问
  （`interact_moving_session.py`）。

## 前置条件

- `make install` 后位于本仓库环境；运行中的 `opencode serve`（默认 4096）；
- `stream_events.py` / `interact_moving_session.py` 会真实发 prompt，
  需要默认 provider/model 可用（同 00_quickstart）；
- `interact_moving_session.py` 默认**自动拒绝**权限（安全侧），加 `--allow`
  才会自动批准。

## 运行

```sh
uv run python -m examples.03_advanced_patterns.client_reuse
uv run python -m examples.03_advanced_patterns.error_handling            # 故意 404，看降级
uv run python -m examples.03_advanced_patterns.stream_events
uv run python -m examples.03_advanced_patterns.interact_moving_session --allow
```

均支持 `--url`，`--help` 查看全部参数。

## 代码里有什么

- **为什么复用 client**：`AsyncOpenCodeClient` 内部是一个 httpx 连接池；
  反复 `create()` 会反复建池、反复握手。正确姿势是建一次、`async with` 到
  作用域结束，或在长生命周期进程里持有一个 client。
- **`with_options()`**：返回一个**新 client**，只覆盖传入的项（未传的保持
  原值），基于 `NOT_GIVEN` 哨兵实现精确覆盖——适合"同一服务器、不同超时"
  的场景，而不是复制粘贴构造函数。
- **异常族谱**：`OpenCodeError` ← `OpenCodeApiError`（带 `status_code`/`payload`）
  ← 各状态码子类；`OpenCodeTransportError`（带 `OpenCodeTimeoutError`/
  `OpenCodeServerConnectionError`）是"根本没拿到 HTTP 响应"的另一族。
  捕获顺序：**先具体子类，后基类**。

# events — 事件流（SSE）

## 本文件夹讲什么

`opencode serve` 在 `/event` 上广播一条 SSE 事件流：turn 的增量输出、
工具调用、会话状态迁移都在这里。本组脚本演示 `client.server.stream_events()`
的两种消费姿势：

| 脚本 | 模式 | 关键点 |
|---|---|---|
| `stream_events.py` | **裸流迭代** | `prompt_async`（fire-and-forget）+ `aiter_events()`；按 `partID` 区分**思考/正文/工具调用**三类事件（delta 的 `field` 对思考和正文都是 `text`）；断流自动重连 |
| `event_router.py` | **事件 Router + 类型化热事件** | `stream.route(session_id)` 收窄广播 + `bus.on(type, handler)` 三行订阅替代 if/elif 监听循环；热事件自动类型化（`event.part: Part`，未知类型回落基类 `Event`）；`run(until="session.idle", timeout=)` 统一收口 |

## 适用场景

- 需要**实时**看到模型输出/工具调用，而不是干等 turn 结束（`stream_events.py`）；
- 实时监听但不想手写 if/elif 分支、不想从 `properties` 字典挖字段——
  按类型订阅 + 类型化 payload（`event_router.py`）。

## 前置条件

- `make install` 后位于本仓库环境；运行中的 `opencode serve`（默认 4096）；
- 会真实发 prompt，需要默认 provider/model 可用（同 quickstart）。

## 运行

```sh
uv run python -m examples.events.stream_events
uv run python -m examples.events.event_router
```

均支持 `--url` 与 `--provider/--model`，`--help` 查看全部参数。

# IT-010 — 事件 Router + 类型化热事件

日期：2026-08-23
宏观：M5 之后的功能补全（流式消费体验；引用设计的前置地基）

## 背景

SSE 事件自 v1 起就是 `Event(type: str, properties: dict)` 一刀切——刻意不建模
具体事件，但切过头了：REST 拉取路径（`prompt()`/`list_messages()` 经
`_wire.py` TypeAdapter）完整类型化同一批实体（Part/Message/PermissionRequest），
而 SSE 路径全是挖字典 + Any 蔓延。`field=="text"` 被误当正文判据的事故（见
`temp/docs/citation-tools-design.md`）就是代价。讨论收敛为两层：**Catalog**
（契约：事件类型 → 类型化 payload，两路径共享）+ **Router**（消费：按类型
订阅、顺序分发、统一终止）。设计定稿见 `temp/docs/event-router-design.md`
（含实施中的事实修正 §12）。

## 目标

1. `EventType` 开放集枚举（`StrEnum`，57 成员，种子 = 服务端 `/doc` 导出的
   v1 事件面）——`on()` 接受 `EventType | str`，未知类型永不 break；
2. 6 个热事件类型化（`message.part.updated`/`message.part.delta`/
   `message.updated`/`session.idle`/`permission.asked`/`question.asked`），
   payload 复用**现有**模型（Part/PermissionRequest/QuestionRequest），
   降级兜底：payload 解析失败退回基类 `Event`，流永不断；
3. `AsyncEventRouter`/`EventRouter`（`stream.route(session_id)`）：单读者
   顺序分发、多订阅、`until`/`timeout`/错误传播统一收口、session 过滤；
4. 加法式：裸流 `aiter_events()`/`iter_events()` 原样保留。

## 范围

- **纳入**：`models/event.py` 扩（枚举 + `_TypedEvent` hoist 基类 + 6 子类 +
  `EVENT_CATALOG` + `typed_event()`）、`sse.py` 解码钩子 + `route()`、
  `router.py` 新文件（包根）、导出、32 项测试；
- **不纳入**：全量事件类型化（deferred，触发式排期，见设计 §9）、
  `bus.stop()` 主动终止、handler 错误隔离模式、引用渲染本身（另迭代）。

## 任务

- [x] 核对权威事件面（`/doc` 导出 57 个 v1 事件 + 6 热事件 payload）
- [x] `models/event.py`：`EventType`(StrEnum) + `_TypedEvent`(properties
      提升) + 6 子类 + `EVENT_CATALOG` + `typed_event()`（升级/降级）
- [x] `sse.py`：`SSEDecoder._take_event` 走 `typed_event`；双流 `route()`
- [x] `router.py`：`AsyncEventRouter`/`EventRouter`（顺序分发/session 过滤/
      until/timeout/错误传播；sync 侧拒绝 coroutine handler）
- [x] `models/__init__.py` + `__init__.py` 注册与导出
- [x] `tests/test_event_router.py` 32 项（升级/直通/降级/顺序/多订阅/
      until/超时/错误传播/session 过滤/route 接线）
- [x] 设计稿事实修正（94→57、permission.updated→permission.asked、
      权威源改 `/doc`）+ BOARD/ROADMAP 归档

## 完成记录

2026-08-23 完成：

- **契约层**（`models/event.py`）：`EventType` 57 成员（`StrEnum`，
  `EventType.SESSION_IDLE == "session.idle"`）；`_TypedEvent` 的 `before`
  校验器把 `properties` 提升到顶层（payload 键覆盖冲突键，`permission.asked`
  的 request id 落基类 `Event.id`）；6 热事件子类——`MessagePartUpdatedEvent`
  （`part: Part` 判别联合）、`MessagePartDeltaEvent`（扁平 5 字段 + 独立
  `MessagePartDeltaPayload`，docstring 写死"field 对 reasoning/text 同为
  text"的协议模糊）、`MessageUpdatedEvent`（`info: Any` 按需 validate）、
  `SessionIdleEvent`、`PermissionAskedEvent`/`QuestionAskedEvent`（扁平字段 +
  `.request` 属性）；`typed_event()` 升级未知类型直通、解析失败降级基类；
- **消费层**（`router.py`）：`AsyncEventRouter`（async，handler 可 sync/async）
  与 `EventRouter`（拒 coroutine handler）；`stream.route(session_id)`
  进 `sse.py`；终止四路（until/超时/错误/干净 EOF）不留悬挂迭代器；
- **关键坑**：`Part` 等必须**运行时**导入（`TYPE_CHECKING` 下 pydantic 延迟
  注解解析会 `model_rebuild` 报错）；pyright strict 对 `Callable[[Event], Any]`
  的 lambda 参数收窄、StrEnum 字面量比较收窄、`dict` spread 的 partial-unknown
  返回各有一处处理（见测试与 `cast`）；
- **权威源修正**：枚举与 Catalog 以 `/doc` 导出的 OpenAPI 为准
  （`packages/schema/src/v1` 只定义 16 个、生成 SDK 有漂移，见设计 §12）；
- 测试 32 项 + 既有全量：**`make check` 全绿（174 passed / 5 skipped）**。

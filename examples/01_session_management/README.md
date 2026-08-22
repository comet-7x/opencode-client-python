# 01_session_management — 会话增删改查

## 本文件夹讲什么

opencode 的核心抽象是 **session（会话）**：一段与 agent 的对话容器，
有 id、标题、所属目录、使用的模型/agent、累计 token 与费用。本组脚本
把 `client.sessions.*` 最常用的四个动词跑一遍：

| 脚本 | 演示的调用 | 看什么 |
|---|---|---|
| `create_session.py` | `sessions.create(...)` | 怎么传 title/agent/model/metadata；创建后返回的 `Session` 有哪些字段 |
| `list_sessions.py` | `sessions.list_sessions(...)` | 列表的过滤参数（limit/search/...）、结果按什么排序 |
| `delete_session.py` | `sessions.delete(id)` | 返回值含义、删除不存在的会话会怎样 |
| `list_messages.py` | `sessions.list_messages(id)` | 会话内的消息历史：`MessageWithParts` 的联合类型与 part 遍历 |

## 适用场景

- 需要程序化管理多个并发/历史会话（建一批、列出来、清理旧的）；
- 想弄清 `Session` 返回对象里每个字段是什么、wire 上长什么样；
- 想学会把服务端返回的 camelCase（`sessionID`、`providerID`）自动映射到
  Python 侧的 snake_case（`session_id`、`provider_id`）——库已做好，这里直接读属性即可。

## 前置条件

- `make install` 后位于本仓库环境；
- 运行中的 `opencode serve`（默认 `http://127.0.0.1:4096`）；
- `list_messages.py` 需要服务器上至少有一个对话过的会话，
  可先跑一遍 `00_quickstart` 或 `--prompt` 参数现造一条。

## 运行

```sh
uv run python -m examples.01_session_management.create_session --title 我的会话
uv run python -m examples.01_session_management.list_sessions --limit 5
uv run python -m examples.01_session_management.delete_session --session ses_XXXX
uv run python -m examples.01_session_management.list_messages --session ses_XXXX
```

均支持 `--url` 指定服务地址，`--help` 查看各脚本全部参数。

## 代码里有什么

- 每个脚本都是同一个骨架：`async with AsyncOpenCodeClient(url) as client:`
  里调用，`OpenCodeApiError` 兜底退出；
- `Session` 字段一览见 `create_session.py` 的打印部分（id/slug/directory/
  title/model/tokens/time…）；
- `list_sessions` 返回**最新在前**；
- 删除返回 `bool`（True = 服务端确认已删）；
- 消息是联合类型：`msg.info` 可能是 user 也可能是 assistant 消息，用
  `isinstance` 收窄后再取各自的字段（如 `tokens` 只在 assistant 上）。

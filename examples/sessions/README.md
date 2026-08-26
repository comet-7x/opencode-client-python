# sessions — 会话管理（增删改查 + 生命周期 + 权限/问答交互）

## 本文件夹讲什么

opencode 的核心抽象是 **session（会话）**：一段与 agent 的对话容器，
有 id、标题、所属目录、使用的模型/agent、累计 token 与费用。本组脚本
把 `client.sessions.*` 的常用动词跑一遍：

| 脚本 | 演示的调用 | 看什么 |
|---|---|---|
| `create_session.py` | `sessions.create(...)` | 怎么传 title/agent/model/metadata；创建后返回的 `Session` 有哪些字段 |
| `list_sessions.py` | `sessions.list_sessions(...)` | 列表的过滤参数（limit/search/...）、结果按什么排序 |
| `delete_session.py` | `sessions.delete(id)` | 返回值含义、删除不存在的会话会怎样 |
| `list_messages.py` | `sessions.list_messages(id)` | 会话内的消息历史：`MessageWithParts` 的联合类型与 part 遍历 |
| `session_lifecycle.py` | `sessions.update/get/fork/abort/share/unshare/summarize/delete_message` | 建删列查之外的全部会话动词，一次在一个临时会话上走完 |
| `session_state_history.py` | `sessions.status/children/list_todos/diff/revert/unrevert` | 会话的运行状态（idle/busy/retry）、子会话、todo 列表、文件改动与历史回退/恢复 |
| `interact_moving_session.py` | `server.list_permissions/list_questions` + 回复端点 | 权限/问答**交互循环**：轮询 pending 请求并应答，让一个会要权限的 turn 走完到 `session.idle`；`--respond` 额外演示 `sessions.respond_permission` 与 `server.reject_question` |
| `prompt_options.py` | `sessions.prompt(...)` 的完整 prompt body | 一次 prompt 里点亮全部选项：model / system / tools（disable/enable）/ agent / no_reply |
| `structured_parts.py` | `sessions.prompt(..., parts=[...])` | 结构化输入：text part + file part（url + mime）+ subtask part（子任务）混排发送 |

## 适用场景

- 需要程序化管理多个并发/历史会话（建一批、列出来、清理旧的）；
- 想弄清 `Session` 返回对象里每个字段是什么、wire 上长什么样；
- 想学会把服务端返回的 camelCase（`sessionID`、`providerID`）自动映射到
  Python 侧的 snake_case（`session_id`、`provider_id`）——库已做好，这里直接读属性即可。

## 前置条件

- `make install` 后位于本仓库环境；
- 运行中的 `opencode serve`（默认 `http://127.0.0.1:4096`）；
- `list_messages.py` 需要服务器上至少有一个对话过的会话，
  可先跑一遍 `quickstart` 或 `--prompt` 参数现造一条。

## 运行

```sh
uv run python -m examples.sessions.create_session --title 我的会话
uv run python -m examples.sessions.list_sessions --limit 5
uv run python -m examples.sessions.delete_session --session ses_XXXX
uv run python -m examples.sessions.list_messages --session ses_XXXX
uv run python -m examples.sessions.session_lifecycle
uv run python -m examples.sessions.session_state_history
uv run python -m examples.sessions.interact_moving_session --allow
uv run python -m examples.sessions.interact_moving_session --respond   # 额外演示 respond_permission / reject_question
uv run python -m examples.sessions.prompt_options
uv run python -m examples.sessions.prompt_options --agent build --disable-tool write
uv run python -m examples.sessions.structured_parts
uv run python -m examples.sessions.structured_parts --file-url file:///tmp/a.txt --mime text/plain
```

均支持 `--url` 指定服务地址，`--help` 查看各脚本全部参数。
`session_lifecycle.py` 会发一条 prompt（summarize/delete_message 需要消息
存在），需要默认 provider/model 可用（同 quickstart）。
`interact_moving_session.py` 默认**自动拒绝**权限（安全侧），加 `--allow`
才会自动批准。

## 代码里有什么

- 每个脚本都是同一个骨架：`async with AsyncOpenCodeClient(url) as client:`
  里调用，`OpenCodeApiError` 兜底退出；
- `Session` 字段一览见 `create_session.py` 的打印部分（id/slug/directory/
  title/model/tokens/time…）；
- `list_sessions` 返回**最新在前**；
- 删除返回 `bool`（True = 服务端确认已删）；
- 消息是联合类型：`msg.info` 可能是 user 也可能是 assistant 消息，用
  `isinstance` 收窄后再取各自的字段（如 `tokens` 只在 assistant 上）。

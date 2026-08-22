# 00_quickstart — 最简入门

## 本文件夹讲什么

用**最少的代码**完成 `opencode-client` 的标准生命周期：

1. 连上运行中的 `opencode serve`（健康检查确认能通）；
2. 创建一个会话（session）；
3. 往会话里发一句 prompt（提问）；
4. 打印模型的回答；
5. 删除会话（清理）。

`quickstart.py` 是这个流程的完整可运行版，每一行都有注释。
读它只需要认识 3 个东西：`AsyncOpenCodeClient`、`client.sessions.*`、
`await`。

## 适用场景

- 第一次接触本库，想确认环境、依赖、服务三者都正常；
- 想知道"问一句话、拿回答"的最短写法；
- 想看看 `directory` 作用域参数怎么写：`quickstart.py` 的 `main()` 里
  `create(title=..., directory=...)` 就是**不带模型/agent 等完整 body、
  只带作用域参数**的最小建会话写法。

## 前置条件

- 已 `make install`（或 `uv sync`），当前处于本仓库环境；
- 有一个运行中的服务（默认 `http://127.0.0.1:4096`）：

  ```sh
  opencode serve --port 4096
  ```

## 运行

```sh
# 方式一（推荐，从仓库根目录执行）
uv run python -m examples.00_quickstart.quickstart

# 方式二（直接文件运行，效果相同）
uv run python examples/00_quickstart/quickstart.py

# 服务不在 4096 时
uv run python -m examples.00_quickstart.quickstart --url http://127.0.0.1:20001

# 看全部参数
uv run python -m examples.00_quickstart.quickstart --help
```

期望输出（大致）：

```
health: opencode v1.x.x
created session: ses_XXXX
assistant: pong
deleted session
```

## 代码里有什么

| 概念 | 在哪行 | 说明 |
|---|---|---|
| `async with AsyncOpenCodeClient(...)` | main 开头 | 客户端即资源；`with` 结束自动关连接 |
| `await client.server.health()` | 第 1 步 | 最小连通性探针，拿到版本号 |
| `await client.sessions.create(title=...)` | 第 2 步 | 建会话，`body` 可选 |
| `await client.sessions.prompt(session_id, "…")` | 第 3 步 | 同步式提问：等到回答返回才继续 |
| `reply.parts` 里的 `TextPart` | 第 4 步 | 回答被拆成若干 part，文本在 `TextPart.text` |
| `except OpenCodeApiError` | cli() | 服务端返回非 2xx 时抛出的分层异常 |
| `client.sessions.create(directory=...)` | main() | 不拼完整 body、只带作用域参数的最小调用 |

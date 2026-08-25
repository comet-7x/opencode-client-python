# client — 客户端配置与错误处理

## 本文件夹讲什么

`AsyncOpenCodeClient` 自身的工程面：连接怎么建、出错怎么接、响应怎么
绕过解析。三个脚本各演示一类：

| 脚本 | 模式 | 关键点 |
|---|---|---|
| `client_reuse.py` | **复用 Client + 超时配置** | 一个连接池跑多次调用 vs 每次都新建；`timeout=`/`max_retries=` 参数；`with_options()` 派生新配置而不动原 client |
| `error_handling.py` | **异常捕获与降级** | `OpenCodeApiError` 的分层族谱（404/429/5xx 各有子类）；怎么捕获后降级而不是崩溃；`status_code`/`payload` 怎么用 |
| `raw_response.py` | **裸响应视图** | `<resource>.with_raw_response.<method>(...)` 返回未解析的 `httpx.Response`（头/状态码/原始 body）；重试与错误映射与正常视图一致；`stream_events` 无 raw 变体 |

## 适用场景

- 写服务/批处理任务，需要控制**超时**与**重试**（`client_reuse.py`）；
- 面向用户的程序，需要**优雅降级**而不是把异常堆栈糊用户脸上（`error_handling.py`）；
- 需要看到**响应头 / 原始 body / 精确状态码**（限流探测、透传、调试），
  而不是被模型解析后的对象（`raw_response.py`）。

## 前置条件

- `make install` 后位于本仓库环境；运行中的 `opencode serve`（默认 4096）。

## 运行

```sh
uv run python -m examples.client.client_reuse
uv run python -m examples.client.error_handling            # 故意 404，看降级
uv run python -m examples.client.raw_response
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

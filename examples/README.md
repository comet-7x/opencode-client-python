# examples — opencode-client 教学示例总入口

## 这是什么

一组**可直接运行**的 Python 脚本，按场景分文件夹组织，演示如何用
`opencode-client` 连接并驱动 `opencode serve` 服务。每个文件夹自带
`README.md`（解释本组脚本讲什么、适用场景、前置条件），脚本内含逐行注释。

## 目录结构

| 文件夹 | 主题 | 内容 |
|---|---|---|
| `00_quickstart/` | 最简入门 | 3 行代码连上服务并完成一问一答（含 `directory` 简写用法） |
| `01_session_management/` | 会话管理 | 创建（各种参数）/ 列表 / 删除 / 历史浏览 / **生命周期全动词**（update·fork·abort·share·summarize·delete_message） |
| `02_discovery_config/` | 服务发现与配置 | health / config / providers / agents / commands / skills 一次摸清新服务 |
| `03_vcs/` | 版本控制 | info / status / diff / diff_raw / apply（看改动、落盘 diff、打补丁） |
| `04_mcp/` | MCP 服务器 | status（判别联合收窄）/ add（local·remote 两种 config） |
| `05_advanced_patterns/` | 进阶模式 | 复用客户端、超时配置、异常捕获降级、事件流、权限/问答交互循环、`with_raw_response` 裸响应 |

编号前缀决定阅读顺序，对应 `client` 上的四个资源域
（`sessions` / `server` / `vcs` / `mcp`）由浅到深；后续可按需新增 `99_*` 等文件夹。

## 环境与依赖

- Python **>= 3.11**；本仓库用 [uv](https://docs.astral.sh/uv/) 管理环境。
- 首次准备（在仓库根目录）：

  ```sh
  make install          # = uv sync，装好依赖（含编辑安装 opencode-client 本身）
  ```

  > 示例脚本依赖 `opencode-client` 包本身，因此必须在**本仓库的环境**里跑；
  > 不要在全局 Python 里裸跑（装不到该包）。

## 前置条件：先起一个 opencode 服务

所有示例都需要一个运行中的 `opencode serve`（默认本地 4096 端口）：

```sh
opencode serve --port 4096
```

服务起好后，任一脚本可用 `curl` 自查：

```sh
curl -s http://127.0.0.1:4096/global/health     # 期望返回 {"healthy": true, ...}
```

## 运行方式（两种等价）

脚本目录名以数字开头（`00_quickstart` 等），是合法的包名但不是 Python
标识符，因此**推荐用 `-m` 方式**（必须从仓库根目录执行）：

```sh
# 方式一（推荐）：模块方式
uv run python -m examples.00_quickstart.quickstart

# 方式二：直接文件方式（同样可用）
uv run python examples/00_quickstart/quickstart.py
```

多数脚本支持 `--url` 指定服务地址，例如服务跑在 20001 端口：

```sh
uv run python -m examples.00_quickstart.quickstart --url http://127.0.0.1:20001
```

## 通用约定

- 所有网络请求均为 `async/await`（`AsyncOpenCodeClient`）；
- 脚本结束前会清理自己创建的会话，不污染服务端；
- 示例中的模型/Provider 若省略，使用服务端默认；
- 每个脚本顶部 docstring 都写明了自己的运行命令，`--help` 可见全部参数。

## 自动验证

`examples/test_examples.py` 用 **respx** 离线 mock 掉 HTTP 层，以
`main()` 入口驱动各示例做冒烟测试，因此：

```sh
uv run pytest examples/     # 无需真实 opencode 服务，CI 可复现
```

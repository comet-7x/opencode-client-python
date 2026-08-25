# IT-016 — 覆盖率工具链 + live 集成套件扩域

日期：2026-08-24
宏观：质量基建；对用户提供的真实服务（http://127.0.0.1:37217，opencode **1.18.22**）做首次全面真实验证

## 背景

两个问题驱动：① 代码从未连真实服务做过全面测试（live 套件停留在 IT-008，
只测 sessions/server.health/events）；② 覆盖率从未量化（无 pytest-cov）。

## 任务

- [x] dev 组加 `pytest-cov`；pyproject 加 `[tool.coverage.*]` 配置
- [x] Makefile：`make coverage` 目标；`make test` 加 `--cov-fail-under=90` 门禁
- [x] 跑基线覆盖率报告，分模块数字记入本文件
- [x] `test_live_server.py` 新增 `TestLiveReadOnlyDomains`（6 用例）：
      server(paths/lsp)、projects(list/current)、files(浏览+搜索，用
      tmp_path 造工作区)、mcp/vcs/formatter、async 孪生镜像
- [x] 对真实服务跑通全部 11 个 live 用例（5 旧 + 6 新）
- [x] `make check` 全绿 + 归档

## 结果

### 覆盖率基线（262 passed 离线套件）

| 模块 | 覆盖 | 备注 |
|---|---:|---|
| models/* | 全部 ≥99%（多数 100%） | |
| client.py | 96% | |
| router.py / sse.py | 97% / 92% | |
| resources/_wire.py | 93% | 缺口集中在错误分支 |
| resources/projects.py | 75% | raw 视图未逐一测（镜像锁只验签名） |
| resources/sessions.py | 81% | 同上，raw 变体多 |
| **TOTAL** | **91.20%** | 门禁阈值定 90 |

门禁生效：`make test --cov-fail-under=90`，跌破即红。

### live 套件（--live-url http://127.0.0.1:37217）

11/11 通过（5 旧 + 6 新），**零模型漂移**——我们基于 v1.18.21 OpenAPI
构建的模型在 v1.18.22 的真实响应上全部解析成功。覆盖面：
health、paths、lsp、projects、files（list/read/status/search_text/
search_files）、mcp status、vcs info/status、formatter、async 孪生。

### 踩坑

- `search_files(query, dirs, type, limit, ...)` 的可选参数紧跟 query，
  测试里不能像其他方法那样用 `**{"directory": ...}` 展开——mypy 会把
  第二个位置参数判成 dirs(bool)。显式传 `directory=workdir`。
- files 搜索类 live 测试用 `tmp_path_factory.mktemp` 自造一次性工作区 +
  已知内容文件，避免依赖服务端 worktree 里恰好有什么文件。

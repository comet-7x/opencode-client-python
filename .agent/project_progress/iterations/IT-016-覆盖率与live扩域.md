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

## 追加（同日）：examples 覆盖率提升

用户要求提高 examples 覆盖率。基线：examples 平均 **73%**（最低
mcp_servers 43%）。措施与结果：

- **修真 bug**：`mcp_servers.py` 的 `--oauth` 块放在 `if name is None:
  return` 之后——单独传 `--oauth` 永远走不到（冒烟没断言输出所以漏检）。
  改为 `if name is not None:` 包住注册流，oauth 块无条件可达。
- **interact_moving_session 竞态修复**：`while not idle.is_set()` 会让快速
  turn 的 idle 抢在首轮轮询前就绪 → pending 交互永远不应答。改为先答一轮
  再检查 idle。
- **fixture 增强**：/mcp 状态图加 failed/disabled/needs_auth（覆盖判联合
  收窄分支）；消息 parts 加 tool/reasoning/step-finish；文件内容带 diff；
  参数级特例路由（二进制读取 / 读 404 / 空目录 / 搜索空命中 / 空项目域）。
- **新用例**：mcp add 流、OAuth 被拒分支、删不存在会话（DELETE 404 特例
  路由）、list_messages 自动取最新、vcs --save/--apply、搜索空命中、
  无参数退出码、browse_files 二进制/空目录/404、explore_projects 空域。
- **新增 `examples/test_cli_errors.py`**：19 个脚本 × 真实 socket 连接拒绝
  （端口 9），批量覆盖各 cli() 的 transport 兜底分支（exit 2）。必须独立
  成文件——test_examples 的 respx autouse fixture 会拦截一切请求，坏 URL
  到不了网络层。注意 session 级 fixture 不能注入 function 级 monkeypatch。

结果：examples **73% → 91%**；全套 **291 passed**；src 门禁保持 90%。
`make coverage` 现同时报告 src + examples。

### 新踩坑

- **respx 匹配顺序是"先注册先匹配"**（与直觉相反）：参数特例路由必须注册
  在同 path 的通用路由之前，否则永不命中。

## 追加 2（同日）：示例对 API 面的全覆盖

用户澄清需求：examples 的"覆盖率"指**示例对源码能力面的场景覆盖**。
用脚本对 7 个资源域 69 个公开方法做了 `examples/` 引用审计，基线 61/69，
缺口：sessions.command/init/shell/update_part/delete_part、
mcp.remove_oauth、projects.directories/git_init/update。

补齐方式（全部并入既有脚本，不开新目录）：

- **session_lifecycle.py**：prompt 变体三兄弟（command/shell/init——
  init 需 provider/model，缺省时跳过）+ part 编辑（update_part 用完整
  响应侧 TextPart 构造，delete_part 收尾）
- **mcp_servers.py**：--oauth 流末尾补 remove_oauth
- **explore_projects.py**：常驻展示 current 项目的 directories；
  新增 --git-init / --rename 两个显式写操作开关

结果：**69/69 全覆盖**；冒烟 +3 用例（part 编辑路由、PATCH project、
DELETE mcp auth）；`make check` 292 passed 全绿。

### 踩坑

- update_part 的 body 是**响应侧 Part 模型**（需三元组 id），不是请求侧
  Input 模型——pyright 直接拦下了 TextPartInput 误用，类型系统帮了大忙。
- 多轮 python 脚本改示例时 replace 锚点被 ruff format 重排打断，出现两次
  "替换成功但 argparse/main 签名没同步"的低级错——**多步文本编辑后必须
  立即跑该文件的冒烟测试**，不要攒到最后。

## 追加 3（同日）：全端点真实服务扫描

用户要求用客户端类逐一访问真实服务（opencode 1.18.22 @ 127.0.0.1:37217）。
编写 `temp/live_sweep.py`（本地工具，不入库）：62 项检查覆盖 7 个资源域
全部公开方法 + event 流，**53 PASS / 1 WARN / 8 SKIP / 0 FAIL**（206s，
含多个真实 LLM turn）。

设计原则：
- 只读端点全部实测；有副作用的端点用一次性会话自清理（session 全生命周期、
  auth 假 provider 往返）；不可撤销的变更类端点显式 SKIP 并注明理由
- 自动应答器：后台任务轮询 list_permissions 并 reply "once"，否则 init 的
  文件写权限会卡死 turn
- 模型相关慢调用（shell/command/init/summarize）用 `with_options(timeout=200)`
  + `asyncio.wait_for(190)` 放宽

### 关键发现（已核实服务端源码）

1. `sessions.command` 对未注册的自定义命令返回 **500 UnknownError**——
   服务端 `SessionPrompt.command` 先查 commands.get()，查不到发 Error 事件
   （`temp/repositories/opencode/packages/opencode/src/session/prompt.ts:1356`）。
   扫描器改为仅在 list_commands 非空时执行第一个注册命令。
2. **IT-012 H1 修复的实战验证**：shell/command/init/summarize 四个端点都是
   真实 LLM turn，实测耗时远超默认读超时；`with_options(timeout=...)`
   放宽后全部通过。若还是旧的 5s 标量超时，这四个端点必然失败且重试会
   重复发送。
3. 权限机制实测：init 触发文件写权限 → list_permissions 出现 pending →
   reply_permission("once") 应答后 turn 继续，整链路符合预期。
4. `vcs.diff(mode)` 需要 mode 参数（git|branch），扫描脚本首版漏传——
   客户端 API 是对的。

报告：`temp/live_sweep_report.{json,md}`（不入库）。重跑：
`uv run python temp/live_sweep.py --url http://127.0.0.1:37217`

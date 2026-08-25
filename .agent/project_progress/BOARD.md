# 📋 任务看板

 > 每次工作前看这里；每次完成后更新这里。最后更新：2026-08-24（IT-016 完成，含两次追加）

## 当前位置

- **宏观**：M5 发布准备 —— ✅ 完成（IT-008：本地 dist + tag v0.1.0；PyPI 后续）
- **微观**：IT-016 覆盖率+live 扩域 ✅（2026-08-24；src 91.4% 门禁 90%；
  examples 场景覆盖 69/69；live 单测 11 用例零漂移；**全端点扫描 62 项
  53P/1W/8S/0F 对真实 1.18.22**，工具 `temp/live_sweep.py` 不入库）
- IT-015 project/auth/system 域 ✅（2026-08-24；+10 端点两个新域，+20 测试）
- IT-014 mcp 域补全 ✅（2026-08-24；+6 端点共 8 方法，+10 测试）
- IT-013 files 域 ✅（2026-08-24；7 端点，`client.files.*`）
- **仓库**：已推送 `origin/develop` + tag `v0.1.0`；日常命令走 Makefile（`make check` 全门禁）
- **下一步行动**：候选：① PyPI 发布（换名
  `opencode-client-python` 等 + token）② 余下端点（TUI/PTY、project、sync 等）
  （更正：早前「OpenAPI 已无 /mcp/* 路径」的备注有误——v1.18.21 导出里
  /mcp 家族 8 端点健在，IT-014 已核实并补全）
- **备注**：本地 `opencode serve` 统一 Docker 管理（Makefile `docker-*` 目标，
  默认 20001；镜像慢走域名代理 + tag 还原）；examples 按资源域组织为
  功能模块目录（quickstart/sessions/server/events/vcs/mcp/files/client）

```
宏观  [█████] M1 ✅ ─ M2 ✅ ── M3 ✅ ── M4 ✅ ── M5 ✅
 微观  [██████████] IT-001 ✅ … IT-012 ✅  IT-013 ✅  IT-014 ✅  IT-015 ✅  IT-016 ✅
```

## API 覆盖进度

见 [`api_coverage.md`](./api_coverage.md)：188 操作，剔除 /api+/experimental
后目标面 105 个已覆盖 69 个（66%）；核心资源域 100%，尾巴 11 个 + tui/pty/sync 未做。

## 宏观里程碑（详见 macro/ROADMAP.md）

| 里程碑 | 主题 | 状态 |
|---|---|---|
| M1 | 奠基：结构 + 工具链 + AGENTS.md | ✅ |
| M2 | 核心功能：会话/消息/事件流 + 真实验证 | ✅ |
| M3 | 功能扩张：补齐端点 + 工程化（IT-003 地基 ✅ / IT-004 双客户端 ✅ / IT-005 permission+question ✅ / IT-006 vcs+skill+MCP ✅） | ✅ |
| M4 | 测试强化：集成/断连重连/边界（IT-007：SSE 自动重连 + 请求重试补全 + 真实 server 集成 + 边界用例） | ✅ |
| M5 | 发布准备：README/CHANGELOG/版本号/打包 | ✅（v0.1.0 本地 dist + tag；PyPI 因名称占用后续） |

## 微观迭代（详见 iterations/）

| 迭代 | 主题 | 状态 | 日期 |
|---|---|---|---|
| IT-001 | 项目奠基 | ✅ | 2026-08-21 |
| IT-002 | 核心功能：会话/消息/事件流 | ✅ | 2026-08-22 |
| IT-003 | 工程化重构：目录/examples/规范 | ✅ | 2026-08-22 |
| IT-004 | 同步客户端 + 官方 SDK 优势吸收 | ✅ | 2026-08-22 |
| IT-005 | permission/question 交互闭环 | ✅ | 2026-08-22 |
| IT-006 | vcs / summary / skill / MCP 基础端点 | ✅ | 2026-08-22 |
| IT-007 | M4 测试强化：SSE 自动重连 + 重试/集成/边界测试 | ✅ | 2026-08-22 |
| IT-008 | M5 发布准备：LICENSE/CHANGELOG/打包/发版（本地 dist + tag v0.1.0） | ✅ | 2026-08-22 |
| IT-009 | with_raw_response 裸响应视图：8 个 raw 代理类 + 镜像一致性锁 + 示例 | ✅ | 2026-08-23 |
| IT-010 | 事件 Router + 类型化热事件：`EventType` 开放集 + 6 热事件子类 + `AsyncEventRouter`/`EventRouter` | ✅ | 2026-08-23 |
| IT-011 | session 域补全：status/children/todo/diff/revert/unrevert/init/command/shell/part 编辑（11 端点×4 类） | ✅ | 2026-08-24 |
| IT-012 | code review 问题修复：默认超时/重试幂等/Router 超时语义/异常分层 + 6 Low + 1 Info | ✅ | 2026-08-24 |
| IT-013 | files 域：list/read/status + search_text/files/symbols + formatter（7 端点×4 类） | ✅ | 2026-08-24 |
| IT-014 | mcp 域补全：OAuth start/callback/authenticate/remove + connect/disconnect（6 端点×4 类） | ✅ | 2026-08-24 |
| IT-015 | project/auth 域 + server 补 get_paths/lsp_status/write_log（10 端点） | ✅ | 2026-08-24 |

## 阻塞 / 风险

- ⚠️ PyPI 名称占用：`opencode-client` 已被第三方（v0.1.1）占用，后续公共发布
  需换名（已探明可用：`opencode-client-python` 等，import 名不受影响）
- ⚠️ 本机 uv python 3.12.13 缺 `collections.abc.AsyncContextManager` → 建议 `uv python install 3.12`
- ⚠️ 真实服务 provider 名会变（`steins-middleware` → `steins-middleware-vllm`），smoke 脚本须用 `list_providers().connected` 探测，不要硬编码

## 待决事项

- [x] M3 第一批先做什么 → 先做 IT-003 工程化地基（用户拍板）
- [x] 是否需要 sync 客户端 → 需要，IT-004 已交付（OpenCodeClient=sync / AsyncOpenCodeClient=async）
- [x] 端点优先级确认（permission/question ✅ IT-005 / vcs+skill+MCP 基础 ✅ IT-006；
      余下候选：MCP connect/disconnect/auth 流、share、with_raw_response）
- [x] 是否补 `with_raw_response`（返回原始 httpx.Response）→ IT-009 已交付
      （官方同款代理前缀形态，镜像一致性锁把守）
- [x] M4 集成/断连重连测试 → IT-007 已交付（live 套件 `--live-url` 开关）
- [x] 发布渠道 → v0.1.0 本地 dist + git tag（用户拍板）；PyPI 后续（名称
      `opencode-client` 被第三方占用，需换名，如 `opencode-client-python`）
- [x] IT-012 L6：examples 中文注释 → 用户拍板：AGENTS.md 显式豁免教学注释
      （已落地，见 `.agent/AGENTS.md` 注释风格节）

# 📋 任务看板

 > 每次工作前看这里；每次完成后更新这里。最后更新：2026-08-22

## 当前位置

- **宏观**：M4 测试强化 —— ✅ 完成（IT-008：SSE 自动重连 + 请求重试/集成/边界全测）
- **微观**：无进行中迭代（IT-001~006 与 IT-008 已归档；IT-007 `with_raw_response` 占号未做）
- **仓库**：已推送 `origin/develop`；日常命令走 Makefile（`make check` 全门禁）
- **下一步行动**：开 M5（发布准备：README/CHANGELOG/版本号/打包）；
  可先择机补做 IT-007（`with_raw_response`）；余下端点候选：share、MCP connect/auth 流
- **备注**：examples 已按资源域全量补齐为 00~05 六个编号目录（quickstart /
  session / discovery / vcs / mcp / advanced，各带 README），37 个公开方法全覆盖，
  M5 写 README 时可直接引用该结构

```
宏观  [███]██ M1 ✅ ─ M2 ✅ ── M3 ✅ ── M4 ✅ ── M5 ⬜
微观  [██████] IT-001 ✅  IT-002 ✅  IT-003 ✅  IT-004 ✅  IT-005 ✅  IT-006 ✅
```

## 宏观里程碑（详见 macro/ROADMAP.md）

| 里程碑 | 主题 | 状态 |
|---|---|---|
| M1 | 奠基：结构 + 工具链 + AGENTS.md | ✅ |
| M2 | 核心功能：会话/消息/事件流 + 真实验证 | ✅ |
| M3 | 功能扩张：补齐端点 + 工程化（IT-003 地基 ✅ / IT-004 双客户端 ✅ / IT-005 permission+question ✅ / IT-006 vcs+skill+MCP ✅） | ✅ |
| M4 | 测试强化：集成/断连重连/边界（IT-008：SSE 自动重连 + 请求重试补全 + 真实 server 集成 + 边界用例） | ✅ |
| M5 | 发布准备：README/CHANGELOG/版本号/打包 | ⬜ |

## 微观迭代（详见 iterations/）

| 迭代 | 主题 | 状态 | 日期 |
|---|---|---|---|
| IT-001 | 项目奠基 | ✅ | 2026-08-21 |
| IT-002 | 核心功能：会话/消息/事件流 | ✅ | 2026-08-22 |
| IT-003 | 工程化重构：目录/examples/规范 | ✅ | 2026-08-22 |
| IT-004 | 同步客户端 + 官方 SDK 优势吸收 | ✅ | 2026-08-22 |
| IT-005 | permission/question 交互闭环 | ✅ | 2026-08-22 |
| IT-006 | vcs / summary / skill / MCP 基础端点 | ✅ | 2026-08-22 |
| IT-008 | M4 测试强化：SSE 自动重连 + 重试/集成/边界测试 | ✅ | 2026-08-22 |

## 阻塞 / 风险

- ⛔ PyPI 网络间歇 TLS 失败 → `uv build` 暂无法验证（不影响本地开发/测试）
- ⚠️ 本机 uv python 3.12.13 缺 `collections.abc.AsyncContextManager` → 建议 `uv python install 3.12`
- ⚠️ 真实服务 provider 名会变（`steins-middleware` → `steins-middleware-vllm`），smoke 脚本须用 `list_providers().connected` 探测，不要硬编码

## 待决事项

- [x] M3 第一批先做什么 → 先做 IT-003 工程化地基（用户拍板）
- [x] 是否需要 sync 客户端 → 需要，IT-004 已交付（OpenCodeClient=sync / AsyncOpenCodeClient=async）
- [x] 端点优先级确认（permission/question ✅ IT-005 / vcs+skill+MCP 基础 ✅ IT-006；
      余下候选：MCP connect/disconnect/auth 流、share、with_raw_response）
- [x] 是否补 `with_raw_response`（返回原始 httpx.Response）→ 占号 IT-007，择机补做
- [x] M4 集成/断连重连测试 → IT-008 已交付（live 套件 `--live-url` 开关）
- [ ] 发布渠道（PyPI / 私有源）

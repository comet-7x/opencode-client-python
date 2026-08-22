# 📋 任务看板

> 每次工作前看这里；每次完成后更新这里。最后更新：2026-08-22

## 当前位置

- **宏观**：M3 功能扩张 —— 🔵 进行中（IT-004 同步客户端 ✅ / IT-005 permission+question 交互闭环 ✅）
- **微观**：无进行中迭代（IT-001~005 已归档）
- **下一步行动**：开 IT-006 — M3 下一批端点（候选：summary/share 完善、`with_raw_response`、MCP/skill）

```
宏观  [███]█  M1 ✅ ─ M2 ✅ ── M3 🔵 ── M4 ⬜ ── M5 ⬜
微观  [█████] IT-001 ✅  IT-002 ✅  IT-003 ✅  IT-004 ✅  IT-005 ✅
```

## 宏观里程碑（详见 macro/ROADMAP.md）

| 里程碑 | 主题 | 状态 |
|---|---|---|
| M1 | 奠基：结构 + 工具链 + AGENTS.md | ✅ |
| M2 | 核心功能：会话/消息/事件流 + 真实验证 | ✅ |
| M3 | 功能扩张：补齐端点 + 工程化（IT-003 地基 ✅ / IT-004 双客户端 ✅ / IT-005 permission+question ✅） | 🔵 |
| M4 | 测试强化：集成/断连重连/边界 | ⬜ |
| M5 | 发布准备：README/CHANGELOG/版本号/打包 | ⬜ |

## 微观迭代（详见 iterations/）

| 迭代 | 主题 | 状态 | 日期 |
|---|---|---|---|
| IT-001 | 项目奠基 | ✅ | 2026-08-21 |
| IT-002 | 核心功能：会话/消息/事件流 | ✅ | 2026-08-22 |
| IT-003 | 工程化重构：目录/examples/规范 | ✅ | 2026-08-22 |
| IT-004 | 同步客户端 + 官方 SDK 优势吸收 | ✅ | 2026-08-22 |
| IT-005 | permission/question 交互闭环 | ✅ | 2026-08-22 |

## 阻塞 / 风险

- ⛔ PyPI 网络间歇 TLS 失败 → `uv build` 暂无法验证（不影响本地开发/测试）
- ⚠️ 本机 uv python 3.12.13 缺 `collections.abc.AsyncContextManager` → 建议 `uv python install 3.12`
- ⚠️ 真实服务 provider 名会变（`steins-middleware` → `steins-middleware-vllm`），smoke 脚本须用 `list_providers().connected` 探测，不要硬编码

## 待决事项

- [x] M3 第一批先做什么 → 先做 IT-003 工程化地基（用户拍板）
- [x] 是否需要 sync 客户端 → 需要，IT-004 已交付（OpenCodeClient=sync / AsyncOpenCodeClient=async）
- [ ] 端点优先级确认（permission/question ✅ IT-005 已交付；下一批：vcs/summary/MCP/skill？）
- [ ] 是否补 `with_raw_response`（返回原始 httpx.Response）
- [ ] 发布渠道（PyPI / 私有源）

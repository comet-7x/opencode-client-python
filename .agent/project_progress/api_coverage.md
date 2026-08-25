# REST API 覆盖进度表

> 数据源：`.agent/learning_log/get_opencode_api/opencode_rest_api.json`（opencode v1.18.21 导出，188 个操作）。
> 生成方式：解析 `src/opencode_client/resources/*.py` 的 `_send(...)` 调用与 helper 路径，
> 与 OpenAPI 逐条比对。审计脚本思路见 `temp/api_audit.json`（本地）。
> 最后更新：2026-08-24（IT-016 后）

## 总览热力图

```
分类                        已做 未做 合计  进度
------------------------------------------------------------
api(应用内部)                0   58   58  ░░░░░░░░░░░░░░░░░░░░   0%
/session(核心)              26    1   27  ███████████████████░  96%
experimental(不稳定)         0   25   25  ░░░░░░░░░░░░░░░░░░░░   0%
tui                          0   13   13  ░░░░░░░░░░░░░░░░░░░░   0%
/mcp(核心)                   8    0    8  ████████████████████ 100%
pty                          0    8    8  ░░░░░░░░░░░░░░░░░░░░   0%
/global(核心)                1    5    6  ███░░░░░░░░░░░░░░░░░  17%
/project(核心)               5    0    5  ████████████████████ 100%
/vcs(核心)                   5    0    5  ████████████████████ 100%
/provider(核心)              1    3    4  █████░░░░░░░░░░░░░░░  25%
sync                         0    4    4  ░░░░░░░░░░░░░░░░░░░░   0%
/config(核心)                2    1    3  █████████████░░░░░░░  67%
/file(核心)                  3    0    3  ████████████████████ 100%
/find(核心)                  3    0    3  ████████████████████ 100%
/question(核心)              3    0    3  ████████████████████ 100%
/permission(核心)            2    0    2  ████████████████████ 100%
/auth(核心)                  2    0    2  ████████████████████ 100%
/agent /command /formatter
/log /lsp /path /skill
/event(核心,各1)             7    0    7  ████████████████████ 100%
/instance(核心)              0    1    1  ░░░░░░░░░░░░░░░░░░░░   0%
------------------------------------------------------------
TOTAL                       69  119  188  ███████░░░░░░░░░░░░░  37%
```

**解读口径**：188 个操作中 `/api`(58) 是 opencode 自带 web UI 的内部接口、
`/experimental`(25) 明确不稳定——这两块 **83 个不在目标范围**。
剔除后目标面 105 个，已覆盖 69 个 = **66%**；其中"核心资源域"
（session/file/find/vcs/mcp/project/auth/permission/question 及发现类）
已 **100%**。

## 剩余缺口明细

### 核心域尾巴（11 个，建议下一批）

| 方法 | 端点 | 说明 |
|---|---|---|
| GET | `/session/{id}/message/{mid}` | 单条消息读取（现只有 list_messages） |
| GET | `/provider/auth` | provider 支持的认证方式 |
| POST | `/provider/{id}/oauth/authorize` | provider OAuth 发起 |
| POST | `/provider/{id}/oauth/callback` | provider OAuth 回调 |
| GET/PATCH | `/global/config` | 全局配置读写（区别于实例级 `/config`） |
| POST | `/global/dispose`、`/instance/dispose` | 实例销毁 |
| GET | `/global/event` | 全局事件流（区别于实例 `/event`） |
| POST | `/global/upgrade` | 自升级 |

### 大块未做（有意延后）

| 组 | 数量 | 延后理由 |
|---|---:|---|
| `/tui/*` | 13 | 控制 opencode 自带终端界面，程序化场景少 |
| `/pty/*` | 8 | 终端会话管理（含 WebSocket），需求出现再做 |
| `/sync/*` | 4 | 多工作区同步，等真实需求 |
| `/api/*` | 58 | opencode web UI 内部接口，不属于公开契约 |
| `/experimental/*` | 25 | 服务端明确标注不稳定 |

## 更新方式

重新跑审计：解析 `resources/*.py` 与 OpenAPI 比对（临时脚本在会话记录中），
或直接对照本表手工核对 `client.<域>.*` 方法清单。

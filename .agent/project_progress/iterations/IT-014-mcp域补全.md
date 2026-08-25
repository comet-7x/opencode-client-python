# IT-014 — mcp 域补全：OAuth 生命周期与连接管理（6 端点）

日期：2026-08-24
宏观：M5 之后的功能扩张；技术债清理

## 背景与核实结论

AGENTS.md 曾备注「pin 镜像 v1.18.21 的 OpenAPI 已无 /mcp/* 路径」——
**经重新核实该说法有误**：`.agent/learning_log/opencode_rest_api.json`
（v1.18.21 导出）里 `/mcp` 家族共 **8 个端点**，全部健在。真实缺口是：
现有 `client.mcp.*` 只实现了 `status`/`add` 两个，其余 6 个未覆盖。

服务端行为已对照 `handlers/mcp.ts` 核实：

| 端点 | 行为要点 |
|---|---|
| `POST /mcp/{name}/auth` | 服务端先查 `supportsOAuth`，不支持则报错；成功返回 `{authorizationUrl, oauthState}`（浏览器跳转流） |
| `DELETE /mcp/{name}/auth` | 移除凭证，返回 `{success: true}` |
| `POST /mcp/{name}/auth/authenticate` | 无头（headless）认证流，同样有 supportsOAuth 前置检查；返回 `MCPStatus` |
| `POST /mcp/{name}/auth/callback` | 完成浏览器流：body `{code}`；返回 `MCPStatus` |
| `POST /mcp/{name}/connect` | 返回 `bool` |
| `POST /mcp/{name}/disconnect` | 返回 `bool` |

通用：`{name}` 是路径参数（复用 `_wire.path_segment` 编码）；
全部支持 directory/workspace scoping；404 → `OpenCodeNotFoundError`
（服务端 McpServerNotFoundError）。

## 目标

`client.mcp.*` 扩到 8 方法（四类镜像同步），对齐完整 wire 面：

```python
start_oauth(name)            -> McpOAuthStart        # 拿 authorizationUrl 供用户浏览器打开
complete_oauth(name, code)   -> dict[str, MCPStatus] # 用回调 code 换 token
authenticate(name)           -> MCPStatus            # 无头流
remove_oauth(name)           -> bool
connect(name)                -> bool
disconnect(name)             -> bool
```

新模型：`McpOAuthStart`（authorization_url/oauth_state 走 id_alias 驼峰）。
返回 `MCPStatus`/`dict[str, MCPStatus]` 复用现有判联合与 TypeAdapter。

## 任务

- [ ] 模型：`models/mcp.py` 加 `McpOAuthStart`；导出三处注册
- [ ] `_wire.py`：`oauth_start`/`oauth_status` TypeAdapter
- [ ] `resources/mcp.py`：6 方法 ×4 类（raw 视图同步）；路径参数走 path_segment
- [ ] 测试：`tests/test_mcp.py` 补 6 端点 sync+async+404+raw 抽查
- [ ] 示例：`examples/mcp/mcp_servers.py` 增加 OAuth 流演示段；
      冒烟 fixture 补路由
- [ ] 文档：修正 AGENTS.md 里「OpenAPI 已无 /mcp/*」的过时备注；
      README 双语表无需动（域级描述不变）
- [ ] `make check` 全绿；IT-014/BOARD 归档

## 决策记录

- `complete_oauth` 对应 wire 的 `/auth/callback`（服务端 handler 叫
  finishAuth）：Python 名取语义（用 code 完成 OAuth），docstring 注明映射。
- `authenticate` 与 `start_oauth+complete_oauth` 是两条独立流（headless vs
  browser），示例里都演示但默认只跑 start_oauth 展示 URL 形态。

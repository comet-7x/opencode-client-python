# IT-006 M3 端点扩张：vcs / summary / skill / MCP 基础

- 状态：✅ 完成（2026-08-22）
- 所属里程碑：M3 功能扩张

## 目标

按使用场景补齐下一批端点（sync + async 双类同步实现）：vcs 全套（5）、
summary（补测试）、skill（1）、MCP 基础（2）。with_raw_response 与 M4 断连重连
测试另开迭代（一迭代一主题）。

## 端点（opencode_rest_api.json 核实 + 真实服务 v1.18.18 冒烟）

- [x] `GET /vcs` → `VcsInfo{branch, default_branch}`（**snake_case 特例**，显式 alias）
- [x] `GET /vcs/status` → `list[VcsFileStatus]`
- [x] `GET /vcs/diff`（`mode`: **`git`|`branch` 枚举**，`context` 可选）→ `list[VcsFileDiff]`
- [x] `GET /vcs/diff/raw` → 纯文本（`validate_text`，非 JSON）
- [x] `POST /vcs/apply` body `{patch}` → 结果 document
- [x] `POST /session/{id}/summarize` — 双类已存在，本迭代补测试
- [x] `GET /skill` → `list[Skill{name,location,content,description?}]`（server 域）
- [x] `GET /mcp` → `dict[name → MCPStatus]`（5 路 `status` 判联合）
- [x] `POST /mcp` body `{name, config: local|remote}`（`type` 判联合）

## 任务

### 模型
- [x] `models/vcs.py`：VcsInfo/VcsFileStatus/VcsFileDiff（`default_branch` 显式 snake_case alias）
- [x] `models/mcp.py`：MCPStatus 5 种兄弟模型 + `status` 判联合（无基类——strict pyright
      不允许子类窄化 Literal，对齐 `Message` union 模式）；McpLocalConfig/McpRemoteConfig
      `type` 判联合；McpOAuthConfig（**`clientId`/`clientSecret` 小写 d 特例**，
      validation/serialization alias 保持 kwargs 为 snake_case）
- [x] `models/discover.py` + Skill；`models/__init__.py` 注册

### 资源
- [x] `_wire.py`：5 个新适配器 + `vcs_diff_query`/`vcs_apply_body`/`mcp_add_body`/`validate_text`
- [x] `resources/vcs.py` 新建（5 端点 × 双类，`diff` 的 mode 收 `Literal["git","branch"]`）
- [x] `resources/mcp.py` 新建（status/add × 双类）
- [x] `server.py` + list_skills（× 双类）；`client.py` 接线 `client.vcs`/`client.mcp`

### 测试
- [x] `tests/test_vcs.py`（9 项：snake_case 往返、mode/context query、raw 文本、apply body、404）
- [x] `tests/test_mcp.py`（7 项：5 状态判联合解析、local/remote 序列化、oauth False / oauth 配置）
- [x] `tests/test_discovery_extra.py`（7 项：skill 解析/缺省 description/空表、summarize 双客户端）
- [x] `tests/conftest.py`：session 级 hermetic fixture 清除环境代理变量
      （本机 SOCKS 代理会让 httpx.Client 构造即抛 ImportError，库保留 trust_env 默认行为，测试自隔离）

### 验证
- [x] 全门禁：ruff / format / mypy(31 文件) / pyright strict / **pytest 68 passed**
- [x] 真实服务（v1.18.18）：vcs.info/status/diff(git+branch)/diff_raw、skill、mcp.status
      sync+async 全通（apply 有写副作用，仅 respx 覆盖）

## 完成记录

- `mode` 合法值是 `git | branch`（**不是** worktree/all）——真实服务 400 报错后对
  spec enum 核实，收紧为 `Literal`
- VcsInfo 全字段 nullable：`default_branch` 可为 null（活服务实测 `{"branch":"develop","default_branch":null}`）
- alias 三特例（均已注释 why）：`default_branch` snake_case / `clientId`/`clientSecret` 小写 d
- MCPStatus 不用基类：strict pyright 禁止子类 Literal 窄化，5 个兄弟模型 + Annotated union
- 环境债：本机 `all_proxy=socks5://…` 泄漏进测试 → conftest 统一清除，未动库行为
- 68 = 45（前序）+ 23（本迭代）
- 下一步候选（另开迭代）：IT-007 with_raw_response / IT-008 M4 集成+断连重连 /
  MCP connect/disconnect/auth 流 / vcs/apply 教学示例

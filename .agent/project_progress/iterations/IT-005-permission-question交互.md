# IT-005 M3 第一批端点：permission/question 交互闭环

- 状态：✅ 完成（2026-08-22）
- 所属里程碑：M3 功能扩张

## 目标

补齐"人机交互闭环"端点：当 opencode 在执行中遇到需要**权限确认**（permission）或
**追问澄清**（question）时，客户端能列出 pending 请求并回复/拒绝，把一次卡住的 turn
推到底。sync + async 双类同步实现。

## 端点（opencode_rest_api.json 已核实 schema）

- [x] `GET /permission` → `list[PermissionRequest]`（list_permissions）
- [x] `POST /permission/{requestID}/reply` body `{reply: once|always|reject, message?}`（reply_permission）
- [x] `GET /question` → `list[QuestionRequest]`（list_questions）
- [x] `POST /question/{requestID}/reply` body `{answers: list[list[str]]}`（reply_question）
- [x] `POST /question/{requestID}/reject`（reject_question）
- 归入 `ServerResource`/`AsyncServerResource`（server 级端点，非 session 域）

## 任务

### 模型
- [x] `models/interaction.py`：`PermissionRequest`/`PermissionTool`、
      `QuestionRequest`/`QuestionInfo`/`QuestionOption`/`QuestionTool`、
      `QuestionAnswer = list[str]`（wire：`sessionID`/`callID` 经 id_alias 自动映射）
- [x] `models/__init__.py` 注册 import + `__all__`

### 资源
- [x] `_wire.py`：`permission_reply_body`/`question_reply_body` 纯函数 +
      `permission_requests`/`question_requests` TypeAdapter
- [x] `server.py`：5 个方法 sync + async 双类（方法体 = send + validate）
- [x] 包根 `__init__.py` 导出 5 个交互模型（import 列表 + `__all__` 同步）

### 测试
- [x] `tests/test_interactions.py`（11 项）：list 解析（union→强类型模型断言）、
      reply body 序列化（once/always+message/reject/multi-answers）、sync+async 对等、
      404 → `OpenCodeNotFoundError`

### 教学
- [x] `examples/respond_interactions.py`：交互闭环模式 — prompt_async 后监听
      SSE，轮询 pending permission/question 并自动应答（默认 permission=reject 安全侧，
      `--allow` 改 once；question 取首选项），`session.idle` 收尾

### 验证
- [x] 全门禁：ruff / format / mypy(23 文件) / pyright strict / **pytest 45 passed**
- [x] 真实服务（v1.18.18 @ 127.0.0.1:20001）：sync+async `list_permissions`/
      `list_questions` 真实调通（当前无 pending 返回 []）；`respond_interactions.py`
      实跑：prompt → 事件流全程可见 → `session.idle` 正常收尾（该 turn 未挂起交互，
      应答路径由 respx 按 spec 覆盖）

## 完成记录

- 交互端点是 **server 级**（`/permission`、`/question`），归 ServerResource 而非 sessions
- wire 要点：question reply 的 `answers` 是"每个问题一组被选 label"，顺序与
  `questions` 数组对应；permission reply 枚举 `once/always/reject`
- `respond_permission`（session 域旧接口 `POST /session/{id}/permissions/{pid}`）保留，
  新端点是 server 级全局版；调用方按场景选择
- 45 passed = 34（IT-004）+ 11（交互）
- 下一步 M3 候选：vcs/summary 端点、`with_raw_response`、MCP/skill 相关

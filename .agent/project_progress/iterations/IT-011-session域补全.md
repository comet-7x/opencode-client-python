# IT-011 — session 域补全（11 端点）

日期：2026-08-24
宏观：M5 之后的功能补全；BOARD 候选方向 A

## 背景

sessions 资源域现有 15 方法，但 `/session` 家族仍有 11 个端点未覆盖：
状态观测（status/children/todo/diff）、历史回退（revert/unrevert）、
命令式输入（command/shell/init）、part 级编辑（update_part/delete_part）。
全部为会话核心链路，与现有方法同域，扩展成本最低。

## 目标

`client.sessions.*` 新增 11 方法（sync/async/raw×2 四类镜像）：

1. `status()` → `dict[str, SessionStatus]`（GET /session/status）
2. `children(id)` → `list[Session]`
3. `list_todos(id)` → `list[Todo]`
4. `diff(id, message_id=None)` → `list[SessionFileDiff]`
5. `revert(id, message_id, part_id=None)` → `Session`（busy → 409）
6. `unrevert(id)` → `Session`（busy → 409）
7. `init(id, provider_id, model_id, message_id)` → `bool`
8. `command(id, command, arguments, ...)` → `MessageWithParts`
9. `shell(id, command, agent, ...)` → `MessageWithParts`（busy → 409）
10. `delete_part(id, message_id, part_id)` → `bool`
11. `update_part(id, message_id, part_id, part)` → `Part`

## 权威源核实记录（服务端 handler / OpenAPI）

- 路由定义：`packages/opencode/src/server/routes/instance/httpapi/groups/session.ts`
  （`SessionPaths`）；行为：同目录 `handlers/session.ts`
- `revert/unrevert/shell` 的 busy 错误映射 409 SessionBusyError
  （`SessionError.mapBusy`）；`command` 把所有失败一律 map 成 400 BadRequest；
  `init` 内部转成 `promptSvc.command(command=INIT)`，返回 true
- `shell` 必填 `agent`+`command`，model 为 `{providerID, modelID}` 对象；
  `command` 必填 `arguments`+`command`，model 为 `"provider/model"` 字符串
- `GET /session/{id}/diff` query 只有可选 `messageID`；响应 SnapshotFileDiff
  仅 additions/deletions 必填（file/patch/status 可缺）
- `update_part` 服务端校验 payload 的 id/messageID/sessionID 与路径参数一致，
  不符 → 400
- 409 已有 `OpenCodeConflictError` 映射（errors.py），无需新异常

## 任务

- [x] 模型：`models/session.py` += `SessionStatus`(idle/busy/retry 判联合)、
      `Todo`、`SessionFileDiff`；`models/__init__.py` + 包根导出
- [x] `_wire.py`：TypeAdapters（status map/todo list/diff list/part）+
      `command_body`/`shell_body`/`revert_body`/`init_body`/`diff_query`
- [x] `resources/sessions.py`：四类各加 11 方法
- [x] 测试：`tests/test_sessions_extra.py`（respx 全端点 sync+async +
      raw 视图抽查 + 409 映射）
- [x] 示例：`01_session_management/session_state_history.py` + 冒烟 fixture 路由
- [x] `make check` 全绿；BOARD/ROADMAP 归档

## 完成记录

2026-08-24 完成：

- **模型**：`SessionStatusIdle/Busy/Retry`（`type` 判联合；retry 带
  attempt/message/next + 可选 action 五必填一可选）、`Todo`
  （content/status/priority 均收窄 Literal）、`SessionFileDiff`
  （仅 additions/deletions 必填——与 `VcsFileDiff` 的关键差异，wire schema
  核实过 file/patch/status 可缺）；
- **方法**（sessions 四类 ×11，共 44 个）：`status`/`children`/`list_todos`/
  `diff`/`revert`/`unrevert`/`init`/`command`/`shell`/`delete_part`/
  `update_part`。wire 差异点：
  - `command` 的 model 是 `"provider/model"` 字符串（服务端 CommandInput 为
    Schema.String），客户端收 `PromptModel | str` 并自动 join；
  - `shell` 的 model 保持 `{providerID, modelID}` 对象，且 agent 必填；
  - `update_part` body 直接 `part.to_wire()`，docstring 写明服务端校验
    id/messageID/sessionID 与路径一致否则 400。
- **行为核实**（groups/session.ts + handlers/session.ts）：revert/unrevert/
  shell busy → 409 → 现有 `OpenCodeConflictError` 直接命中，零新异常；
  command 服务端把一切失败 map 成 400 BadRequest；init 内部转
  `promptSvc.command(INIT)` 返回 true。
- **测试**：`tests/test_sessions_extra.py` 16 项（判联合解析、body 形状、
  409 映射 sync+async、raw 视图 11 方法镜像×2）；examples 冒烟 +1 例
  （fixture 用 `$` 锚定 revert/unrevert 两 regex 防互吞）。raw 一致性锁
  自动通过（四类方法签名逐字镜像）。
- 结果：**`make check` 全绿（192 passed / 5 skipped）**。

### 踩坑

- `Part` 是 Annotated 判联合，不能 `Part.model_validate(...)`（UnionType 无
  此方法）；测试里用具体子类 `TextPart(...)` 构造，断言前 isinstance 收窄。
- respx `url.params["k"] is None` 断言不对——未发送的 query key 直接不在
  dict 里，应断言 `key not in params`。


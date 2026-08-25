# IT-013 — files 域：文件系统与搜索端点

日期：2026-08-24
宏观：M5 之后的功能扩张；BOARD 候选方向 A（文件/搜索域）

## 背景

客户端现有 sessions/server/vcs/mcp 四个资源域，但 opencode 的文件系统
与搜索面（`/file*`、`/find*`、`/formatter`）完全未覆盖——这是 agent 类
工具最高频的读取面。全部为 GET 端点，无副作用，实现成本低。

## 权威源核实记录（OpenAPI + 服务端 handler）

OpenAPI：`.agent/learning_log/get_opencode_api/opencode_rest_api.json`；
行为：`temp/repositories/opencode/packages/opencode/src/server/routes/
instance/httpapi/handlers/file.ts`（路由组定义在同目录 `groups/file.ts`）。

7 个端点，**全部 GET**，除 `/file/status` 与 `/formatter` 外都带必填 query：

| # | 端点 | 必填 query | 可选 query | 200 响应 |
|---|---|---|---|---|
| 1 | `GET /file` | `path` | directory/workspace | `FileNode[]`（目录树一层） |
| 2 | `GET /file/content` | `path` | directory/workspace | `FileContent` |
| 3 | `GET /file/status` | - | directory/workspace | `File[]`（git 视角增删改） |
| 4 | `GET /find` | `pattern` | directory/workspace | 匹配项数组（ripgrep 文本搜索） |
| 5 | `GET /find/file` | `query` | `dirs`(bool 字符串)/`type`(file\|directory)/`limit`/directory/workspace | `string[]` 路径 |
| 6 | `GET /find/symbol` | `query` | directory/workspace | `Symbol[]`（LSP 符号） |
| 7 | `GET /formatter` | - | directory/workspace | `FormatterStatus[]` |

服务端行为要点（handler 核实）：
- `findText`：`limit` **硬编码 10**（handler 内 `.grep({..., limit: 10})`），
  客户端不暴露 limit 参数；
- `findFile`：`limit` 默认 10；`type` 缺省时由 `dirs` 推导
  （`dirs === "false"` → `"file"`，否则 undefined = 全部）；`dirs` 是
  **字符串布尔**（`"true"/"false"`），wire 上直接传字符串；
- `content`：`type` 判联合——`text`（content 为文本）与 `binary`
  （`encoding: "base64"` + `mimeType`）；可选携带 `diff`/`patch`
  （unidiff 结构化 hunks）；
- 全部端点支持 `directory`/`workspace` scoping query；
- wire 字段注意：`line_number`/`absolute_offset` 是 snake_case 特例
  （其余 camelCase），模型映射需显式处理。

## 目标

新资源域 `client.files.*`（sync/async/raw×4 类镜像，7 方法）：

1. `list(path)` → `list[FileNode]`
2. `read(path)` → `FileContent`
3. `status()` → `list[FileChange]`
4. `search_text(pattern)` → `list[TextMatch]`
5. `search_files(query, dirs=None, type=None, limit=None)` → `list[str]`
6. `search_symbols(query)` → `list[Symbol]`
7. `formatter_status()` → `list[FormatterStatus]`

新模型 `models/files.py`：

- `FileNode`（name/path/absolute/type 判联合 file|directory/ignored）
- `FileContent`（type 判联合 text|binary；binary 带 encoding="base64"+
  mimeType）+ `FilePatch`/`FileHunk`（unidiff 结构）
- `FileChange`（wire schema 名 `File`；path/added/removed/status
  Literal added|deleted|modified）
- `TextMatch` + `TextSubmatch`（/find 匹配项）
- `Symbol` + `SymbolLocation` + `SourceRange` + `SourcePosition`（LSP 形状）
- `FormatterStatus`（name/extensions/enabled）

命名说明：wire 的 `File` 在 Python 侧改名 `FileChange`（`File` 过于通用，
且避免与 `FileNode` 混淆）；`/find` 匹配项 wire 无名，取语义名 `TextMatch`。

## 任务

- [x] 模型：`models/files.py` 上述实体；`models/__init__.py` + 包根导出
      （snake_case 特例字段显式 alias 处理）
- [x] `_wire.py`：TypeAdapters（node list/content/change list/match list/
      str list/symbol list/formatter list）+ `find_file_query` 助手
      （dirs 布尔转字符串、type 推导逻辑放客户端侧文档化）
- [x] `resources/files.py`：`FilesResource`/`AsyncFilesResource` +
      双 raw 代理类；`client.py` 挂载 `client.files`；
      `resources/__init__.py` 导出
- [x] 测试：`tests/test_files.py`（respx 全端点 sync+async、判联合解析、
      raw 视图镜像抽查、404 映射）；raw 一致性锁自动覆盖
- [x] 示例：`examples/files/` 新模块目录（browse + search 两脚本）+
      README；`test_examples.py` 加冒烟 fixture 路由
- [x] 文档同步：根 README 双语表加 files 行、AGENTS.md 资源域列表、
      examples/README.md 目录表
- [x] `make check` 全绿；IT-013/BOARD 归档

## 决策记录

- 资源域名用 `files`（对齐 wire 的 `/file` 家族），搜索三端点并入同域
  （服务端本就放在同一 `fileHandlers` 组，不单拆 find 域）。
- `formatter_status` 并入 files 域（服务端同组；formatter 是文件处理设施）。

## 完成记录

2026-08-24 完成：

- **模型** `models/files.py` 14 个公开名：`FileNode`、`TextFileContent`/
  `BinaryFileContent` 判联合（discriminator=`type`，wire 名 `FileContent`）、
  `FilePatch`/`FileHunk`、`FileChange`、`TextFragment`/`TextSubmatch`/
  `TextMatch`（`line_number`/`absolute_offset` 显式 snake_case alias）、
  `Symbol`/`SymbolLocation`/`SourceRange`/`SourcePosition`、
  `FormatterStatus`。
- **资源**：`resources/files.py` 四类 ×7 方法（list/read/status/
  search_text/search_files/search_symbols/formatter_status）；
  `_wire.find_file_query` 处理 dirs 字符串布尔与 type/limit；client 挂载
  `client.files`；包根 + models + resources 三处导出同步。
- **测试**：`tests/test_files.py` 15 项（判联合、snake_case wire、字符串
  布尔透传、404 映射、sync+async+raw 抽查）；`test_raw_response.py`
  DOMAINS 加 files，镜像锁自动覆盖新域。
- **示例**：`examples/files/` 新模块（browse_files / search_code +
  README）；冒烟 fixture 补 7 个端点路由，+2 用例。
- **文档**：根 README 双语表加 files 行；AGENTS.md 结构树与 examples
  模块清单同步。
- 结果：**`make check` 全绿（232 passed / 5 skipped，+18）**。

### 踩坑

- 资源方法命名 `list` 会**遮蔽类体内的内置 `list`**——同文件后续注解
  `-> list[X]` 被 mypy/pyright 当成方法类型报错。解法：类内返回注解一律
  写 `builtins.list[...]`（import builtins）。这是给后续新增域的警示：
  方法名撞内置名时注解要限定。
- pyright 对判联合的 isinstance 收窄很严格：example 里
  `elif isinstance(content, BinaryFileContent)` 报 unnecessary（if 分支已
  收窄掉 text），改用 `content.type == "text"` 字面量收窄更干净。

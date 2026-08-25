# files — 文件系统与搜索

## 本文件夹讲什么

`client.files.*` 让**远端**的 opencode 服务替你读文件、找东西——客户端和
项目不在同一台机器时（容器/服务器场景），这是你的 "ls / cat / grep /
fuzzy-find"。两个脚本各覆盖一半：

| 脚本 | 端点 | 关键点 |
|---|---|---|
| `browse_files.py` | `files.list/read/status/formatter_status` | 目录树一层（`FileNode`）；读文件是 **text/binary 判联合**（二进制为 base64 + mimeType）；git 视角增删改；已注册 formatter |
| `search_code.py` | `files.search_text/search_files/search_symbols` | ripgrep 文本命中带 `line_number` 与行内 `submatches` 区间；文件名模糊搜索（注意服务端默认上限 10 条）；LSP 符号（`kind` 是数字） |

## 适用场景

- 容器/远程开发：程序在宿主机、项目在容器里，需要读写项目文件；
- 做工具链/UI：想复刻 TUI 的文件树、全局搜索、符号跳转；
- 自动化脚本：检查工作区改动、批量检索代码模式。

## wire 形状的坑（库已处理，这里说明来源）

- `/find` 的 `line_number`/`absolute_offset` 是 **snake_case**——全 API
  少见的例外，模型里用了显式 alias；
- `/find/file` 的 `dirs` 参数是**字符串布尔**（`"true"/"false"`），
  Python 侧收真布尔自动转换；
- 服务端把文本搜索结果**写死为 10 条**，文件名搜索默认也是 10
  （可用 `limit` 放大）。

## 前置条件

- `make install` 后位于本仓库环境；运行中的 `opencode serve`（默认 4096）；
- 全部为只读 GET，不发 prompt、不依赖 provider/model；
- 符号搜索需要服务端装了对应语言的 LSP，否则返回空列表。

## 运行

```sh
uv run python -m examples.files.browse_files --path src
uv run python -m examples.files.browse_files --read README.md
uv run python -m examples.files.search_code --pattern "TODO"
uv run python -m examples.files.search_code --pattern "def main" --find-file workflow --symbol main
```

均支持 `--url` 与 `--directory`，`--help` 查看全部参数。

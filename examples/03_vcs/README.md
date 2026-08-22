# 03_vcs — 版本控制（VCS）端点

## 本文件夹讲什么

`client.vcs.*` 让 opencode 服务端替你操作项目仓库的版本状态：当前分支、
改了哪些文件、diff 长什么样、直接应用一个补丁。适合"客户端与仓库同机、
但想用一个编程入口管理改动"的场景（比如 CI 里先 diff 再决定 apply）。
本组脚本按工作流顺序把 5 个端点走一遍：

| 脚本 | 演示的调用 | 看什么 |
|---|---|---|
| `vcs_workflow.py` | `vcs.info()` / `status()` / `diff(mode)` / `diff_raw()`（+ 可选 `apply()`） | 每个端点的返回结构；`directory` 如何定位仓库；raw 与结构化 diff 的区别 |

## 适用场景

- 想在脚本里"先看再改"：`status` 看改动面 → `diff`/`diff_raw` 看细节 →
  `apply` 应用准备好的补丁；
- 把 `diff_raw` 的输出落盘（`--save`）或转发给别的系统；
- 理解 `directory` 作用域：vcs 端点通过 query 参数 `directory` 告诉服务端
  "操作哪个项目目录"，不传则用服务端默认。

## 前置条件

- `make install` 后位于本仓库环境；
- 运行中的 `opencode serve`，且 `--directory` 指向一个**存在的 git 仓库**
  （默认是脚本的当前工作目录）；
- `--apply` 需要一份 unified diff 文件（可用本脚本 `--save` 先生成一份）。

## 运行

```sh
# 在本仓库根目录直接跑（默认 --directory 为 cwd，--mode git）
uv run python -m examples.03_vcs.vcs_workflow

# 指定仓库目录 + 与当前分支比较
uv run python -m examples.03_vcs.vcs_workflow --directory /path/to/repo --mode branch

# 把 raw diff 保存到文件
uv run python -m examples.03_vcs.vcs_workflow --save /tmp/diff.txt

# 应用一个补丁文件（真正改动工作区，谨慎）
uv run python -m examples.03_vcs.vcs_workflow --apply /tmp/patch.txt
```

均支持 `--url` 指定服务地址，`--help` 查看全部参数。

## 代码里有什么

- `info()` 返回 `VcsInfo`（branch / default_branch，均可选——非 git 仓库
  服务端会回空）；
- `status()` / `diff()` 返回**列表**（每文件一条），带
  `+additions/-deletions/status`；`diff()` 额外带每文件的 `patch` 文本；
- `diff_raw()` 返回**整段** unified diff 的纯文本（`text/x-diff`，
  库不做 JSON 解析，直接给字符串）；
- `apply(patch)` 是唯一写操作，所以脚本里放在 `--apply` 开关后面，
  结果结构随服务端演进，原样打印不做强类型。

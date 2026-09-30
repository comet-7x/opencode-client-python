# IT-019 — examples 全面中文化 + 本地未合并工作择优吸收

日期：2026-08-26

## 背景

本地 develop 之前有一批未提交改动（stash）：examples 全量重写为中文教学风格 +
3 个新脚本（sync 入门 / prompt 全参数 / 结构化 parts）。远端 develop 在此期间
独立把 examples 重组为功能模块目录（quickstart/sessions/server/events/vcs/mcp/
files/projects/client）并补了大量脚本。两边冲突，用户拍板：**择优吸收**
（丢弃 stash，只把远端仍缺的内容按新结构重落）+ **全面中文化**（全部示例脚本）。

## 任务

- [x] 远端 develop fast-forward 合并（`2d3249d`），3 个有价值脚本先抢救到
      `/var/folders/.../T/opencode/stash-rescue/` 再 `git stash drop`
- [x] 按远端新结构重落 3 个新脚本（中文）：
      - `quickstart/quickstart_sync.py` —— sync 客户端对等入门
        （远端 quickstart 只有 async 版）
      - `sessions/prompt_options.py` —— prompt 完整参数面：model 动态探测 /
        system / tools / agent / no_reply / 多轮
      - `sessions/structured_parts.py` —— parts 列表形式：text + file +
        subtask 混排
- [x] 既有 18 个示例脚本全部中文化（行为零改动，只换 docstring/注释/文案）
- [x] 清理远端遗留的旧数字目录路径（`03_vcs/`、`04_mcp/`、
      `02_discovery_config/` 等，server/vcs/mcp 三个 README）
- [x] 测试登记：`test_examples.py` +5 用例（含 --agent/--disable-tool 与
      --file-url/--mime/--subtask 分支变体）；`test_cli_errors.py` CASES +3
- [x] 文档：examples/README.md 总表 + quickstart/README + sessions/README
      补新脚本
- [x] `make check` 全绿（291 passed, 33 skipped, 覆盖率 90.67%）

## 决策记录

- **`test_cli_errors.py` 本机环境问题**：该文件把每个脚本指向
  `127.0.0.1:9`（无人监听的端口）验证 transport-error 分支 exit 2。
  本机（macOS + 全局透明代理）下该端点不是"立即拒绝"而是被代理拦截
  （502）或静默丢弃（ReadTimeout），22 个用例每个 ~11-17s 且断言失败。
  修法：`clear_proxy_env` fixture 加**探针**——用与脚本相同路径
  （trust_env=True，含 macOS 系统代理）先打一次该端口，只有
  `ConnectError`（真·立即拒绝）才放行，否则整模块 skip。CI（Linux）
  行为不变照常跑。
- **弃用项**：stash 里的 `delete_message` 演示被远端
  `session_lifecycle.py` 已覆盖，不再单独落脚本。
- **f-string 陷阱**：Python >= 3.11 硬下限，禁止 PEP 701 嵌套同引号
  f-string（3.12 特性）——重写中已多次触发并修掉（先提取中间变量）。

## 完成记录

2026-08-26 完成：

- 21 个示例脚本全部中文（3 新增 + 18 重写），`make check` 全绿
- 新增用例 5 + cli_errors CASES 3，examples 冒烟 39 passed / 22 skipped
- 未提交（等用户确认后与后续工作一起提交）

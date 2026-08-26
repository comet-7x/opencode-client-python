# IT-018 — CI/CD 基建：GitHub Actions 门禁 + Trusted Publishing

日期：2026-08-24

## 背景

v0.2.0 已发布，但工程底座有两块缺失：① 质量门禁只在本机跑（`make check`），
回归可能悄悄进 develop；② 发版靠手动 `uv publish` + token。

## 任务

- [x] `.github/workflows/ci.yml`：push(develop/main) + PR 触发，
      uv sync 后跑与本地等价的门禁（format-check/lint/types/test）
- [x] `.github/workflows/publish.yml`：push tag `v*` 触发，
      校验 tag 与 pyproject 版本一致 → `uv build` →
      `pypa/gh-action-pypi-publish` 以 **Trusted Publishing**（OIDC 免密钥）上传
- [x] 用户侧一次性配置：PyPI 项目页绑定 GitHub publisher（见下）
- [x] AGENTS.md 发版流程补充 tag 触发自动发布的说明
- [x] 归档 + 提交

## 用户侧一次性配置（PyPI）

1. 打开 https://pypi.org/manage/project/opencode-client-python/settings/publishing/
2. Add GitHub Publisher：
   - Owner `comet-7x` · Repository `opencode-client-python`
   - Workflow name `publish.yml` · Environment 留空
3. 保存后，以后 push 一个 `v*` tag 即自动构建并上传 PyPI——**不再需要 token**
4. 同时建议把 Entire-account API token 换成项目 scoped（或直接删除改用 TP）

## 决策记录

- CI 直接跑 `make check`（与本地完全同源，避免两套门禁漂移）
- 发布用 `pypa/gh-action-pypi-publish` 官方 action 而非 `uv publish`：
  该 action 是 PyPI Trusted Publishing 的标准实现；`uv build` 只负责产出 dist
- 版本一致性校验放在 publish 前（tag != pyproject.version 直接 fail）

## 完成记录

2026-08-24 完成：

- `.github/workflows/ci.yml`：push(develop/main)+PR → uv sync → `make check`
  （与本地完全同源的四道门禁，含 90% 覆盖率卡控）
- `.github/workflows/publish.yml`：push `v*` tag → 校验 tag==pyproject.version
  （`uv version --short`）→ `uv build` → `pypa/gh-action-pypi-publish@release/v1`
  以 OIDC 免密钥上传；workflow YAML 已本地校验
- AGENTS.md 发版流程更新：步骤 6 改为"自动（push tag）/手动（环境变量）二选一"
- **用户侧待办**（一次性）：PyPI 项目页 Settings → Publishing 绑定
  Owner=comet-7x / repo=opencode-client-python / workflow=publish.yml；
  之后 push v* tag 即自动发版

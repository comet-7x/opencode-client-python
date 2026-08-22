# 常用命令入口（底层仍用 uv 驱动，见 .agent/AGENTS.md「常用命令」）
UV_RUN := uv run

.PHONY: help install test lint format format-check types check clean

help: ## 显示所有目标
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

install: ## 安装依赖（uv sync；等价 pip install -e ".[dev]"）
	uv sync

test: ## 运行全部测试（pytest，含 examples 离线冒烟）
	$(UV_RUN) pytest

lint: ## ruff 静态检查
	$(UV_RUN) ruff check .

format: ## ruff 格式化
	$(UV_RUN) ruff format .

format-check: ## 仅检查格式（提交前/CI 用）
	$(UV_RUN) ruff format --check .

types: ## 类型检查（mypy 全量 + pyright strict，src 与 tests 一起查）
	$(UV_RUN) mypy src/ tests/
	$(UV_RUN) pyright

check: format-check lint types test ## 全量质量门禁（提交前必须全绿）
	@echo "✓ all gates passed"

clean: ## 清理构建产物与工具缓存（不动 .venv）
	rm -rf dist build .mypy_cache .pytest_cache .ruff_cache
	find . -type d \( -name __pycache__ -o -name .pyright -o -name "*.egg-info" \) -not -path "./.venv/*" -not -path "./temp/*" -exec rm -rf {} +

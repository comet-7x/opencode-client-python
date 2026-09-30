# 常用命令入口（底层仍用 uv 驱动，见 .agent/AGENTS.md「常用命令」）
UV_RUN := uv run

# ---- 本地服务（Docker）默认值 -------------------------------------------
# 服务定义见 docker-compose.yml（唯一声明源）；这里只是给它喂默认值。
# 官方镜像；最新版本查 https://github.com/anomalyco/opencode/pkgs/container/opencode
# （发布页 "Latest" 即最新 tag），升级时改这里即可。
# 拉取慢时换域名代理（ghcr.io -> ghcr.nju.edu.cn 或 ghcr.m.daocloud.io），
# 拉完用 docker tag 还原官方名再 up，详见 .agent/AGENTS.md「本地服务（Docker）」。
OC_IMAGE ?= ghcr.io/anomalyco/opencode:1.18.21
OC_PORT  ?= 4096
OC_HOST  ?= 0.0.0.0
COMPOSE  ?= docker compose

.PHONY: help install test coverage lint format format-check types check clean \
        docker-pull docker-run docker-tui docker-stop docker-logs docker-health

help: ## 显示所有目标
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

install: ## 安装依赖（uv sync；等价 pip install -e ".[dev]"）
	uv sync

test: ## 运行全部测试（pytest，含 examples 离线冒烟 + 覆盖率门禁）
	$(UV_RUN) pytest --cov=src/opencode_client --cov-report=term-missing --cov-fail-under=90

coverage: ## 跑测试并输出 src 分模块覆盖率报告（同 test，不带阈值）
	$(UV_RUN) pytest --cov=src/opencode_client --cov-report=term-missing

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

# ---- 本地服务（Docker，管理 opencode 服务；见 AGENTS.md「本地服务（Docker）」）----
docker-pull: ## 拉取官方镜像（慢时换 OC_IMAGE 为域名代理，如 ghcr.nju.edu.cn/anomalyco/opencode:1.18.21）
	docker pull $(OC_IMAGE)

docker-run: ## 后台启动 API 服务（默认端口 4096；先 docker-pull）
	OC_IMAGE=$(OC_IMAGE) OC_PORT=$(OC_PORT) OC_HOST=$(OC_HOST) $(COMPOSE) up -d

docker-tui: ## 交互式 TUI（临时容器，Ctrl-D 退出即删；entrypoint 已是 opencode，参数只写子命令）
	docker run -it --rm -v $(PWD):/app $(OC_IMAGE) tui

docker-stop: ## 停止并移除容器（配置在 ~/.config/opencode 持久化，不受影响）
	-OC_PORT=$(OC_PORT) $(COMPOSE) down

docker-logs: ## 查看服务日志（排查启动报错）
	$(COMPOSE) logs -f

docker-health: ## 探活（期望返回 {"healthy": true, ...}）
	@curl -fsS http://127.0.0.1:$(OC_PORT)/global/health && echo

clean: ## 清理构建产物与工具缓存（不动 .venv）
	rm -rf dist build .mypy_cache .pytest_cache .ruff_cache
	find . -type d \( -name __pycache__ -o -name .pyright -o -name "*.egg-info" \) -not -path "./.venv/*" -not -path "./temp/*" -exec rm -rf {} +

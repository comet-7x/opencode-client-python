# AGENTS.md

> 本文件真实位置是 `.agent/AGENTS.md`；根目录 `AGENTS.md` / `CLAUDE.md` 是指向它的
> symlink。修改项目指令只编辑本文件，不要动根目录 symlink。

## 项目简介

`opencode serve` 的轻量 Python 客户端库（REST API 封装：会话管理、消息、SSE 事件流、
VCS/MCP/files/project/auth）。双客户端 `OpenCodeClient`（sync）/
`AsyncOpenCodeClient`（async）方法签名完全一致（async 侧仅多 `await`）。
手写 httpx + pydantic v2，无代码生成。Python >= 3.11。

参考仓库（`temp/` 下，gitignore、只读、已排除 lint/typecheck，**不要修改**）：

- `temp/repositories/opencode` —— **opencode 官方源码**（TS/bun monorepo），端点行为
  /事件语义的最终依据：副作用、阻塞语义先查 `packages/server/src/handlers/*`，再查 schema
- `temp/repositories/opencode-sdk-python` —— 官方 SDK（旧版 Stainless 生成代码），
  仅借鉴风格，字段可能过时
- `.agent/learning_log/get_opencode_api/opencode_rest_api.json` —— 服务端 `/doc`
  导出的 OpenAPI 3.1（162 paths）；新增端点先查它的路径/参数/schema

## 常用命令

```sh
make install            # = uv sync（editable + dev 依赖）
make check              # 全部门禁：format-check + lint + types + test（提交前必跑）
make test               # = pytest --cov-fail-under=90；testpaths 含 tests/ + examples/
                        # （examples 冒烟用 respx 离线跑；覆盖率门禁 90% 是真实门禁）
make coverage           # 同 test 但只报告 src 分模块覆盖率、不带 90% 门禁
make lint               # = uv run ruff check .
make format             # = uv run ruff format .
make types              # mypy src/ tests/ + pyright（strict），两者都要过
```

- 单测：`uv run pytest tests/test_sse.py -k reconnect`（标准 pytest 语法）。
- live 集成测试 opt-in：`uv run pytest --live-url http://127.0.0.1:20001`
  （可加 `--live-password`，用户名默认 `opencode`）；不给 flag 时
  `tests/test_live_server.py` 整模块 skip、不触网。
- pytest 配置（`pyproject.toml`）：`asyncio_mode=auto`（async 测试无需 marker）、
  `xfail_strict=true`（xfail 通过即失败）。
- 测试是 hermetic 的：`tests/conftest.py` 的 session fixture 会清掉环境 proxy 变量
  （本机有全局 proxy，会劫持 localhost 请求）。自己写脚本直连 localhost 时
  用 `curl --noproxy '*'`。

## 发版流程与状态

**包名 `opencode-client-python`**（PyPI 名；导入名始终是 `opencode_client`，
`opencode-client` 已被第三方占用故更名）。

发版步骤（按序，全部完成后才算闭环）：

```sh
# 1. CHANGELOG.md：[Unreleased] 改成 [x.y.z] - 日期，并补 compare 链接（发版说明底稿）
# 2. pyproject.toml：version 升级；constants.py 的 DEFAULT_USER_AGENT 同步版本号
# 3. 质量门禁
make check
# 4. 构建 dist（wheel + sdist）
uv build
# 5. 提交 + 打 tag（push tag 即触发 publish.yml 自动构建上传 PyPI）
git add -A && git commit -m "release: vx.y.z ..." && git tag -a vx.y.z -m "..."
# 6. 上传 PyPI——两种方式二选一：
#    a) 自动：git push origin develop --tags（需已在 PyPI 绑定 Trusted
#       Publishing，见下）；CI 会校验 tag 与 pyproject 版本一致
#    b) 手动（⚠️ uv publish 不读 ~/.pypirc！用环境变量免交互）
export UV_PUBLISH_USERNAME=__token__
export UV_PUBLISH_PASSWORD=pypi-...   # 建议项目 scoped token
uv publish
# 7. GitHub Release（CHANGELOG 对应段落作为 notes）
gh release create vx.y.z --title "vx.y.z" --notes-file <notes> --latest
# 8. 推远端
git push origin develop --tags
```

当前发布进度：

| 版本 | 状态 |
|---|---|
| v0.1.0 | ✅ 2026-08-22（旧名 `opencode-client`，仅本地 dist + tag） |
| v0.2.0 | ✅ 2026-08-24 **已上 PyPI**（新名首发）：https://pypi.org/project/opencode-client-python/ ；GitHub Release 同步创建；核心资源域 API 100%，详见 `api_coverage.md` |

注意事项：
- token 属密钥：只放环境变量/keyring，**绝不入库**；建议 scope 收紧到本项目
- GitHub Release 页的 "Source code (zip/tar.gz)" 是 tag 快照自动生成，
  不是构建产物；正式产物只有 PyPI 上的 `.whl` + `.tar.gz`
- **CI**：`.github/workflows/ci.yml`（push develop/main + PR 跑与本地同源的
  `make check`）；`.github/workflows/publish.yml`（push `v*` tag 自动发 PyPI，
  Trusted Publishing OIDC 免密钥——首次需在 PyPI 项目页
  Settings → Publishing 绑定 workflow 名 `publish.yml`）


## 本地服务（Docker）

开发/联调需要真实 `opencode serve`；统一用 **Docker** 管理（不自建进程），默认端口 `20001`：

```sh
make docker-pull        # 拉 ghcr.io/anomalyco/opencode:1.18.21
make docker-run         # 后台起 API（./ -> /app，~/.config/opencode -> /root/.config/opencode）
make docker-health      # curl /global/health
make docker-logs / make docker-stop / make docker-tui
```

- `docker-compose.yml` 是唯一声明源；`OC_IMAGE`/`OC_PORT`/`OC_HOST` 经 `.env` 覆盖
  （`cp .env.template .env`）；一次性覆盖直接前置环境变量（`OC_PORT=20002 ...`）。
  镜像 pin 三处同步：`.env.template` / Makefile / compose 兜底值。
- **拉镜像慢**：换域名代理（不改全局 Docker 配置），拉完 `docker tag` 还原官方名：
  `ghcr.io` → `ghcr.nju.edu.cn` 或 `ghcr.m.daocloud.io`。
- 镜像 entrypoint 已是 `opencode`，compose 的 `command` 只写子命令（`serve ...`）；
  写全名会拼成 `opencode opencode serve`，容器秒退。
- **探活先确认应答方**：宿主机若另跑原生 `opencode serve` 占同端口，curl 打到的是它
  （`lsof -iTCP:20001` 可查；`docker ps` 是第一手）。
- `temp/` 与 `.venv/` 用空命名卷（`temp-shadow`/`venv-shadow`）遮蔽——bind mount
  无法负向排除子路径；**不要删这两个卷**。
- **Mac 专属**：模型服务（vLLM）在宿主机时容器内不能用 `127.0.0.1`，provider 的
  `baseURL` 用 `http://host.docker.internal:8000/v1`（provider 配置经挂载复用）。
- examples 默认服务地址是 **4096**；Docker 服务在 20001 时加
  `--url http://127.0.0.1:20001`（多数脚本支持）。

## 代码结构（src 布局）

```
src/opencode_client/
  __init__.py    # 公开 API 唯一入口；import 列表与 __all__ 必须同步维护
  client.py      # 双客户端：传输/重试 + 资源挂载（self.sessions/server/vcs/mcp/
                 #   files/projects/auth）
  errors.py      # 分层异常 + make_api_error/make_transport_error（映射逻辑只在这里）
  sse.py         # SSEDecoder（热事件自动类型化）+ EventStream/AsyncEventStream（自动重连）
  router.py      # EventRouter/AsyncEventRouter（stream.route() 返回）
  constants.py   # 默认值：超时（connect 5s/read 60s）/重试 2 次/重连预算 5 次/User-Agent
  _types.py      # NOT_GIVEN 哨兵（with_options 与可选参数用）
  models/        # pydantic 模型按实体拆文件，__init__ 统一 re-export；
                 #   base.py = OpencodeModel 基类 + id_alias 生成器
  resources/     # API 资源层按端点域分文件，每域 sync/async 双类 + *WithRawResponse 代理
    _wire.py     # 共享 wire 纯函数（路径/query/body 组装、TypeAdapter 解析）
tests/           # pytest + respx；conftest.py = hermetic proxy + --live-url 选项
examples/        # 教学示例按功能模块分目录，各带 cli() + README.md；
                 #   test_examples.py 用 importlib + respx 离线驱动
.agent/          # 多 Agent 共享区：AGENTS.md 真身 / project_progress / learning_log /
                 #   skills / plugins
temp/repositories/ # 参考仓库（见上）
```

## 扩展配方

- **加新端点**：先查 OpenAPI json（路径/参数/schema），行为存疑查官方源码 handler；
  按域放进已有资源文件（新域建 `resources/<域>.py`，`class XxxResource(Resource)` +
  `class AsyncXxxResource(AsyncResource)` 双类，在 `client.py` 挂载、
  `resources/__init__.py` 导出）。**wire 细节一律走 `_wire.py` 纯函数，双类方法体
  只写「send + validate」。**
- **加新模型**：放进 `models/<实体>.py`，继承 `OpencodeModel`，在 `models/__init__.py`
  的 import + `__all__` 注册。资源层只 import 公开名（`from ..models import Session`），
  不 import 子模块路径。
- **加新端点必须同步加 `*WithRawResponse` 代理**（镜像全部方法、签名一致、成功返回
  未解析 `httpx.Response`；`stream_events` 无 raw 变体）；
  `tests/test_raw_response.py` 的镜像一致性锁把守。
- **加新热事件**：加 `EventType` 成员（若缺）+ 类型化子类（复用现有模型）+
  `EVENT_CATALOG` 条目；事件面权威源是 OpenAPI json 的 `EventXxx` schema 组
  （生成 SDK 有漂移）。
- **examples 只按功能模块分目录**（quickstart/sessions/server/events/vcs/mcp/files/
  projects/client）；**禁止按难度/模式分类**（不出现 `advanced/` 之类）、
  **不用数字前缀**；客户端本体能力（连接配置、错误处理、裸响应）归 `client/`。

## 约定

- **sync/async 命名：裸名 = sync，`Async` 前缀 = async**（对齐官方 SDK/httpx 生态）；
  **禁止 `Sync` 前缀**。全家族统一：`EventStream`/`AsyncEventStream`、
  `EventRouter`/`AsyncEventRouter` 等。
- **导出规则**：对外 API 唯一入口是包根（`from opencode_client import X`）；
  子包仅 `models` 允许用户直接 import（`client`/`errors`/`sse`/`constants` 也可），
  `resources/*` 与 `models/*` 具体子模块是实现细节，**禁止在对外文档/示例中引用**。
  `examples/`、`tests/` 一律从包根或 `opencode_client.models` import。
- **wire 格式**：camelCase，ID 字段是大写 `ID` 后缀（`sessionID` 不是 `sessionId`）；
  `models/base.py` 的 `id_alias` 统一映射，个别特例用显式 `Field(alias=...)`
  （如 `TextMatch` 是 snake_case 特例）。
- **docstring（ruff `D` 强制）**：每个模块/类/公开函数必须有（`tests/`、`examples/`
  豁免）；Google 风格（一行摘要 ≤120 列 + `Args:`/`Returns:`/`Raises:`）。
- **代码内注释英文、只解释 why**（怪癖绕过、非显然时序）；**例外：`examples/` 是
  教学材料，允许中文行内注释**；`src/`、`tests/` 一律英文。
- 客户端保持轻量：响应解析走模块级 `TypeAdapter` 常量（资源文件顶部）；query 参数
  平铺为关键字参数（`directory`/`workspace` 等）。
- **错误**：非 2xx 按状态码抛（404→`OpenCodeNotFoundError`、429→`OpenCodeRateLimitError`、
  5xx→`OpenCodeServerError`，基类 `OpenCodeApiError`）；连接/超时→`OpenCodeTransportError`
  子类。429/5xx/连接错误自动重试（`max_retries`，指数退避 + `Retry-After`）；
  `with_options(...)` 用 `NOT_GIVEN` 哨兵精确 override。
- **事件流**（`/event`，SSE）：`stream.aiter_events()`/`iter_events()` 得 `Event`；
  6 个热事件自动类型化（`message.part.updated`/`message.part.delta`/`message.updated`/
  `session.idle`/`permission.asked`/`question.asked`），未知类型与解析失败回落基类
  （流永不断）；`EventType` 是开放集 StrEnum（57 成员，服务端新类型以基类流过）。
  `stream.route(session_id)` 返回 Router：`on(type, handler)` 订阅、按到达序分发、
  `run(until=, timeout=)` 统一收口（handler 抛错向外传播）。
  自动重连仅**传输错误**触发（指数退避，预算 `max_reconnect_attempts`，收任意行
  重置预算）；**干净 EOF 结束迭代**；在途半帧丢弃（服务端不重放）。
- 从官方 SDK 移植时：它是 Stainless 生成的重型代码，本项目只挑需要的部分，
  保持轻量手写风格，不要整体拷贝生成目录。

## 多 Agent 共享布局

- 技能/插件写一份、全 Agent 生效：内容放 `.agent/skills/<name>/SKILL.md` 与
  `.agent/plugins/`，经 symlink（`.claude/skills`、`.opencode/skill`、
  `.opencode/plugin`）接入。
- 进度文档与 API 资料收敛在 `.agent/` 内（见下节与「项目简介」）。

## 项目进度（必读）

进度唯一事实来源 `.agent/project_progress/`（规则见其 README）：

- **开始工作前**：读 `.agent/project_progress/BOARD.md`，确认当前宏观阶段/微观迭代。
- **完成工作后**：更新对应 `iterations/IT-XXX-*.md` 的任务状态，并同步 `BOARD.md`；
  跨阶段决策与发版信息写入 `macro/ROADMAP.md`；API 覆盖进度看
  `project_progress/api_coverage.md`。
- **发版**：流程与当前发布状态见上方「发版流程与状态」一节。
- **Code review 报告是时点产物，不在 `.agent/` 堆叠**：问题修完即把结论（含踩坑）
  沉淀进迭代文件，报告本身删除或只留本地（如 `temp/code_review/`，不入库）；
  未修复遗留项写进 BOARD 阻塞区即可。

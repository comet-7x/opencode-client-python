# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-08-22

First public release.

### Added

- **Dual clients with identical API**: `OpenCodeClient` (sync) and
  `AsyncOpenCodeClient` (async) — same methods, the async side adds `await`.
- **Session management** (`client.sessions.*`): `list_sessions`, `create`,
  `get`, `update`, `delete`, `fork`, `abort`, `share`, `unshare`,
  `summarize`, `respond_permission`, `list_messages`, `prompt`,
  `prompt_async`, `delete_message`.
- **Server endpoints** (`client.server.*`): `health`, `get_config`,
  `update_config`, `list_providers`, `list_agents`, `list_commands`,
  `list_skills`, `list_permissions`, `reply_permission`, `list_questions`,
  `reply_question`, `reject_question`, `stream_events`.
- **VCS endpoints** (`client.vcs.*`): `info`, `status`, `diff`, `diff_raw`,
  `apply`.
- **MCP endpoints** (`client.mcp.*`): `status`, `add`.
- **SSE event stream with auto-reconnection**: `stream_events()` yields
  decoded `Event` objects; transport errors are retried with exponential
  backoff (0.5 s → 8 s, budget `max_reconnect_attempts`, reset on any line);
  a clean EOF ends the iteration.
- **Automatic request retries**: 429 (honoring `Retry-After`), 5xx and
  connection errors are retried `max_retries` times with exponential backoff.
- **Layered exceptions** rooted at `OpenCodeError`: `OpenCodeApiError`
  (with `status_code` + `payload`) with per-status subclasses (401/403/404/
  409/422/429/5xx), and `OpenCodeTransportError` with
  `OpenCodeTimeoutError` / `OpenCodeServerConnectionError`.
- **Typed responses**: every endpoint is parsed into pydantic v2 models; the
  server's camelCase / uppercase-`ID` wire fields map to `snake_case`
  attributes automatically.
- **`client.with_options(...)`**: derive a new client overriding only the
  settings passed (`NOT_GIVEN` sentinel keeps the rest).
- **Bilingual docs**: `README.md` (English) + `README-CN.md` (Chinese),
  scenario-based runnable examples in `examples/` (00_quickstart through
  05_advanced_patterns), all smoke-tested offline with respx.
- **Docker-managed local server**: `make docker-pull/run/tui/stop/logs/health`
  targets (default port 20001).

[0.1.0]: https://github.com/comet-7x/opencode-client-python/releases/tag/v0.1.0

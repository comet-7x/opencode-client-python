# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Typed hot events & event router**: frequently consumed `/event` types
  now arrive as typed subclasses (`message.part.updated` → `event.part: Part`,
  `message.part.delta`, `message.updated`, `session.idle`, `permission.asked`,
  `question.asked`), reusing the existing models; unknown types and payloads
  that no longer validate degrade to the base `Event`, so the stream never
  breaks. `stream.route(session_id)` returns an `AsyncEventRouter` /
  `EventRouter` for subscription-based consumption (`on(type, handler)`
  dispatches in arrival order; `run(until=, timeout=)` stops on the `until`
  type, a raising handler, the timeout, or a clean stream end). `EventType`
  is an open-set `StrEnum` (57 members from the server's v1 event surface)
  usable in place of raw strings; the plain `aiter_events()` /
  `iter_events()` iterators are unchanged.
- **Raw response view** (`with_raw_response`): every resource group
  (`sessions` / `server` / `vcs` / `mcp`), in both sync and async flavours,
  exposes a `<resource>.with_raw_response` prefix whose methods mirror the
  parsed ones one-for-one but return the unprocessed `httpx.Response` on
  success — handy for reading response headers, exact status codes, or the
  body before model mapping. Retries and non-2xx error mapping are shared
  with the normal view; `stream_events` has no raw variant (it yields an
  event stream, not a one-shot response).

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

[Unreleased]: https://github.com/comet-7x/opencode-client-python/compare/v0.1.0...develop
[0.1.0]: https://github.com/comet-7x/opencode-client-python/releases/tag/v0.1.0

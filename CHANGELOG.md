# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Files domain** (`client.files.*`): directory listing (`list`), content
  reads with a text/binary discriminated union (`read`), git-style change
  status (`status`), ripgrep-style text search with line numbers and
  submatch spans (`search_text`), fuzzy filename search (`search_files`,
  string-boolean `dirs` handled client-side), LSP workspace symbol search
  (`search_symbols`), and registered formatters (`formatter_status`).
- **MCP lifecycle completion** (`client.mcp.*`): the full `/mcp` family —
  OAuth flows (`start_oauth` / `complete_oauth` browser flow,
  `authenticate` headless flow, `remove_oauth`) plus explicit
  `connect` / `disconnect`.
- **Projects domain** (`client.projects.*`): `list`, `current`, partial
  `update` (name/icon/commands), per-project `directories`, and
  `git_init`.
- **Auth domain** (`client.auth.*`): provider credential management
  (`set_credentials` / `remove_credentials`; oauth / api / wellknown
  discriminated union) and provider OAuth flows
  (`provider_auth_methods` / `start_provider_oauth` /
  `complete_provider_oauth`).
- **Server system endpoints**: `get_paths`, `lsp_status`, `write_log`,
  global config read/patch (`get_global_config` / `update_global_config`),
  the global SSE stream (`stream_global_events`, `GlobalEvent` envelope),
  instance/global disposal, and self-upgrade (`upgrade_global`).
- **Single message fetch**: `sessions.get_message(session_id, message_id)`.
- **Coverage & live-test infrastructure**: pytest-cov with a 90% gate in
  `make test` (~92% measured); an opt-in live suite
  (`pytest --live-url ...`, 11 read-only tests) and a full-surface live
  sweep covering every public method against a real opencode server.

### Fixed

- **Default timeout unusable for blocking calls**: the default is now a
  layered `httpx.Timeout(read=60s, connect=5s)` instead of a flat 5 s —
  blocking calls like `sessions.prompt()` wait for the whole LLM turn.
- **Retry idempotency awareness**: transport failures are retried on
  idempotent methods always, and on non-idempotent ones only when the
  request provably never reached the server (connection-phase errors);
  read timeouts no longer blindly re-send `POST`s.
- **Sync `EventRouter.run(timeout=...)` now enforces a real wall-clock
  deadline** (worker-thread watchdog), matching the async twin; previously
  a silent stream blocked past the timeout indefinitely.
- **Response schema drift surfaces as `OpenCodeResponseError`** (an
  `OpenCodeError` subclass carrying the original `pydantic.ValidationError`)
  instead of leaking pydantic exceptions past `except OpenCodeError`.
- **SSE decoder hardening**: frames outside the instance-event envelope
  (e.g. `/global/event` wrappers) degrade to a base event instead of
  breaking the stream.
- `Retry-After` headers in HTTP-date form are honoured (previously only
  delta-seconds); retry responses are closed before backing off;
  path parameters are percent-encoded.

### Changed

- Examples are organised purely by functional module
  (`quickstart/sessions/server/events/vcs/mcp/files/projects/client`);
  every one of the library's 69 public resource methods has a runnable
  demonstration.

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

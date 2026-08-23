# opencode-client

A lightweight Python client for the [opencode](https://opencode.ai) server.
Connect to an `opencode serve` process and drive it programmatically:
manage sessions, send prompts, inspect messages, answer permission/question
prompts, inspect VCS state, manage MCP servers, and consume the live event
stream — with both **synchronous** and **asynchronous** clients sharing one
API surface.

- **Typed responses**: every endpoint is parsed into a pydantic v2 model
  (the server's camelCase / uppercase-`ID` wire fields map to `snake_case`
  attributes automatically).
- **Resilient**: automatic retries with exponential backoff for 429 / 5xx /
  connection errors (honors `Retry-After`), plus a layered exception
  hierarchy so you can catch exactly what you need.
- **Live streams**: the `/event` SSE endpoint is exposed as an iterable with
  built-in auto-reconnection (drops are retried with backoff; a clean EOF
  ends the iteration).
- **Sync + async parity**: `OpenCodeClient` and `AsyncOpenCodeClient` have
  identical method signatures — the async one just adds `await`.
- **Deliberately small**: no code generation, no heavyweight runtime —
  a handful of small modules wrapping `httpx`.

> 🇨🇳 中文文档见 [README-CN.md](README-CN.md)

## Requirements

- Python **>= 3.11**
- A running `opencode serve` process to talk to (see [Running a local server](#running-a-local-server-docker))

## Installation

The package is not on PyPI yet; install from this repository:

```sh
git clone https://github.com/comet-7x/opencode-client-python.git
cd opencode-client-python
pip install .            # or: uv pip install .
```

For development (tests, linters, type checkers):

```sh
make install             # = uv sync, editable install + dev tools
```

## Quick start

### Async

```python
import asyncio
from opencode_client import AsyncOpenCodeClient


async def main() -> None:
    async with AsyncOpenCodeClient("http://127.0.0.1:4096") as client:
        print((await client.server.health()).version)
        session = await client.sessions.create()
        reply = await client.sessions.prompt(session.id, "Hello!")
        print([p.text for p in reply.parts if p.type == "text"])


asyncio.run(main())
```

### Sync

```python
from opencode_client import OpenCodeClient

with OpenCodeClient("http://127.0.0.1:4096") as client:
    print(client.server.health().version)
    session = client.sessions.create()
    reply = client.sessions.prompt(session.id, "Hello!")
```

Client options: `base_url` (required), `username` / `password` (Basic auth,
optional), `timeout` (seconds, default 5), `max_retries` (default 2). Use
`client.with_options(...)` to derive a new client that overrides only the
settings you pass.

## Resource groups

The API is grouped by endpoint domain under the client:

| Group | Methods |
|---|---|
| `client.sessions.*` | `list_sessions` `create` `get` `update` `delete` `fork` `abort` `share` `unshare` `summarize` `respond_permission` `list_messages` `prompt` `prompt_async` `delete_message` |
| `client.server.*` | `health` `get_config` `update_config` `list_providers` `list_agents` `list_commands` `list_skills` `list_permissions` `reply_permission` `list_questions` `reply_question` `reject_question` `stream_events` |
| `client.vcs.*` | `info` `status` `diff` `diff_raw` `apply` |
| `client.mcp.*` | `status` `add` |

Most methods take optional `directory` / `workspace` scoping query params
passed as plain keyword arguments.

## Error handling

Non-2xx responses raise from a single hierarchy rooted at `OpenCodeError`:

```
OpenCodeError
├── OpenCodeApiError            (status_code + payload)
│   ├── OpenCodeAuthenticationError   (401)
│   ├── OpenCodePermissionError       (403)
│   ├── OpenCodeNotFoundError         (404)
│   ├── OpenCodeConflictError         (409)
│   ├── OpenCodeUnprocessableEntityError (422)
│   ├── OpenCodeRateLimitError        (429)
│   └── OpenCodeServerError           (5xx)
└── OpenCodeTransportError        (no HTTP response at all)
    ├── OpenCodeServerConnectionError
    └── OpenCodeTimeoutError
```

```python
from opencode_client import OpenCodeApiError, OpenCodeNotFoundError, OpenCodeTransportError

try:
    session = await client.sessions.get("ses_missing")
except OpenCodeNotFoundError as exc:
    print(f"missing: {exc.status_code}")
except OpenCodeApiError as exc:
    print(exc.status_code, exc.payload)
except OpenCodeTransportError as exc:
    print("server unreachable:", exc)
```

Transient failures (429 / 5xx / connection errors) are retried automatically
`max_retries` times with exponential backoff before raising.

## Event stream (SSE)

`server.stream_events()` opens the `/event` stream as a context manager;
iterate decoded `Event` objects with automatic reconnection:

```python
async with client.server.stream_events() as stream:
    async for event in stream.aiter_events():
        print(event.type, event.properties)
        if event.type == "session.idle":
            break
```

Reconnection semantics: only **transport errors** trigger a retry (exponential
backoff 0.5 s → 8 s, budget `max_reconnect_attempts`, reset on any received
line); a clean EOF ends the iteration. `prompt_async` + `stream_events` is
the standard pattern for watching a turn live.

## Raw responses

Every method returns a parsed model. For headers, exact status codes, or the
body before model mapping, use the `with_raw_response` prefix — same
signatures, same retries, same error mapping on non-2xx, but the unprocessed
`httpx.Response` on success:

```python
raw = await client.sessions.with_raw_response.get(session_id)
print(raw.status_code, raw.headers["content-type"])
session = Session.model_validate(raw.json())  # parse it yourself if you like
```

Available on all four resource groups (`sessions` / `server` / `vcs` / `mcp`);
`stream_events` has no raw variant (it returns an event stream, not a
one-shot response).

## Running a local server (Docker)

A running `opencode serve` is required. It is declared in
[docker-compose.yml](docker-compose.yml); the Makefile targets below are thin
wrappers around `docker compose`. Default port **20001**, image
`ghcr.io/anomalyco/opencode:1.18.21` (latest listed at
<https://github.com/anomalyco/opencode/pkgs/container/opencode>).
Overrides (`OC_IMAGE` / `OC_PORT` / `OC_HOST`) go in a local `.env` —
`cp .env.template .env` — or as one-off env prefixes
(`OC_PORT=20002 docker compose up -d`):

```sh
make docker-pull        # pull the official image
make docker-run         # start the API server in the background
make docker-health      # curl /global/health
make docker-logs        # inspect logs on trouble
make docker-stop        # stop + remove (config persists in ~/.config/opencode)
make docker-tui         # interactive TUI in a throwaway container
```

`docker-run` mounts the repository into `/app` and `~/.config/opencode` into
the container, so your provider/model configuration is reused. If pulling is
slow, swap the registry domain for a mirror (no global Docker config change),
then tag back to the official name:

```sh
docker pull ghcr.nju.edu.cn/anomalyco/opencode:1.18.21     # or ghcr.m.daocloud.io/...
docker tag  ghcr.nju.edu.cn/anomalyco/opencode:1.18.21 ghcr.io/anomalyco/opencode:1.18.21
```

> **macOS note**: if your model backend (e.g. vLLM) runs on the host, the
> container must reach it via `http://host.docker.internal:8000/v1` — not
> `127.0.0.1`. Set that in the provider's `baseURL` in
> `~/.config/opencode/opencode.json`.

Once healthy, point the client (and all examples/tests) at it:

```sh
uv run python -m examples.00_quickstart.quickstart --url http://127.0.0.1:20001
uv run pytest --live-url http://127.0.0.1:20001   # opt-in integration tests
```

## Examples

Runnable, commented walkthroughs organized by scenario — start at
[examples/README.md](examples/README.md):

| Folder | Topic |
|---|---|
| `00_quickstart/` | Minimal one-question client (incl. `directory` shorthand) |
| `01_session_management/` | Session CRUD + full lifecycle verbs + message history |
| `02_discovery_config/` | Health, config, providers, agents, commands, skills |
| `03_vcs/` | Repo info / status / diff / raw diff / patch apply |
| `04_mcp/` | MCP server status + registration |
| `05_advanced_patterns/` | Client reuse, error handling, live streaming, interaction loops, raw responses |

Every script runs offline under the test suite via `respx`, so
`uv run pytest` verifies them without a server.

## Development

```sh
make install            # uv sync
make test               # pytest (offline)
make lint               # ruff check
make format             # ruff format
make types              # mypy + pyright (strict)
make check              # full gate: format-check + lint + types + test
```

Layout: `src/opencode_client/` (package), `tests/` (pytest + respx),
`examples/` (walkthroughs), `temp/` (reference SDK, excluded from tooling).
Contributor-facing conventions live in [AGENTS.md](AGENTS.md).

## License

[MIT](https://opensource.org/licenses/MIT)

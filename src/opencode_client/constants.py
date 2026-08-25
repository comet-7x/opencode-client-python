"""Package-level constants shared across the client library."""

from __future__ import annotations

import httpx

#: User-Agent sent with every request; server logs use it to identify client versions.
DEFAULT_USER_AGENT = "opencode-client-python/0.1.0"

#: Seconds to wait when establishing a connection.
DEFAULT_CONNECT_TIMEOUT = 5.0

#: Seconds to wait for a response on regular (non-streaming) requests.
#:
#: Deliberately generous: blocking calls like ``sessions.prompt()`` only return
#: after the whole LLM turn finishes, which routinely exceeds a few seconds.
DEFAULT_READ_TIMEOUT = 60.0

#: Default per-phase timeouts used when the caller does not override ``timeout``.
DEFAULT_TIMEOUT = httpx.Timeout(DEFAULT_READ_TIMEOUT, connect=DEFAULT_CONNECT_TIMEOUT)

#: How many times a failed (5xx/429/connection-error) request is retried, on top of the first attempt.
DEFAULT_MAX_RETRIES = 2

#: How many times a dropped ``/event`` stream is reconnected, on top of the first attempt.
#: The budget resets whenever a line is received, so a healthy stream reconnects indefinitely.
DEFAULT_STREAM_RECONNECT_ATTEMPTS = 5

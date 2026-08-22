"""Package-level constants shared across the client library."""

from __future__ import annotations

#: User-Agent sent with every request; server logs use it to identify client versions.
DEFAULT_USER_AGENT = "opencode-client-python/0.1.0"

#: Seconds to wait when establishing a connection (also the default request timeout).
DEFAULT_CONNECT_TIMEOUT = 5.0

#: Seconds to wait for a response on regular (non-streaming) requests.
DEFAULT_READ_TIMEOUT = 60.0

#: How many times a failed (5xx/429/connection-error) request is retried, on top of the first attempt.
DEFAULT_MAX_RETRIES = 2

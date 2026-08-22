"""Shared test fixtures: isolate HTTP tests from the ambient proxy environment.

The library keeps httpx's default ``trust_env=True`` so real users get proxy
support for free; tests must instead be hermetic and route everything through
respx. A session-scoped autouse fixture therefore clears any ambient proxy
variables before the suite runs and restores them afterwards.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

_PROXY_VARS = (
    "all_proxy",
    "ALL_PROXY",
    "http_proxy",
    "HTTP_PROXY",
    "https_proxy",
    "HTTPS_PROXY",
    "no_proxy",
    "NO_PROXY",
)


@pytest.fixture(autouse=True, scope="session")
def hermetic_proxy_env() -> Iterator[None]:
    """Drop ambient proxy variables for the whole test session, restoring them after.

    Without this, an environment with a local SOCKS/HTTP proxy (e.g.
    ``all_proxy=socks5://127.0.0.1:7897``) makes ``httpx.Client`` try to use it
    and raise ``ImportError`` (missing ``socksio``) at client-construction time.
    """
    monkeypatch = pytest.MonkeyPatch()
    for var in _PROXY_VARS:
        if var in os.environ:
            monkeypatch.delenv(var)
    yield
    monkeypatch.undo()

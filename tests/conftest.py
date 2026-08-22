"""Shared test fixtures: hermetic HTTP environment + live-server opt-in.

The library keeps httpx's default ``trust_env=True`` so real users get proxy
support for free; tests must instead be hermetic and route everything through
respx. A session-scoped autouse fixture therefore clears any ambient proxy
variables before the suite runs and restores them afterwards.

Optional: ``pytest --live-url http://127.0.0.1:4096`` points the integration
suite (``tests/test_live_server.py``) at a real running opencode server;
without the flag those tests skip and never touch the network.

``pytest_addoption`` lives here (not in a root conftest) because the live flag
is a tests-only concept. It is registered for every standard invocation —
``make test``, bare ``pytest`` (testpaths = tests + examples), and
``pytest tests/`` all load this conftest. The one combination that would not
recognize the flag is ``pytest examples/ --live-url ...``, which is meaningless
anyway: the examples smoke tests are fully respx-mocked and never open a real
connection.
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


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register the optional live-server endpoints for the integration tests."""
    parser.addoption(
        "--live-url",
        default="",
        help="Base URL of a running opencode server; enables tests/test_live_server.py",
    )
    parser.addoption(
        "--live-password",
        default="",
        help="Basic-auth password for --live-url (username defaults to 'opencode')",
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

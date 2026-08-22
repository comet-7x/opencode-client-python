"""Root pytest hooks: register the optional live-server CLI options.

``--live-url`` / ``--live-password`` (see ``tests/test_live_server.py``) must
be declared here — option hooks in subdirectory conftests are ignored by
pytest — so that any invocation of the suite, including ``pytest --live-url
...``, accepts them and plain runs default to an offline skip.
"""

from __future__ import annotations

import pytest


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

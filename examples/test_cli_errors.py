"""Example CLI transport-error handling: real socket, no respx.

The smoke suite (``test_examples.py``) runs every script under a respx mock;
these tests deliberately do the opposite — point each script at a port with
nothing listening so the ``OpenCodeTransportError`` branch of its ``cli()``
runs for real (connection refused is immediate).  A separate file because
the respx autouse fixture in ``test_examples.py`` would otherwise intercept
the request before it reaches the network.
"""

from __future__ import annotations

import importlib
import sys
from types import ModuleType

import pytest

_PROXY_VARS = (
    "all_proxy",
    "ALL_PROXY",
    "http_proxy",
    "HTTP_PROXY",
    "https_proxy",
    "HTTPS_PROXY",
)

#: (module path, extra cli args) for every example that has the standard
#: transport-error handler in its ``cli()``.
CASES: list[tuple[str, list[str]]] = [
    ("quickstart.quickstart", []),
    ("sessions.create_session", ["--title", "t"]),
    ("sessions.list_sessions", []),
    ("sessions.delete_session", []),
    ("sessions.list_messages", []),
    ("sessions.session_lifecycle", []),
    ("sessions.session_state_history", []),
    ("server.explore_server", []),
    ("vcs.vcs_workflow", ["--directory", "/tmp"]),
    ("mcp.mcp_servers", []),
    ("files.browse_files", []),
    ("files.search_code", ["--pattern", "x"]),
    ("projects.explore_projects", []),
    ("client.client_reuse", []),
    ("client.error_handling", []),
    ("client.raw_response", []),
    ("sessions.interact_moving_session", []),
    ("events.stream_events", []),
    ("events.event_router", []),
]


@pytest.fixture(autouse=True, scope="session")
def clear_proxy_env():
    """Drop ambient proxy variables so 127.0.0.1 really means this machine."""
    import os

    saved: dict[str, str] = {}
    for var in _PROXY_VARS:
        if var in os.environ:
            saved[var] = os.environ.pop(var)
    yield
    os.environ.update(saved)


def _load(pkg: str) -> ModuleType:
    """Import an example module (same helper as the smoke suite)."""
    return importlib.import_module(f"examples.{pkg}")


@pytest.mark.parametrize("pkg,args", CASES)
def test_transport_error_exits_2(pkg: str, args: list[str]) -> None:
    """A dead endpoint must produce the friendly hint and exit code 2."""
    module = _load(pkg)
    sys.argv = [module.__file__, "--url", "http://127.0.0.1:9", *args]
    with pytest.raises(SystemExit) as excinfo:
        module.cli()
    assert excinfo.value.code == 2

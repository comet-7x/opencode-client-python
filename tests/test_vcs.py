"""Tests for the /vcs endpoints (sync + async)."""

from __future__ import annotations

import json
from collections.abc import Generator
from typing import Any

import httpx
import pytest
import respx

from opencode_client import (
    AsyncOpenCodeClient,
    OpenCodeClient,
    OpenCodeNotFoundError,
    VcsFileDiff,
    VcsFileStatus,
    VcsInfo,
)

BASE = "http://localhost:4096"

_PATCH = "--- a/main.py\n+++ b/main.py\n@@ -1 +1 @@\n-print('a')\n+print('b')\n"


def _diff_item(file_: str = "src/x.py") -> dict[str, Any]:
    return {
        "file": file_,
        "patch": f"--- a/{file_}\n+++ b/{file_}\n@@ -1 +1 @@",
        "additions": 2,
        "deletions": 1,
        "status": "modified",
    }


def _status_item(file_: str = "src/x.py") -> dict[str, Any]:
    return {"file": file_, "additions": 2, "deletions": 1, "status": "modified"}


@pytest.fixture(autouse=True)
def mock_server() -> Generator[respx.MockRouter, None, None]:
    with respx.mock(base_url=BASE) as router:
        yield router


class TestVcsSync:
    def test_info_parses_snake_case_fields(self, mock_server: respx.MockRouter) -> None:
        mock_server.get("/vcs").mock(
            return_value=httpx.Response(200, json={"branch": "develop", "default_branch": None})
        )
        with OpenCodeClient(BASE) as client:
            info = client.vcs.info()
        assert isinstance(info, VcsInfo)
        assert info.branch == "develop"
        assert info.default_branch is None
        # round-trip must keep the wire's snake_case key
        assert info.to_wire() == {"branch": "develop"}
        assert VcsInfo.model_validate({"branch": "main", "default_branch": "main"}).to_wire() == {
            "branch": "main",
            "default_branch": "main",
        }

    def test_status_parses_list(self, mock_server: respx.MockRouter) -> None:
        mock_server.get("/vcs/status").mock(return_value=httpx.Response(200, json=[_status_item()]))
        with OpenCodeClient(BASE) as client:
            items = client.vcs.status()
        assert len(items) == 1
        item = items[0]
        assert isinstance(item, VcsFileStatus)
        assert item.status == "modified" and item.additions == 2

    def test_diff_sends_mode_and_context(self, mock_server: respx.MockRouter) -> None:
        mock_server.get("/vcs/diff").mock(return_value=httpx.Response(200, json=[_diff_item()]))
        with OpenCodeClient(BASE) as client:
            items = client.vcs.diff("git", context=3, directory="/tmp/dir")
        assert isinstance(items[0], VcsFileDiff)
        sent = mock_server.get("/vcs/diff").calls.last.request.url.params
        assert sent["mode"] == "git"
        assert sent["context"] == "3"
        assert sent["directory"] == "/tmp/dir"

    def test_diff_raw_returns_text(self, mock_server: respx.MockRouter) -> None:
        mock_server.get("/vcs/diff/raw").mock(
            return_value=httpx.Response(200, content=_PATCH.encode(), headers={"Content-Type": "text/x-diff"})
        )
        with OpenCodeClient(BASE) as client:
            raw = client.vcs.diff_raw()
        assert raw == _PATCH

    def test_apply_sends_patch(self, mock_server: respx.MockRouter) -> None:
        mock_server.post("/vcs/apply").mock(return_value=httpx.Response(200, json={"applied": True}))
        with OpenCodeClient(BASE) as client:
            result = client.vcs.apply(_PATCH)
        assert result == {"applied": True}
        sent = json.loads(mock_server.post("/vcs/apply").calls.last.request.content)
        assert sent == {"patch": _PATCH}

    def test_missing_repo_raises_not_found(self, mock_server: respx.MockRouter) -> None:
        mock_server.get("/vcs").mock(
            return_value=httpx.Response(404, json={"name": "NotFoundError", "data": {"message": "not a git repo"}})
        )
        with OpenCodeClient(BASE) as client:
            with pytest.raises(OpenCodeNotFoundError):
                client.vcs.info(directory="/tmp/nowhere")


class TestVcsAsync:
    async def test_info_and_status(self, mock_server: respx.MockRouter) -> None:
        mock_server.get("/vcs").mock(
            return_value=httpx.Response(200, json={"branch": "main", "default_branch": "main"})
        )
        mock_server.get("/vcs/status").mock(return_value=httpx.Response(200, json=[]))
        async with AsyncOpenCodeClient(BASE) as client:
            info = await client.vcs.info()
            items = await client.vcs.status()
        assert info.branch == "main" and info.default_branch == "main"
        assert items == []

    async def test_diff_and_diff_raw(self, mock_server: respx.MockRouter) -> None:
        mock_server.get("/vcs/diff").mock(return_value=httpx.Response(200, json=[_diff_item()]))
        mock_server.get("/vcs/diff/raw").mock(
            return_value=httpx.Response(200, content=_PATCH.encode(), headers={"Content-Type": "text/x-diff"})
        )
        async with AsyncOpenCodeClient(BASE) as client:
            items = await client.vcs.diff("branch")
            raw = await client.vcs.diff_raw()
        assert len(items) == 1 and raw == _PATCH

    async def test_apply(self, mock_server: respx.MockRouter) -> None:
        mock_server.post("/vcs/apply").mock(return_value=httpx.Response(200, json={"applied": True}))
        async with AsyncOpenCodeClient(BASE) as client:
            result = await client.vcs.apply(_PATCH)
        assert result == {"applied": True}
        sent = json.loads(mock_server.post("/vcs/apply").calls.last.request.content)
        assert sent == {"patch": _PATCH}

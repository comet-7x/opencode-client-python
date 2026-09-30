"""Tests for the files domain: /file*, /find* and /formatter endpoints."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

import httpx
import pytest
import respx

from opencode_client import (
    AsyncOpenCodeClient,
    BinaryFileContent,
    FileNode,
    OpenCodeClient,
    OpenCodeNotFoundError,
    Symbol,
    TextFileContent,
    TextMatch,
)

BASE = "http://localhost:4096"


def _node(name: str, path: str, type_: str = "file") -> dict[str, Any]:
    return {"name": name, "path": path, "absolute": f"/tmp/proj/{path}", "type": type_, "ignored": False}


def _match(path: str = "src/a.py") -> dict[str, Any]:
    return {
        "path": {"text": path},
        "lines": {"text": "def hello():\n"},
        "line_number": 3,
        "absolute_offset": 42,
        "submatches": [{"match": {"text": "hello"}, "start": 4, "end": 9}],
    }


@pytest.fixture(autouse=True)
def mock_server() -> Generator[respx.MockRouter, None, None]:
    with respx.mock(base_url=BASE) as router:
        yield router


class TestSyncFiles:
    def test_list_sends_path_and_parses_nodes(self, mock_server: respx.MockRouter) -> None:
        route = mock_server.get("/file").mock(
            return_value=httpx.Response(200, json=[_node("a.py", "src/a.py"), _node("src", "src", "directory")])
        )
        with OpenCodeClient(BASE) as client:
            nodes = client.files.list("src")
        assert [n.name for n in nodes] == ["a.py", "src"]
        assert isinstance(nodes[1], FileNode)
        assert route.calls.last.request.url.params["path"] == "src"

    def test_read_text_content(self, mock_server: respx.MockRouter) -> None:
        payload = {
            "type": "text",
            "content": "print('hi')\n",
            "diff": "-x\n+y\n",
            "patch": {
                "oldFileName": "a.py",
                "newFileName": "a.py",
                "hunks": [{"oldStart": 1, "oldLines": 1, "newStart": 1, "newLines": 1, "lines": ["-x", "+y"]}],
            },
        }
        mock_server.get("/file/content").mock(return_value=httpx.Response(200, json=payload))
        with OpenCodeClient(BASE) as client:
            content = client.files.read("a.py")
        assert isinstance(content, TextFileContent)
        assert content.content == "print('hi')\n"
        assert content.patch is not None
        assert content.patch.hunks[0].lines == ["-x", "+y"]

    def test_read_binary_content(self, mock_server: respx.MockRouter) -> None:
        payload = {"type": "binary", "content": "aGVsbG8=", "encoding": "base64", "mimeType": "image/png"}
        mock_server.get("/file/content").mock(return_value=httpx.Response(200, json=payload))
        with OpenCodeClient(BASE) as client:
            content = client.files.read("logo.png")
        assert isinstance(content, BinaryFileContent)
        assert content.encoding == "base64"
        assert content.mime_type == "image/png"

    def test_status_parses_changes(self, mock_server: respx.MockRouter) -> None:
        payload = [{"path": "a.py", "added": 2, "removed": 1, "status": "modified"}]
        mock_server.get("/file/status").mock(return_value=httpx.Response(200, json=payload))
        with OpenCodeClient(BASE) as client:
            changes = client.files.status()
        assert changes[0].status == "modified"
        assert (changes[0].added, changes[0].removed) == (2, 1)

    def test_search_text_parses_snake_case_wire(self, mock_server: respx.MockRouter) -> None:
        route = mock_server.get("/find").mock(return_value=httpx.Response(200, json=[_match()]))
        with OpenCodeClient(BASE) as client:
            matches = client.files.search_text("hello")
        m = matches[0]
        assert isinstance(m, TextMatch)
        # wire is snake_case here (line_number/absolute_offset), unlike the rest of the API
        assert (m.line_number, m.absolute_offset) == (3, 42)
        assert m.path.text == "src/a.py"
        assert m.submatches[0].match.text == "hello"
        assert route.calls.last.request.url.params["pattern"] == "hello"

    def test_search_files_forwards_string_boolean_and_filters(self, mock_server: respx.MockRouter) -> None:
        route = mock_server.get("/find/file").mock(return_value=httpx.Response(200, json=["src/a.py"]))
        with OpenCodeClient(BASE) as client:
            paths = client.files.search_files("a.py", dirs=False, type="file", limit=5)
        assert paths == ["src/a.py"]
        params = route.calls.last.request.url.params
        assert params["query"] == "a.py"
        assert params["dirs"] == "false"
        assert params["type"] == "file"
        assert params["limit"] == "5"

    def test_search_files_omits_unset_params(self, mock_server: respx.MockRouter) -> None:
        route = mock_server.get("/find/file").mock(return_value=httpx.Response(200, json=[]))
        with OpenCodeClient(BASE) as client:
            client.files.search_files("x")
        params = route.calls.last.request.url.params
        assert set(params.keys()) == {"query"}

    def test_search_symbols_parses_lsp_shape(self, mock_server: respx.MockRouter) -> None:
        payload = [
            {
                "name": "hello",
                "kind": 12,
                "location": {
                    "uri": "file:///tmp/proj/src/a.py",
                    "range": {
                        "start": {"line": 2, "character": 4},
                        "end": {"line": 2, "character": 9},
                    },
                },
            }
        ]
        route = mock_server.get("/find/symbol").mock(return_value=httpx.Response(200, json=payload))
        with OpenCodeClient(BASE) as client:
            symbols = client.files.search_symbols("hello")
        s = symbols[0]
        assert isinstance(s, Symbol)
        assert s.kind == 12
        assert s.location.range.start.line == 2
        assert route.calls.last.request.url.params["query"] == "hello"

    def test_formatter_status_parses(self, mock_server: respx.MockRouter) -> None:
        payload = [{"name": "ruff", "extensions": [".py"], "enabled": True}]
        mock_server.get("/formatter").mock(return_value=httpx.Response(200, json=payload))
        with OpenCodeClient(BASE) as client:
            formatters = client.files.formatter_status()
        assert formatters[0].name == "ruff"
        assert formatters[0].enabled is True

    def test_missing_file_maps_to_not_found(self, mock_server: respx.MockRouter) -> None:
        mock_server.get("/file/content").mock(
            return_value=httpx.Response(404, json={"name": "NotFound", "data": {"message": "nope"}})
        )
        with OpenCodeClient(BASE) as client:
            with pytest.raises(OpenCodeNotFoundError):
                client.files.read("missing.py")


class TestAsyncFiles:
    async def test_list_read_status_roundtrip(self, mock_server: respx.MockRouter) -> None:
        mock_server.get("/file").mock(return_value=httpx.Response(200, json=[_node("a.py", "a.py")]))
        mock_server.get("/file/content").mock(return_value=httpx.Response(200, json={"type": "text", "content": "x"}))
        mock_server.get("/file/status").mock(return_value=httpx.Response(200, json=[]))
        async with AsyncOpenCodeClient(BASE) as client:
            nodes = await client.files.list("")
            content = await client.files.read("a.py")
            changes = await client.files.status()
        assert nodes[0].name == "a.py"
        assert isinstance(content, TextFileContent)
        assert changes == []

    async def test_find_endpoints(self, mock_server: respx.MockRouter) -> None:
        mock_server.get("/find").mock(return_value=httpx.Response(200, json=[_match()]))
        mock_server.get("/find/file").mock(return_value=httpx.Response(200, json=["b.py"]))
        mock_server.get("/find/symbol").mock(return_value=httpx.Response(200, json=[]))
        mock_server.get("/formatter").mock(return_value=httpx.Response(200, json=[]))
        async with AsyncOpenCodeClient(BASE) as client:
            matches = await client.files.search_text("hello")
            paths = await client.files.search_files("b")
            symbols = await client.files.search_symbols("hello")
            formatters = await client.files.formatter_status()
        assert matches[0].lines.text.startswith("def ")
        assert paths == ["b.py"]
        assert symbols == []
        assert formatters == []


class TestRawViewSpotCheck:
    def test_raw_read_returns_unparsed_response(self, mock_server: respx.MockRouter) -> None:
        mock_server.get("/file/content").mock(return_value=httpx.Response(200, json={"type": "text", "content": "raw"}))
        with OpenCodeClient(BASE) as client:
            response = client.files.with_raw_response.read("a.py")
        assert response.json()["content"] == "raw"

    async def test_async_raw_list_returns_unparsed_response(self, mock_server: respx.MockRouter) -> None:
        mock_server.get("/file").mock(return_value=httpx.Response(200, json=[_node("a.py", "a.py")]))
        async with AsyncOpenCodeClient(BASE) as client:
            response = await client.files.with_raw_response.list("")
        assert len(response.json()) == 1

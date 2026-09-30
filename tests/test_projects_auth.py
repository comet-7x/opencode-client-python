"""Tests for the projects + auth domains and the server system-info endpoints."""

from __future__ import annotations

import json
from collections.abc import Generator
from typing import Any

import httpx
import pytest
import respx

from opencode_client import (
    ApiKeyCredentials,
    AsyncOpenCodeClient,
    OAuthCredentials,
    OpenCodeClient,
    Project,
    ServerPaths,
    UpdateProjectRequest,
    WellKnownCredentials,
)

BASE = "http://localhost:4096"


def _project(project_id: str = "prj_1", name: str | None = "demo") -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": project_id,
        "worktree": "/tmp/proj",
        "time": {"created": 1000, "updated": 2000, "initialized": 1500},
        "sandboxes": [],
    }
    if name is not None:
        payload["name"] = name
        payload["icon"] = {"color": "#ff0000"}
        payload["commands"] = {"start": "npm run dev"}
    return payload


@pytest.fixture(autouse=True)
def mock_server() -> Generator[respx.MockRouter, None, None]:
    with respx.mock(base_url=BASE) as router:
        yield router


class TestProjectsSync:
    def test_list_parses_projects(self, mock_server: respx.MockRouter) -> None:
        mock_server.get("/project").mock(return_value=httpx.Response(200, json=[_project()]))
        with OpenCodeClient(BASE) as client:
            projects = client.projects.list()
        p = projects[0]
        assert isinstance(p, Project)
        assert (p.id, p.worktree) == ("prj_1", "/tmp/proj")
        assert p.time.initialized == 1500
        assert p.vcs is None  # optional on the wire
        assert p.icon is not None and p.icon.color == "#ff0000"

    def test_current(self, mock_server: respx.MockRouter) -> None:
        mock_server.get("/project/current").mock(return_value=httpx.Response(200, json=_project("prj_cur")))
        with OpenCodeClient(BASE) as client:
            project = client.projects.current()
        assert project.id == "prj_cur"

    def test_update_sends_only_given_fields(self, mock_server: respx.MockRouter) -> None:
        route = mock_server.patch(path__regex=r"/project/[^/]+$").mock(
            return_value=httpx.Response(200, json=_project(name="renamed"))
        )
        with OpenCodeClient(BASE) as client:
            updated = client.projects.update("prj_1", UpdateProjectRequest(name="only-name"))
        assert updated.name == "renamed"
        sent = json.loads(route.calls.last.request.content)
        assert sent == {"name": "only-name"}

    def test_directories(self, mock_server: respx.MockRouter) -> None:
        route = mock_server.get(path__regex=r"/project/[^/]+/directories").mock(
            return_value=httpx.Response(
                200, json=[{"directory": "/tmp/proj"}, {"directory": "/other", "strategy": "git"}]
            )
        )
        with OpenCodeClient(BASE) as client:
            directories = client.projects.directories("prj_1")
        assert [d.directory for d in directories] == ["/tmp/proj", "/other"]
        assert directories[0].strategy is None
        assert directories[1].strategy == "git"
        assert route.calls.last.request.url.path == "/project/prj_1/directories"

    def test_git_init(self, mock_server: respx.MockRouter) -> None:
        mock_server.post("/project/git/init").mock(return_value=httpx.Response(200, json=_project()))
        with OpenCodeClient(BASE) as client:
            project = client.projects.git_init()
        assert isinstance(project, Project)


class TestAuthSync:
    def test_set_api_credentials_serialises_tagged_body(self, mock_server: respx.MockRouter) -> None:
        route = mock_server.put("/auth/anthropic").mock(return_value=httpx.Response(200, json=True))
        with OpenCodeClient(BASE) as client:
            ok = client.auth.set_credentials("anthropic", ApiKeyCredentials(type="api", key="sk-123"))
        assert ok is True
        sent = json.loads(route.calls.last.request.content)
        assert sent == {"type": "api", "key": "sk-123"}

    def test_set_oauth_credentials(self, mock_server: respx.MockRouter) -> None:
        route = mock_server.put("/auth/openai").mock(return_value=httpx.Response(200, json=True))
        credentials = OAuthCredentials(
            type="oauth", refresh="r", access="a", expires=123, account_id="acc", enterprise_url="https://ent"
        )
        with OpenCodeClient(BASE) as client:
            client.auth.set_credentials("openai", credentials)
        sent = json.loads(route.calls.last.request.content)
        assert sent["type"] == "oauth"
        # id_alias maps account_id -> accountId / enterprise_url -> enterpriseUrl
        assert sent["accountId"] == "acc" and sent["enterpriseUrl"] == "https://ent"

    def test_set_wellknown_credentials(self, mock_server: respx.MockRouter) -> None:
        route = mock_server.put("/auth/foo").mock(return_value=httpx.Response(200, json=True))
        with OpenCodeClient(BASE) as client:
            client.auth.set_credentials("foo", WellKnownCredentials(type="wellknown", key="k", token="t"))
        sent = json.loads(route.calls.last.request.content)
        assert sent == {"type": "wellknown", "key": "k", "token": "t"}

    def test_remove_credentials_encodes_provider_id(self, mock_server: respx.MockRouter) -> None:
        route = mock_server.delete(url__startswith=f"{BASE}/auth/anthropic").mock(
            return_value=httpx.Response(200, json=True)
        )
        with OpenCodeClient(BASE) as client:
            assert client.auth.remove_credentials("anthropic") is True
        assert route.calls.last.request.method == "DELETE"


class TestServerSystemInfo:
    def test_get_paths(self, mock_server: respx.MockRouter) -> None:
        payload = {
            "home": "/home/u",
            "state": "/home/u/.local/state/opencode",
            "config": "/home/u/.config/opencode",
            "worktree": "/tmp/proj",
            "directory": "/tmp/proj",
        }
        mock_server.get("/path").mock(return_value=httpx.Response(200, json=payload))
        with OpenCodeClient(BASE) as client:
            paths = client.server.get_paths()
        assert isinstance(paths, ServerPaths)
        assert paths.config.endswith("opencode")

    def test_lsp_status(self, mock_server: respx.MockRouter) -> None:
        mock_server.get("/lsp").mock(
            return_value=httpx.Response(
                200,
                json=[{"id": "pyright", "name": "pyright", "root": "/tmp/proj", "status": "connected"}],
            )
        )
        with OpenCodeClient(BASE) as client:
            servers = client.server.lsp_status()
        assert servers[0].status == "connected"
        assert servers[0].name == "pyright"

    def test_write_log_sends_optional_fields_only(self, mock_server: respx.MockRouter) -> None:
        route = mock_server.post("/log").mock(return_value=httpx.Response(200, json=True))
        with OpenCodeClient(BASE) as client:
            ok = client.server.write_log(service="my-tool", level="warn", message="watch out")
        assert ok is True
        sent = json.loads(route.calls.last.request.content)
        assert sent == {"service": "my-tool", "level": "warn", "message": "watch out"}

    async def test_async_roundtrip(self, mock_server: respx.MockRouter) -> None:
        mock_server.get("/project/current").mock(return_value=httpx.Response(200, json=_project()))
        mock_server.get("/path").mock(
            return_value=httpx.Response(
                200,
                json={
                    "home": "/h",
                    "state": "/s",
                    "config": "/c",
                    "worktree": "/w",
                    "directory": "/d",
                },
            )
        )
        mock_server.delete("/auth/x").mock(return_value=httpx.Response(200, json=True))
        mock_server.get("/path").mock(
            return_value=httpx.Response(
                200,
                json={
                    "home": "/h",
                    "state": "/s",
                    "config": "/c",
                    "worktree": "/w",
                    "directory": "/d",
                },
            )
        )
        async with AsyncOpenCodeClient(BASE) as client:
            project = await client.projects.current()
            paths = await client.server.get_paths()
            removed = await client.auth.remove_credentials("x")
        assert project.id == "prj_1"
        assert isinstance(paths, ServerPaths)
        assert removed is True


class TestRawSpotCheck:
    def test_raw_project_list(self, mock_server: respx.MockRouter) -> None:
        mock_server.get("/project").mock(return_value=httpx.Response(200, json=[_project()]))
        with OpenCodeClient(BASE) as client:
            response = client.projects.with_raw_response.list()
        assert len(response.json()) == 1

    def test_raw_set_credentials(self, mock_server: respx.MockRouter) -> None:
        mock_server.put("/auth/x").mock(return_value=httpx.Response(200, json=True))
        with OpenCodeClient(BASE) as client:
            response = client.auth.with_raw_response.set_credentials("x", ApiKeyCredentials(type="api", key="k"))
        assert response.json() is True

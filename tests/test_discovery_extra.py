"""Tests for skill listing (server) and session summarization (sessions), sync + async."""

from __future__ import annotations

import json
from collections.abc import Generator
from typing import Any

import httpx
import pytest
import respx

from opencode_client import AsyncOpenCodeClient, OpenCodeClient, Skill

BASE = "http://localhost:4096"


def _skill_item() -> dict[str, Any]:
    return {
        "name": "git-release",
        "description": "Create releases and changelogs",
        "location": "project",
        "content": "# git-release\n...body...",
    }


@pytest.fixture(autouse=True)
def mock_server() -> Generator[respx.MockRouter, None, None]:
    with respx.mock(base_url=BASE) as router:
        yield router


class TestSkillsSync:
    def test_list_skills_parses(self, mock_server: respx.MockRouter) -> None:
        mock_server.get("/skill").mock(return_value=httpx.Response(200, json=[_skill_item()]))
        with OpenCodeClient(BASE) as client:
            skills = client.server.list_skills(directory="/tmp/dir")
        assert len(skills) == 1
        skill = skills[0]
        assert isinstance(skill, Skill)
        assert skill.name == "git-release"
        assert skill.description == "Create releases and changelogs"
        assert skill.location == "project"
        assert "body" in skill.content

    def test_list_skills_optional_description(self, mock_server: respx.MockRouter) -> None:
        item = _skill_item()
        del item["description"]
        mock_server.get("/skill").mock(return_value=httpx.Response(200, json=[item]))
        with OpenCodeClient(BASE) as client:
            skills = client.server.list_skills()
        assert skills[0].description is None

    def test_list_skills_empty(self, mock_server: respx.MockRouter) -> None:
        mock_server.get("/skill").mock(return_value=httpx.Response(200, json=[]))
        with OpenCodeClient(BASE) as client:
            assert client.server.list_skills() == []


class TestSummarizeSync:
    def test_sends_provider_and_model(self, mock_server: respx.MockRouter) -> None:
        mock_server.post("/session/ses_1/summarize").mock(return_value=httpx.Response(200, json=True))
        with OpenCodeClient(BASE) as client:
            ok = client.sessions.summarize("ses_1", "steins-middleware-vllm", "Qwen/Qwen3.8-27B")
        assert ok is True
        sent = json.loads(mock_server.post("/session/ses_1/summarize").calls.last.request.content)
        assert sent == {"providerID": "steins-middleware-vllm", "modelID": "Qwen/Qwen3.8-27B"}

    def test_auto_flag_roundtrip(self, mock_server: respx.MockRouter) -> None:
        mock_server.post("/session/ses_1/summarize").mock(return_value=httpx.Response(200, json=False))
        with OpenCodeClient(BASE) as client:
            client.sessions.summarize("ses_1", "p", "m", auto=True)
        sent = json.loads(mock_server.post("/session/ses_1/summarize").calls.last.request.content)
        assert sent == {"providerID": "p", "modelID": "m", "auto": True}


class TestSkillsAndSummarizeAsync:
    async def test_list_skills(self, mock_server: respx.MockRouter) -> None:
        mock_server.get("/skill").mock(return_value=httpx.Response(200, json=[_skill_item()]))
        async with AsyncOpenCodeClient(BASE) as client:
            skills = await client.server.list_skills()
        assert isinstance(skills[0], Skill) and skills[0].name == "git-release"

    async def test_summarize(self, mock_server: respx.MockRouter) -> None:
        mock_server.post("/session/ses_1/summarize").mock(return_value=httpx.Response(200, json=True))
        async with AsyncOpenCodeClient(BASE) as client:
            ok = await client.sessions.summarize("ses_1", "p", "m", auto=False)
        assert ok is True
        sent = json.loads(mock_server.post("/session/ses_1/summarize").calls.last.request.content)
        assert sent == {"providerID": "p", "modelID": "m", "auto": False}

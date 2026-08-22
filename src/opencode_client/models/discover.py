"""Models for discovery endpoints: health, config, providers, agents, commands."""

from typing import Any, Literal

from .base import OpencodeModel
from .session import PermissionRuleset

__all__ = ["Agent", "Command", "Health", "Model", "Provider", "ProviderList", "ServerConfig"]


class Model(OpencodeModel):
    """A model offered by a provider, with its API metadata."""

    id: str
    provider_id: str
    api: dict[str, Any]
    name: str
    family: str | None = None
    capabilities: dict[str, Any]


class Provider(OpencodeModel):
    """An LLM provider and the models it exposes."""

    id: str
    name: str
    source: Literal["env", "config", "custom", "api"]
    env: list[str]
    options: dict[str, Any]
    models: dict[str, Model]


class ProviderList(OpencodeModel):
    """Full provider directory plus the connected subset."""

    all: list[Provider]
    default: dict[str, str]
    connected: list[str]


class Health(OpencodeModel):
    """Server health status and version."""

    healthy: Literal[True]
    version: str


class ServerConfig(OpencodeModel):
    """The server's own configuration (port, hostname, mDNS, CORS)."""

    port: int | None = None
    hostname: str | None = None
    mdns: bool | None = None
    mdns_domain: str | None = None
    cors: list[str] | None = None


class Command(OpencodeModel):
    """A slash command available in a session (built-in, MCP or skill)."""

    name: str
    description: str | None = None
    agent: str | None = None
    model: str | None = None
    source: Literal["command", "mcp", "skill"] | None = None
    template: str
    subtask: bool | None = None
    hints: list[str]


class Agent(OpencodeModel):
    """An agent definition (primary or subagent) with model/sampling/permission config."""

    name: str
    description: str | None = None
    mode: Literal["subagent", "primary", "all"]
    native: bool | None = None
    hidden: bool | None = None
    top_p: float | None = None
    temperature: float | None = None
    color: str | None = None
    permission: PermissionRuleset | None = None
    model: dict[str, str] | None = None
    variant: str | None = None
    prompt: str | None = None
    options: dict[str, Any]

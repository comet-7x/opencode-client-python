"""Server resource: health, config, discovery, skills, interactions, and the event stream.

Maps to the non-session endpoints (``/global/health``, ``/config``,
``/provider``, ``/agent``, ``/command``, ``/skill``, ``/permission*``,
``/question*``, ``/event``) and ships in two flavours:

- :class:`ServerResource` — synchronous, backed by :class:`OpenCodeClient`;
- :class:`AsyncServerResource` — asynchronous, backed by :class:`AsyncOpenCodeClient`.

``stream_events`` returns the matching :class:`~opencode_client.AsyncEventStream`
(sync or async) for the owning client, with automatic reconnection after
drops — iterate its ``iter_events()`` / ``aiter_events()`` for decoded
events.
"""

from __future__ import annotations

import builtins
from typing import TYPE_CHECKING, Any, Literal

import httpx

from ..models import (
    Agent,
    Command,
    Health,
    LSPStatus,
    PermissionRequest,
    ProviderList,
    QuestionRequest,
    ServerPaths,
    Skill,
)
from ._wire import (
    TYPE_ADAPTERS,
    log_body,
    path_segment,
    permission_reply_body,
    question_reply_body,
    request_spec,
    validate_response,
)
from .base import AsyncResource, Resource, query_params

if TYPE_CHECKING:
    from ..sse import AsyncEventStream, EventStream

__all__ = [
    "AsyncServerResource",
    "AsyncServerResourceWithRawResponse",
    "ServerResource",
    "ServerResourceWithRawResponse",
]


class ServerResource(Resource):
    """Synchronous client for server-level endpoints."""

    @property
    def with_raw_response(self) -> ServerResourceWithRawResponse:
        """Prefix for the raw-response variants of every method below.

        Each call returns the unprocessed :class:`httpx.Response` instead of
        the parsed model (same retries, same error mapping on non-2xx).
        ``stream_events`` has no raw variant (it returns an AsyncEventStream, not
        a one-shot response).
        """
        return ServerResourceWithRawResponse(self._client)

    # -- health & config --------------------------------------------------

    def health(self) -> Health:
        """Check server liveness and get its version."""
        response = self._send("GET", "/global/health")
        return validate_response(response, TYPE_ADAPTERS.health)

    def get_paths(self, directory: str | None = None, workspace: str | None = None) -> ServerPaths:
        """Get the server's filesystem layout (home/state/config/worktree/directory)."""
        response = self._send("GET", "/path", **request_spec(directory=directory, workspace=workspace))
        return validate_response(response, TYPE_ADAPTERS.server_paths)

    def lsp_status(self, directory: str | None = None, workspace: str | None = None) -> builtins.list[LSPStatus]:
        """List the language servers attached to the worktree and their status."""
        response = self._send("GET", "/lsp", **request_spec(directory=directory, workspace=workspace))
        return validate_response(response, TYPE_ADAPTERS.lsp_statuses)

    def write_log(
        self,
        service: str | None = None,
        level: Literal["debug", "info", "error", "warn"] | None = None,
        message: str | None = None,
        extra: dict[str, Any] | None = None,
        directory: str | None = None,
        workspace: str | None = None,
    ) -> bool:
        """Write an entry into the server's own log (for remote debugging).

        Args:
            service: Service name for the entry.
            level: Log level; server default applies when omitted.
            message: The message text.
            extra: Arbitrary structured context.
        """
        json_body = log_body(service, level, message, extra)
        response = self._send(
            "POST", "/log", **request_spec(directory=directory, workspace=workspace, json_body=json_body)
        )
        return validate_response(response, TYPE_ADAPTERS.bool)

    def get_config(self, directory: str | None = None, workspace: str | None = None) -> dict[str, Any]:
        """Read the effective server configuration (optionally scoped)."""
        response = self._send("GET", "/config", **request_spec(directory=directory, workspace=workspace))
        return validate_response(response, TYPE_ADAPTERS.config)

    def update_config(
        self,
        body: dict[str, Any],
        directory: str | None = None,
        workspace: str | None = None,
    ) -> dict[str, Any]:
        """Patch the server configuration and return the updated document."""
        response = self._send(
            "PATCH", "/config", **request_spec(directory=directory, workspace=workspace, json_body=body)
        )
        return validate_response(response, TYPE_ADAPTERS.config)

    # -- discovery --------------------------------------------------------

    def list_providers(self, directory: str | None = None, workspace: str | None = None) -> ProviderList:
        """List all providers, the default per-provider model, and the connected ones."""
        response = self._send("GET", "/provider", **request_spec(directory=directory, workspace=workspace))
        return validate_response(response, TYPE_ADAPTERS.provider_list)

    def list_agents(self, directory: str | None = None, workspace: str | None = None) -> list[Agent]:
        """List the agents configured for the session context."""
        response = self._send("GET", "/agent", **request_spec(directory=directory, workspace=workspace))
        return validate_response(response, TYPE_ADAPTERS.agent_list)

    def list_commands(self, directory: str | None = None, workspace: str | None = None) -> list[Command]:
        """List available slash commands (built-ins, MCP tools, skills)."""
        response = self._send("GET", "/command", **request_spec(directory=directory, workspace=workspace))
        return validate_response(response, TYPE_ADAPTERS.command_list)

    def list_skills(self, directory: str | None = None, workspace: str | None = None) -> list[Skill]:
        """List the skills exposed by the server, with location and body."""
        response = self._send("GET", "/skill", **request_spec(directory=directory, workspace=workspace))
        return validate_response(response, TYPE_ADAPTERS.skill_list)

    # -- interactions: permissions ---------------------------------------

    def list_permissions(self, directory: str | None = None, workspace: str | None = None) -> list[PermissionRequest]:
        """List pending permission requests across all running sessions.

        A permission request blocks a running turn until answered, so poll
        this while watching events for the ``permission.updated`` type.
        """
        response = self._send("GET", "/permission", **request_spec(directory=directory, workspace=workspace))
        return validate_response(response, TYPE_ADAPTERS.permission_requests)

    def reply_permission(
        self,
        request_id: str,
        reply: str,
        message: str | None = None,
        directory: str | None = None,
        workspace: str | None = None,
    ) -> bool:
        """Answer a pending permission request.

        Args:
            request_id: The ``per_...`` id returned by :meth:`list_permissions`.
            reply: One of ``"once"`` (allow this time), ``"always"`` (allow
                and persist), or ``"reject"`` (deny).
            message: Optional note attached to the reply.

        Returns:
            ``True`` when the server processed the reply.
        """
        json_body = permission_reply_body(reply, message)
        response = self._send(
            "POST",
            f"/permission/{path_segment(request_id)}/reply",
            **request_spec(directory=directory, workspace=workspace, json_body=json_body),
        )
        return validate_response(response, TYPE_ADAPTERS.bool)

    # -- interactions: questions -----------------------------------------

    def list_questions(self, directory: str | None = None, workspace: str | None = None) -> list[QuestionRequest]:
        """List pending question requests across all running sessions.

        A question request blocks a running turn until answered or rejected.
        """
        response = self._send("GET", "/question", **request_spec(directory=directory, workspace=workspace))
        return validate_response(response, TYPE_ADAPTERS.question_requests)

    def reply_question(
        self,
        request_id: str,
        answers: list[list[str]],
        directory: str | None = None,
        workspace: str | None = None,
    ) -> bool:
        """Answer a pending question request.

        Args:
            request_id: The ``que_...`` id returned by :meth:`list_questions`.
            answers: One entry per question, each a list of selected option
                labels; the order must match the request's ``questions``.

        Returns:
            ``True`` when the server accepted the answers.
        """
        json_body = question_reply_body(answers)
        response = self._send(
            "POST",
            f"/question/{path_segment(request_id)}/reply",
            **request_spec(directory=directory, workspace=workspace, json_body=json_body),
        )
        return validate_response(response, TYPE_ADAPTERS.bool)

    def reject_question(
        self,
        request_id: str,
        directory: str | None = None,
        workspace: str | None = None,
    ) -> bool:
        """Reject a pending question request (decline to answer).

        Args:
            request_id: The ``que_...`` id returned by :meth:`list_questions`.

        Returns:
            ``True`` when the server accepted the rejection.
        """
        response = self._send(
            "POST",
            f"/question/{path_segment(request_id)}/reject",
            **request_spec(directory=directory, workspace=workspace),
        )
        return validate_response(response, TYPE_ADAPTERS.bool)

    # -- events -----------------------------------------------------------

    def stream_events(
        self,
        directory: str | None = None,
        workspace: str | None = None,
        max_reconnect_attempts: int | None = None,
    ) -> EventStream:
        """Open the ``/event`` SSE stream as a (sync) context manager.

        Args:
            directory: Optional scoping query param.
            workspace: Optional scoping query param.
            max_reconnect_attempts: Reconnect budget after a drop; ``None``
                uses the package default.  The budget resets whenever a line
                is received, so a healthy stream reconnects indefinitely.

        Returns:
            An :class:`~opencode_client.EventStream`; iterate
            ``iter_events()`` for decoded events with automatic
            reconnection.
        """
        from ..sse import EventStream

        request = self._client.http.build_request("GET", "/event", params=query_params(directory, workspace))
        return EventStream(self._client.http, request, max_reconnect_attempts=max_reconnect_attempts)


class AsyncServerResource(AsyncResource):
    """Asynchronous client for server-level endpoints."""

    @property
    def with_raw_response(self) -> AsyncServerResourceWithRawResponse:
        """Prefix for the raw-response variants of every method below.

        Each call returns the unprocessed :class:`httpx.Response` instead of
        the parsed model (same retries, same error mapping on non-2xx).
        ``stream_events`` has no raw variant (it returns an AsyncEventStream, not
        a one-shot response).
        """
        return AsyncServerResourceWithRawResponse(self._client)

    # -- health & config --------------------------------------------------

    async def health(self) -> Health:
        """Check server liveness and get its version."""
        response = await self._send("GET", "/global/health")
        return validate_response(response, TYPE_ADAPTERS.health)

    async def get_paths(self, directory: str | None = None, workspace: str | None = None) -> ServerPaths:
        """Get the server's filesystem layout (home/state/config/worktree/directory)."""
        response = await self._send("GET", "/path", **request_spec(directory=directory, workspace=workspace))
        return validate_response(response, TYPE_ADAPTERS.server_paths)

    async def lsp_status(self, directory: str | None = None, workspace: str | None = None) -> builtins.list[LSPStatus]:
        """List the language servers attached to the worktree and their status."""
        response = await self._send("GET", "/lsp", **request_spec(directory=directory, workspace=workspace))
        return validate_response(response, TYPE_ADAPTERS.lsp_statuses)

    async def write_log(
        self,
        service: str | None = None,
        level: Literal["debug", "info", "error", "warn"] | None = None,
        message: str | None = None,
        extra: dict[str, Any] | None = None,
        directory: str | None = None,
        workspace: str | None = None,
    ) -> bool:
        """Write an entry into the server's own log (for remote debugging).

        Args:
            service: Service name for the entry.
            level: Log level; server default applies when omitted.
            message: The message text.
            extra: Arbitrary structured context.
        """
        json_body = log_body(service, level, message, extra)
        response = await self._send(
            "POST", "/log", **request_spec(directory=directory, workspace=workspace, json_body=json_body)
        )
        return validate_response(response, TYPE_ADAPTERS.bool)

    async def get_config(self, directory: str | None = None, workspace: str | None = None) -> dict[str, Any]:
        """Read the effective server configuration (optionally scoped)."""
        response = await self._send("GET", "/config", **request_spec(directory=directory, workspace=workspace))
        return validate_response(response, TYPE_ADAPTERS.config)

    async def update_config(
        self,
        body: dict[str, Any],
        directory: str | None = None,
        workspace: str | None = None,
    ) -> dict[str, Any]:
        """Patch the server configuration and return the updated document."""
        response = await self._send(
            "PATCH", "/config", **request_spec(directory=directory, workspace=workspace, json_body=body)
        )
        return validate_response(response, TYPE_ADAPTERS.config)

    # -- discovery --------------------------------------------------------

    async def list_providers(self, directory: str | None = None, workspace: str | None = None) -> ProviderList:
        """List all providers, the default per-provider model, and the connected ones."""
        response = await self._send("GET", "/provider", **request_spec(directory=directory, workspace=workspace))
        return validate_response(response, TYPE_ADAPTERS.provider_list)

    async def list_agents(self, directory: str | None = None, workspace: str | None = None) -> list[Agent]:
        """List the agents configured for the session context."""
        response = await self._send("GET", "/agent", **request_spec(directory=directory, workspace=workspace))
        return validate_response(response, TYPE_ADAPTERS.agent_list)

    async def list_commands(self, directory: str | None = None, workspace: str | None = None) -> list[Command]:
        """List available slash commands (built-ins, MCP tools, skills)."""
        response = await self._send("GET", "/command", **request_spec(directory=directory, workspace=workspace))
        return validate_response(response, TYPE_ADAPTERS.command_list)

    async def list_skills(self, directory: str | None = None, workspace: str | None = None) -> list[Skill]:
        """List the skills exposed by the server, with location and body."""
        response = await self._send("GET", "/skill", **request_spec(directory=directory, workspace=workspace))
        return validate_response(response, TYPE_ADAPTERS.skill_list)

    # -- interactions: permissions ---------------------------------------

    async def list_permissions(
        self, directory: str | None = None, workspace: str | None = None
    ) -> list[PermissionRequest]:
        """List pending permission requests across all running sessions."""
        response = await self._send("GET", "/permission", **request_spec(directory=directory, workspace=workspace))
        return validate_response(response, TYPE_ADAPTERS.permission_requests)

    async def reply_permission(
        self,
        request_id: str,
        reply: str,
        message: str | None = None,
        directory: str | None = None,
        workspace: str | None = None,
    ) -> bool:
        """Answer a pending permission request.

        Args:
            request_id: The ``per_...`` id returned by :meth:`list_permissions`.
            reply: One of ``"once"``, ``"always"`` or ``"reject"``.
            message: Optional note attached to the reply.

        Returns:
            ``True`` when the server processed the reply.
        """
        json_body = permission_reply_body(reply, message)
        response = await self._send(
            "POST",
            f"/permission/{path_segment(request_id)}/reply",
            **request_spec(directory=directory, workspace=workspace, json_body=json_body),
        )
        return validate_response(response, TYPE_ADAPTERS.bool)

    # -- interactions: questions -----------------------------------------

    async def list_questions(self, directory: str | None = None, workspace: str | None = None) -> list[QuestionRequest]:
        """List pending question requests across all running sessions."""
        response = await self._send("GET", "/question", **request_spec(directory=directory, workspace=workspace))
        return validate_response(response, TYPE_ADAPTERS.question_requests)

    async def reply_question(
        self,
        request_id: str,
        answers: list[list[str]],
        directory: str | None = None,
        workspace: str | None = None,
    ) -> bool:
        """Answer a pending question request.

        Args:
            request_id: The ``que_...`` id returned by :meth:`list_questions`.
            answers: One entry per question, each a list of selected option labels.

        Returns:
            ``True`` when the server accepted the answers.
        """
        json_body = question_reply_body(answers)
        response = await self._send(
            "POST",
            f"/question/{path_segment(request_id)}/reply",
            **request_spec(directory=directory, workspace=workspace, json_body=json_body),
        )
        return validate_response(response, TYPE_ADAPTERS.bool)

    async def reject_question(
        self,
        request_id: str,
        directory: str | None = None,
        workspace: str | None = None,
    ) -> bool:
        """Reject a pending question request.

        Args:
            request_id: The ``que_...`` id returned by :meth:`list_questions`.

        Returns:
            ``True`` when the server accepted the rejection.
        """
        response = await self._send(
            "POST",
            f"/question/{path_segment(request_id)}/reject",
            **request_spec(directory=directory, workspace=workspace),
        )
        return validate_response(response, TYPE_ADAPTERS.bool)

    # -- events -----------------------------------------------------------

    def stream_events(
        self,
        directory: str | None = None,
        workspace: str | None = None,
        max_reconnect_attempts: int | None = None,
    ) -> AsyncEventStream:
        """Open the ``/event`` SSE stream as an async context manager.

        Args:
            directory: Optional scoping query param.
            workspace: Optional scoping query param.
            max_reconnect_attempts: Reconnect budget after a drop; ``None``
                uses the package default.  The budget resets whenever a line
                is received, so a healthy stream reconnects indefinitely.

        Returns:
            An :class:`~opencode_client.AsyncEventStream`; iterate
            ``aiter_events()`` for decoded events with automatic
            reconnection.
        """
        from ..sse import AsyncEventStream

        request = self._client.http.build_request("GET", "/event", params=query_params(directory, workspace))
        return AsyncEventStream(self._client.http, request, max_reconnect_attempts=max_reconnect_attempts)


class ServerResourceWithRawResponse(Resource):
    """Synchronous raw-response view of the server-level endpoints.

    Mirrors :class:`ServerResource` method-for-method (minus ``stream_events``)
    but returns the unprocessed response instead of the parsed model. Non-2xx
    still raise the same mapped errors; retries are shared.
    """

    def health(self) -> httpx.Response:
        """Check server liveness; return the raw response."""
        return self._send("GET", "/global/health")

    def get_paths(self, directory: str | None = None, workspace: str | None = None) -> httpx.Response:
        """Get the server's filesystem layout; return the raw response."""
        return self._send("GET", "/path", **request_spec(directory=directory, workspace=workspace))

    def lsp_status(self, directory: str | None = None, workspace: str | None = None) -> httpx.Response:
        """List language servers; return the raw response."""
        return self._send("GET", "/lsp", **request_spec(directory=directory, workspace=workspace))

    def write_log(
        self,
        service: str | None = None,
        level: Literal["debug", "info", "error", "warn"] | None = None,
        message: str | None = None,
        extra: dict[str, Any] | None = None,
        directory: str | None = None,
        workspace: str | None = None,
    ) -> httpx.Response:
        """Write a server log entry; return the raw response."""
        json_body = log_body(service, level, message, extra)
        return self._send("POST", "/log", **request_spec(directory=directory, workspace=workspace, json_body=json_body))

    def get_config(self, directory: str | None = None, workspace: str | None = None) -> httpx.Response:
        """Read the effective configuration; return the raw response."""
        return self._send("GET", "/config", **request_spec(directory=directory, workspace=workspace))

    def update_config(
        self,
        body: dict[str, Any],
        directory: str | None = None,
        workspace: str | None = None,
    ) -> httpx.Response:
        """Patch the server configuration; return the raw response."""
        return self._send("PATCH", "/config", **request_spec(directory=directory, workspace=workspace, json_body=body))

    def list_providers(self, directory: str | None = None, workspace: str | None = None) -> httpx.Response:
        """List providers; return the raw response."""
        return self._send("GET", "/provider", **request_spec(directory=directory, workspace=workspace))

    def list_agents(self, directory: str | None = None, workspace: str | None = None) -> httpx.Response:
        """List agents; return the raw response."""
        return self._send("GET", "/agent", **request_spec(directory=directory, workspace=workspace))

    def list_commands(self, directory: str | None = None, workspace: str | None = None) -> httpx.Response:
        """List slash commands; return the raw response."""
        return self._send("GET", "/command", **request_spec(directory=directory, workspace=workspace))

    def list_skills(self, directory: str | None = None, workspace: str | None = None) -> httpx.Response:
        """List skills; return the raw response."""
        return self._send("GET", "/skill", **request_spec(directory=directory, workspace=workspace))

    def list_permissions(self, directory: str | None = None, workspace: str | None = None) -> httpx.Response:
        """List pending permission requests; return the raw response."""
        return self._send("GET", "/permission", **request_spec(directory=directory, workspace=workspace))

    def reply_permission(
        self,
        request_id: str,
        reply: str,
        message: str | None = None,
        directory: str | None = None,
        workspace: str | None = None,
    ) -> httpx.Response:
        """Answer a permission request; return the raw response."""
        json_body = permission_reply_body(reply, message)
        return self._send(
            "POST",
            f"/permission/{path_segment(request_id)}/reply",
            **request_spec(directory=directory, workspace=workspace, json_body=json_body),
        )

    def list_questions(self, directory: str | None = None, workspace: str | None = None) -> httpx.Response:
        """List pending question requests; return the raw response."""
        return self._send("GET", "/question", **request_spec(directory=directory, workspace=workspace))

    def reply_question(
        self,
        request_id: str,
        answers: list[list[str]],
        directory: str | None = None,
        workspace: str | None = None,
    ) -> httpx.Response:
        """Answer a question request; return the raw response."""
        json_body = question_reply_body(answers)
        return self._send(
            "POST",
            f"/question/{path_segment(request_id)}/reply",
            **request_spec(directory=directory, workspace=workspace, json_body=json_body),
        )

    def reject_question(
        self,
        request_id: str,
        directory: str | None = None,
        workspace: str | None = None,
    ) -> httpx.Response:
        """Reject a question request; return the raw response."""
        return self._send(
            "POST",
            f"/question/{path_segment(request_id)}/reject",
            **request_spec(directory=directory, workspace=workspace),
        )


class AsyncServerResourceWithRawResponse(AsyncResource):
    """Asynchronous raw-response view of the server-level endpoints.

    Mirrors :class:`AsyncServerResource` method-for-method (minus
    ``stream_events``) but returns the unprocessed response instead of the
    parsed model. Non-2xx still raise the same mapped errors; retries are
    shared.
    """

    async def health(self) -> httpx.Response:
        """Check server liveness; return the raw response."""
        return await self._send("GET", "/global/health")

    async def get_paths(self, directory: str | None = None, workspace: str | None = None) -> httpx.Response:
        """Get the server's filesystem layout; return the raw response."""
        return await self._send("GET", "/path", **request_spec(directory=directory, workspace=workspace))

    async def lsp_status(self, directory: str | None = None, workspace: str | None = None) -> httpx.Response:
        """List language servers; return the raw response."""
        return await self._send("GET", "/lsp", **request_spec(directory=directory, workspace=workspace))

    async def write_log(
        self,
        service: str | None = None,
        level: Literal["debug", "info", "error", "warn"] | None = None,
        message: str | None = None,
        extra: dict[str, Any] | None = None,
        directory: str | None = None,
        workspace: str | None = None,
    ) -> httpx.Response:
        """Write a server log entry; return the raw response."""
        json_body = log_body(service, level, message, extra)
        return await self._send(
            "POST", "/log", **request_spec(directory=directory, workspace=workspace, json_body=json_body)
        )

    async def get_config(self, directory: str | None = None, workspace: str | None = None) -> httpx.Response:
        """Read the effective configuration; return the raw response."""
        return await self._send("GET", "/config", **request_spec(directory=directory, workspace=workspace))

    async def update_config(
        self,
        body: dict[str, Any],
        directory: str | None = None,
        workspace: str | None = None,
    ) -> httpx.Response:
        """Patch the server configuration; return the raw response."""
        return await self._send(
            "PATCH", "/config", **request_spec(directory=directory, workspace=workspace, json_body=body)
        )

    async def list_providers(self, directory: str | None = None, workspace: str | None = None) -> httpx.Response:
        """List providers; return the raw response."""
        return await self._send("GET", "/provider", **request_spec(directory=directory, workspace=workspace))

    async def list_agents(self, directory: str | None = None, workspace: str | None = None) -> httpx.Response:
        """List agents; return the raw response."""
        return await self._send("GET", "/agent", **request_spec(directory=directory, workspace=workspace))

    async def list_commands(self, directory: str | None = None, workspace: str | None = None) -> httpx.Response:
        """List slash commands; return the raw response."""
        return await self._send("GET", "/command", **request_spec(directory=directory, workspace=workspace))

    async def list_skills(self, directory: str | None = None, workspace: str | None = None) -> httpx.Response:
        """List skills; return the raw response."""
        return await self._send("GET", "/skill", **request_spec(directory=directory, workspace=workspace))

    async def list_permissions(self, directory: str | None = None, workspace: str | None = None) -> httpx.Response:
        """List pending permission requests; return the raw response."""
        return await self._send("GET", "/permission", **request_spec(directory=directory, workspace=workspace))

    async def reply_permission(
        self,
        request_id: str,
        reply: str,
        message: str | None = None,
        directory: str | None = None,
        workspace: str | None = None,
    ) -> httpx.Response:
        """Answer a permission request; return the raw response."""
        json_body = permission_reply_body(reply, message)
        return await self._send(
            "POST",
            f"/permission/{path_segment(request_id)}/reply",
            **request_spec(directory=directory, workspace=workspace, json_body=json_body),
        )

    async def list_questions(self, directory: str | None = None, workspace: str | None = None) -> httpx.Response:
        """List pending question requests; return the raw response."""
        return await self._send("GET", "/question", **request_spec(directory=directory, workspace=workspace))

    async def reply_question(
        self,
        request_id: str,
        answers: list[list[str]],
        directory: str | None = None,
        workspace: str | None = None,
    ) -> httpx.Response:
        """Answer a question request; return the raw response."""
        json_body = question_reply_body(answers)
        return await self._send(
            "POST",
            f"/question/{path_segment(request_id)}/reply",
            **request_spec(directory=directory, workspace=workspace, json_body=json_body),
        )

    async def reject_question(
        self,
        request_id: str,
        directory: str | None = None,
        workspace: str | None = None,
    ) -> httpx.Response:
        """Reject a question request; return the raw response."""
        return await self._send(
            "POST",
            f"/question/{path_segment(request_id)}/reject",
            **request_spec(directory=directory, workspace=workspace),
        )

"""Server resource: health, config, discovery, interactions, and the event stream.

Maps to the non-session endpoints (``/global/health``, ``/config``,
``/provider``, ``/agent``, ``/command``, ``/permission*``, ``/question*``,
``/event``) and ships in two flavours:

- :class:`ServerResource` — synchronous, backed by :class:`OpenCodeClient`;
- :class:`AsyncServerResource` — asynchronous, backed by :class:`AsyncOpenCodeClient`.

``stream_events`` returns the matching :class:`~opencode_client.EventStream`
(sync or async) for the owning client.
"""

from __future__ import annotations

from typing import Any

from ..models import Agent, Command, Health, PermissionRequest, ProviderList, QuestionRequest
from ._wire import TYPE_ADAPTERS, permission_reply_body, question_reply_body, request_spec, validate_response
from .base import AsyncResource, Resource, query_params

__all__ = ["AsyncServerResource", "ServerResource"]


class ServerResource(Resource):
    """Synchronous client for server-level endpoints."""

    # -- health & config --------------------------------------------------

    def health(self) -> Health:
        """Check server liveness and get its version."""
        response = self._send("GET", "/global/health")
        return validate_response(response, TYPE_ADAPTERS.health)

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
            f"/permission/{request_id}/reply",
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
            f"/question/{request_id}/reply",
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
            "POST", f"/question/{request_id}/reject", **request_spec(directory=directory, workspace=workspace)
        )
        return validate_response(response, TYPE_ADAPTERS.bool)

    # -- events -----------------------------------------------------------

    def stream_events(self, directory: str | None = None, workspace: str | None = None) -> Any:
        """Open the ``/event`` SSE stream as a (sync) context manager.

        Args:
            directory: Optional scoping query param.
            workspace: Optional scoping query param.

        Returns:
            An :class:`~opencode_client.SyncEventStream`; feed
            ``iter_lines()`` into :class:`~opencode_client.SSEDecoder`.
        """
        from ..sse import SyncEventStream

        request = self._client.http.build_request("GET", "/event", params=query_params(directory, workspace))
        return SyncEventStream(self._client.http, request)


class AsyncServerResource(AsyncResource):
    """Asynchronous client for server-level endpoints."""

    # -- health & config --------------------------------------------------

    async def health(self) -> Health:
        """Check server liveness and get its version."""
        response = await self._send("GET", "/global/health")
        return validate_response(response, TYPE_ADAPTERS.health)

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
            f"/permission/{request_id}/reply",
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
            f"/question/{request_id}/reply",
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
            "POST", f"/question/{request_id}/reject", **request_spec(directory=directory, workspace=workspace)
        )
        return validate_response(response, TYPE_ADAPTERS.bool)

    # -- events -----------------------------------------------------------

    def stream_events(self, directory: str | None = None, workspace: str | None = None) -> Any:
        """Open the ``/event`` SSE stream as an async context manager.

        Args:
            directory: Optional scoping query param.
            workspace: Optional scoping query param.

        Returns:
            An :class:`~opencode_client.EventStream`; feed
            ``aiter_lines()`` into :class:`~opencode_client.SSEDecoder`.
        """
        from ..sse import EventStream

        request = self._client.http.build_request("GET", "/event", params=query_params(directory, workspace))
        return EventStream(self._client.http, request)

"""Session resource: CRUD plus fork/abort/share/summarize and permission replies.

Maps to the ``/session`` endpoint family of the OpenAPI spec and ships in two
flavours:

- :class:`SessionsResource` — synchronous, backed by :class:`OpenCodeClient`;
- :class:`AsyncSessionsResource` — asynchronous, backed by :class:`AsyncOpenCodeClient`.

Both expose identical method signatures. Request shaping (paths, query params,
bodies, parse adapters) is shared via :mod:`opencode_client.resources._wire`.
"""

from __future__ import annotations

from typing import Any

import httpx

from ..models import (
    CreateSessionRequest,
    MessageWithParts,
    Part,
    PromptModel,
    PromptPart,
    Session,
    SessionFileDiff,
    SessionStatus,
    Todo,
    UpdateSessionRequest,
)
from ._wire import (
    TYPE_ADAPTERS,
    command_body,
    create_body,
    diff_query,
    fork_body,
    init_body,
    messages_query,
    path_segment,
    permission_body,
    prompt_body,
    request_spec,
    revert_body,
    session_list_query,
    shell_body,
    summarize_body,
    update_body,
    validate_response,
)
from .base import AsyncResource, Resource

__all__ = [
    "AsyncSessionsResource",
    "AsyncSessionsResourceWithRawResponse",
    "SessionsResource",
    "SessionsResourceWithRawResponse",
]


class SessionsResource(Resource):
    """Synchronous client for everything under ``/session``."""

    @property
    def with_raw_response(self) -> SessionsResourceWithRawResponse:
        """Prefix for the raw-response variants of every method below.

        Each call returns the unprocessed :class:`httpx.Response` instead of
        the parsed model (same retries, same error mapping on non-2xx).
        """
        return SessionsResourceWithRawResponse(self._client)

    # -- CRUD -------------------------------------------------------------

    def list_sessions(
        self,
        directory: str | None = None,
        workspace: str | None = None,
        scope: str | None = None,
        path: str | None = None,
        roots: bool | None = None,
        start: float | None = None,
        search: str | None = None,
        limit: int | None = None,
    ) -> list[Session]:
        """List sessions, with optional scope/path/time/search filters.

        Returns:
            Sessions matching the filters, newest first.
        """
        query = session_list_query(scope, path, roots, start, search, limit)
        response = self._send("GET", "/session", **request_spec(directory=directory, workspace=workspace, query=query))
        return validate_response(response, TYPE_ADAPTERS.sessions)

    def create(
        self,
        directory: str | None = None,
        workspace: str | None = None,
        body: CreateSessionRequest | None = None,
    ) -> Session:
        """Create a session.

        Args:
            directory: Scope to a project directory (server query param).
            workspace: Scope to a workspace (server query param).
            body: Optional creation options (title/agent/model/permission/...).

        Returns:
            The created session.
        """
        json_body = create_body(body)
        response = self._send(
            "POST", "/session", **request_spec(directory=directory, workspace=workspace, json_body=json_body)
        )
        return validate_response(response, TYPE_ADAPTERS.session)

    def get(self, session_id: str, directory: str | None = None, workspace: str | None = None) -> Session:
        """Fetch one session by id.

        Raises:
            OpenCodeApiError: If the session does not exist (404).
        """
        response = self._send(
            "GET", f"/session/{path_segment(session_id)}", **request_spec(directory=directory, workspace=workspace)
        )
        return validate_response(response, TYPE_ADAPTERS.session)

    def update(
        self,
        session_id: str,
        body: UpdateSessionRequest,
        directory: str | None = None,
        workspace: str | None = None,
    ) -> Session:
        """Update mutable session fields (title/metadata/permission/archived)."""
        json_body = update_body(body)
        response = self._send(
            "PATCH",
            f"/session/{path_segment(session_id)}",
            **request_spec(directory=directory, workspace=workspace, json_body=json_body),
        )
        return validate_response(response, TYPE_ADAPTERS.session)

    def delete(self, session_id: str, directory: str | None = None, workspace: str | None = None) -> bool:
        """Delete a session. Returns ``True`` on success."""
        response = self._send(
            "DELETE", f"/session/{path_segment(session_id)}", **request_spec(directory=directory, workspace=workspace)
        )
        return validate_response(response, TYPE_ADAPTERS.bool)

    # -- lifecycle --------------------------------------------------------

    def fork(
        self,
        session_id: str,
        message_id: str | None = None,
        directory: str | None = None,
        workspace: str | None = None,
    ) -> Session:
        """Create a branch off an existing session, optionally at a given message."""
        json_body = fork_body(message_id)
        response = self._send(
            "POST",
            f"/session/{path_segment(session_id)}/fork",
            **request_spec(directory=directory, workspace=workspace, json_body=json_body),
        )
        return validate_response(response, TYPE_ADAPTERS.session)

    def abort(self, session_id: str, directory: str | None = None, workspace: str | None = None) -> bool:
        """Abort a running session. Returns ``True`` on success."""
        response = self._send(
            "POST",
            f"/session/{path_segment(session_id)}/abort",
            **request_spec(directory=directory, workspace=workspace),
        )
        return validate_response(response, TYPE_ADAPTERS.bool)

    def share(self, session_id: str, directory: str | None = None, workspace: str | None = None) -> Session:
        """Publish the session; the updated session carries the share URL."""
        response = self._send(
            "POST",
            f"/session/{path_segment(session_id)}/share",
            **request_spec(directory=directory, workspace=workspace),
        )
        return validate_response(response, TYPE_ADAPTERS.session)

    def unshare(self, session_id: str, directory: str | None = None, workspace: str | None = None) -> Session:
        """Remove the session's share URL."""
        response = self._send(
            "DELETE",
            f"/session/{path_segment(session_id)}/share",
            **request_spec(directory=directory, workspace=workspace),
        )
        return validate_response(response, TYPE_ADAPTERS.session)

    def summarize(
        self,
        session_id: str,
        provider_id: str,
        model_id: str,
        auto: bool | None = None,
        directory: str | None = None,
        workspace: str | None = None,
    ) -> bool:
        """Ask the server to (re)summarize the session with the given model."""
        json_body = summarize_body(provider_id, model_id, auto)
        response = self._send(
            "POST",
            f"/session/{path_segment(session_id)}/summarize",
            **request_spec(directory=directory, workspace=workspace, json_body=json_body),
        )
        return validate_response(response, TYPE_ADAPTERS.bool)

    # -- state & history ---------------------------------------------------

    def status(self, directory: str | None = None, workspace: str | None = None) -> dict[str, SessionStatus]:
        """Report the run state of every active session (idle/busy/retry)."""
        response = self._send("GET", "/session/status", **request_spec(directory=directory, workspace=workspace))
        return validate_response(response, TYPE_ADAPTERS.status_map)

    def children(self, session_id: str, directory: str | None = None, workspace: str | None = None) -> list[Session]:
        """List the child sessions spawned by this session (subagents/tasks).

        Raises:
            OpenCodeApiError: If the session does not exist (404).
        """
        response = self._send(
            "GET",
            f"/session/{path_segment(session_id)}/children",
            **request_spec(directory=directory, workspace=workspace),
        )
        return validate_response(response, TYPE_ADAPTERS.sessions)

    def list_todos(self, session_id: str, directory: str | None = None, workspace: str | None = None) -> list[Todo]:
        """List the session's todo list written by the todo tool.

        Raises:
            OpenCodeApiError: If the session does not exist (404).
        """
        response = self._send(
            "GET", f"/session/{path_segment(session_id)}/todo", **request_spec(directory=directory, workspace=workspace)
        )
        return validate_response(response, TYPE_ADAPTERS.todo_list)

    def diff(
        self,
        session_id: str,
        message_id: str | None = None,
        directory: str | None = None,
        workspace: str | None = None,
    ) -> list[SessionFileDiff]:
        """List the file changes made by the session's messages.

        Args:
            message_id: Only include changes up to this message.

        Returns:
            Per-file addition/deletion stats with optional patch text.
        """
        query = diff_query(message_id)
        response = self._send(
            "GET",
            f"/session/{path_segment(session_id)}/diff",
            **request_spec(directory=directory, workspace=workspace, query=query),
        )
        return validate_response(response, TYPE_ADAPTERS.session_diffs)

    def revert(
        self,
        session_id: str,
        message_id: str,
        part_id: str | None = None,
        directory: str | None = None,
        workspace: str | None = None,
    ) -> Session:
        """Revert messages up to and including ``message_id``.

        Raises:
            OpenCodeConflictError: If the session is busy (409).
        """
        json_body = revert_body(message_id, part_id)
        response = self._send(
            "POST",
            f"/session/{path_segment(session_id)}/revert",
            **request_spec(directory=directory, workspace=workspace, json_body=json_body),
        )
        return validate_response(response, TYPE_ADAPTERS.session)

    def unrevert(self, session_id: str, directory: str | None = None, workspace: str | None = None) -> Session:
        """Restore previously reverted messages.

        Raises:
            OpenCodeConflictError: If the session is busy (409).
        """
        response = self._send(
            "POST",
            f"/session/{path_segment(session_id)}/unrevert",
            **request_spec(directory=directory, workspace=workspace),
        )
        return validate_response(response, TYPE_ADAPTERS.session)

    def init(
        self,
        session_id: str,
        provider_id: str,
        model_id: str,
        message_id: str,
        directory: str | None = None,
        workspace: str | None = None,
    ) -> bool:
        """Run project initialization (AGENTS.md discovery) with the given model."""
        json_body = init_body(provider_id, model_id, message_id)
        response = self._send(
            "POST",
            f"/session/{path_segment(session_id)}/init",
            **request_spec(directory=directory, workspace=workspace, json_body=json_body),
        )
        return validate_response(response, TYPE_ADAPTERS.bool)

    # -- interaction ------------------------------------------------------

    def respond_permission(
        self,
        session_id: str,
        permission_id: str,
        response: str,
        directory: str | None = None,
        workspace: str | None = None,
    ) -> bool:
        """Answer a pending permission request (``once``/``always``/``reject``).

        Args:
            response: One of ``"once"``, ``"always"`` or ``"reject"``.
        """
        json_body = permission_body(response)
        response_obj = self._send(
            "POST",
            f"/session/{path_segment(session_id)}/permissions/{path_segment(permission_id)}",
            **request_spec(directory=directory, workspace=workspace, json_body=json_body),
        )
        return validate_response(response_obj, TYPE_ADAPTERS.bool)

    # -- messages ---------------------------------------------------------

    def list_messages(
        self,
        session_id: str,
        directory: str | None = None,
        workspace: str | None = None,
        limit: int | None = None,
        before: str | None = None,
    ) -> list[MessageWithParts]:
        """List a session's messages (info + parts), newest first."""
        query = messages_query(limit, before)
        response = self._send(
            "GET",
            f"/session/{path_segment(session_id)}/message",
            **request_spec(directory=directory, workspace=workspace, query=query),
        )
        return validate_response(response, TYPE_ADAPTERS.messages)

    def prompt(
        self,
        session_id: str,
        prompt: str | list[PromptPart],
        model: PromptModel | dict[str, Any] | None = None,
        agent: str | None = None,
        tools: dict[str, bool] | None = None,
        system: str | None = None,
        variant: str | None = None,
        no_reply: bool | None = None,
        message_id: str | None = None,
        directory: str | None = None,
        workspace: str | None = None,
    ) -> MessageWithParts:
        """Send a prompt and wait for the assistant to finish.

        Args:
            prompt: Plain text (wrapped into a text part) or explicit parts.
            model: Target model as :class:`PromptModel` or a raw dict; session default if omitted.

        Returns:
            The assistant message with its parts (text/tool/reasoning/...).
        """
        json_body = prompt_body(
            prompt,
            model=model,
            agent=agent,
            tools=tools,
            system=system,
            variant=variant,
            no_reply=no_reply,
            message_id=message_id,
        )
        response = self._send(
            "POST",
            f"/session/{path_segment(session_id)}/message",
            **request_spec(directory=directory, workspace=workspace, json_body=json_body),
        )
        return validate_response(response, TYPE_ADAPTERS.message)

    def prompt_async(
        self,
        session_id: str,
        prompt: str | list[PromptPart],
        model: PromptModel | dict[str, Any] | None = None,
        agent: str | None = None,
        tools: dict[str, bool] | None = None,
        system: str | None = None,
        variant: str | None = None,
        no_reply: bool | None = None,
        message_id: str | None = None,
        directory: str | None = None,
        workspace: str | None = None,
    ) -> None:
        """Send a prompt and return immediately; follow results over ``server.stream_events()``.

        Args:
            prompt: Plain text or explicit parts.
            model: Target model as :class:`PromptModel` or raw dict; session default if omitted.
        """
        json_body = prompt_body(
            prompt,
            model=model,
            agent=agent,
            tools=tools,
            system=system,
            variant=variant,
            no_reply=no_reply,
            message_id=message_id,
        )
        self._send(
            "POST",
            f"/session/{path_segment(session_id)}/prompt_async",
            **request_spec(directory=directory, workspace=workspace, json_body=json_body),
        )

    def command(
        self,
        session_id: str,
        command: str,
        arguments: str,
        agent: str | None = None,
        model: PromptModel | str | None = None,
        variant: str | None = None,
        message_id: str | None = None,
        parts: list[PromptPart] | None = None,
        directory: str | None = None,
        workspace: str | None = None,
    ) -> MessageWithParts:
        """Execute a configured command (``/init``, custom commands) in the session.

        Args:
            command: The command name to execute.
            arguments: Free-text arguments passed to the command.
            agent: The agent to act as.
            model: Target model; a :class:`PromptModel` is joined into
                ``"provider/model"`` (the wire format for commands), or pass
                an already-joined string.
            variant: Model variant override.
            message_id: Caller-chosen message id (for idempotency).
            parts: Optional file attachments alongside the command.

        Returns:
            The assistant message with its parts.
        """
        json_body = command_body(
            command,
            arguments,
            agent=agent,
            model=model,
            variant=variant,
            message_id=message_id,
            parts=parts,
        )
        response = self._send(
            "POST",
            f"/session/{path_segment(session_id)}/command",
            **request_spec(directory=directory, workspace=workspace, json_body=json_body),
        )
        return validate_response(response, TYPE_ADAPTERS.message)

    def shell(
        self,
        session_id: str,
        command: str,
        agent: str,
        model: PromptModel | dict[str, Any] | None = None,
        message_id: str | None = None,
        directory: str | None = None,
        workspace: str | None = None,
    ) -> MessageWithParts:
        """Run a shell command as a user message (``!cmd`` semantics).

        Args:
            command: The shell command to run.
            agent: The agent to attribute the run to (required by the server).
            model: Target model as :class:`PromptModel` or raw dict; session
                default if omitted.

        Returns:
            The created user message with its parts (tool output follows via events).
        """
        json_body = shell_body(command, agent, model=model, message_id=message_id)
        response = self._send(
            "POST",
            f"/session/{path_segment(session_id)}/shell",
            **request_spec(directory=directory, workspace=workspace, json_body=json_body),
        )
        return validate_response(response, TYPE_ADAPTERS.message)

    def delete_part(
        self,
        session_id: str,
        message_id: str,
        part_id: str,
        directory: str | None = None,
        workspace: str | None = None,
    ) -> bool:
        """Delete one part of a message. Returns ``True`` on success."""
        response = self._send(
            "DELETE",
            f"/session/{path_segment(session_id)}/message/{path_segment(message_id)}/part/{path_segment(part_id)}",
            **request_spec(directory=directory, workspace=workspace),
        )
        return validate_response(response, TYPE_ADAPTERS.bool)

    def update_part(
        self,
        session_id: str,
        message_id: str,
        part_id: str,
        part: Part,
        directory: str | None = None,
        workspace: str | None = None,
    ) -> Part:
        """Replace one part of a message with the given part.

        Args:
            part: The new part; its ``id``/``message_id``/``session_id`` must
                match the path parameters or the server rejects with 400.

        Returns:
            The updated part.
        """
        response = self._send(
            "PATCH",
            f"/session/{path_segment(session_id)}/message/{path_segment(message_id)}/part/{path_segment(part_id)}",
            **request_spec(directory=directory, workspace=workspace, json_body=part.to_wire()),
        )
        return validate_response(response, TYPE_ADAPTERS.part)

    def delete_message(
        self,
        session_id: str,
        message_id: str,
        directory: str | None = None,
        workspace: str | None = None,
    ) -> bool:
        """Delete one message from a session. Returns ``True`` on success."""
        response = self._send(
            "DELETE",
            f"/session/{path_segment(session_id)}/message/{path_segment(message_id)}",
            **request_spec(directory=directory, workspace=workspace),
        )
        return validate_response(response, TYPE_ADAPTERS.bool)


class AsyncSessionsResource(AsyncResource):
    """Asynchronous client for everything under ``/session``."""

    @property
    def with_raw_response(self) -> AsyncSessionsResourceWithRawResponse:
        """Prefix for the raw-response variants of every method below.

        Each call returns the unprocessed :class:`httpx.Response` instead of
        the parsed model (same retries, same error mapping on non-2xx).
        """
        return AsyncSessionsResourceWithRawResponse(self._client)

    # -- CRUD -------------------------------------------------------------

    async def list_sessions(
        self,
        directory: str | None = None,
        workspace: str | None = None,
        scope: str | None = None,
        path: str | None = None,
        roots: bool | None = None,
        start: float | None = None,
        search: str | None = None,
        limit: int | None = None,
    ) -> list[Session]:
        """List sessions, with optional scope/path/time/search filters.

        Returns:
            Sessions matching the filters, newest first.
        """
        query = session_list_query(scope, path, roots, start, search, limit)
        response = await self._send(
            "GET", "/session", **request_spec(directory=directory, workspace=workspace, query=query)
        )
        return validate_response(response, TYPE_ADAPTERS.sessions)

    async def create(
        self,
        directory: str | None = None,
        workspace: str | None = None,
        body: CreateSessionRequest | None = None,
    ) -> Session:
        """Create a session.

        Args:
            directory: Scope to a project directory (server query param).
            workspace: Scope to a workspace (server query param).
            body: Optional creation options (title/agent/model/permission/...).

        Returns:
            The created session.
        """
        json_body = create_body(body)
        response = await self._send(
            "POST", "/session", **request_spec(directory=directory, workspace=workspace, json_body=json_body)
        )
        return validate_response(response, TYPE_ADAPTERS.session)

    async def get(self, session_id: str, directory: str | None = None, workspace: str | None = None) -> Session:
        """Fetch one session by id.

        Raises:
            OpenCodeApiError: If the session does not exist (404).
        """
        response = await self._send(
            "GET", f"/session/{path_segment(session_id)}", **request_spec(directory=directory, workspace=workspace)
        )
        return validate_response(response, TYPE_ADAPTERS.session)

    async def update(
        self,
        session_id: str,
        body: UpdateSessionRequest,
        directory: str | None = None,
        workspace: str | None = None,
    ) -> Session:
        """Update mutable session fields (title/metadata/permission/archived)."""
        json_body = update_body(body)
        response = await self._send(
            "PATCH",
            f"/session/{path_segment(session_id)}",
            **request_spec(directory=directory, workspace=workspace, json_body=json_body),
        )
        return validate_response(response, TYPE_ADAPTERS.session)

    async def delete(self, session_id: str, directory: str | None = None, workspace: str | None = None) -> bool:
        """Delete a session. Returns ``True`` on success."""
        response = await self._send(
            "DELETE", f"/session/{path_segment(session_id)}", **request_spec(directory=directory, workspace=workspace)
        )
        return validate_response(response, TYPE_ADAPTERS.bool)

    # -- lifecycle --------------------------------------------------------

    async def fork(
        self,
        session_id: str,
        message_id: str | None = None,
        directory: str | None = None,
        workspace: str | None = None,
    ) -> Session:
        """Create a branch off an existing session, optionally at a given message."""
        json_body = fork_body(message_id)
        response = await self._send(
            "POST",
            f"/session/{path_segment(session_id)}/fork",
            **request_spec(directory=directory, workspace=workspace, json_body=json_body),
        )
        return validate_response(response, TYPE_ADAPTERS.session)

    async def abort(self, session_id: str, directory: str | None = None, workspace: str | None = None) -> bool:
        """Abort a running session. Returns ``True`` on success."""
        response = await self._send(
            "POST",
            f"/session/{path_segment(session_id)}/abort",
            **request_spec(directory=directory, workspace=workspace),
        )
        return validate_response(response, TYPE_ADAPTERS.bool)

    async def share(self, session_id: str, directory: str | None = None, workspace: str | None = None) -> Session:
        """Publish the session; the updated session carries the share URL."""
        response = await self._send(
            "POST",
            f"/session/{path_segment(session_id)}/share",
            **request_spec(directory=directory, workspace=workspace),
        )
        return validate_response(response, TYPE_ADAPTERS.session)

    async def unshare(self, session_id: str, directory: str | None = None, workspace: str | None = None) -> Session:
        """Remove the session's share URL."""
        response = await self._send(
            "DELETE",
            f"/session/{path_segment(session_id)}/share",
            **request_spec(directory=directory, workspace=workspace),
        )
        return validate_response(response, TYPE_ADAPTERS.session)

    async def summarize(
        self,
        session_id: str,
        provider_id: str,
        model_id: str,
        auto: bool | None = None,
        directory: str | None = None,
        workspace: str | None = None,
    ) -> bool:
        """Ask the server to (re)summarize the session with the given model."""
        json_body = summarize_body(provider_id, model_id, auto)
        response = await self._send(
            "POST",
            f"/session/{path_segment(session_id)}/summarize",
            **request_spec(directory=directory, workspace=workspace, json_body=json_body),
        )
        return validate_response(response, TYPE_ADAPTERS.bool)

    # -- state & history ---------------------------------------------------

    async def status(self, directory: str | None = None, workspace: str | None = None) -> dict[str, SessionStatus]:
        """Report the run state of every active session (idle/busy/retry)."""
        response = await self._send("GET", "/session/status", **request_spec(directory=directory, workspace=workspace))
        return validate_response(response, TYPE_ADAPTERS.status_map)

    async def children(
        self, session_id: str, directory: str | None = None, workspace: str | None = None
    ) -> list[Session]:
        """List the child sessions spawned by this session (subagents/tasks).

        Raises:
            OpenCodeApiError: If the session does not exist (404).
        """
        response = await self._send(
            "GET",
            f"/session/{path_segment(session_id)}/children",
            **request_spec(directory=directory, workspace=workspace),
        )
        return validate_response(response, TYPE_ADAPTERS.sessions)

    async def list_todos(
        self, session_id: str, directory: str | None = None, workspace: str | None = None
    ) -> list[Todo]:
        """List the session's todo list written by the todo tool.

        Raises:
            OpenCodeApiError: If the session does not exist (404).
        """
        response = await self._send(
            "GET", f"/session/{path_segment(session_id)}/todo", **request_spec(directory=directory, workspace=workspace)
        )
        return validate_response(response, TYPE_ADAPTERS.todo_list)

    async def diff(
        self,
        session_id: str,
        message_id: str | None = None,
        directory: str | None = None,
        workspace: str | None = None,
    ) -> list[SessionFileDiff]:
        """List the file changes made by the session's messages.

        Args:
            message_id: Only include changes up to this message.

        Returns:
            Per-file addition/deletion stats with optional patch text.
        """
        query = diff_query(message_id)
        response = await self._send(
            "GET",
            f"/session/{path_segment(session_id)}/diff",
            **request_spec(directory=directory, workspace=workspace, query=query),
        )
        return validate_response(response, TYPE_ADAPTERS.session_diffs)

    async def revert(
        self,
        session_id: str,
        message_id: str,
        part_id: str | None = None,
        directory: str | None = None,
        workspace: str | None = None,
    ) -> Session:
        """Revert messages up to and including ``message_id``.

        Raises:
            OpenCodeConflictError: If the session is busy (409).
        """
        json_body = revert_body(message_id, part_id)
        response = await self._send(
            "POST",
            f"/session/{path_segment(session_id)}/revert",
            **request_spec(directory=directory, workspace=workspace, json_body=json_body),
        )
        return validate_response(response, TYPE_ADAPTERS.session)

    async def unrevert(self, session_id: str, directory: str | None = None, workspace: str | None = None) -> Session:
        """Restore previously reverted messages.

        Raises:
            OpenCodeConflictError: If the session is busy (409).
        """
        response = await self._send(
            "POST",
            f"/session/{path_segment(session_id)}/unrevert",
            **request_spec(directory=directory, workspace=workspace),
        )
        return validate_response(response, TYPE_ADAPTERS.session)

    async def init(
        self,
        session_id: str,
        provider_id: str,
        model_id: str,
        message_id: str,
        directory: str | None = None,
        workspace: str | None = None,
    ) -> bool:
        """Run project initialization (AGENTS.md discovery) with the given model."""
        json_body = init_body(provider_id, model_id, message_id)
        response = await self._send(
            "POST",
            f"/session/{path_segment(session_id)}/init",
            **request_spec(directory=directory, workspace=workspace, json_body=json_body),
        )
        return validate_response(response, TYPE_ADAPTERS.bool)

    # -- interaction ------------------------------------------------------

    async def respond_permission(
        self,
        session_id: str,
        permission_id: str,
        response: str,
        directory: str | None = None,
        workspace: str | None = None,
    ) -> bool:
        """Answer a pending permission request (``once``/``always``/``reject``).

        Args:
            response: One of ``"once"``, ``"always"`` or ``"reject"``.
        """
        json_body = permission_body(response)
        response_obj = await self._send(
            "POST",
            f"/session/{path_segment(session_id)}/permissions/{path_segment(permission_id)}",
            **request_spec(directory=directory, workspace=workspace, json_body=json_body),
        )
        return validate_response(response_obj, TYPE_ADAPTERS.bool)

    # -- messages ---------------------------------------------------------

    async def list_messages(
        self,
        session_id: str,
        directory: str | None = None,
        workspace: str | None = None,
        limit: int | None = None,
        before: str | None = None,
    ) -> list[MessageWithParts]:
        """List a session's messages (info + parts), newest first."""
        query = messages_query(limit, before)
        response = await self._send(
            "GET",
            f"/session/{path_segment(session_id)}/message",
            **request_spec(directory=directory, workspace=workspace, query=query),
        )
        return validate_response(response, TYPE_ADAPTERS.messages)

    async def prompt(
        self,
        session_id: str,
        prompt: str | list[PromptPart],
        model: PromptModel | dict[str, Any] | None = None,
        agent: str | None = None,
        tools: dict[str, bool] | None = None,
        system: str | None = None,
        variant: str | None = None,
        no_reply: bool | None = None,
        message_id: str | None = None,
        directory: str | None = None,
        workspace: str | None = None,
    ) -> MessageWithParts:
        """Send a prompt and wait for the assistant to finish.

        Args:
            prompt: Plain text (wrapped into a text part) or explicit parts.
            model: Target model as :class:`PromptModel` or a raw dict; session default if omitted.

        Returns:
            The assistant message with its parts (text/tool/reasoning/...).
        """
        json_body = prompt_body(
            prompt,
            model=model,
            agent=agent,
            tools=tools,
            system=system,
            variant=variant,
            no_reply=no_reply,
            message_id=message_id,
        )
        response = await self._send(
            "POST",
            f"/session/{path_segment(session_id)}/message",
            **request_spec(directory=directory, workspace=workspace, json_body=json_body),
        )
        return validate_response(response, TYPE_ADAPTERS.message)

    async def prompt_async(
        self,
        session_id: str,
        prompt: str | list[PromptPart],
        model: PromptModel | dict[str, Any] | None = None,
        agent: str | None = None,
        tools: dict[str, bool] | None = None,
        system: str | None = None,
        variant: str | None = None,
        no_reply: bool | None = None,
        message_id: str | None = None,
        directory: str | None = None,
        workspace: str | None = None,
    ) -> None:
        """Send a prompt and return immediately; follow results over ``server.stream_events()``.

        Args:
            prompt: Plain text or explicit parts.
            model: Target model as :class:`PromptModel` or raw dict; session default if omitted.
        """
        json_body = prompt_body(
            prompt,
            model=model,
            agent=agent,
            tools=tools,
            system=system,
            variant=variant,
            no_reply=no_reply,
            message_id=message_id,
        )
        await self._send(
            "POST",
            f"/session/{path_segment(session_id)}/prompt_async",
            **request_spec(directory=directory, workspace=workspace, json_body=json_body),
        )

    async def command(
        self,
        session_id: str,
        command: str,
        arguments: str,
        agent: str | None = None,
        model: PromptModel | str | None = None,
        variant: str | None = None,
        message_id: str | None = None,
        parts: list[PromptPart] | None = None,
        directory: str | None = None,
        workspace: str | None = None,
    ) -> MessageWithParts:
        """Execute a configured command (``/init``, custom commands) in the session.

        Args:
            command: The command name to execute.
            arguments: Free-text arguments passed to the command.
            agent: The agent to act as.
            model: Target model; a :class:`PromptModel` is joined into
                ``"provider/model"`` (the wire format for commands), or pass
                an already-joined string.
            variant: Model variant override.
            message_id: Caller-chosen message id (for idempotency).
            parts: Optional file attachments alongside the command.

        Returns:
            The assistant message with its parts.
        """
        json_body = command_body(
            command,
            arguments,
            agent=agent,
            model=model,
            variant=variant,
            message_id=message_id,
            parts=parts,
        )
        response = await self._send(
            "POST",
            f"/session/{path_segment(session_id)}/command",
            **request_spec(directory=directory, workspace=workspace, json_body=json_body),
        )
        return validate_response(response, TYPE_ADAPTERS.message)

    async def shell(
        self,
        session_id: str,
        command: str,
        agent: str,
        model: PromptModel | dict[str, Any] | None = None,
        message_id: str | None = None,
        directory: str | None = None,
        workspace: str | None = None,
    ) -> MessageWithParts:
        """Run a shell command as a user message (``!cmd`` semantics).

        Args:
            command: The shell command to run.
            agent: The agent to attribute the run to (required by the server).
            model: Target model as :class:`PromptModel` or raw dict; session
                default if omitted.

        Returns:
            The created user message with its parts (tool output follows via events).
        """
        json_body = shell_body(command, agent, model=model, message_id=message_id)
        response = await self._send(
            "POST",
            f"/session/{path_segment(session_id)}/shell",
            **request_spec(directory=directory, workspace=workspace, json_body=json_body),
        )
        return validate_response(response, TYPE_ADAPTERS.message)

    async def delete_part(
        self,
        session_id: str,
        message_id: str,
        part_id: str,
        directory: str | None = None,
        workspace: str | None = None,
    ) -> bool:
        """Delete one part of a message. Returns ``True`` on success."""
        response = await self._send(
            "DELETE",
            f"/session/{path_segment(session_id)}/message/{path_segment(message_id)}/part/{path_segment(part_id)}",
            **request_spec(directory=directory, workspace=workspace),
        )
        return validate_response(response, TYPE_ADAPTERS.bool)

    async def update_part(
        self,
        session_id: str,
        message_id: str,
        part_id: str,
        part: Part,
        directory: str | None = None,
        workspace: str | None = None,
    ) -> Part:
        """Replace one part of a message with the given part.

        Args:
            part: The new part; its ``id``/``message_id``/``session_id`` must
                match the path parameters or the server rejects with 400.

        Returns:
            The updated part.
        """
        response = await self._send(
            "PATCH",
            f"/session/{path_segment(session_id)}/message/{path_segment(message_id)}/part/{path_segment(part_id)}",
            **request_spec(directory=directory, workspace=workspace, json_body=part.to_wire()),
        )
        return validate_response(response, TYPE_ADAPTERS.part)

    async def delete_message(
        self,
        session_id: str,
        message_id: str,
        directory: str | None = None,
        workspace: str | None = None,
    ) -> bool:
        """Delete one message from a session. Returns ``True`` on success."""
        response = await self._send(
            "DELETE",
            f"/session/{path_segment(session_id)}/message/{path_segment(message_id)}",
            **request_spec(directory=directory, workspace=workspace),
        )
        return validate_response(response, TYPE_ADAPTERS.bool)


class SessionsResourceWithRawResponse(Resource):
    """Synchronous raw-response view: same calls, returns ``httpx.Response``.

    Mirrors :class:`SessionsResource` method-for-method but returns the
    unprocessed response (headers / status / raw body) instead of the parsed
    model. Non-2xx still raise the same mapped errors; retries are shared.
    """

    def list_sessions(
        self,
        directory: str | None = None,
        workspace: str | None = None,
        scope: str | None = None,
        path: str | None = None,
        roots: bool | None = None,
        start: float | None = None,
        search: str | None = None,
        limit: int | None = None,
    ) -> httpx.Response:
        """List sessions; return the raw response."""
        query = session_list_query(scope, path, roots, start, search, limit)
        return self._send("GET", "/session", **request_spec(directory=directory, workspace=workspace, query=query))

    def create(
        self,
        directory: str | None = None,
        workspace: str | None = None,
        body: CreateSessionRequest | None = None,
    ) -> httpx.Response:
        """Create a session; return the raw response."""
        json_body = create_body(body)
        return self._send(
            "POST", "/session", **request_spec(directory=directory, workspace=workspace, json_body=json_body)
        )

    def get(self, session_id: str, directory: str | None = None, workspace: str | None = None) -> httpx.Response:
        """Fetch one session; return the raw response."""
        return self._send(
            "GET", f"/session/{path_segment(session_id)}", **request_spec(directory=directory, workspace=workspace)
        )

    def update(
        self,
        session_id: str,
        body: UpdateSessionRequest,
        directory: str | None = None,
        workspace: str | None = None,
    ) -> httpx.Response:
        """Update a session; return the raw response."""
        json_body = update_body(body)
        return self._send(
            "PATCH",
            f"/session/{path_segment(session_id)}",
            **request_spec(directory=directory, workspace=workspace, json_body=json_body),
        )

    def delete(self, session_id: str, directory: str | None = None, workspace: str | None = None) -> httpx.Response:
        """Delete a session; return the raw response."""
        return self._send(
            "DELETE", f"/session/{path_segment(session_id)}", **request_spec(directory=directory, workspace=workspace)
        )

    def fork(
        self,
        session_id: str,
        message_id: str | None = None,
        directory: str | None = None,
        workspace: str | None = None,
    ) -> httpx.Response:
        """Fork a session; return the raw response."""
        json_body = fork_body(message_id)
        return self._send(
            "POST",
            f"/session/{path_segment(session_id)}/fork",
            **request_spec(directory=directory, workspace=workspace, json_body=json_body),
        )

    def abort(self, session_id: str, directory: str | None = None, workspace: str | None = None) -> httpx.Response:
        """Abort a session; return the raw response."""
        return self._send(
            "POST",
            f"/session/{path_segment(session_id)}/abort",
            **request_spec(directory=directory, workspace=workspace),
        )

    def share(self, session_id: str, directory: str | None = None, workspace: str | None = None) -> httpx.Response:
        """Publish a session; return the raw response."""
        return self._send(
            "POST",
            f"/session/{path_segment(session_id)}/share",
            **request_spec(directory=directory, workspace=workspace),
        )

    def unshare(self, session_id: str, directory: str | None = None, workspace: str | None = None) -> httpx.Response:
        """Withdraw a session's share; return the raw response."""
        return self._send(
            "DELETE",
            f"/session/{path_segment(session_id)}/share",
            **request_spec(directory=directory, workspace=workspace),
        )

    def summarize(
        self,
        session_id: str,
        provider_id: str,
        model_id: str,
        auto: bool | None = None,
        directory: str | None = None,
        workspace: str | None = None,
    ) -> httpx.Response:
        """Ask for a summary; return the raw response."""
        json_body = summarize_body(provider_id, model_id, auto)
        return self._send(
            "POST",
            f"/session/{path_segment(session_id)}/summarize",
            **request_spec(directory=directory, workspace=workspace, json_body=json_body),
        )

    def status(self, directory: str | None = None, workspace: str | None = None) -> httpx.Response:
        """Report session run states; return the raw response."""
        return self._send("GET", "/session/status", **request_spec(directory=directory, workspace=workspace))

    def children(self, session_id: str, directory: str | None = None, workspace: str | None = None) -> httpx.Response:
        """List child sessions; return the raw response."""
        return self._send(
            "GET",
            f"/session/{path_segment(session_id)}/children",
            **request_spec(directory=directory, workspace=workspace),
        )

    def list_todos(self, session_id: str, directory: str | None = None, workspace: str | None = None) -> httpx.Response:
        """List the session's todos; return the raw response."""
        return self._send(
            "GET", f"/session/{path_segment(session_id)}/todo", **request_spec(directory=directory, workspace=workspace)
        )

    def diff(
        self,
        session_id: str,
        message_id: str | None = None,
        directory: str | None = None,
        workspace: str | None = None,
    ) -> httpx.Response:
        """List the session's file changes; return the raw response."""
        query = diff_query(message_id)
        return self._send(
            "GET",
            f"/session/{path_segment(session_id)}/diff",
            **request_spec(directory=directory, workspace=workspace, query=query),
        )

    def revert(
        self,
        session_id: str,
        message_id: str,
        part_id: str | None = None,
        directory: str | None = None,
        workspace: str | None = None,
    ) -> httpx.Response:
        """Revert messages; return the raw response."""
        json_body = revert_body(message_id, part_id)
        return self._send(
            "POST",
            f"/session/{path_segment(session_id)}/revert",
            **request_spec(directory=directory, workspace=workspace, json_body=json_body),
        )

    def unrevert(self, session_id: str, directory: str | None = None, workspace: str | None = None) -> httpx.Response:
        """Restore reverted messages; return the raw response."""
        return self._send(
            "POST",
            f"/session/{path_segment(session_id)}/unrevert",
            **request_spec(directory=directory, workspace=workspace),
        )

    def init(
        self,
        session_id: str,
        provider_id: str,
        model_id: str,
        message_id: str,
        directory: str | None = None,
        workspace: str | None = None,
    ) -> httpx.Response:
        """Run project initialization; return the raw response."""
        json_body = init_body(provider_id, model_id, message_id)
        return self._send(
            "POST",
            f"/session/{path_segment(session_id)}/init",
            **request_spec(directory=directory, workspace=workspace, json_body=json_body),
        )

    def respond_permission(
        self,
        session_id: str,
        permission_id: str,
        response: str,
        directory: str | None = None,
        workspace: str | None = None,
    ) -> httpx.Response:
        """Answer a permission request; return the raw response."""
        json_body = permission_body(response)
        return self._send(
            "POST",
            f"/session/{path_segment(session_id)}/permissions/{path_segment(permission_id)}",
            **request_spec(directory=directory, workspace=workspace, json_body=json_body),
        )

    def list_messages(
        self,
        session_id: str,
        directory: str | None = None,
        workspace: str | None = None,
        limit: int | None = None,
        before: str | None = None,
    ) -> httpx.Response:
        """List a session's messages; return the raw response."""
        query = messages_query(limit, before)
        return self._send(
            "GET",
            f"/session/{path_segment(session_id)}/message",
            **request_spec(directory=directory, workspace=workspace, query=query),
        )

    def prompt(
        self,
        session_id: str,
        prompt: str | list[PromptPart],
        model: PromptModel | dict[str, Any] | None = None,
        agent: str | None = None,
        tools: dict[str, bool] | None = None,
        system: str | None = None,
        variant: str | None = None,
        no_reply: bool | None = None,
        message_id: str | None = None,
        directory: str | None = None,
        workspace: str | None = None,
    ) -> httpx.Response:
        """Send a prompt (blocking); return the raw response."""
        json_body = prompt_body(
            prompt,
            model=model,
            agent=agent,
            tools=tools,
            system=system,
            variant=variant,
            no_reply=no_reply,
            message_id=message_id,
        )
        return self._send(
            "POST",
            f"/session/{path_segment(session_id)}/message",
            **request_spec(directory=directory, workspace=workspace, json_body=json_body),
        )

    def prompt_async(
        self,
        session_id: str,
        prompt: str | list[PromptPart],
        model: PromptModel | dict[str, Any] | None = None,
        agent: str | None = None,
        tools: dict[str, bool] | None = None,
        system: str | None = None,
        variant: str | None = None,
        no_reply: bool | None = None,
        message_id: str | None = None,
        directory: str | None = None,
        workspace: str | None = None,
    ) -> httpx.Response:
        """Send a prompt (fire-and-forget); return the raw response."""
        json_body = prompt_body(
            prompt,
            model=model,
            agent=agent,
            tools=tools,
            system=system,
            variant=variant,
            no_reply=no_reply,
            message_id=message_id,
        )
        return self._send(
            "POST",
            f"/session/{path_segment(session_id)}/prompt_async",
            **request_spec(directory=directory, workspace=workspace, json_body=json_body),
        )

    def command(
        self,
        session_id: str,
        command: str,
        arguments: str,
        agent: str | None = None,
        model: PromptModel | str | None = None,
        variant: str | None = None,
        message_id: str | None = None,
        parts: list[PromptPart] | None = None,
        directory: str | None = None,
        workspace: str | None = None,
    ) -> httpx.Response:
        """Execute a command; return the raw response."""
        json_body = command_body(
            command,
            arguments,
            agent=agent,
            model=model,
            variant=variant,
            message_id=message_id,
            parts=parts,
        )
        return self._send(
            "POST",
            f"/session/{path_segment(session_id)}/command",
            **request_spec(directory=directory, workspace=workspace, json_body=json_body),
        )

    def shell(
        self,
        session_id: str,
        command: str,
        agent: str,
        model: PromptModel | dict[str, Any] | None = None,
        message_id: str | None = None,
        directory: str | None = None,
        workspace: str | None = None,
    ) -> httpx.Response:
        """Run a shell command; return the raw response."""
        json_body = shell_body(command, agent, model=model, message_id=message_id)
        return self._send(
            "POST",
            f"/session/{path_segment(session_id)}/shell",
            **request_spec(directory=directory, workspace=workspace, json_body=json_body),
        )

    def delete_part(
        self,
        session_id: str,
        message_id: str,
        part_id: str,
        directory: str | None = None,
        workspace: str | None = None,
    ) -> httpx.Response:
        """Delete one part; return the raw response."""
        return self._send(
            "DELETE",
            f"/session/{path_segment(session_id)}/message/{path_segment(message_id)}/part/{path_segment(part_id)}",
            **request_spec(directory=directory, workspace=workspace),
        )

    def update_part(
        self,
        session_id: str,
        message_id: str,
        part_id: str,
        part: Part,
        directory: str | None = None,
        workspace: str | None = None,
    ) -> httpx.Response:
        """Replace one part; return the raw response."""
        return self._send(
            "PATCH",
            f"/session/{path_segment(session_id)}/message/{path_segment(message_id)}/part/{path_segment(part_id)}",
            **request_spec(directory=directory, workspace=workspace, json_body=part.to_wire()),
        )

    def delete_message(
        self,
        session_id: str,
        message_id: str,
        directory: str | None = None,
        workspace: str | None = None,
    ) -> httpx.Response:
        """Delete one message; return the raw response."""
        return self._send(
            "DELETE",
            f"/session/{path_segment(session_id)}/message/{path_segment(message_id)}",
            **request_spec(directory=directory, workspace=workspace),
        )


class AsyncSessionsResourceWithRawResponse(AsyncResource):
    """Asynchronous raw-response view: same calls, returns ``httpx.Response``.

    Mirrors :class:`AsyncSessionsResource` method-for-method but returns the
    unprocessed response instead of the parsed model. Non-2xx still raise the
    same mapped errors; retries are shared.
    """

    async def list_sessions(
        self,
        directory: str | None = None,
        workspace: str | None = None,
        scope: str | None = None,
        path: str | None = None,
        roots: bool | None = None,
        start: float | None = None,
        search: str | None = None,
        limit: int | None = None,
    ) -> httpx.Response:
        """List sessions; return the raw response."""
        query = session_list_query(scope, path, roots, start, search, limit)
        return await self._send(
            "GET", "/session", **request_spec(directory=directory, workspace=workspace, query=query)
        )

    async def create(
        self,
        directory: str | None = None,
        workspace: str | None = None,
        body: CreateSessionRequest | None = None,
    ) -> httpx.Response:
        """Create a session; return the raw response."""
        json_body = create_body(body)
        return await self._send(
            "POST", "/session", **request_spec(directory=directory, workspace=workspace, json_body=json_body)
        )

    async def get(self, session_id: str, directory: str | None = None, workspace: str | None = None) -> httpx.Response:
        """Fetch one session; return the raw response."""
        return await self._send(
            "GET", f"/session/{path_segment(session_id)}", **request_spec(directory=directory, workspace=workspace)
        )

    async def update(
        self,
        session_id: str,
        body: UpdateSessionRequest,
        directory: str | None = None,
        workspace: str | None = None,
    ) -> httpx.Response:
        """Update a session; return the raw response."""
        json_body = update_body(body)
        return await self._send(
            "PATCH",
            f"/session/{path_segment(session_id)}",
            **request_spec(directory=directory, workspace=workspace, json_body=json_body),
        )

    async def delete(
        self, session_id: str, directory: str | None = None, workspace: str | None = None
    ) -> httpx.Response:
        """Delete a session; return the raw response."""
        return await self._send(
            "DELETE", f"/session/{path_segment(session_id)}", **request_spec(directory=directory, workspace=workspace)
        )

    async def fork(
        self,
        session_id: str,
        message_id: str | None = None,
        directory: str | None = None,
        workspace: str | None = None,
    ) -> httpx.Response:
        """Fork a session; return the raw response."""
        json_body = fork_body(message_id)
        return await self._send(
            "POST",
            f"/session/{path_segment(session_id)}/fork",
            **request_spec(directory=directory, workspace=workspace, json_body=json_body),
        )

    async def abort(
        self, session_id: str, directory: str | None = None, workspace: str | None = None
    ) -> httpx.Response:
        """Abort a session; return the raw response."""
        return await self._send(
            "POST",
            f"/session/{path_segment(session_id)}/abort",
            **request_spec(directory=directory, workspace=workspace),
        )

    async def share(
        self, session_id: str, directory: str | None = None, workspace: str | None = None
    ) -> httpx.Response:
        """Publish a session; return the raw response."""
        return await self._send(
            "POST",
            f"/session/{path_segment(session_id)}/share",
            **request_spec(directory=directory, workspace=workspace),
        )

    async def unshare(
        self, session_id: str, directory: str | None = None, workspace: str | None = None
    ) -> httpx.Response:
        """Withdraw a session's share; return the raw response."""
        return await self._send(
            "DELETE",
            f"/session/{path_segment(session_id)}/share",
            **request_spec(directory=directory, workspace=workspace),
        )

    async def summarize(
        self,
        session_id: str,
        provider_id: str,
        model_id: str,
        auto: bool | None = None,
        directory: str | None = None,
        workspace: str | None = None,
    ) -> httpx.Response:
        """Ask for a summary; return the raw response."""
        json_body = summarize_body(provider_id, model_id, auto)
        return await self._send(
            "POST",
            f"/session/{path_segment(session_id)}/summarize",
            **request_spec(directory=directory, workspace=workspace, json_body=json_body),
        )

    async def status(self, directory: str | None = None, workspace: str | None = None) -> httpx.Response:
        """Report session run states; return the raw response."""
        return await self._send("GET", "/session/status", **request_spec(directory=directory, workspace=workspace))

    async def children(
        self, session_id: str, directory: str | None = None, workspace: str | None = None
    ) -> httpx.Response:
        """List child sessions; return the raw response."""
        return await self._send(
            "GET",
            f"/session/{path_segment(session_id)}/children",
            **request_spec(directory=directory, workspace=workspace),
        )

    async def list_todos(
        self, session_id: str, directory: str | None = None, workspace: str | None = None
    ) -> httpx.Response:
        """List the session's todos; return the raw response."""
        return await self._send(
            "GET", f"/session/{path_segment(session_id)}/todo", **request_spec(directory=directory, workspace=workspace)
        )

    async def diff(
        self,
        session_id: str,
        message_id: str | None = None,
        directory: str | None = None,
        workspace: str | None = None,
    ) -> httpx.Response:
        """List the session's file changes; return the raw response."""
        query = diff_query(message_id)
        return await self._send(
            "GET",
            f"/session/{path_segment(session_id)}/diff",
            **request_spec(directory=directory, workspace=workspace, query=query),
        )

    async def revert(
        self,
        session_id: str,
        message_id: str,
        part_id: str | None = None,
        directory: str | None = None,
        workspace: str | None = None,
    ) -> httpx.Response:
        """Revert messages; return the raw response."""
        json_body = revert_body(message_id, part_id)
        return await self._send(
            "POST",
            f"/session/{path_segment(session_id)}/revert",
            **request_spec(directory=directory, workspace=workspace, json_body=json_body),
        )

    async def unrevert(
        self, session_id: str, directory: str | None = None, workspace: str | None = None
    ) -> httpx.Response:
        """Restore reverted messages; return the raw response."""
        return await self._send(
            "POST",
            f"/session/{path_segment(session_id)}/unrevert",
            **request_spec(directory=directory, workspace=workspace),
        )

    async def init(
        self,
        session_id: str,
        provider_id: str,
        model_id: str,
        message_id: str,
        directory: str | None = None,
        workspace: str | None = None,
    ) -> httpx.Response:
        """Run project initialization; return the raw response."""
        json_body = init_body(provider_id, model_id, message_id)
        return await self._send(
            "POST",
            f"/session/{path_segment(session_id)}/init",
            **request_spec(directory=directory, workspace=workspace, json_body=json_body),
        )

    async def respond_permission(
        self,
        session_id: str,
        permission_id: str,
        response: str,
        directory: str | None = None,
        workspace: str | None = None,
    ) -> httpx.Response:
        """Answer a permission request; return the raw response."""
        json_body = permission_body(response)
        return await self._send(
            "POST",
            f"/session/{path_segment(session_id)}/permissions/{path_segment(permission_id)}",
            **request_spec(directory=directory, workspace=workspace, json_body=json_body),
        )

    async def list_messages(
        self,
        session_id: str,
        directory: str | None = None,
        workspace: str | None = None,
        limit: int | None = None,
        before: str | None = None,
    ) -> httpx.Response:
        """List a session's messages; return the raw response."""
        query = messages_query(limit, before)
        return await self._send(
            "GET",
            f"/session/{path_segment(session_id)}/message",
            **request_spec(directory=directory, workspace=workspace, query=query),
        )

    async def prompt(
        self,
        session_id: str,
        prompt: str | list[PromptPart],
        model: PromptModel | dict[str, Any] | None = None,
        agent: str | None = None,
        tools: dict[str, bool] | None = None,
        system: str | None = None,
        variant: str | None = None,
        no_reply: bool | None = None,
        message_id: str | None = None,
        directory: str | None = None,
        workspace: str | None = None,
    ) -> httpx.Response:
        """Send a prompt (blocking); return the raw response."""
        json_body = prompt_body(
            prompt,
            model=model,
            agent=agent,
            tools=tools,
            system=system,
            variant=variant,
            no_reply=no_reply,
            message_id=message_id,
        )
        return await self._send(
            "POST",
            f"/session/{path_segment(session_id)}/message",
            **request_spec(directory=directory, workspace=workspace, json_body=json_body),
        )

    async def prompt_async(
        self,
        session_id: str,
        prompt: str | list[PromptPart],
        model: PromptModel | dict[str, Any] | None = None,
        agent: str | None = None,
        tools: dict[str, bool] | None = None,
        system: str | None = None,
        variant: str | None = None,
        no_reply: bool | None = None,
        message_id: str | None = None,
        directory: str | None = None,
        workspace: str | None = None,
    ) -> httpx.Response:
        """Send a prompt (fire-and-forget); return the raw response."""
        json_body = prompt_body(
            prompt,
            model=model,
            agent=agent,
            tools=tools,
            system=system,
            variant=variant,
            no_reply=no_reply,
            message_id=message_id,
        )
        return await self._send(
            "POST",
            f"/session/{path_segment(session_id)}/prompt_async",
            **request_spec(directory=directory, workspace=workspace, json_body=json_body),
        )

    async def command(
        self,
        session_id: str,
        command: str,
        arguments: str,
        agent: str | None = None,
        model: PromptModel | str | None = None,
        variant: str | None = None,
        message_id: str | None = None,
        parts: list[PromptPart] | None = None,
        directory: str | None = None,
        workspace: str | None = None,
    ) -> httpx.Response:
        """Execute a command; return the raw response."""
        json_body = command_body(
            command,
            arguments,
            agent=agent,
            model=model,
            variant=variant,
            message_id=message_id,
            parts=parts,
        )
        return await self._send(
            "POST",
            f"/session/{path_segment(session_id)}/command",
            **request_spec(directory=directory, workspace=workspace, json_body=json_body),
        )

    async def shell(
        self,
        session_id: str,
        command: str,
        agent: str,
        model: PromptModel | dict[str, Any] | None = None,
        message_id: str | None = None,
        directory: str | None = None,
        workspace: str | None = None,
    ) -> httpx.Response:
        """Run a shell command; return the raw response."""
        json_body = shell_body(command, agent, model=model, message_id=message_id)
        return await self._send(
            "POST",
            f"/session/{path_segment(session_id)}/shell",
            **request_spec(directory=directory, workspace=workspace, json_body=json_body),
        )

    async def delete_part(
        self,
        session_id: str,
        message_id: str,
        part_id: str,
        directory: str | None = None,
        workspace: str | None = None,
    ) -> httpx.Response:
        """Delete one part; return the raw response."""
        return await self._send(
            "DELETE",
            f"/session/{path_segment(session_id)}/message/{path_segment(message_id)}/part/{path_segment(part_id)}",
            **request_spec(directory=directory, workspace=workspace),
        )

    async def update_part(
        self,
        session_id: str,
        message_id: str,
        part_id: str,
        part: Part,
        directory: str | None = None,
        workspace: str | None = None,
    ) -> httpx.Response:
        """Replace one part; return the raw response."""
        return await self._send(
            "PATCH",
            f"/session/{path_segment(session_id)}/message/{path_segment(message_id)}/part/{path_segment(part_id)}",
            **request_spec(directory=directory, workspace=workspace, json_body=part.to_wire()),
        )

    async def delete_message(
        self,
        session_id: str,
        message_id: str,
        directory: str | None = None,
        workspace: str | None = None,
    ) -> httpx.Response:
        """Delete one message; return the raw response."""
        return await self._send(
            "DELETE",
            f"/session/{path_segment(session_id)}/message/{path_segment(message_id)}",
            **request_spec(directory=directory, workspace=workspace),
        )

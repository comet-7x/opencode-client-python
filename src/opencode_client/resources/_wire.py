"""Shared request-spec + response-parse helpers, used by both sync and async resources.

An *endpoint* is reduced to three pure, transport-agnostic pieces that do not
depend on sync/async at all:

- query params (see :func:`base.query_params` / :func:`request_spec`),
- an optional JSON body assembled by :func:`prompt_body` and friends,
- a :class:`~pydantic.TypeAdapter` matched to the response shape.

``sync`` and ``async`` resources therefore only differ in *how* they send the
request and parse the response, never in *what* is sent or how it is shaped.
"""

from __future__ import annotations

import builtins
from typing import Any, Literal, TypeVar
from urllib.parse import quote

import httpx
from pydantic import TypeAdapter, ValidationError

from ..errors import make_response_error
from ..models import (
    Agent,
    AuthCredentials,
    Command,
    CreateSessionRequest,
    FileChange,
    FileContent,
    FileNode,
    FormatterStatus,
    Health,
    LSPStatus,
    McpLocalConfig,
    McpOAuthStart,
    McpRemoteConfig,
    MCPStatus,
    MessageWithParts,
    Part,
    PermissionRequest,
    Project,
    ProjectDirectory,
    PromptModel,
    PromptPart,
    ProviderList,
    QuestionRequest,
    ServerPaths,
    Session,
    SessionFileDiff,
    SessionStatus,
    Skill,
    Symbol,
    TextMatch,
    TextPartInput,
    Todo,
    UpdateProjectRequest,
    UpdateSessionRequest,
    VcsFileDiff,
    VcsFileStatus,
    VcsInfo,
)
from .base import query_params

__all__ = [
    "TYPE_ADAPTERS",
    "command_body",
    "create_body",
    "diff_query",
    "find_file_query",
    "fork_body",
    "init_body",
    "messages_query",
    "mcp_add_body",
    "path_segment",
    "permission_body",
    "prompt_body",
    "request_spec",
    "revert_body",
    "session_list_query",
    "shell_body",
    "summarize_body",
    "update_body",
    "validate_response",
    "validate_text",
    "vcs_apply_body",
    "vcs_diff_query",
    "permission_reply_body",
    "question_reply_body",
]

_T = TypeVar("_T")


class TypeAdapters:
    """Module-lifetime :class:`pydantic.TypeAdapter` constants, one per response shape.

    Keeping them in one namespace avoids regenerating adapters on every call and
    makes each endpoint's response type explicit (``list[Session]`` etc.).
    """

    #: ``GET /session`` -> list of sessions.
    sessions: TypeAdapter[list[Session]] = TypeAdapter(list[Session])
    #: Single session (create/get/update/fork/share/unshare).
    session: TypeAdapter[Session] = TypeAdapter(Session)
    #: ``GET /session/{id}/message`` -> list of message+parts.
    messages: TypeAdapter[list[MessageWithParts]] = TypeAdapter(list[MessageWithParts])
    #: ``POST /session/{id}/message`` -> assistant message+parts.
    message: TypeAdapter[MessageWithParts] = TypeAdapter(MessageWithParts)
    #: Boolean responses (delete/abort/share/summarize/delete_message/permission).
    bool: TypeAdapter[bool] = TypeAdapter(bool)
    #: ``GET /global/health``.
    health: TypeAdapter[Health] = TypeAdapter(Health)
    #: ``GET /agent``.
    agent_list: TypeAdapter[list[Agent]] = TypeAdapter(list[Agent])
    #: ``GET /command``.
    command_list: TypeAdapter[list[Command]] = TypeAdapter(list[Command])
    #: ``GET /provider``.
    provider_list: TypeAdapter[ProviderList] = TypeAdapter(ProviderList)
    #: ``GET/PATCH /config``.
    config: TypeAdapter[dict[str, Any]] = TypeAdapter(dict[str, Any])
    #: ``GET /permission``.
    permission_requests: TypeAdapter[list[PermissionRequest]] = TypeAdapter(list[PermissionRequest])
    #: ``GET /question``.
    question_requests: TypeAdapter[list[QuestionRequest]] = TypeAdapter(list[QuestionRequest])
    #: ``GET /vcs``.
    vcs_info: TypeAdapter[VcsInfo] = TypeAdapter(VcsInfo)
    #: ``GET /vcs/status``.
    vcs_status: TypeAdapter[list[VcsFileStatus]] = TypeAdapter(list[VcsFileStatus])
    #: ``GET /vcs/diff``.
    vcs_diff: TypeAdapter[list[VcsFileDiff]] = TypeAdapter(list[VcsFileDiff])
    #: ``POST /vcs/apply`` result document.
    vcs_apply: TypeAdapter[dict[str, Any]] = TypeAdapter(dict[str, Any])
    #: ``GET /skill``.
    skill_list: TypeAdapter[list[Skill]] = TypeAdapter(list[Skill])
    #: ``GET /mcp`` — server name -> status union.
    mcp_status: TypeAdapter[dict[str, MCPStatus]] = TypeAdapter(dict[str, MCPStatus])
    #: ``POST /mcp/{name}/auth`` — browser-flow kick-off document.
    mcp_oauth_start: TypeAdapter[McpOAuthStart] = TypeAdapter(McpOAuthStart)
    #: ``DELETE /mcp/{name}/auth`` — ``{"success": true}`` envelope.
    # the class attribute named ``bool`` above shadows the builtin here
    mcp_oauth_remove: TypeAdapter[dict[str, builtins.bool]] = TypeAdapter(dict[str, builtins.bool])
    #: ``POST /mcp/{name}/auth/{authenticate,callback}`` — one server's status.
    mcp_single_status: TypeAdapter[MCPStatus] = TypeAdapter(MCPStatus)
    #: ``POST /mcp`` result document.
    mcp_add: TypeAdapter[dict[str, Any]] = TypeAdapter(dict[str, Any])
    #: ``GET /session/status`` — session id -> status union.
    status_map: TypeAdapter[dict[str, SessionStatus]] = TypeAdapter(dict[str, SessionStatus])
    #: ``GET /session/{id}/todo``.
    todo_list: TypeAdapter[list[Todo]] = TypeAdapter(list[Todo])
    #: ``GET /session/{id}/diff``.
    session_diffs: TypeAdapter[list[SessionFileDiff]] = TypeAdapter(list[SessionFileDiff])
    #: ``PATCH /session/{id}/message/{mid}/part/{pid}``.
    part: TypeAdapter[Part] = TypeAdapter(Part)
    #: ``GET /file``.
    file_nodes: TypeAdapter[list[FileNode]] = TypeAdapter(list[FileNode])
    #: ``GET /file/content`` — text/binary discriminated union.
    file_content: TypeAdapter[FileContent] = TypeAdapter(FileContent)
    #: ``GET /file/status``.
    file_changes: TypeAdapter[list[FileChange]] = TypeAdapter(list[FileChange])
    #: ``GET /find``.
    text_matches: TypeAdapter[list[TextMatch]] = TypeAdapter(list[TextMatch])
    #: ``GET /find/file`` — plain paths.
    found_paths: TypeAdapter[list[str]] = TypeAdapter(list[str])
    #: ``GET /find/symbol``.
    symbols: TypeAdapter[list[Symbol]] = TypeAdapter(list[Symbol])
    #: ``GET /formatter``.
    formatter_statuses: TypeAdapter[list[FormatterStatus]] = TypeAdapter(list[FormatterStatus])
    #: ``GET /project``.
    projects: TypeAdapter[list[Project]] = TypeAdapter(list[Project])
    #: ``GET /project/current`` / ``PATCH /project/{id}`` / ``POST /project/git/init``.
    project: TypeAdapter[Project] = TypeAdapter(Project)
    #: ``GET /project/{id}/directories``.
    project_directories: TypeAdapter[list[ProjectDirectory]] = TypeAdapter(list[ProjectDirectory])
    #: ``GET /path``.
    server_paths: TypeAdapter[ServerPaths] = TypeAdapter(ServerPaths)
    #: ``GET /lsp``.
    lsp_statuses: TypeAdapter[list[LSPStatus]] = TypeAdapter(list[LSPStatus])


#: Shared response validators keyed by response shape.
TYPE_ADAPTERS = TypeAdapters()


def validate_response(response: httpx.Response, adapter: TypeAdapter[_T]) -> _T:
    """Parse a response body into the model described by ``adapter``.

    Shared by the sync and async transports so the parse rule lives in one
    place; the adapter's generic parameter flows through to the return type.

    Args:
        response: A completed (already sent) response.
        adapter: The :class:`TypeAdapter` matching the endpoint's return type.

    Returns:
        The validated model (or list / scalar) described by ``adapter``.

    Raises:
        OpenCodeResponseError: The 2xx body no longer matches the expected
            schema (server/client version drift); wraps the underlying
            :class:`pydantic.ValidationError`.
    """
    try:
        return adapter.validate_python(response.json())
    except ValidationError as exc:
        raise make_response_error(exc) from exc


def path_segment(value: str) -> str:
    """Percent-encode a single path segment for safe interpolation.

    Ids are normally server-issued tokens, but this is a public API: a
    caller-supplied string containing reserved characters would otherwise
    corrupt the request path or silently match a different resource.

    Args:
        value: The raw path segment.

    Returns:
        The percent-encoded segment.
    """
    return quote(value, safe="")


def validate_text(response: httpx.Response) -> str:
    """Return a non-JSON response body as text (e.g. ``GET /vcs/diff/raw``).

    Args:
        response: A completed (already sent) response.

    Returns:
        The decoded body text.
    """
    return response.text


def request_spec(
    *,
    directory: str | None = None,
    workspace: str | None = None,
    query: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the httpx ``**kwargs`` both transports pass to ``client.send``.

    The method and path are supplied separately by the caller; this only
    assembles the query params and optional JSON body. Centralising it means
    any change to how params/bodies are transmitted is made in one place.

    Args:
        directory: Optional ``directory`` scoping query param.
        workspace: Optional ``workspace`` scoping query param.
        query: Extra query params (callers include only non-``None`` values).
        json_body: Optional JSON body. When ``None`` no body key is added.

    Returns:
        A dict safe to pass through to :meth:`httpx.Client.request` /
        :meth:`httpx.AsyncClient.request` as ``**kwargs``.
    """
    params: dict[str, Any] = query_params(directory, workspace, query)
    kwargs: dict[str, Any] = {"params": params or None}
    if json_body is not None:
        kwargs["json"] = json_body
    return kwargs


def prompt_body(
    prompt: str | list[PromptPart],
    model: PromptModel | dict[str, Any] | None = None,
    agent: str | None = None,
    tools: dict[str, bool] | None = None,
    system: str | None = None,
    variant: str | None = None,
    no_reply: bool | None = None,
    message_id: str | None = None,
) -> dict[str, Any]:
    """Assemble the wire-format body for the prompt endpoints.

    Plain strings are wrapped in a :class:`TextPartInput`; model/agent/tools/...
    are included only when supplied.

    Args:
        prompt: Plain text or a list of prompt parts.
        model: Target model as :class:`PromptModel` or a raw wire dict.
        agent: The agent to act as.
        tools: Per-tool enable map.
        system: System prompt override.
        variant: Model variant override.
        no_reply: When ``True``, do not produce a user-visible assistant reply.
        message_id: Caller-chosen message id (for idempotency).

    Returns:
        The JSON body dict ready to send.
    """
    if isinstance(prompt, str):
        parts: list[PromptPart] = [TextPartInput(type="text", text=prompt)]
    else:
        parts = prompt
    body: dict[str, Any] = {"parts": [p.to_wire() for p in parts]}
    if model is not None:
        body["model"] = model.to_wire() if isinstance(model, PromptModel) else model
    if agent is not None:
        body["agent"] = agent
    if tools is not None:
        body["tools"] = tools
    if system is not None:
        body["system"] = system
    if variant is not None:
        body["variant"] = variant
    if no_reply is not None:
        body["noReply"] = no_reply
    if message_id is not None:
        body["messageID"] = message_id
    return body


def _optional(params: dict[str, Any], key: str, value: Any) -> None:
    """Add ``key`` to ``params`` only when ``value`` is not ``None``.

    Args:
        params: The query dict being built.
        key: The query parameter name.
        value: The value to add, or ``None`` to skip.
    """
    if value is not None:
        params[key] = value


def session_list_query(
    scope: str | None,
    path: str | None,
    roots: bool | None,
    start: float | None,
    search: str | None,
    limit: int | None,
) -> dict[str, Any]:
    """Collect the optional filters for ``GET /session`` into a query dict.

    Args:
        scope: Restrict to a session scope.
        path: Restrict to a directory path prefix.
        roots: When set, restrict to root (non-child) sessions.
        start: Only sessions created after this unix timestamp.
        search: Free-text filter on session attributes.
        limit: Maximum number of sessions to return.

    Returns:
        A dict of only the supplied (non-``None``) query params.
    """
    query: dict[str, Any] = {}
    _optional(query, "scope", scope)
    _optional(query, "path", path)
    _optional(query, "roots", roots)
    _optional(query, "start", start)
    _optional(query, "search", search)
    _optional(query, "limit", limit)
    return query


def messages_query(limit: int | None, before: str | None) -> dict[str, Any]:
    """Collect the optional filters for ``GET /session/{id}/message``.

    Args:
        limit: Maximum number of messages to return.
        before: Only messages created before this message id (pagination cursor).

    Returns:
        A dict of only the supplied (non-``None``) query params.
    """
    query: dict[str, Any] = {}
    _optional(query, "limit", limit)
    _optional(query, "before", before)
    return query


def fork_body(message_id: str | None) -> dict[str, Any]:
    """Build the ``POST /session/{id}/fork`` body (empty when forking the head).

    Args:
        message_id: Fork from this message, or ``None`` to fork the latest state.

    Returns:
        The JSON body dict (possibly empty).
    """
    body: dict[str, Any] = {}
    if message_id is not None:
        body["messageID"] = message_id
    return body


def summarize_body(provider_id: str, model_id: str, auto: bool | None) -> dict[str, Any]:
    """Build the ``POST /session/{id}/summarize`` body.

    Args:
        provider_id: Provider that performs the summarization.
        model_id: Model that performs the summarization.
        auto: When set, whether the summarization is automatic.

    Returns:
        The JSON body dict.
    """
    body: dict[str, Any] = {"providerID": provider_id, "modelID": model_id}
    if auto is not None:
        body["auto"] = auto
    return body


def permission_body(response: str) -> dict[str, Any]:
    """Build the ``POST /session/{id}/permissions/{pid}`` body.

    Args:
        response: One of ``"once"``, ``"always"`` or ``"reject"``.

    Returns:
        The JSON body dict.
    """
    return {"response": response}


def create_body(body: CreateSessionRequest | None) -> dict[str, Any]:
    """Wire-format the optional ``POST /session`` body (empty dict when omitted).

    Args:
        body: Create options, or ``None`` for a bare session.

    Returns:
        The JSON body dict.
    """
    return body.to_wire() if body is not None else {}


def update_body(body: UpdateSessionRequest) -> dict[str, Any]:
    """Wire-format the ``PATCH /session/{id}`` body.

    Args:
        body: The fields to update.

    Returns:
        The JSON body dict.
    """
    return body.to_wire()


def permission_reply_body(reply: str, message: str | None = None) -> dict[str, Any]:
    """Build the ``POST /permission/{requestID}/reply`` body.

    Args:
        reply: One of ``"once"``, ``"always"`` or ``"reject"``.
        message: Optional free-text note for the reply.

    Returns:
        The JSON body dict.
    """
    body: dict[str, Any] = {"reply": reply}
    if message is not None:
        body["message"] = message
    return body


def question_reply_body(answers: list[list[str]]) -> dict[str, Any]:
    """Build the ``POST /question/{requestID}/reply`` body.

    Args:
        answers: One entry per question, each a list of selected option labels
            (order must match the request's ``questions``).

    Returns:
        The JSON body dict.
    """
    return {"answers": answers}


def vcs_diff_query(mode: str, context: int | None) -> dict[str, Any]:
    """Collect the query params for ``GET /vcs/diff`` (``mode`` is required).

    Args:
        mode: Diff base, ``"git"`` or ``"branch"`` (required by the server).
        context: Optional number of context lines.

    Returns:
        The query dict.
    """
    query: dict[str, Any] = {"mode": mode}
    _optional(query, "context", context)
    return query


def vcs_apply_body(patch: str) -> dict[str, Any]:
    """Build the ``POST /vcs/apply`` body.

    Args:
        patch: The unified diff patch to apply to the working tree.

    Returns:
        The JSON body dict.
    """
    return {"patch": patch}


def update_project_body(body: UpdateProjectRequest) -> dict[str, Any]:
    """Serialize the optional fields for ``PATCH /project/{id}``.

    Args:
        body: The mutable project fields (name/icon/commands).

    Returns:
        The JSON body containing only the supplied fields.
    """
    return body.to_wire()


def log_body(
    service: str | None,
    level: Literal["debug", "info", "error", "warn"] | None,
    message: str | None,
    extra: dict[str, object] | None,
) -> dict[str, Any]:
    """Collect the optional fields for ``POST /log``.

    Args:
        service: Service name for the log entry.
        level: Log level (server default applies when omitted).
        message: The log message itself.
        extra: Arbitrary structured context.

    Returns:
        A dict of only the supplied fields, plus ``extra`` verbatim when given.
    """
    payload: dict[str, Any] = {}
    _optional(payload, "service", service)
    _optional(payload, "level", level)
    _optional(payload, "message", message)
    if extra is not None:
        payload["extra"] = extra
    return payload


def credentials_body(credentials: AuthCredentials) -> dict[str, Any]:
    """Serialize the discriminated-union credentials for ``PUT /auth``.

    Args:
        credentials: One of the three credential shapes (oauth/api/wellknown).

    Returns:
        The JSON body tagged with its ``type`` discriminator.
    """
    return credentials.to_wire()


def mcp_add_body(name: str, config: McpLocalConfig | McpRemoteConfig | dict[str, Any]) -> dict[str, Any]:
    """Build the ``POST /mcp`` body from a validated config model.

    Args:
        name: The server name to register.
        config: A :class:`McpLocalConfig` / :class:`McpRemoteConfig`, or a raw
            wire dict escape hatch (see :func:`prompt_body`'s ``model``).

    Returns:
        The JSON body dict.
    """
    if isinstance(config, (McpLocalConfig, McpRemoteConfig)):
        config_wire: dict[str, Any] = config.to_wire()
    else:
        config_wire = dict(config)
    return {"name": name, "config": config_wire}


def command_body(
    command: str,
    arguments: str,
    agent: str | None = None,
    model: PromptModel | str | None = None,
    variant: str | None = None,
    message_id: str | None = None,
    parts: list[PromptPart] | None = None,
) -> dict[str, Any]:
    """Build the ``POST /session/{id}/command`` body.

    Unlike ``prompt``, the wire format carries the model as a single
    ``"provider/model"`` string (verified against the server's
    ``CommandInput`` schema), so a :class:`PromptModel` is flattened here.

    Args:
        command: The command name to execute.
        arguments: Free-text arguments passed to the command.
        agent: The agent to act as.
        model: Target model; a :class:`PromptModel` is joined into
            ``"provider/model"``, or pass an already-joined string.
        variant: Model variant override.
        message_id: Caller-chosen message id (for idempotency).
        parts: Optional file attachments alongside the command.

    Returns:
        The JSON body dict.
    """
    body: dict[str, Any] = {"command": command, "arguments": arguments}
    if agent is not None:
        body["agent"] = agent
    if model is not None:
        body["model"] = f"{model.provider_id}/{model.model_id}" if isinstance(model, PromptModel) else model
    if variant is not None:
        body["variant"] = variant
    if message_id is not None:
        body["messageID"] = message_id
    if parts is not None:
        body["parts"] = [p.to_wire() for p in parts]
    return body


def shell_body(
    command: str,
    agent: str,
    model: PromptModel | dict[str, Any] | None = None,
    message_id: str | None = None,
) -> dict[str, Any]:
    """Build the ``POST /session/{id}/shell`` body.

    Args:
        command: The shell command to run.
        agent: The agent to attribute the run to (required by the server).
        model: Target model as :class:`PromptModel` or raw ``{providerID,
            modelID}`` dict (the shell wire format keeps the object shape).
        message_id: Caller-chosen message id (for idempotency).

    Returns:
        The JSON body dict.
    """
    body: dict[str, Any] = {"agent": agent, "command": command}
    if model is not None:
        body["model"] = model.to_wire() if isinstance(model, PromptModel) else model
    if message_id is not None:
        body["messageID"] = message_id
    return body


def revert_body(message_id: str, part_id: str | None = None) -> dict[str, Any]:
    """Build the ``POST /session/{id}/revert`` body.

    Args:
        message_id: Revert messages up to and including this one.
        part_id: Optionally revert only up to this part within the message.

    Returns:
        The JSON body dict.
    """
    body: dict[str, Any] = {"messageID": message_id}
    if part_id is not None:
        body["partID"] = part_id
    return body


def init_body(provider_id: str, model_id: str, message_id: str) -> dict[str, Any]:
    """Build the ``POST /session/{id}/init`` body.

    Args:
        provider_id: Provider that runs the project initialization.
        model_id: Model that runs the project initialization.
        message_id: Caller-chosen message id for the init turn.

    Returns:
        The JSON body dict.
    """
    return {"providerID": provider_id, "modelID": model_id, "messageID": message_id}


def diff_query(message_id: str | None) -> dict[str, Any]:
    """Collect the optional filters for ``GET /session/{id}/diff``.

    Args:
        message_id: Restrict the diff to messages up to this one.

    Returns:
        A dict of only the supplied (non-``None``) query params.
    """
    query: dict[str, Any] = {}
    _optional(query, "messageID", message_id)
    return query


def find_file_query(
    query: str,
    dirs: bool | None,
    type: Literal["file", "directory"] | None,
    limit: int | None,
) -> dict[str, Any]:
    """Collect the query params for ``GET /find/file`` (``query`` is required).

    The server derives its search type from ``dirs`` when ``type`` is absent
    (``dirs=False`` means files only); the client forwards both as given so
    callers can express exactly what they mean.

    Args:
        query: Filename fragment to search for.
        dirs: Whether directories are included (sent as a string boolean).
        type: Restrict results to files or directories.
        limit: Maximum number of paths (server default is 10).

    Returns:
        A dict of only the supplied params plus the required ``query``.
    """
    params: dict[str, Any] = {"query": query}
    if dirs is not None:
        # wire quirk: a string boolean, not a real bool
        params["dirs"] = "true" if dirs else "false"
    _optional(params, "type", type)
    _optional(params, "limit", limit)
    return params

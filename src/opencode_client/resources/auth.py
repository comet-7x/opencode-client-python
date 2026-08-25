"""Auth resource: provider credentials and provider OAuth flows.

Maps to the ``PUT/DELETE /auth/{providerID}`` endpoints and ships in two
flavours:

- :class:`AuthResource` — synchronous, backed by :class:`OpenCodeClient`;
- :class:`AsyncAuthResource` — asynchronous, backed by :class:`AsyncOpenCodeClient`.

Provider credentials are global (no directory/workspace scoping on the wire).
The credential body is a discriminated union: :class:`OAuthCredentials`,
:class:`ApiKeyCredentials` or :class:`WellKnownCredentials`.
"""

from __future__ import annotations

import builtins
from typing import Any

import httpx

from ..models import AuthCredentials, ProviderAuthAuthorization, ProviderAuthMethod
from ._wire import TYPE_ADAPTERS, credentials_body, path_segment, request_spec, validate_response
from .base import AsyncResource, Resource

__all__ = ["AsyncAuthResource", "AsyncAuthResourceWithRawResponse", "AuthResource", "AuthResourceWithRawResponse"]


def _provider_path(provider_id: str) -> str:
    """Build ``/auth/{providerID}`` with the id percent-encoded."""
    return f"/auth/{path_segment(provider_id)}"


class AuthResource(Resource):
    """Synchronous client for provider credential management."""

    @property
    def with_raw_response(self) -> AuthResourceWithRawResponse:
        """Prefix for the raw-response variants of every method below.

        Each call returns the unprocessed :class:`httpx.Response` instead of
        the parsed model (same retries, same error mapping on non-2xx).
        """
        return AuthResourceWithRawResponse(self._client)

    def set_credentials(self, provider_id: str, credentials: AuthCredentials) -> bool:
        """Store credentials for a provider (replacing any existing ones).

        Args:
            provider_id: The provider's identifier (e.g. ``"anthropic"``).
            credentials: One of the three tagged shapes — oauth / api / wellknown.
        """
        json_body = credentials_body(credentials)
        response = self._send("PUT", _provider_path(provider_id), json=json_body)
        return validate_response(response, TYPE_ADAPTERS.bool)

    def remove_credentials(self, provider_id: str) -> bool:
        """Remove stored credentials for a provider. Returns ``True`` on success."""
        response = self._send("DELETE", _provider_path(provider_id))
        return validate_response(response, TYPE_ADAPTERS.bool)

    def provider_auth_methods(
        self, directory: str | None = None, workspace: str | None = None
    ) -> dict[str, builtins.list[ProviderAuthMethod]]:
        """List the auth methods each provider supports (oauth / api + prompts).

        Wire path: ``GET /provider/auth``.  Keys are provider ids.
        """
        response = self._send("GET", "/provider/auth", **request_spec(directory=directory, workspace=workspace))
        return validate_response(response, TYPE_ADAPTERS.provider_auth_methods)

    def start_provider_oauth(
        self,
        provider_id: str,
        method: int,
        inputs: dict[str, str] | None = None,
        directory: str | None = None,
        workspace: str | None = None,
    ) -> ProviderAuthAuthorization:
        """Start a provider's OAuth authorization flow.

        Args:
            provider_id: The provider's identifier.
            method: Index into the provider's auth-method list (see
                :meth:`provider_auth_methods`).
            inputs: Answers to the method's text/select prompts, keyed by
                prompt ``key``.

        Returns:
            The authorization document; ``method == "auto"`` completes by
            itself, ``"code"`` needs :meth:`complete_provider_oauth`.
        """
        json_body: dict[str, Any] = {"method": method}
        if inputs is not None:
            json_body["inputs"] = inputs
        response = self._send(
            "POST",
            f"/provider/{path_segment(provider_id)}/oauth/authorize",
            **request_spec(directory=directory, workspace=workspace, json_body=json_body),
        )
        return validate_response(response, TYPE_ADAPTERS.provider_auth_authorization)

    def complete_provider_oauth(
        self,
        provider_id: str,
        method: int,
        code: str,
        directory: str | None = None,
        workspace: str | None = None,
    ) -> bool:
        """Deliver the OAuth redirect code for a provider (``/oauth/callback``).

        Args:
            provider_id: The provider's identifier.
            method: The same auth-method index passed to
                :meth:`start_provider_oauth`.
            code: The code from the OAuth redirect.
        """
        response = self._send(
            "POST",
            f"/provider/{path_segment(provider_id)}/oauth/callback",
            **request_spec(directory=directory, workspace=workspace, json_body={"method": method, "code": code}),
        )
        return validate_response(response, TYPE_ADAPTERS.bool)


class AsyncAuthResource(AsyncResource):
    """Asynchronous client for provider credential management."""

    @property
    def with_raw_response(self) -> AsyncAuthResourceWithRawResponse:
        """Prefix for the raw-response variants of every method below.

        Each call returns the unprocessed :class:`httpx.Response` instead of
        the parsed model (same retries, same error mapping on non-2xx).
        """
        return AsyncAuthResourceWithRawResponse(self._client)

    async def set_credentials(self, provider_id: str, credentials: AuthCredentials) -> bool:
        """Store credentials for a provider (replacing any existing ones).

        Args:
            provider_id: The provider's identifier (e.g. ``"anthropic"``).
            credentials: One of the three tagged shapes — oauth / api / wellknown.
        """
        json_body = credentials_body(credentials)
        response = await self._send("PUT", _provider_path(provider_id), json=json_body)
        return validate_response(response, TYPE_ADAPTERS.bool)

    async def remove_credentials(self, provider_id: str) -> bool:
        """Remove stored credentials for a provider. Returns ``True`` on success."""
        response = await self._send("DELETE", _provider_path(provider_id))
        return validate_response(response, TYPE_ADAPTERS.bool)

    async def provider_auth_methods(
        self, directory: str | None = None, workspace: str | None = None
    ) -> dict[str, builtins.list[ProviderAuthMethod]]:
        """List the auth methods each provider supports (oauth / api + prompts)."""
        response = await self._send("GET", "/provider/auth", **request_spec(directory=directory, workspace=workspace))
        return validate_response(response, TYPE_ADAPTERS.provider_auth_methods)

    async def start_provider_oauth(
        self,
        provider_id: str,
        method: int,
        inputs: dict[str, str] | None = None,
        directory: str | None = None,
        workspace: str | None = None,
    ) -> ProviderAuthAuthorization:
        """Start a provider's OAuth authorization flow.

        Args:
            provider_id: The provider's identifier.
            method: Index into the provider's auth-method list.
            inputs: Answers to the method's prompts, keyed by prompt ``key``.
        """
        json_body: dict[str, Any] = {"method": method}
        if inputs is not None:
            json_body["inputs"] = inputs
        response = await self._send(
            "POST",
            f"/provider/{path_segment(provider_id)}/oauth/authorize",
            **request_spec(directory=directory, workspace=workspace, json_body=json_body),
        )
        return validate_response(response, TYPE_ADAPTERS.provider_auth_authorization)

    async def complete_provider_oauth(
        self,
        provider_id: str,
        method: int,
        code: str,
        directory: str | None = None,
        workspace: str | None = None,
    ) -> bool:
        """Deliver the OAuth redirect code for a provider (``/oauth/callback``).

        Args:
            provider_id: The provider's identifier.
            method: The same auth-method index passed to
                :meth:`start_provider_oauth`.
            code: The code from the OAuth redirect.
        """
        response = await self._send(
            "POST",
            f"/provider/{path_segment(provider_id)}/oauth/callback",
            **request_spec(directory=directory, workspace=workspace, json_body={"method": method, "code": code}),
        )
        return validate_response(response, TYPE_ADAPTERS.bool)


class AuthResourceWithRawResponse(Resource):
    """Synchronous raw-response view of the ``/auth*`` endpoints.

    Mirrors :class:`AuthResource` method-for-method but returns the
    unprocessed response instead of the parsed model. Non-2xx still raise
    the same mapped errors; retries are shared.
    """

    def set_credentials(self, provider_id: str, credentials: AuthCredentials) -> httpx.Response:
        """Store credentials; return the raw response."""
        return self._send("PUT", _provider_path(provider_id), json=credentials_body(credentials))

    def remove_credentials(self, provider_id: str) -> httpx.Response:
        """Remove stored credentials; return the raw response."""
        return self._send("DELETE", _provider_path(provider_id))

    def provider_auth_methods(self, directory: str | None = None, workspace: str | None = None) -> httpx.Response:
        """List provider auth methods; return the raw response."""
        return self._send("GET", "/provider/auth", **request_spec(directory=directory, workspace=workspace))

    def start_provider_oauth(
        self,
        provider_id: str,
        method: int,
        inputs: dict[str, str] | None = None,
        directory: str | None = None,
        workspace: str | None = None,
    ) -> httpx.Response:
        """Start a provider OAuth flow; return the raw response."""
        json_body: dict[str, Any] = {"method": method}
        if inputs is not None:
            json_body["inputs"] = inputs
        return self._send(
            "POST",
            f"/provider/{path_segment(provider_id)}/oauth/authorize",
            **request_spec(directory=directory, workspace=workspace, json_body=json_body),
        )

    def complete_provider_oauth(
        self,
        provider_id: str,
        method: int,
        code: str,
        directory: str | None = None,
        workspace: str | None = None,
    ) -> httpx.Response:
        """Deliver an OAuth redirect code; return the raw response."""
        return self._send(
            "POST",
            f"/provider/{path_segment(provider_id)}/oauth/callback",
            **request_spec(directory=directory, workspace=workspace, json_body={"method": method, "code": code}),
        )


class AsyncAuthResourceWithRawResponse(AsyncResource):
    """Asynchronous raw-response view of the ``/auth*`` endpoints.

    Mirrors :class:`AsyncAuthResource` method-for-method but returns the
    unprocessed response instead of the parsed model. Non-2xx still raise
    the same mapped errors; retries are shared.
    """

    async def set_credentials(self, provider_id: str, credentials: AuthCredentials) -> httpx.Response:
        """Store credentials; return the raw response."""
        return await self._send("PUT", _provider_path(provider_id), json=credentials_body(credentials))

    async def remove_credentials(self, provider_id: str) -> httpx.Response:
        """Remove stored credentials; return the raw response."""
        return await self._send("DELETE", _provider_path(provider_id))

    async def provider_auth_methods(self, directory: str | None = None, workspace: str | None = None) -> httpx.Response:
        """List provider auth methods; return the raw response."""
        return await self._send("GET", "/provider/auth", **request_spec(directory=directory, workspace=workspace))

    async def start_provider_oauth(
        self,
        provider_id: str,
        method: int,
        inputs: dict[str, str] | None = None,
        directory: str | None = None,
        workspace: str | None = None,
    ) -> httpx.Response:
        """Start a provider OAuth flow; return the raw response."""
        json_body: dict[str, Any] = {"method": method}
        if inputs is not None:
            json_body["inputs"] = inputs
        return await self._send(
            "POST",
            f"/provider/{path_segment(provider_id)}/oauth/authorize",
            **request_spec(directory=directory, workspace=workspace, json_body=json_body),
        )

    async def complete_provider_oauth(
        self,
        provider_id: str,
        method: int,
        code: str,
        directory: str | None = None,
        workspace: str | None = None,
    ) -> httpx.Response:
        """Deliver an OAuth redirect code; return the raw response."""
        return await self._send(
            "POST",
            f"/provider/{path_segment(provider_id)}/oauth/callback",
            **request_spec(directory=directory, workspace=workspace, json_body={"method": method, "code": code}),
        )

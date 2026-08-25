"""Auth resource: provider credential management.

Maps to the ``PUT/DELETE /auth/{providerID}`` endpoints and ships in two
flavours:

- :class:`AuthResource` — synchronous, backed by :class:`OpenCodeClient`;
- :class:`AsyncAuthResource` — asynchronous, backed by :class:`AsyncOpenCodeClient`.

Provider credentials are global (no directory/workspace scoping on the wire).
The credential body is a discriminated union: :class:`OAuthCredentials`,
:class:`ApiKeyCredentials` or :class:`WellKnownCredentials`.
"""

from __future__ import annotations

import httpx

from ..models import AuthCredentials
from ._wire import TYPE_ADAPTERS, credentials_body, path_segment, validate_response
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

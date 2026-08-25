"""Public exception types raised by :mod:`opencode_client`.

The hierarchy mirrors common HTTP conditions so callers can catch the
granularity they care about::

    except OpenCodeNotFound:      # only 404s
    except OpenCodeApiError:      # any API error (the base class)

The :func:`make_api_error` factory is shared by both the sync and async
transports and is intentionally not part of the public API surface.
"""

from __future__ import annotations

from typing import Any

import httpx
from pydantic import ValidationError

__all__ = [
    "OpenCodeApiError",
    "OpenCodeAuthenticationError",
    "OpenCodeConflictError",
    "OpenCodeError",
    "OpenCodeNotFoundError",
    "OpenCodePermissionError",
    "OpenCodeRateLimitError",
    "OpenCodeResponseError",
    "OpenCodeServerConnectionError",
    "OpenCodeServerError",
    "OpenCodeTimeoutError",
    "OpenCodeTransportError",
    "OpenCodeUnprocessableEntityError",
]


class OpenCodeError(Exception):
    """Base class for every error raised by :mod:`opencode_client`."""


class OpenCodeApiError(OpenCodeError):
    """The opencode server responded with a non-2xx status code.

    Attributes:
        status_code: HTTP status code returned by the server.
        payload: Parsed JSON error body, or the raw text when not JSON.
    """

    def __init__(self, status_code: int, payload: Any) -> None:
        self.status_code = status_code
        self.payload = payload
        super().__init__(f"HTTP {status_code}: {payload!r}")


class OpenCodeNotFoundError(OpenCodeApiError):
    """HTTP 404: the requested resource does not exist."""


class OpenCodeAuthenticationError(OpenCodeApiError):
    """HTTP 401: credentials missing or rejected."""


class OpenCodePermissionError(OpenCodeApiError):
    """HTTP 403: authenticated but not allowed."""


class OpenCodeConflictError(OpenCodeApiError):
    """HTTP 409: the request conflicts with current server state."""


class OpenCodeUnprocessableEntityError(OpenCodeApiError):
    """HTTP 422: request body failed validation."""


class OpenCodeRateLimitError(OpenCodeApiError):
    """HTTP 429: too many requests; consider backing off."""


class OpenCodeServerError(OpenCodeApiError):
    """HTTP 5xx: an error inside the opencode server."""


class OpenCodeTransportError(OpenCodeError):
    """The request never completed for reasons other than an HTTP status.

    Subclasses cover timeouts and connection failures.
    """


class OpenCodeTimeoutError(OpenCodeTransportError):
    """A request timed out while waiting for the server."""


class OpenCodeServerConnectionError(OpenCodeTransportError):
    """Could not establish or maintain a connection to the server."""


class OpenCodeResponseError(OpenCodeError):
    """A 2xx response body failed schema validation.

    Raised when the server answers success but the payload no longer matches
    the expected model (schema drift across server versions, missing fields).
    Carries the original :class:`pydantic.ValidationError` so callers can
    inspect the offending fields.

    Attributes:
        validation_error: The underlying pydantic validation failure.
    """

    def __init__(self, message: str, *, validation_error: ValidationError) -> None:
        super().__init__(message)
        self.validation_error = validation_error


def _error_class_for_status(status_code: int) -> type[OpenCodeApiError]:
    """Choose the most specific :class:`OpenCodeApiError` subclass for a status code."""
    if status_code == 401:
        return OpenCodeAuthenticationError
    if status_code == 403:
        return OpenCodePermissionError
    if status_code == 404:
        return OpenCodeNotFoundError
    if status_code == 409:
        return OpenCodeConflictError
    if status_code == 422:
        return OpenCodeUnprocessableEntityError
    if status_code == 429:
        return OpenCodeRateLimitError
    if status_code >= 500:
        return OpenCodeServerError
    return OpenCodeApiError


def make_api_error(response: httpx.Response) -> OpenCodeApiError:
    """Build the right :class:`OpenCodeApiError` (or subclass) from an error response.

    Shared by the sync and async transports.

    Args:
        response: A response with a non-2xx status code.

    Returns:
        The most specific exception for the status, carrying the parsed payload.
    """
    try:
        payload: Any = response.json()
    except ValueError:
        payload = response.text
    return _error_class_for_status(response.status_code)(response.status_code, payload)


def make_transport_error(exc: httpx.HTTPError) -> OpenCodeTransportError:
    """Map an :class:`httpx.HTTPError` raised by the transport onto our hierarchy.

    Args:
        exc: The httpx exception that bubbled up out of the request.

    Returns:
        An :class:`OpenCodeTimeoutError` for timeouts, otherwise
        :class:`OpenCodeServerConnectionError`, both chained to ``exc``.
    """
    if isinstance(exc, httpx.TimeoutException):
        error: OpenCodeTransportError = OpenCodeTimeoutError(str(exc))
    else:
        error = OpenCodeServerConnectionError(str(exc))
    error.__cause__ = exc
    return error


def make_response_error(exc: ValidationError) -> OpenCodeResponseError:
    """Wrap a response-schema validation failure into our exception hierarchy.

    Shared by the sync and async transports so ``except OpenCodeError``
    covers every failure mode of this library, including schema drift on
    2xx responses.

    Args:
        exc: The :class:`pydantic.ValidationError` raised while parsing a
            successful (2xx) response body.

    Returns:
        An :class:`OpenCodeResponseError` chained to ``exc``.
    """
    error = OpenCodeResponseError(f"response failed schema validation: {exc}", validation_error=exc)
    error.__cause__ = exc
    return error

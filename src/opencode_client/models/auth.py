"""Models for the /auth endpoints: provider credential shapes."""

from __future__ import annotations

from typing import Annotated, Literal

import pydantic
from pydantic import Field

from .base import OpencodeModel

__all__ = [
    "ApiKeyCredentials",
    "AuthCredentials",
    "OAuthCredentials",
    "WellKnownCredentials",
]


class OAuthCredentials(OpencodeModel):
    """Provider credentials from an OAuth flow (refresh + access tokens).

    ``expires`` is an epoch-millis timestamp; ``account_id`` and
    ``enterprise_url`` are optional extras some providers return.
    """

    type: Literal["oauth"]
    refresh: str
    access: str
    expires: int
    # id_alias would produce "accountID"; the wire uses lowercase "accountId"
    account_id: str | None = Field(default=None, validation_alias="accountId", serialization_alias="accountId")
    enterprise_url: str | None = None


class ApiKeyCredentials(OpencodeModel):
    """Plain API-key credentials for a provider."""

    type: Literal["api"]
    key: str
    metadata: dict[str, str] | None = None


class WellKnownCredentials(OpencodeModel):
    """Credentials derived from a provider's well-known endpoint."""

    type: Literal["wellknown"]
    key: str
    token: str


#: Discriminated union of the three ``PUT /auth`` credential shapes.
AuthCredentials = Annotated[
    OAuthCredentials | ApiKeyCredentials | WellKnownCredentials,
    pydantic.Field(discriminator="type"),
]

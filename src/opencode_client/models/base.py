"""Base model for all opencode response/request data classes."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


def id_alias(field_name: str) -> str:
    """Map a snake_case field name to the opencode wire alias.

    The wire format is camelCase, except ID-ish fields which use an uppercase
    ``ID`` suffix (``sessionID``, ``providerID``, ...). Fields starting with
    ``_`` are internal and are not aliased.
    """
    if field_name.startswith("_"):
        return field_name
    camel = to_camel(field_name)
    if camel.endswith("Id"):
        camel = camel[:-2] + "ID"
    return camel


class OpencodeModel(BaseModel):
    """Base class for every pydantic model in this package.

    - aliases follow the opencode wire format (see :func:`id_alias`),
      while Python code uses snake_case (``populate_by_name=True``);
    - unknown fields from the server are ignored, so newer server
      versions remain backwards compatible;
    - every subclass must re-enable ``from_attributes``-free semantics by
      inheriting this class, never raw :class:`~pydantic.BaseModel`.
    """

    model_config = ConfigDict(
        alias_generator=id_alias,
        populate_by_name=True,
        extra="ignore",
    )

    def to_wire(self) -> dict[str, object]:
        """Serialize to the wire format (aliased keys, ``None`` fields dropped)."""
        return self.model_dump(by_alias=True, exclude_none=True)

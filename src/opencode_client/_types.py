"""Small typing helpers shared across the client.

The star of this module is :data:`NOT_GIVEN`, a sentinel used to tell
"the caller didn't pass this optional argument" apart from "the caller
explicitly passed ``None``". Mirrors the ergonomics of the Stainless
generated SDKs (OpenAI/Anthropic/opencode) while staying dependency-free.
"""

from __future__ import annotations

from typing import Any

__all__ = ["NOT_GIVEN", "NotGiven", "is_given"]


class NotGiven:
    """Marker type for "argument not provided".

    :data:`NOT_GIVEN` is a shared singleton of this type.
    """

    def __repr__(self) -> str:
        return "NOT_GIVEN"

    def __bool__(self) -> bool:
        return False


#: Singleton sentinel indicating an optional argument was not supplied.
NOT_GIVEN = NotGiven()


def is_given(value: Any) -> bool:
    """Return ``False`` when ``value`` is the :data:`NOT_GIVEN` sentinel.

    Args:
        value: An argument value, possibly :data:`NOT_GIVEN`.

    Returns:
        ``True`` if the caller actually supplied a value (including ``None``).
    """
    return not isinstance(value, NotGiven)

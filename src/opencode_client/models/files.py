"""Models for the /file*, /find* and /formatter endpoints (files domain)."""

from __future__ import annotations

from typing import Annotated, Literal

import pydantic
from pydantic import Field

from .base import OpencodeModel

__all__ = [
    "BinaryFileContent",
    "FileChange",
    "FileContent",
    "FileHunk",
    "FileNode",
    "FilePatch",
    "FormatterStatus",
    "SourcePosition",
    "SourceRange",
    "Symbol",
    "SymbolLocation",
    "TextFragment",
    "TextMatch",
    "TextSubmatch",
]


# -- GET /file ----------------------------------------------------------------


class FileNode(OpencodeModel):
    """One entry of a directory listing from ``GET /file``."""

    name: str
    path: str
    absolute: str
    type: Literal["file", "directory"]
    ignored: bool


# -- GET /file/content --------------------------------------------------------


class FileHunk(OpencodeModel):
    """One unidiff hunk inside :attr:`FilePatch.hunks`."""

    old_start: int
    old_lines: int
    new_start: int
    new_lines: int
    lines: list[str]


class FilePatch(OpencodeModel):
    """Structured unidiff metadata optionally attached to a file's content."""

    old_file_name: str
    new_file_name: str
    old_header: str | None = None
    new_header: str | None = None
    hunks: list[FileHunk]
    index: str | None = None


class TextFileContent(OpencodeModel):
    """A text file's content (``type == "text"``)."""

    type: Literal["text"]
    content: str
    diff: str | None = None
    patch: FilePatch | None = None


class BinaryFileContent(OpencodeModel):
    """A binary file's content (``type == "binary"``, base64-encoded)."""

    type: Literal["binary"]
    content: str
    encoding: Literal["base64"]
    mime_type: str | None = None


#: Discriminated union of the two ``GET /file/content`` shapes.
FileContent = Annotated[
    TextFileContent | BinaryFileContent,
    pydantic.Field(discriminator="type"),
]


# -- GET /file/status ---------------------------------------------------------


class FileChange(OpencodeModel):
    """One changed file in ``GET /file/status`` (git-style add/delete/modify).

    The wire schema is named ``File``; the Python name avoids clashing with
    :class:`FileNode` and reads better at call sites.
    """

    path: str
    added: int
    removed: int
    status: Literal["added", "deleted", "modified"]


# -- GET /find ----------------------------------------------------------------


class TextFragment(OpencodeModel):
    """A wire-side ``{text: ...}`` wrapper (paths, matched lines, submatches)."""

    text: str


class TextSubmatch(OpencodeModel):
    """One exact match region within a :class:`TextMatch` line."""

    match: TextFragment
    start: int
    end: int


class TextMatch(OpencodeModel):
    """One ripgrep hit from ``GET /find`` (pattern search).

    ``line_number``/``absolute_offset`` are snake_case on the wire — unlike
    the API's usual camelCase — so they carry explicit aliases.
    """

    path: TextFragment
    lines: TextFragment
    line_number: int = Field(validation_alias="line_number", serialization_alias="line_number")
    absolute_offset: int = Field(validation_alias="absolute_offset", serialization_alias="absolute_offset")
    submatches: list[TextSubmatch]


# -- GET /find/symbol ---------------------------------------------------------


class SourcePosition(OpencodeModel):
    """Zero-based LSP position (line + character)."""

    line: int
    character: int


class SourceRange(OpencodeModel):
    """A start/end span of source code, in LSP coordinates."""

    start: SourcePosition
    end: SourcePosition


class SymbolLocation(OpencodeModel):
    """Where a symbol lives: document URI plus its range."""

    uri: str
    range: SourceRange


class Symbol(OpencodeModel):
    """One workspace symbol from ``GET /find/symbol``.

    ``kind`` is the numeric LSP symbol kind (1=file, 2=module, 6=method,
    12=function, ...); the server passes it through untranslated.
    """

    name: str
    kind: int
    location: SymbolLocation


# -- GET /formatter -----------------------------------------------------------


class FormatterStatus(OpencodeModel):
    """One registered formatter from ``GET /formatter``."""

    name: str
    extensions: list[str]
    enabled: bool

"""Small, lossless-enough dotenv document model used by the Linux installer.

The installer must update a handful of managed keys without turning a user's
``.env`` into a generated file.  This module intentionally does not implement
shell expansion: values are parsed for their quoting semantics and every
unknown/comment line is retained verbatim.
"""

from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator


_ASSIGNMENT = re.compile(
    r"^(?P<prefix>[ \t]*(?:export[ \t]+)?)"
    r"(?P<key>[A-Za-z_][A-Za-z0-9_]*)"
    r"(?P<separator>[ \t]*=[ \t]*)(?P<rest>.*)$"
)
_SAFE_UNQUOTED = re.compile(r"^[A-Za-z0-9_./:@%+,=-]+$")


def _split_line_ending(line: str) -> tuple[str, str]:
    if line.endswith("\r\n"):
        return line[:-2], "\r\n"
    if line.endswith(("\n", "\r")):
        return line[:-1], line[-1]
    return line, ""


def _comment_index(value: str) -> int | None:
    """Return an inline-comment position, if ``#`` is shell-comment-like."""

    for index, character in enumerate(value):
        if character == "#" and (index == 0 or value[index - 1].isspace()):
            return index
    return None


def _decode_double_quoted(value: str) -> str:
    decoded: list[str] = []
    index = 0
    escapes = {"n": "\n", "r": "\r", "t": "\t", '"': '"', "\\": "\\"}
    while index < len(value):
        character = value[index]
        if character == "\\" and index + 1 < len(value):
            next_character = value[index + 1]
            decoded.append(escapes.get(next_character, next_character))
            index += 2
            continue
        decoded.append(character)
        index += 1
    return "".join(decoded)


def _parse_value(rest: str) -> tuple[str, str, str | None]:
    """Parse value text into decoded value, untouched suffix and quote style."""

    if rest.startswith("'"):
        closing = rest.find("'", 1)
        if closing >= 0:
            return rest[1:closing], rest[closing + 1 :], "'"
    if rest.startswith('"'):
        index = 1
        escaped = False
        closing = -1
        while index < len(rest):
            character = rest[index]
            if character == '"' and not escaped:
                closing = index
                break
            if character == "\\" and not escaped:
                escaped = True
            else:
                escaped = False
            index += 1
        if closing >= 0:
            return _decode_double_quoted(rest[1:closing]), rest[closing + 1 :], '"'

    comment = _comment_index(rest)
    value_part = rest if comment is None else rest[:comment]
    value = value_part.rstrip(" \t")
    suffix = rest[len(value) :]
    return value, suffix, None


def _encode_value(value: Any, quote: str | None = None) -> str:
    text = "" if value is None else str(value)
    if quote == "'" and "'" not in text:
        return f"'{text}'"
    if quote == '"' or (quote == "'" and "'" in text):
        escaped = (
            text.replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("\r", "\\r")
            .replace("\n", "\\n")
            .replace("\t", "\\t")
        )
        return f'"{escaped}"'
    if text and _SAFE_UNQUOTED.fullmatch(text):
        return text
    if not text:
        return ""
    escaped = (
        text.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\r", "\\r")
        .replace("\n", "\\n")
        .replace("\t", "\\t")
    )
    return f'"{escaped}"'


@dataclass
class _Entry:
    original: str
    line_ending: str
    key: str | None = None
    prefix: str = ""
    separator: str = ""
    value: str | None = None
    suffix: str = ""
    quote: str | None = None
    changed: bool = False

    def render(self) -> str:
        if self.key is None or not self.changed:
            return self.original
        return f"{self.prefix}{self.key}{self.separator}{_encode_value(self.value)}{self.suffix}{self.line_ending}"


class DotEnvDocument:
    """An ordered dotenv document whose comments and unknown lines survive edits."""

    def __init__(self, entries: list[_Entry], *, newline: str = "\n") -> None:
        self._entries = entries
        self._newline = newline

    @classmethod
    def parse(cls, source: str | bytes | Path | None) -> "DotEnvDocument":
        """Parse dotenv text, or read it when a :class:`~pathlib.Path` is supplied."""

        if source is None:
            text = ""
        elif isinstance(source, Path):
            text = source.read_text(encoding="utf-8")
        elif isinstance(source, bytes):
            text = source.decode("utf-8")
        else:
            text = source
        newline = "\r\n" if "\r\n" in text else "\n"
        entries: list[_Entry] = []
        for line in text.splitlines(keepends=True):
            body, ending = _split_line_ending(line)
            match = _ASSIGNMENT.match(body)
            if match is None:
                entries.append(_Entry(original=line, line_ending=ending))
                continue
            value, suffix, quote = _parse_value(match.group("rest"))
            entries.append(
                _Entry(
                    original=line,
                    line_ending=ending,
                    key=match.group("key"),
                    prefix=match.group("prefix"),
                    separator=match.group("separator"),
                    value=value,
                    suffix=suffix,
                    quote=quote,
                )
            )
        # ``splitlines(keepends=True)`` has no item for an empty document and
        # retains a final unterminated line as desired.
        return cls(entries, newline=newline)

    def _effective_entry(self, key: str) -> _Entry | None:
        for entry in reversed(self._entries):
            if entry.key == key:
                return entry
        return None

    def get(self, key: str, default: Any = None) -> str | Any:
        entry = self._effective_entry(key)
        return default if entry is None else entry.value

    def __contains__(self, key: object) -> bool:
        return isinstance(key, str) and self._effective_entry(key) is not None

    def keys(self) -> Iterator[str]:
        seen: set[str] = set()
        for entry in self._entries:
            if entry.key is not None and entry.key not in seen:
                seen.add(entry.key)
                yield entry.key

    @property
    def values(self) -> dict[str, str]:
        return {key: self.get(key) for key in self.keys()}

    def set(self, key: str, value: Any) -> None:
        """Set a key while retaining its location, prefix, quote style, and suffix."""

        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            raise ValueError(f"invalid dotenv key: {key!r}")
        entry = self._effective_entry(key)
        if entry is not None:
            entry.value = "" if value is None else str(value)
            entry.changed = True
            return

        if self._entries and not self._entries[-1].render().endswith(("\n", "\r")):
            self._entries[-1].original += self._newline
        self._entries.append(
            _Entry(
                original="",
                line_ending=self._newline,
                key=key,
                prefix="",
                separator="=",
                value="" if value is None else str(value),
                suffix="",
                quote=None,
                changed=True,
            )
        )

    def render(self) -> str:
        rendered: list[str] = []
        for entry in self._entries:
            if entry.key is None or not entry.changed:
                rendered.append(entry.render())
                continue
            # Preserve the quote style of an existing value.  This is kept in
            # the entry rather than normalized into a new generated document.
            encoded = _encode_value(entry.value, entry.quote)
            rendered.append(
                f"{entry.prefix}{entry.key}{entry.separator}"
                f"{encoded}{entry.suffix}{entry.line_ending}"
            )
        return "".join(rendered)

    def copy(self) -> "DotEnvDocument":
        return DotEnvDocument.parse(self.render())

    def __iter__(self) -> Iterator[str]:
        return self.keys()

    def __getitem__(self, key: str) -> str:
        value = self.get(key)
        if value is None:
            raise KeyError(key)
        return value

    def __repr__(self) -> str:
        return f"DotEnvDocument(keys={list(self.keys())!r})"


def _fsync_parent(parent: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(str(parent), flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def write_atomic(path: str | Path, content: str | bytes, mode: int = 0o600) -> None:
    """Write content through a same-directory fsynced temporary file and replace."""

    destination = Path(path)
    parent = destination.parent
    if not parent.is_dir():
        raise FileNotFoundError(str(parent))
    if not isinstance(mode, int) or mode < 0 or mode > 0o777:
        raise ValueError("mode must be a valid Unix permission mode")
    payload = content.encode("utf-8") if isinstance(content, str) else content
    if not isinstance(payload, bytes):
        raise TypeError("content must be text or bytes")

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        suffix=".tmp",
        dir=str(parent),
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        # Sync the directory before and after the rename.  The first sync
        # makes creation of the temporary inode durable; the second makes the
        # atomic name replacement durable.
        _fsync_parent(parent)
        os.replace(str(temporary), str(destination))
        _fsync_parent(parent)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def plan_environment(existing: Any, host: Any, answers: Any) -> Any:
    """Compatibility import for callers treating dotenv planning as one API.

    The implementation lives in :mod:`lumen_installer.environment` to keep
    parsing/atomic I/O separate from host-fact reconciliation.  Importing
    lazily avoids a module cycle while retaining the task's public dotenv
    entrypoint.
    """

    from .environment import plan_environment as _plan_environment

    return _plan_environment(existing, host, answers)


__all__ = ["DotEnvDocument", "plan_environment", "write_atomic"]

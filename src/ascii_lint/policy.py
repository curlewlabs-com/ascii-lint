"""A repository's exemptions: which non-ASCII characters may stand in which
files, each with the reason, read from `.ascii-lint.toml`.

    [[exempt]]
    reason = "translated store listings: the characters are the deliverable"
    paths = ['^fastlane/metadata/[a-z]{2,3}(-[A-Za-z0-9]{2,4})*/']

    [[exempt]]
    reason = "the marks the widget draws as its face"
    paths = ['']
    except_paths = ['^tools/', '^scripts/']
    characters = "<the marks, as TOML escapes>"

`paths` and `except_paths` are Python regular expressions searched in each
file's path from the repository root, so a pattern anchors itself with `^` and
`$`; an empty pattern matches every path. An exemption covers a character when
some `paths` pattern matches the file, no `except_paths` pattern does, and the
character is one of `characters`, or `characters` is absent. Write
`characters` with TOML's `\\u` and `\\U` escapes, so the file stays ASCII too.

Every exemption needs a reason, and one that exempted nothing in the files it
was judged against is reported: an exemption nobody needs any more is one
nobody re-examined. A file this cannot read as that shape is an error, never
an empty policy.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

from ascii_lint import files

CONFIG_NAME = ".ascii-lint.toml"

_KEYS = frozenset({"reason", "paths", "except_paths", "characters"})


class PolicyError(Exception):
    pass


@dataclass(frozen=True)
class Exemption:
    number: int
    reason: str
    paths: tuple[re.Pattern[str], ...]
    except_paths: tuple[re.Pattern[str], ...]
    characters: frozenset[str] | None

    def covers(self, path: str, char: str) -> bool:
        if self.characters is not None and char not in self.characters:
            return False
        if any(pattern.search(path) for pattern in self.except_paths):
            return False
        return any(pattern.search(path) for pattern in self.paths)

    def __str__(self) -> str:
        return f"exemption {self.number} ({self.reason})"


@dataclass(frozen=True)
class Policy:
    exemptions: tuple[Exemption, ...] = ()

    def covering(self, path: str, char: str) -> list[Exemption]:
        return [e for e in self.exemptions if e.covers(path, char)]


def _patterns(value: object, where: str, key: str) -> tuple[re.Pattern[str], ...]:
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise PolicyError(f"{where}: {key} must be a list of strings")
    try:
        return tuple(re.compile(v) for v in value)
    except re.error as error:
        raise PolicyError(f"{where}: {key} holds a bad pattern: {error}") from error


def _exemption(number: int, table: object) -> Exemption:
    where = f"exemption {number}"
    if not isinstance(table, dict):
        raise PolicyError(f"{where} is not a table")
    unknown = sorted(set(table) - _KEYS)
    if unknown:
        raise PolicyError(f"{where}: unknown key {', '.join(unknown)}")
    reason = table.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        raise PolicyError(f"{where} has no reason")
    if "paths" not in table:
        raise PolicyError(f"{where} has no paths")
    paths = _patterns(table["paths"], where, "paths")
    if not paths:
        raise PolicyError(f"{where}: paths is empty, so it covers nothing")
    except_paths = _patterns(table.get("except_paths", []), where, "except_paths")
    characters: frozenset[str] | None = None
    if "characters" in table:
        chars = table["characters"]
        if not isinstance(chars, str) or not chars:
            raise PolicyError(f"{where}: characters must be a non-empty string")
        if not all(not c.isascii() for c in chars):
            raise PolicyError(f"{where}: characters holds an ASCII character")
        characters = frozenset(chars)
    return Exemption(number, reason.strip(), paths, except_paths, characters)


def parse(text: str) -> Policy:
    try:
        document = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        raise PolicyError(f"not TOML: {error}") from error
    unknown = sorted(set(document) - {"exempt"})
    if unknown:
        raise PolicyError(f"unknown key {', '.join(unknown)}")
    tables = document.get("exempt", [])
    if not isinstance(tables, list):
        raise PolicyError("exempt must be an array of tables, [[exempt]]")
    return Policy(tuple(_exemption(n, t) for n, t in enumerate(tables, start=1)))


def load(base: Path, name: str) -> Policy:
    """The policy in `name`, written relative to `base`, read as the files the
    lint judges are: not through a symlink, and only from a regular file."""
    try:
        text = files.read(base, name).decode("utf-8")
    except files.Unreadable as error:
        raise PolicyError(str(error)) from error
    except UnicodeDecodeError as error:
        raise PolicyError(f"{name} is not UTF-8") from error
    return parse(text)

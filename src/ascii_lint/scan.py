"""Judge one file's bytes: where a text file holds anything outside ASCII.

A file is binary, and skipped, when its first BINARY_PROBE bytes hold a NUL:
the test git itself uses to decide whether to show a diff as text, so a file
this skips is one a reviewer never saw as text either.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

BINARY_PROBE = 8000


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    column: int
    what: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}:{self.column}: {self.what}"


def is_binary(data: bytes) -> bool:
    return b"\0" in data[:BINARY_PROBE]


def _describe(char: str) -> str:
    # The name is what makes an invisible character findable: U+00A0 and
    # U+200B print as nothing, so the codepoint alone sends the reader hunting.
    name = unicodedata.name(char, "unnamed")
    return f"U+{ord(char):04X} {name}"


def scan(path: str, data: bytes) -> list[Finding]:
    if is_binary(data):
        return []
    findings: list[Finding] = []
    for number, raw in enumerate(data.split(b"\n"), start=1):
        if raw.isascii():
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as error:
            findings.append(
                Finding(
                    path,
                    number,
                    error.start + 1,
                    f"not UTF-8 (byte 0x{raw[error.start]:02X})",
                )
            )
            continue
        for column, char in enumerate(text, start=1):
            if not char.isascii():
                findings.append(Finding(path, number, column, _describe(char)))
    return findings

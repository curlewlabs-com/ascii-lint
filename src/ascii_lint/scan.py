"""Judge one file's bytes: where a text file holds anything outside ASCII that
the repository's policy does not exempt.

A file is binary, and skipped, when its first BINARY_PROBE bytes hold a NUL:
the test git itself uses to decide whether to show a diff as text, so a file
this skips is one a reviewer never saw as text either.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

from ascii_lint.policy import Policy

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


def scan(
    path: str,
    data: bytes,
    policy: Policy | None = None,
    used: set[int] | None = None,
) -> list[Finding]:
    """The findings in one file. Each exemption that covered a character here
    has its number added to `used`, so a caller judging many files can tell
    which exemptions none of them needed."""
    if is_binary(data):
        return []
    findings: list[Finding] = []
    for number, raw in enumerate(data.split(b"\n"), start=1):
        if raw.isascii():
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as error:
            # No exemption covers this: there is no character to exempt, only
            # bytes in an encoding the policy cannot name.
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
            if char.isascii():
                continue
            covering = policy.covering(path, char) if policy else []
            if covering:
                if used is not None:
                    used.update(e.number for e in covering)
                continue
            findings.append(Finding(path, number, column, _describe(char)))
    return findings

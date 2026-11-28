"""Judge files' bytes against a repository's policy: where a text file holds
anything outside ASCII that the policy does not exempt (scan), and, over a set
of files, which exemptions none of them needed (judge).

A file is binary, and skipped, when its first BINARY_PROBE bytes hold a NUL:
the test git itself uses to decide whether to show a diff as text, so a file
this skips is one a reviewer never saw as text either.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass

from ascii_lint.policy import Exemption, Policy

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
    if used is None:
        return _scan(path, data, policy, None)
    covered: set[Exemption] = set()
    findings = _scan(path, data, policy, covered)
    used.update(exemption.number for exemption in covered)
    return findings


def _scan(
    path: str, data: bytes, policy: Policy | None, used: set[Exemption] | None
) -> list[Finding]:
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
                    used.update(covering)
                continue
            findings.append(Finding(path, number, column, _describe(char)))
    return findings


@dataclass(frozen=True)
class Verdict:
    findings: tuple[Finding, ...]
    # The exemptions that covered no character in the files judged. That is a
    # finding only when those files are every file the exemptions are for:
    # judged alone, a subset says nothing about what the rest still needs.
    unused: tuple[Exemption, ...]


def judge(files: Iterable[tuple[str, bytes]], policy: Policy) -> Verdict:
    """Supply each file's canonical repository-relative path and its bytes.

    Patterns match the path as supplied, so use slash separators, omit any
    `.` or `..` components, and use the exact Git index spelling for tracked
    files. The caller handles file reads, and an iterator is consumed one
    file at a time.
    """
    # A composed policy can contain exemptions with the same display number.
    used: set[Exemption] = set()
    findings: list[Finding] = []
    for path, data in files:
        findings.extend(_scan(path, data, policy, used))
    unused = tuple(
        exemption for exemption in policy.exemptions if exemption not in used
    )
    return Verdict(tuple(findings), unused)

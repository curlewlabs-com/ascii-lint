"""Tests for judging one file's bytes."""

from __future__ import annotations

import unittest

from ascii_lint.scan import BINARY_PROBE, scan


class Scan(unittest.TestCase):
    def test_ascii_is_clean(self) -> None:
        self.assertEqual(scan("a.txt", b"plain\r\ntext\ttabs\n"), [])

    def test_each_character_is_reported_with_its_position(self) -> None:
        findings = scan("a.md", "ok\nan \u2014 dash and \u2026\n".encode())
        self.assertEqual(
            [str(f) for f in findings],
            [
                "a.md:2:4: U+2014 EM DASH",
                "a.md:2:15: U+2026 HORIZONTAL ELLIPSIS",
            ],
        )

    def test_an_invisible_character_is_named(self) -> None:
        # The case the lint exists for: these print as nothing, so a reviewer
        # reading the diff cannot see them, and the name is how one is found.
        findings = scan("a.py", "x\u00a0= 1\u200b\n".encode())
        self.assertEqual(
            [f.what for f in findings],
            ["U+00A0 NO-BREAK SPACE", "U+200B ZERO WIDTH SPACE"],
        )

    def test_bytes_that_are_not_utf8_are_reported_not_skipped(self) -> None:
        # Latin-1 text decodes as nothing in particular; reporting the byte
        # keeps a file in another encoding from passing as clean.
        findings = scan("a.txt", b"caf\xe9\n")
        self.assertEqual(
            [str(f) for f in findings], ["a.txt:1:4: not UTF-8 (byte 0xE9)"]
        )

    def test_a_binary_file_is_skipped(self) -> None:
        self.assertEqual(scan("a.png", b"\x89PNG\0\xff\xfe"), [])

    def test_a_nul_past_the_probe_does_not_make_a_file_binary(self) -> None:
        data = b"a" * BINARY_PROBE + b"\0" + "\u00e9".encode()
        self.assertEqual(len(scan("a.txt", data)), 1)


if __name__ == "__main__":
    unittest.main()

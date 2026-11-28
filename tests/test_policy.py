"""Tests for reading `.ascii-lint.toml` and deciding what an exemption covers."""

from __future__ import annotations

import unittest

from ascii_lint.policy import PolicyError, parse
from ascii_lint.scan import scan

CHECK = chr(0x2713)
DASH = chr(0x2014)
# TOML's own escape for CHECK, so a config written this way stays ASCII.
CHECK_ESCAPED = chr(92) + "u2713"


class Reading(unittest.TestCase):
    def test_no_file_content_is_no_exemptions(self) -> None:
        self.assertEqual(parse("").exemptions, ())

    def test_an_exemption_is_read_with_its_number(self) -> None:
        policy = parse(
            "[[exempt]]\nreason = 'listings'\npaths = ['^meta/']\n"
            "[[exempt]]\nreason = 'face'\npaths = ['']\n"
            f'characters = "{CHECK_ESCAPED}"\n'
        )
        self.assertEqual([e.number for e in policy.exemptions], [1, 2])
        self.assertEqual(policy.exemptions[1].characters, frozenset(CHECK))
        self.assertEqual(str(policy.exemptions[0]), "exemption 1 (listings)")

    def test_a_malformed_exemption_is_an_error_not_an_empty_policy(self) -> None:
        # Each of these would otherwise exempt nothing, or everything, silently.
        for text, message in (
            ("[[exempt]]\npaths = ['']\n", "has no reason"),
            ("[[exempt]]\nreason = ' '\npaths = ['']\n", "has no reason"),
            ("[[exempt]]\nreason = 'r'\n", "has no paths"),
            ("[[exempt]]\nreason = 'r'\npaths = []\n", "paths is empty"),
            ("[[exempt]]\nreason = 'r'\npaths = '^a'\n", "list of strings"),
            ("[[exempt]]\nreason = 'r'\npaths = ['(']\n", "bad pattern"),
            ("[[exempt]]\nreason = 'r'\npaths = ['']\npath = ['x']\n", "unknown key"),
            ("[[exempt]]\nreason = 'r'\npaths = ['']\ncharacters = 'a'\n", "ASCII"),
            ("exemptions = []\n", "unknown key"),
            ("exempt = 'x'\n", "array of tables"),
            ("[[exempt]\n", "not TOML"),
        ):
            with self.subTest(text=text):
                with self.assertRaises(PolicyError) as raised:
                    parse(text)
                self.assertIn(message, str(raised.exception))

    def test_pattern_compiler_limits_are_policy_errors(self) -> None:
        # A pattern can reach the engine's limit before it raises a syntax
        # error. Callers still need the exemption and field that failed.
        overflow = "a{4294967296}"
        nested = "(" * 2000 + "a" + ")" * 2000
        long_repeat = "a{" + "9" * 5000 + "}"
        for paths, except_paths, field in (
            (overflow, "", "paths"),
            ("", overflow, "except_paths"),
            (nested, "", "paths"),
            (long_repeat, "", "paths"),
        ):
            with self.subTest(field=field, pattern_length=len(paths or except_paths)):
                text = (
                    "[[exempt]]\nreason = 'r'\n"
                    f"paths = ['{paths}']\nexcept_paths = ['{except_paths}']\n"
                )
                with self.assertRaisesRegex(
                    PolicyError, f"exemption 1: {field} holds a bad pattern"
                ):
                    parse(text)

    def test_an_unreadable_toml_value_is_a_policy_error(self) -> None:
        # A document can exceed the decoder's limits before policy validation.
        for value in ("[" * 2000 + "0" + "]" * 2000, "9" * 5000):
            with self.assertRaises(PolicyError):
                parse(f"exempt = {value}")


class Covering(unittest.TestCase):
    def test_paths_are_searched_and_except_paths_win(self) -> None:
        policy = parse(
            "[[exempt]]\nreason = 'face'\npaths = ['']\n"
            "except_paths = ['^tools/']\n"
            f'characters = "{CHECK_ESCAPED}"\n'
        )
        self.assertTrue(policy.covering("app/face.kt", CHECK))
        self.assertFalse(policy.covering("tools/report.py", CHECK))
        self.assertFalse(policy.covering("app/face.kt", DASH))

    def test_a_pattern_matches_where_it_is_anchored_and_nowhere_else(self) -> None:
        # Searched, not matched whole, so the anchor is the author's to write.
        policy = parse("[[exempt]]\nreason = 'r'\npaths = ['^meta/[a-z]{2}/']\n")
        self.assertTrue(policy.covering("meta/fr/title.txt", DASH))
        self.assertFalse(policy.covering("app/meta/fr/title.txt", DASH))
        self.assertFalse(policy.covering("meta/android/title.txt", DASH))

    def test_scan_skips_a_covered_character_and_records_who_covered_it(self) -> None:
        policy = parse(
            "[[exempt]]\nreason = 'a'\npaths = ['^a/']\n"
            "[[exempt]]\nreason = 'b'\npaths = ['^b/']\n"
        )
        used: set[int] = set()
        line = f"x {DASH} y\n".encode()
        self.assertEqual(scan("a/f.txt", line, policy, used), [])
        self.assertEqual(len(scan("c/f.txt", line, policy, used)), 1)
        self.assertEqual(used, {1})

    def test_bytes_that_are_not_utf8_are_never_exempt(self) -> None:
        # There is no character to name, so no exemption can be about it.
        policy = parse("[[exempt]]\nreason = 'r'\npaths = ['']\n")
        self.assertEqual(len(scan("f.txt", b"caf\xe9\n", policy)), 1)


if __name__ == "__main__":
    unittest.main()

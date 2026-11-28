"""Tests for the library interface: judging files the caller has read."""

from __future__ import annotations

import unittest

import ascii_lint

DASH = chr(0x2014)
E_ACUTE = chr(0x00E9)

POLICY = (
    "[[exempt]]\nreason = 'names'\npaths = ['^docs/']\n"
    'characters = "\\u00e9"\n'
    "[[exempt]]\nreason = 'listings'\npaths = ['^meta/']\n"
)


class Judge(unittest.TestCase):
    def test_findings_and_the_exemptions_that_covered_nothing(self) -> None:
        verdict = ascii_lint.judge(
            [
                ("docs/a.md", f"caf{E_ACUTE} {DASH}\n".encode()),
                ("src/b.py", b"ascii\n"),
            ],
            ascii_lint.parse(POLICY),
        )
        self.assertEqual(
            [str(f) for f in verdict.findings], ["docs/a.md:1:6: U+2014 EM DASH"]
        )
        # The first exemption covered the accent, so only the second is unused.
        self.assertEqual([str(e) for e in verdict.unused], ["exemption 2 (listings)"])

    def test_a_file_is_judged_by_the_path_it_is_handed_with(self) -> None:
        # A build reads a file at a sandbox path; the policy must still see the
        # path from the repository root, or an exemption would decide
        # differently there than in a whole-repository run.
        data = f"caf{E_ACUTE}\n".encode()
        policy = ascii_lint.parse(POLICY)
        self.assertEqual(ascii_lint.judge([("docs/a.md", data)], policy).findings, ())
        self.assertEqual(
            [str(f) for f in ascii_lint.judge([("a.md", data)], policy).findings],
            ["a.md:1:4: U+00E9 LATIN SMALL LETTER E WITH ACUTE"],
        )

    def test_an_exemption_number_is_local_to_its_parsed_policy(self) -> None:
        # Composing policies must not hide an unused exemption when both
        # inputs assign its display number to one of their exemptions.
        names = ascii_lint.parse(POLICY).exemptions[0]
        listings = ascii_lint.parse(
            "[[exempt]]\nreason = 'listings'\npaths = ['^meta/']\n"
        ).exemptions[0]
        policy = ascii_lint.Policy((names, listings))

        verdict = ascii_lint.judge([("docs/a.md", f"caf{E_ACUTE}\n".encode())], policy)

        self.assertEqual(verdict.findings, ())
        self.assertEqual(verdict.unused, (listings,))


if __name__ == "__main__":
    unittest.main()

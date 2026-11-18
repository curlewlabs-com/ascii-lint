"""Tests for the `ascii-lint` command: which files it reads, and that a lint
that could not run never exits clean."""

from __future__ import annotations

import contextlib
import io
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ascii_lint.cli import files_in_listing, main


def run(argv: list[str]) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        status = main(argv)
    return status, out.getvalue(), err.getvalue()


class TheCommand(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        cwd = os.getcwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, cwd)

    def git(self, *args: str) -> None:
        subprocess.run(["git", *args], cwd=self.root, check=True, capture_output=True)

    def test_tracked_files_are_read_and_untracked_ones_are_not(self) -> None:
        self.git("init", "-q")
        (self.root / "tracked.md").write_text("a \u2014 b\n")
        (self.root / "untracked.md").write_text("a \u2014 b\n")
        self.git("add", "tracked.md")
        status, out, _ = run([])
        self.assertEqual(status, 1)
        self.assertEqual(out, "tracked.md:1:3: U+2014 EM DASH\n")

    def test_a_clean_repository_exits_zero(self) -> None:
        self.git("init", "-q")
        (self.root / "a.txt").write_text("ascii\n")
        self.git("add", "a.txt")
        self.assertEqual(run([]), (0, "", ""))

    def test_a_tracked_symlink_is_skipped(self) -> None:
        # Its content is its target's path; the target is outside the
        # repository, or is a file read on its own.
        self.git("init", "-q")
        elsewhere = tempfile.TemporaryDirectory()
        self.addCleanup(elsewhere.cleanup)
        outside = Path(elsewhere.name) / "target.txt"
        outside.write_text("\u2014\n")
        (self.root / "link").symlink_to(outside)
        self.git("add", "link")
        self.assertEqual(run([])[0], 0)

    def test_a_named_symlink_fails_rather_than_being_followed(self) -> None:
        (self.root / "target.txt").write_text("ascii\n")
        (self.root / "link").symlink_to("target.txt")
        status, _, err = run(["link"])
        self.assertEqual(status, 1)
        self.assertIn("link: link is a symlink", err)

    def test_a_tracked_file_replaced_by_a_symlink_fails(self) -> None:
        # The index says a file; what is on disk now points elsewhere, and
        # reading its target would judge something that was not asked for.
        self.git("init", "-q")
        (self.root / "a.txt").write_text("ascii\n")
        self.git("add", "a.txt")
        (self.root / "a.txt").unlink()
        (self.root / "a.txt").symlink_to("/dev/null")
        status, _, err = run([])
        self.assertEqual(status, 1)
        self.assertIn("a.txt: a.txt is a symlink", err)

    def test_a_symlinked_parent_directory_fails(self) -> None:
        # Checking only the last component would read the file through the
        # linked directory, which is not the tracked one.
        self.git("init", "-q")
        (self.root / "docs").mkdir()
        (self.root / "docs/a.md").write_text("ascii\n")
        self.git("add", "docs/a.md")
        (self.root / "real").mkdir()
        (self.root / "real/a.md").write_text("ascii\n")
        (self.root / "docs/a.md").unlink()
        (self.root / "docs").rmdir()
        (self.root / "docs").symlink_to("real")
        for argv in ([], ["docs/a.md"]):
            with self.subTest(argv=argv):
                status, _, err = run(argv)
                self.assertEqual(status, 1)
                self.assertIn("docs is a symlink", err)

    def test_a_fifo_fails_rather_than_blocking(self) -> None:
        # Opening a FIFO for reading waits for a writer; a lint that hung
        # there would never report.
        os.mkfifo(self.root / "pipe")
        status, _, err = run(["pipe"])
        self.assertEqual(status, 1)
        self.assertIn("pipe is not a regular file", err)

    def test_a_root_ending_in_whitespace_is_kept_whole(self) -> None:
        # Stripping the name would judge the clean sibling instead.
        (self.root / "repo").mkdir()
        spaced = self.root / "repo "
        spaced.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=spaced, check=True)
        (spaced / "a.md").write_text("\u2014\n")
        subprocess.run(["git", "add", "a.md"], cwd=spaced, check=True)
        os.chdir(spaced)
        self.assertEqual(run([])[0], 1)

    def test_a_listed_name_is_decoded_as_the_filesystem_does(self) -> None:
        # A POSIX filename need not be UTF-8; it must still be read, not
        # rejected or skipped.
        listing = b"100644 " + b"0" * 40 + b" 0\tcaf\xe9.txt\0"
        (name,) = files_in_listing(listing)
        self.assertEqual(os.fsencode(name), b"caf\xe9.txt")

    def test_the_repository_policy_exempts_and_reports_what_it_did_not_need(
        self,
    ) -> None:
        # The second exemption covers nothing: judged against the whole
        # repository, it is an excuse nobody needs, and that is a finding.
        self.git("init", "-q")
        (self.root / "meta").mkdir()
        (self.root / "meta/fr.txt").write_text("caf\u00e9\n")
        (self.root / ".ascii-lint.toml").write_text(
            "[[exempt]]\nreason = 'listings'\npaths = ['^meta/']\n"
            "[[exempt]]\nreason = 'gone'\npaths = ['^old/']\n"
        )
        self.git("add", "meta/fr.txt", ".ascii-lint.toml")
        self.assertEqual(
            run([]),
            (
                1,
                ".ascii-lint.toml: exemption 2 (gone) covered nothing; delete it\n",
                "",
            ),
        )

    def test_named_files_report_unused_exemptions_only_when_asked(self) -> None:
        # A file list may be one package of many; the rest may need it.
        (self.root / "a.txt").write_text("ascii\n")
        (self.root / ".ascii-lint.toml").write_text(
            "[[exempt]]\nreason = 'r'\npaths = ['^meta/']\n"
        )
        self.assertEqual(run(["a.txt"]), (0, "", ""))
        status, out, _ = run(["--check-unused", "a.txt"])
        self.assertEqual(status, 1)
        self.assertIn("exemption 1 (r) covered nothing", out)

    def test_a_named_config_is_read_and_must_exist(self) -> None:
        (self.root / "a.txt").write_text("caf\u00e9\n")
        (self.root / "policy.toml").write_text(
            "[[exempt]]\nreason = 'r'\npaths = ['^a[.]txt$']\n"
        )
        self.assertEqual(run(["--config", "policy.toml", "a.txt"]), (0, "", ""))
        status, _, err = run(["--config", "missing.toml", "a.txt"])
        self.assertEqual(status, 1)
        self.assertIn("missing.toml: cannot read", err)

    def test_a_malformed_policy_fails_rather_than_exempting_nothing(self) -> None:
        (self.root / "a.txt").write_text("ascii\n")
        (self.root / ".ascii-lint.toml").write_text("[[exempt]]\npaths = ['']\n")
        status, _, err = run(["a.txt"])
        self.assertEqual(status, 1)
        self.assertIn(".ascii-lint.toml: exemption 1 has no reason", err)

    def test_a_named_file_is_matched_by_one_spelling_however_it_is_named(
        self,
    ) -> None:
        # Matched as written, `./scripts/x` would slip past an except_paths
        # pattern that `scripts/x` meets, and the exemption would cover it.
        self.git("init", "-q")
        (self.root / "scripts").mkdir()
        (self.root / "scripts/x.sh").write_text("\u2713\n")
        (self.root / ".ascii-lint.toml").write_text(
            "[[exempt]]\nreason = 'face'\npaths = ['']\nexcept_paths = ['^scripts/']\n"
        )
        expected = "scripts/x.sh:1:1: U+2713 CHECK MARK\n"
        for name in (
            "scripts/x.sh",
            "./scripts/x.sh",
            "scripts/../scripts/x.sh",
            # The real path: on some systems the temporary directory sits
            # behind a symlink, which the lint refuses to read through.
            str(self.root.resolve() / "scripts/x.sh"),
        ):
            with self.subTest(name=name):
                self.assertEqual(run([name]), (1, expected, ""))

    def test_from_a_subdirectory_the_root_policy_applies(self) -> None:
        # The policy is the repository's, not the current directory's.
        self.git("init", "-q")
        (self.root / "meta").mkdir()
        (self.root / "meta/fr.txt").write_text("caf\u00e9\n")
        (self.root / ".ascii-lint.toml").write_text(
            "[[exempt]]\nreason = 'r'\npaths = ['^meta/']\n"
        )
        os.chdir(self.root / "meta")
        self.assertEqual(run(["fr.txt"]), (0, "", ""))

    def test_a_named_file_outside_the_repository_fails(self) -> None:
        self.git("init", "-q")
        (self.root / "sub").mkdir()
        os.chdir(self.root / "sub")
        self.git("-C", str(self.root / "sub"), "init", "-q")
        status, _, err = run(["../outside.txt"])
        self.assertEqual(status, 1)
        self.assertIn("outside the repository", err)

    def test_the_policy_is_read_with_the_same_guards_as_a_file(self) -> None:
        # Read any other way, a FIFO config would hang the run and a symlinked
        # one would apply a policy from somewhere the repository does not hold.
        self.git("init", "-q")
        (self.root / "a.txt").write_text("ascii\n")
        self.git("add", "a.txt")
        real = self.root / "real.toml"
        real.write_text("")
        os.mkfifo(self.root / "fifo.toml")
        (self.root / "link.toml").symlink_to(real)
        (self.root / "dir").mkdir()
        (self.root / "dir/p.toml").write_text("")
        (self.root / "linked-dir").symlink_to("dir")
        for argv, message in (
            (["--config", "fifo.toml"], "fifo.toml is not a regular file"),
            (["--config", "link.toml"], "link.toml is a symlink"),
            (["--config", "linked-dir/p.toml"], "linked-dir is a symlink"),
        ):
            with self.subTest(argv=argv):
                status, _, err = run(argv)
                self.assertEqual(status, 1)
                self.assertIn(message, err)

    def test_a_dangling_default_policy_fails_rather_than_reading_as_none(
        self,
    ) -> None:
        self.git("init", "-q")
        (self.root / "a.txt").write_text("ascii\n")
        self.git("add", "a.txt")
        (self.root / ".ascii-lint.toml").symlink_to("missing.toml")
        status, _, err = run([])
        self.assertEqual(status, 1)
        self.assertIn(".ascii-lint.toml is a symlink", err)

    def ignores_case(self) -> bool:
        probe = self.root / "case-probe"
        probe.write_text("")
        try:
            return (self.root / "CASE-PROBE").exists()
        finally:
            probe.unlink()

    def test_a_name_spelled_unlike_its_directory_entry_fails(self) -> None:
        # On a filesystem that ignores case, `Scripts/x.sh` opens scripts/x.sh
        # but would slip past an except_paths pattern for `^scripts/`; where
        # case counts, it names nothing.
        self.git("init", "-q")
        (self.root / "scripts").mkdir()
        (self.root / "scripts/x.sh").write_text("ascii\n")
        status, _, err = run(["Scripts/x.sh"])
        self.assertEqual(status, 1)
        if self.ignores_case():
            self.assertIn("is not spelled as the directory entry it names", err)
        else:
            self.assertIn("No such file or directory", err)

    def test_a_name_the_index_spells_differently_fails(self) -> None:
        # The directory was renamed on disk only; the index still says
        # scripts/, and a whole-repository run judges it by that spelling.
        if not self.ignores_case():
            self.skipTest("only a filesystem that ignores case can alias these")
        self.git("init", "-q")
        (self.root / "scripts").mkdir()
        (self.root / "scripts/x.sh").write_text("ascii\n")
        self.git("add", "scripts/x.sh")
        (self.root / "scripts").rename(self.root / "Scripts")
        status, _, err = run(["Scripts/x.sh"])
        self.assertEqual(status, 1)
        self.assertIn("is tracked as scripts/x.sh", err)

    def test_without_git_named_files_fail_rather_than_falling_back(self) -> None:
        # Only git saying there is no repository allows judging from here;
        # anything else, judged from here, would match `scripts/x.sh` as
        # `x.sh`, past any pattern anchored at the root.
        (self.root / "a.txt").write_text("ascii\n")
        with mock.patch.dict(os.environ, {"PATH": str(self.root)}):
            status, _, err = run(["a.txt"])
        self.assertEqual(status, 1)
        self.assertIn("git is not on PATH", err)

    def test_an_empty_config_name_fails_rather_than_choosing_the_default(
        self,
    ) -> None:
        # An unset variable expands to it; the default here would exempt all.
        self.git("init", "-q")
        (self.root / "a.txt").write_text("\u2014\n")
        (self.root / ".ascii-lint.toml").write_text(
            "[[exempt]]\nreason = 'all'\npaths = ['']\n"
        )
        self.git("add", "a.txt", ".ascii-lint.toml")
        status, _, err = run(["--config", ""])
        self.assertEqual(status, 1)
        self.assertIn("could not run", err)

    def test_named_files_are_read_instead_of_the_tracked_set(self) -> None:
        (self.root / "a.txt").write_text("\u00e9\n")
        status, out, _ = run(["a.txt"])
        self.assertEqual(
            (status, out), (1, "a.txt:1:1: U+00E9 LATIN SMALL LETTER E WITH ACUTE\n")
        )

    def test_outside_a_repository_it_fails_rather_than_passing(self) -> None:
        # No file list means nothing was judged; that must not read as clean.
        status, out, err = run([])
        self.assertEqual((status, out), (1, ""))
        self.assertIn("could not run: git rev-parse failed", err)

    def test_from_a_subdirectory_the_whole_repository_is_read(self) -> None:
        # Run from a clean subdirectory, a scan of only that subtree would pass
        # a repository whose other files hold findings.
        self.git("init", "-q")
        (self.root / "top.md").write_text("\u2014\n")
        (self.root / "sub").mkdir()
        (self.root / "sub/clean.md").write_text("ascii\n")
        self.git("add", "top.md", "sub/clean.md")
        os.chdir(self.root / "sub")
        self.assertEqual(run([]), (1, "top.md:1:1: U+2014 EM DASH\n", ""))

    def test_a_submodule_is_not_read(self) -> None:
        self.git("init", "-q")
        (self.root / "sub").mkdir()
        self.git(
            "update-index",
            "--add",
            "--cacheinfo",
            "160000,0123456789abcdef0123456789abcdef01234567,sub",
        )
        self.assertEqual(run([]), (0, "", ""))

    def test_a_tracked_file_replaced_by_a_directory_fails(self) -> None:
        # Only a gitlink is skipped; any other path that cannot be read as a
        # file means part of the tree went unjudged.
        self.git("init", "-q")
        (self.root / "a.txt").write_text("ascii\n")
        self.git("add", "a.txt")
        (self.root / "a.txt").unlink()
        (self.root / "a.txt").mkdir()
        status, _, err = run([])
        self.assertEqual(status, 1)
        self.assertIn("cannot read a.txt", err)

    def test_a_named_directory_fails_rather_than_passing(self) -> None:
        (self.root / "d").mkdir()
        status, _, err = run(["d"])
        self.assertEqual(status, 1)
        self.assertIn("cannot read d", err)

    def test_a_missing_named_file_fails_rather_than_passing(self) -> None:
        status, _, err = run(["missing.txt"])
        self.assertEqual(status, 1)
        self.assertIn("cannot read missing.txt", err)


if __name__ == "__main__":
    unittest.main()

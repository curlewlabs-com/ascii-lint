"""The `ascii-lint` command: report non-ASCII bytes in tracked text.

    ascii-lint [FILE...]

With no FILE, it reads every file the index of the current directory's
repository holds, from the repository's root wherever it is run, so a file is
judged because it is tracked, not because its name looks like text. A symlink
and a submodule are entries of the index but not files of this repository's,
and are skipped; any other tracked path that is not a readable file is an
error. Named FILEs are read relative to the current directory. A symlink is
never followed: where one stands anywhere on the path to a file to read, named
or tracked as a file, that is an error, since its target is not what was asked
for. Nor is anything but a regular file read: a FIFO would block and a device
would not end.

It prints one line per character, with its codepoint and name, and exits 1 on
any finding; it also exits 1, with the reason on stderr, when it could not read
what it was asked to, since a lint that did not run must not read as clean.
"""

from __future__ import annotations

import argparse
import os
import stat
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from ascii_lint.scan import Finding, scan


class CouldNotRun(Exception):
    pass


# Index modes that are not this repository's file content: a symlink's
# content is its target's path, and a gitlink is another repository's commit.
NOT_FILES = ("120000", "160000")


def _git(root: Path, *args: str) -> bytes:
    try:
        return subprocess.run(
            ["git", *args], cwd=root, capture_output=True, check=True
        ).stdout
    except FileNotFoundError as error:
        raise CouldNotRun("git is not on PATH") from error
    except subprocess.CalledProcessError as error:
        stderr = error.stderr.decode(errors="replace").strip()
        raise CouldNotRun(f"git {args[0]} failed: {stderr}") from error


def repository_root(cwd: Path) -> Path:
    # Only git's terminating newline is removed: a path may end in whitespace,
    # and it is bytes in the filesystem's encoding, not necessarily UTF-8.
    out = _git(cwd, "rev-parse", "--show-toplevel")
    return Path(os.fsdecode(out.removesuffix(b"\n")))


def files_in_listing(listing: bytes) -> list[str]:
    """The file paths in `git ls-files -z --stage` output."""
    names = []
    for entry in listing.split(b"\0"):
        if not entry:
            continue
        meta, _, name = entry.partition(b"\t")
        if meta.split(b" ")[0].decode() not in NOT_FILES:
            names.append(os.fsdecode(name))
    # A path with a merge conflict is listed once per stage.
    return list(dict.fromkeys(names))


def tracked_files(root: Path) -> list[str]:
    return files_in_listing(_git(root, "ls-files", "-z", "--stage"))


def read_file(path: Path) -> bytes:
    # O_NOFOLLOW refuses a symlink in the last component at open time, so
    # nothing can swap one in between a check and the read; O_NONBLOCK keeps a
    # FIFO from blocking the open, and the fstat then refuses it, a device, or
    # anything else that is not a regular file before a byte is read.
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as file:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise NotARegularFile
        return file.read()


class NotARegularFile(Exception):
    pass


def symlink_on_the_way(base: Path, name: str) -> str | None:
    """The first leading part of `name`, as written, that is a symlink."""
    walked = Path()
    for part in Path(name).parts:
        walked = walked / part
        if (base / walked).is_symlink():
            return str(walked)
    return None


def check(root: Path, names: Sequence[str]) -> list[Finding]:
    findings: list[Finding] = []
    for name in names:
        link = symlink_on_the_way(root, name)
        if link is not None:
            raise CouldNotRun(
                f"{name}: {link} is a symlink; name the file it points to"
            )
        try:
            data = read_file(root / name)
        except NotARegularFile as error:
            raise CouldNotRun(f"{name} is not a regular file") from error
        except OSError as error:
            raise CouldNotRun(f"cannot read {name}: {error.strerror}") from error
        findings.extend(scan(name, data))
    return findings


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ascii-lint",
        description="Report every non-ASCII character in tracked text files.",
    )
    parser.add_argument(
        "files",
        nargs="*",
        metavar="FILE",
        help="files to read instead of every tracked file",
    )
    args = parser.parse_args(argv)
    try:
        if args.files:
            findings = check(Path.cwd(), args.files)
        else:
            root = repository_root(Path.cwd())
            findings = check(root, tracked_files(root))
    except CouldNotRun as error:
        print(f"ERROR: ascii-lint could not run: {error}", file=sys.stderr)
        return 1
    for finding in findings:
        print(finding)
    return 1 if findings else 0

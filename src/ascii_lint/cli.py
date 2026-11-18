"""The `ascii-lint` command: report non-ASCII bytes in tracked text.

    ascii-lint [--config FILE] [--check-unused] [FILE...]

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

The exemptions are policy.py's, read from `.ascii-lint.toml` at the
repository root, or from --config, named from the current directory. A named
FILE is matched against them by its path from the repository root, however it
was spelled; outside any repository, the current directory is the root. Judging the whole repository, an exemption that covered nothing
is a finding. Judging named FILEs it is not, since the rest of the repository
may need it, unless --check-unused says the FILEs are every file the
exemptions are for: a build that hands a lint its file list says so.

It prints one line per character, with its codepoint and name, and exits 1 on
any finding; it also exits 1, with the reason on stderr, when it could not read
what it was asked to or the policy is malformed, since a lint that did not run
must not read as clean.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from ascii_lint import files
from ascii_lint.policy import CONFIG_NAME, Policy, PolicyError, load
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


def repository_root_if_any(cwd: Path) -> Path | None:
    """The repository root, or None only when git says there is none. Any
    other failure is raised: falling back to the current directory then would
    change the path every exemption is matched against."""
    try:
        listed = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=cwd,
            capture_output=True,
            check=True,
        ).stdout
    except FileNotFoundError as error:
        raise CouldNotRun("git is not on PATH") from error
    except subprocess.CalledProcessError as error:
        stderr = error.stderr.decode(errors="replace").strip()
        if "not a git repository" in stderr:
            return None
        raise CouldNotRun(f"git rev-parse failed: {stderr}") from error
    return Path(os.fsdecode(listed.removesuffix(b"\n")))


def files_in_listing(listing: bytes) -> list[str]:
    """The file paths in `git ls-files -z --stage` output."""
    names: list[str] = []
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


def check(
    items: Sequence[tuple[str, Path, str]],
    policy: Policy | None = None,
    used: set[int] | None = None,
) -> list[Finding]:
    """Each item is the path the policy matches and the report names, from the
    repository root, and the base and name the file is read through as given,
    so a symlink on the way as written is still refused."""
    findings: list[Finding] = []
    for shown, base, name in items:
        try:
            data = files.read(base, name)
        except files.Unreadable as error:
            raise CouldNotRun(str(error)) from error
        findings.extend(scan(shown, data, policy, used))
    return findings


def from_root(root: Path, cwd: Path, name: str) -> str:
    """A named file as a path from the repository root, spelled one way
    whatever way it was named (`./a`, `sub/../a`, an absolute path, or `A` for
    `a` on a filesystem that ignores case), so an exemption's pattern sees the
    same path a whole-repository run does. A part spelled differently from the
    directory entry it opens is refused rather than guessed at."""
    canonical = os.path.relpath(os.path.abspath(cwd / name), root)
    if canonical == ".." or canonical.startswith("../"):
        raise CouldNotRun(f"{name} is outside the repository at {root}")
    parent = root
    for part in Path(canonical).parts:
        try:
            entries = os.listdir(parent)
        except OSError as error:
            raise CouldNotRun(f"cannot read {name}: {error.strerror}") from error
        if part not in entries and not os.path.lexists(parent / part):
            raise CouldNotRun(f"cannot read {name}: No such file or directory")
        if part not in entries:
            raise CouldNotRun(
                f"{name}: {parent / part} is not spelled as the directory"
                " entry it names; name the file as it is spelled on disk"
            )
        parent = parent / part
    return canonical


def refuse_index_aliases(root: Path, canonicals: Sequence[str]) -> None:
    """Refuse a named file the index tracks under another spelling. On a
    filesystem that ignores case, a directory renamed on disk alone leaves the
    index spelling `scripts/x.sh` and the disk spelling `Scripts/x.sh` naming
    one file, and the exemptions would judge the two differently; a
    whole-repository run uses the index's, so the named run must agree."""
    if not canonicals:
        return
    # The whole index in one read, matched here: a build can name more files
    # than fit on a command line as pathspecs.
    listed = _git(root, "ls-files", "-z")
    tracked: dict[str, list[str]] = {}
    for entry in listed.split(b"\0"):
        if entry:
            name = os.fsdecode(entry)
            tracked.setdefault(name.lower(), []).append(name)
    for name in canonicals:
        spellings = tracked.get(name.lower(), [])
        if spellings and name not in spellings:
            raise CouldNotRun(
                f"{name} is tracked as {spellings[0]}; name it as the index spells it"
            )


def read_policy(
    explicit: str | None, root: Path, cwd: Path
) -> tuple[Policy, str | None]:
    """The policy, and the name of the file it came from, if any. A named
    config must be readable; the default one at the root may be absent, which
    is no exemptions, but not a symlink or anything else in its place."""
    if explicit is not None:
        base, name = cwd, explicit
    elif os.path.lexists(root / CONFIG_NAME):
        base, name = root, CONFIG_NAME
    else:
        return Policy(), None
    try:
        return load(base, name), name
    except PolicyError as error:
        raise CouldNotRun(f"{name}: {error}") from error


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ascii-lint",
        description="Report every non-ASCII character in tracked text files.",
    )
    parser.add_argument(
        "--config",
        metavar="FILE",
        help=f"the exemptions to apply instead of {CONFIG_NAME}",
    )
    parser.add_argument(
        "--check-unused",
        action="store_true",
        help="with FILEs: they are every file the exemptions are for, so report"
        " an exemption none of them needed",
    )
    parser.add_argument(
        "files",
        nargs="*",
        metavar="FILE",
        help="files to read instead of every tracked file",
    )
    args = parser.parse_args(argv)
    used: set[int] = set()
    cwd = Path.cwd()
    try:
        if args.files:
            # Named files need no repository; outside one, they are judged
            # from here.
            repository = repository_root_if_any(cwd)
            root = repository or cwd
            items = [(from_root(root, cwd, name), cwd, name) for name in args.files]
            if repository is not None:
                refuse_index_aliases(repository, [shown for shown, _, _ in items])
            check_unused = args.check_unused
        else:
            root = repository_root(cwd)
            items = [(name, root, name) for name in tracked_files(root)]
            check_unused = True
        policy, source = read_policy(args.config, root, cwd)
        findings = check(items, policy, used)
    except CouldNotRun as error:
        print(f"ERROR: ascii-lint could not run: {error}", file=sys.stderr)
        return 1
    for finding in findings:
        print(finding)
    unused = (
        [e for e in policy.exemptions if e.number not in used] if check_unused else []
    )
    for exemption in unused:
        print(f"{source}: {exemption} covered nothing; delete it")
    return 1 if findings or unused else 0

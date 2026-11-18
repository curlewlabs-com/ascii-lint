# ascii-lint

## What it is

A lint that fails on any character outside ASCII in a repository's tracked text
files, and names each one: `docs/a.md:12:40: U+00A0 NO-BREAK SPACE`. Binary
files are skipped. Characters a repository needs, such as a locale's own text,
are exempted in `.ascii-lint.toml`, each with its reason.

## Why it exists

Non-ASCII characters arrive in source without anyone typing them: pasted prose,
editors that substitute punctuation as you type, and generated text. Some are
invisible. A no-break space (U+00A0) or a zero-width space (U+200B) inside a
word renders as nothing in a diff, so a reviewer cannot see what they are
approving. Others look like their ASCII neighbors: an en dash in a command line,
or a curly quote in a config value, reads as correct and fails when the line
runs.

Review does not catch these, because the reviewer is looking at the same
rendering the author was. A check over the bytes does.

## How to use it

As a GitHub Action, after a checkout. Pin it by commit:

```yaml
- uses: actions/checkout@<sha> # vX.Y.Z
  with:
    persist-credentials: false
- uses: curlewlabs-com/ascii-lint@<sha> # vX.Y.Z
```

As a command, from inside a repository:

```sh
pip install git+https://github.com/curlewlabs-com/ascii-lint@v0.2.0
ascii-lint            # every tracked file, with .ascii-lint.toml
ascii-lint a.md b.py  # just these
```

It prints one line per character and exits 1 on any finding. It also exits 1,
with the reason on stderr, when it could not run (no `git`, not a repository, an
unreadable file), so a lint that did not run never reads as clean.

## What it reads

- **Tracked files**, as `git ls-files` lists them. An untracked file is not
  read, and neither is a submodule or a symlink tracked as one. A symlink is
  never followed: one anywhere on the path to a file it reads, named or tracked,
  is an error. Nothing but a regular file is read.
- **Text files.** A file whose first 8000 bytes contain a NUL is binary and is
  skipped. That is the test git uses to decide whether to show a diff as text.
- **UTF-8.** A line that is not valid UTF-8 is reported with the first byte that
  is not, rather than skipped.

## When you need the character

Code that must match or emit a character outside ASCII writes it as an escape,
which states what it is instead of looking like a typo:

| Language                | Escape                  |
| ----------------------- | ----------------------- |
| Python                  | `"\u2014"`              |
| JavaScript / TypeScript | `"\u2014"`              |
| POSIX shell             | `printf '\342\200\224'` |

## Exemptions

Where the character is the point (translated text, a mark the product draws, a
test whose input is the character), the repository says so in `.ascii-lint.toml`
at its root, one `[[exempt]]` table per reason:

```toml
[[exempt]]
reason = "translated store listings: the characters are the deliverable"
paths = ['^fastlane/metadata/[a-z]{2,3}(-[A-Za-z0-9]{2,4})*/']

[[exempt]]
reason = "the marks the app draws as its status"
paths = ['']
except_paths = ['^scripts/', '^[.]github/']
characters = "\u2713\u26a0"
```

- `reason` is required.
- `paths` and `except_paths` are Python regular expressions searched in each
  file's path from the repository root, so anchor them with `^` and `$`. An
  empty pattern matches every path.
- `characters`, when present, limits the exemption to those characters. Write
  them as TOML `\u` or `\U` escapes, so the config is ASCII too.

An exemption covers a character when some `paths` pattern matches the file, no
`except_paths` pattern does, and `characters` is absent or holds it.

An exemption that covered nothing is a finding when the whole repository is
judged: one nobody needs any more is one nobody re-examined. When named files
are judged it is not, since the rest of the repository may need it; pass
`--check-unused` when the named files are every file the exemptions are for, as
a build that hands the lint its file list does. `--config FILE` reads the
exemptions from another file, named from the current directory.

A named file is matched by its path from the repository root, however it was
spelled (`./a`, `sub/../a`, an absolute path) and wherever the lint is run, so
an exemption decides the same way for it as in a whole-repository run. A name
spelled unlike the directory entry it opens, or unlike the index's spelling of
the same file, is refused rather than guessed at. The config is read as the
files are: never through a symlink, and only from a regular file.

A config that is not this shape (a table without a reason, an unknown key, a bad
pattern) is an error, never an empty policy.

## License

MIT. See [LICENSE](LICENSE).

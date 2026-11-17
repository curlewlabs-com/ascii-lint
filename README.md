# ascii-lint

## What it is

A lint that fails on any character outside ASCII in a repository's tracked text
files, and names each one: `docs/a.md:12:40: U+00A0 NO-BREAK SPACE`. Binary
files are skipped. There is no exemption list.

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
pip install git+https://github.com/curlewlabs-com/ascii-lint@v0.1.0
ascii-lint            # every tracked file
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

A repository whose text is meant for readers in another language is not what
this lint is for.

## License

MIT. See [LICENSE](LICENSE).

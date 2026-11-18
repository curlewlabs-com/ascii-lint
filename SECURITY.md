# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in this project, please report it
privately via
[GitHub's security advisory feature](https://github.com/curlewlabs-com/ascii-lint/security/advisories/new).

Do not open a public issue for security vulnerabilities.

## Scope

The lint reads files and runs `git ls-files`. It never runs what it reads. The
security surface is:

- **The `git` it runs.** This is the first `git` on `PATH`, trusted the way
  `python3` is. It is given no argument from the files it reads.
- **The files it reads.** These are the tracked files of the repository it runs
  in, or the paths named on the command line. A symlink is never followed: one
  anywhere on the path to a file it reads is an error, and nothing but a regular
  file is read.
- **The policy it reads.** `.ascii-lint.toml`, or the file `--config` names, is
  parsed as TOML and its patterns compiled as Python regular expressions. It is
  the repository's own, trusted the way its other files are.
- **A false clean.** A non-ASCII character in a tracked text file that the lint
  passes is a defect in what the lint promises. Report it as a bug, or privately
  if you think it matters more than that.

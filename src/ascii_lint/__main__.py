"""`python3 -m ascii_lint`, the command-line entry point; cli.py owns it."""

from ascii_lint.cli import main

if __name__ == "__main__":
    raise SystemExit(main())

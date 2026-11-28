"""Report every byte above 0x7F in a repository's tracked text. See the README.

The command (cli.py) is the interface that finds and reads the files itself.
`judge` (scan.py) is the interface for a caller that reads them: a build that
holds each file at a sandbox path, often through a symlink the command refuses,
hands over each file's canonical repository-relative path with its bytes and
the policy from `parse`. For tracked files use the exact Git index spelling.
The result gives the findings and the exemptions that covered nothing.
"""

import sys

# Checked here, before any other module of the package is imported, so an older
# interpreter gets this message rather than a syntax error from a newer form.
if sys.version_info < (3, 12):  # noqa: UP036 - the point is to run on older ones
    sys.exit("ascii-lint needs Python 3.12 or newer")

# After the version check, which is why these are not at the top.
from ascii_lint.policy import Exemption, Policy, PolicyError, parse
from ascii_lint.scan import Finding, Verdict, judge

__all__ = [
    "Exemption",
    "Finding",
    "Policy",
    "PolicyError",
    "Verdict",
    "judge",
    "parse",
]

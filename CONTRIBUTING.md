# Contributing

Thanks for your interest in improving `ascii-lint`. The bar for a change is
whether it keeps the lint failing closed: a file it cannot read is an error,
never a pass. A file it misjudges, a sharper message, and clearer docs are all
welcome.

## Reporting a file it gets wrong

Include the smallest file that shows it (attach it: pasting it into an issue can
change its bytes), what the lint printed, and what you expected.

## Running the checks

These are the checks CI runs on every push and pull request:

```sh
python3 -m unittest discover -s tests -t .
python3 -m pip install -r requirements-dev.txt
ruff format --check . && ruff check . && mypy && shellcheck action/run.sh
```

## Conventions

- **Tests ship with the change.** A bug fix or a feature includes a test in the
  same pull request. A test that guards a failure mode says which one.
- **Fail closed.** Anything the lint cannot read is an error, with the reason.
- **Exemptions are the repository's, with reasons.** An option is added only for
  a user who cannot use the lint without it.
- **Standard library only at runtime.** `git` is the only other requirement.
- **The action's steps call scripts.** Each `run:` in `action.yml` is one call
  of an executable file in this repository, so shellcheck reads all of the shell
  the action runs.
- **Pin dependencies exactly.** An action reference is its release's commit SHA
  with the version beside it, since a tag can be moved. The tools in
  `requirements-dev.txt` are exact versions. Renovate proposes their updates. A
  pin written inline needs a `# renovate:` comment above it saying what the
  literal is.
- **Comments explain why, not what.**
- **Keep tracked text ASCII.** CI runs this lint on its own tree.

## Submitting

Keep each pull request focused on one change, make sure the checks pass, and
describe the why in the pull request body. CI must be green before merge.

## Releasing

A patch or minor release needs no approval: whoever cuts it follows the steps
below in order, on a `main` commit whose required checks have passed. A major
version, a 1.0, or a minor before 1.0 that changes an interface consumers use
needs the maintainer's explicit approval before its tag is pushed.

Every release gets a fixed `vMAJOR.MINOR.PATCH` tag. The repository blocks
updates and deletions of those tags, and publishing the GitHub Release makes the
tag immutable.

1. Bump `version` in `pyproject.toml` and merge that to `main`.
2. Tag the merge commit `vMAJOR.MINOR.PATCH` and push the tag.
3. Publish it: `gh release create vMAJOR.MINOR.PATCH --verify-tag`.

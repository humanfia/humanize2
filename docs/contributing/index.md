# Contributing

PRs accepted. Ask a question or discuss a substantial change first in
[issues](https://github.com/humanfia/humanize2/issues).

## Set up

```sh
git clone https://github.com/humanfia/humanize2.git
cd humanize2
uv sync
uv run pre-commit install
```

Installing the hooks once means every commit is checked before it is made.

## The two gates

**A commit** runs the formatter, the linter and the type checker — everything that answers in
seconds:

```sh
uv run pre-commit run --all-files
```

**CI** runs those over every file, and the tests on each Python the package claims:

```sh
uv run pytest                       # everything that does not need a real agent
uv run pytest --run-agents          # also drives the real coding agent CLIs
```

`--run-agents` starts the CLIs that are actually installed and spends real tokens on them. The
rest of the suite drives [stand-in agents](/reference/flows#testing-a-flow) instead.

Both gates have to pass. `ruff` and `pyright` run out of this project's own environment rather
than one pre-commit builds, so bump them with `uv lock --upgrade-package ruff` rather than by
editing a second pin.

## What the code is held to

- **`pyright` in strict mode**, over `src` and `tests`. `# type: ignore` comments are switched
  off; a suppression names a pyright rule.
- **`ruff` with every rule on**, less the ones this codebase has a written reason to be without —
  each is annotated in `pyproject.toml`.
- **Google-style docstrings.**
- **Popular, well-maintained libraries** in preference to a custom implementation.

## Where things go

[Architecture](/contributing/architecture) has the layers and the rules that keep them. The short
version: each package depends only downwards, and the layering is checked by a test.

Beside most packages there is a `SPEC.md`. **Do not modify a `SPEC.md`** unless you were asked
to — it is the contract, and the code is what has to move.

## Documentation

- `README.md` follows [standard-readme](https://github.com/RichardLitt/standard-readme), and
  says what humanize does and how to use it — never how it works.
- Everything else is this site, under `docs/`. See
  [Working on these docs](/contributing/docs) for running it locally and for how the terminal
  demos are recorded.

## Commits

There is no commit message convention beyond writing what changed and why. Keep a change and its
tests in the same commit.

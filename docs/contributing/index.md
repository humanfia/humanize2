# Contributing

PRs accepted. Ask a question or discuss a substantial change first in
[issues](https://github.com/humanfia/humanize2/issues).

## Tutorials

| | |
| --- | --- |
| [Your first patch](/contributing/tutorials/first-patch) | Clone it, change one thing, both gates, a pull request |
| [Add a page to these docs](/contributing/tutorials/a-page-of-docs) | Write it, put it in the sidebar, prove the links resolve |

## Set up

```sh
git clone https://github.com/humanfia/humanize2.git
cd humanize2
uv sync
uv run pre-commit install
```

Installing the hooks once means every commit is checked before it is made.

## The two gates

| | |
| --- | --- |
| `uv run pre-commit run --all-files` | The file-hygiene hooks, the formatter, the linter and the type checker — everything that answers in seconds |
| `uv run pytest` | The tests, against [stand-in agents](/reference/flows#testing-a-flow) |
| `uv run pytest --run-agents` | Also the `agent`-marked tests, which drive the real coding agent CLIs and spend real tokens |

Both of the first two have to pass. CI runs them over every file and on each Python the package
claims, and never runs the third. `ruff` and `pyright` come from this project's own environment
rather than one pre-commit builds, so bump them with `uv lock --upgrade-package ruff` rather
than by editing a second pin.

## What the code is held to

- **`pyright` in strict mode**, over `src` and `tests`. `# type: ignore` comments are switched
  off; a suppression names a pyright rule.
- **`ruff` with every rule on**, less the ones this codebase has a written reason to be without —
  each is annotated in `pyproject.toml`.
- **Google-style docstrings.**
- **Popular, well-maintained libraries** in preference to a custom implementation.
- **Each package depends only downwards**, which is checked by a test.
  [Architecture](/contributing/architecture) has the layers and the rules that keep them.
- **Beside most packages there is a `SPEC.md`.** Do not modify one unless you were asked to —
  it is the contract, and the code is what has to move.

## Documentation

- `README.md` follows [standard-readme](https://github.com/RichardLitt/standard-readme), and
  says what humanize does and how to use it — never how it works.
- Everything else is this site, under `docs/`. See
  [Working on these docs](/contributing/docs) for running it locally and for how the terminal
  demos are recorded.

## Commits

[Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/): `fix(agents): …`,
`docs(contributing): …`, with a `!` before the colon for a breaking change. Keep a change and
its tests in the same commit.

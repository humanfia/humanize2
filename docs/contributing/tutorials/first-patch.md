# Your first patch

**Half an hour**, most of it spent on the first `uv sync` and the test suite. You will clone
humanize, change one small thing, put it through both gates, and open a pull request that CI
agrees with.

::: tip Before you start
`git` and [`uv`](https://docs.astral.sh/uv/). Nothing else — `uv sync` builds the environment,
Python included.
:::

## Clone it, and install the hooks

```sh
git clone https://github.com/humanfia/humanize2.git
cd humanize2
uv sync
uv run pre-commit install
```

`uv sync` builds `.venv` from `uv.lock`, so the `ruff` and `pyright` you run are the ones CI
runs. `pre-commit install` writes the hook that checks a commit before it is made — once, and
every commit after it is checked.

Run everything through `uv run` rather than `uvx`: `uvx` fetches whatever is newest, and the
lockfile exists so that nothing here is whatever is newest.

## Find something small

A good first patch is one screen of diff you can defend:

- an error message that says what went wrong but not what to do about it;
- a docstring that no longer describes its function;
- a `--help` line that is out of date;
- a test for a branch that has none.

[Architecture](/contributing/architecture) is the map: one directory per layer under
`src/hmz/`, each named after what it holds. Working backwards from a command instead,
[CLI](/reference/cli) names the module behind each one.

Branch, then make the change:

```sh
git switch -c fix/say-what-to-do
```

## What the change is held to

- **`pyright` in strict mode**, over `src` and `tests`. `# type: ignore` is switched off — a
  suppression names a pyright rule, or it does not exist.
- **`ruff` with `select = ["ALL"]`**, less the rules this codebase has a written reason to be
  without. Every exemption in `pyproject.toml` carries that reason beside it, and adding one
  means writing the next.
- **Google-style docstrings**, and type annotations everywhere.
- **Popular, well-maintained libraries** in preference to a custom implementation of the same
  thing.

And two rules that catch people out:

**Do not modify a `SPEC.md`.** Beside most packages there is one, and it is normative: where
these docs say what humanize *does*, a SPEC says what it *must* do, in MUST/MUST NOT terms. It
is the contract and the code is what moves. If the contract itself is wrong, propose that
separately — `AGENTS.md` says not to change one unless you were asked to.

**Each package depends only downwards.** `tests/test_layering.py` holds the table of what each
layer may import, and fails on an import that climbs, on two layers that name each other, and
on a top-level module missing from the table. [Architecture](/contributing/architecture) draws
the same table.

## Gate one: everything that answers in seconds

```sh
uv run pre-commit run --all-files
```

```
check for added large files..............................................Passed
check for case conflicts.................................................Passed
check for merge conflicts................................................Passed
check toml...............................................................Passed
check yaml...............................................................Passed
fix end of files.........................................................Passed
mixed line ending........................................................Passed
trim trailing whitespace.................................................Passed
uv lock --check..........................................................Passed
ruff check...............................................................Passed
ruff format..............................................................Passed
pyright (strict).........................................................Passed
```

Three of those behave in a way worth knowing about:

- **`ruff check` runs with `--fix`.** A run that fixes something reports `Failed` and `files
  were modified by this hook`. Read what it did, `git add` it, and run the gate again.
- **`ruff format` runs after the linter**, because a `--fix` can emit code the formatter then
  wants to reflow — lint-then-format settles in one pass where the other order takes two.
- **`pyright` checks the whole project**, not the files you touched. A type checker reads what
  a file imports, so checking only what changed checks the wrong half of the change.

`ruff` and `pyright` come from this project's own environment rather than one pre-commit
builds, since `uv.lock` already pins them. Bump one with `uv lock --upgrade-package ruff`
rather than by editing a second pin.

## Gate two: the tests

```sh
uv run pytest
```

The slow gate — minutes, not seconds. `-ra` is set in `pyproject.toml`, so the summary names
everything that was skipped, and a test that quietly stops running says so.

The `agent`-marked tests are skipped unless you ask for them:

```
SKIPPED [1] tests/agents/test_steering.py:30: needs --run-agents (drives real agents, costs tokens)
```

```sh
uv run pytest --run-agents
```

That drives the coding agent CLIs actually installed on your machine, under your own accounts,
and spends real tokens doing it. CI never runs it. Run it yourself when the change is a driver
under `agents/`, and leave it alone otherwise: the rest of the suite drives
[stand-in agents](/reference/flows#testing-a-flow), which is why it can run at all in CI.

## Commit it

[Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/), which `AGENTS.md`
requires:

```sh
git add -A
git commit -m "fix(agents): a suppressed failed turn leaves its reason on stderr"
```

`feat`, `fix`, `docs`, `refactor`, `test`, `chore` and `ci` are the types in use here; the
scope is the package or the documentation section; a `!` before the colon is a breaking change.
**A change and its tests go in one commit** — one that passes on its own is one that can be
reverted on its own.

## Open the pull request

```sh
git push -u origin fix/say-what-to-do
gh pr create --fill
```

Without push access here, `gh repo fork --remote` first and push to the fork; `gh pr create`
opens the pull request across it either way.

Two workflows then run:

| | |
| --- | --- |
| `ci.yml` | `uv lock --check`, `uv sync --frozen`, those same hooks over every file with `--show-diff-on-failure`, and `uv build` — then `pytest` on Python 3.12, 3.13 and 3.14 |
| `build-docs.yml` | Only if the change touches `docs/`: `pnpm build`, then `pnpm check:anchors` |

`--show-diff-on-failure` is why a formatting failure in CI prints the patch that would fix it.

## What you have now

A branch that passes both gates locally, and a pull request that says what it changed and why.
If the change wants explaining as well as making,
[Add a page to these docs](/contributing/tutorials/a-page-of-docs) is the other half of it. If
the next one is bigger than a screen, [Architecture](/contributing/architecture) is the shape
it has to fit.

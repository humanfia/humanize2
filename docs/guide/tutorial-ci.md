# 19 · humanize in CI

**Fifteen minutes.** A flow that runs on a schedule, opens a pull request, and leaves a trace you
can read.

::: tip Before you start
[Another machine](/guide/tutorial-remote). This tutorial uses GitHub Actions; nothing in it is
specific to GitHub beyond the YAML.
:::

## What changes when nobody is watching

| | |
| --- | --- |
| **Questions** | An agent that asks is told nobody answered and carries on. There is nothing to switch — see [Being away](/features/afk). |
| **The person** | A `HumanAgent` answers nothing, so a conversation flow does the one thing it was given and returns. |
| **Settings** | `hmz exec` reads nothing and remembers nothing. The line is the whole configuration. |
| **Stopping** | Nothing presses esc. A `while True` flow will run until the job's timeout, so give it a bound. |

## Step 1 — bound the run

The single most important thing. A Ralph loop is a `while True`, and a CI job has a bill.

Bound it three ways, and take whichever fires first:

```python
# .humanize/flows/nightly/__init__.py
"""One pass over TASK.md, bounded by rounds and by the clock."""

import time
from pathlib import Path

from hmz.agents import AgentBase
from hmz.flows import flow


@flow
def run(agents: tuple[AgentBase], task: str) -> None:
    (agent,) = agents
    deadline = time.monotonic() + 45 * 60
    for _ in range(12):                                  # rounds
        if time.monotonic() > deadline:                  # the clock
            print("out of time")
            return
        agent(task, suppress=True)
        if "- [ ]" not in Path("TASK.md").read_text():   # the finish line
            return
```

And give the job a `timeout-minutes` as the outermost bound.

## Step 2 — get a credential into the runner

humanize holds no API key. It drives the CLI you already logged in — so the question is how *that
CLI* is signed in on a machine nobody is sitting at.

Use a [provider](/features/providers), made non-interactively from a secret:

```sh
hmz providers add claude/ci -w token -s CLAUDE_CODE_OAUTH_TOKEN="$CLAUDE_TOKEN"
```

```sh
hmz providers add codex/ci -w key -s OPENAI_API_KEY="$OPENAI_API_KEY"
```

A line with nobody at a terminal has to answer everything itself; `-s` is how. Then name the
account on the agent:

```sh
hmz exec -f nightly -a claude@ci/claude-opus-5:high "$(cat TASK.md)"
```

::: tip Why a provider rather than an exported variable
A turn under a provider is run with every **other** account's variables unset. An
`ANTHROPIC_API_KEY` in the environment is a key the CLI would rather have than the one you meant,
and the turn would be taken as the wrong account with nothing looking wrong.
:::

## Step 3 — narrow what it may do

```sh
hmz exec -f nightly \
    -a cli=claude,model=claude-opus-5,effort=high,provider=ci,permission=workspace-write \
    "$(cat TASK.md)"
```

`bypass` is the default and is what a flow driving an agent unattended has always run at. On a
runner, `workspace-write` costs you nothing and bounds the blast radius to the checkout. See
[Permissions](/features/permissions).

## Step 4 — the workflow

```yaml
# .github/workflows/nightly.yml
name: nightly

on:
  schedule:
    - cron: "0 2 * * *"
  workflow_dispatch:

permissions:
  contents: write
  pull-requests: write

jobs:
  loop:
    runs-on: ubuntu-latest
    timeout-minutes: 60
    steps:
      - uses: actions/checkout@v7

      - uses: astral-sh/setup-uv@v9.0.0

      - name: Install the coding agent CLI
        run: npm install -g @anthropic-ai/claude-code

      - name: Install humanize
        run: uv tool install git+https://github.com/humanfia/humanize2.git

      - name: Sign the CLI in as an account of its own
        env:
          CLAUDE_TOKEN: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}
        run: hmz providers add claude/ci -w token -s CLAUDE_CODE_OAUTH_TOKEN="$CLAUDE_TOKEN"

      - name: Run the loop
        run: |
          hmz exec -f nightly \
            -a cli=claude,model=claude-opus-5,effort=high,provider=ci,permission=workspace-write \
            "$(cat TASK.md)"

      - name: Collect the trace
        if: always()
        run: hmz trace collect --output trace.json

      - uses: actions/upload-artifact@v5
        if: always()
        with:
          name: trace
          path: trace.json

      - uses: peter-evans/create-pull-request@v7
        with:
          branch: nightly/${{ github.run_id }}
          title: "nightly: what the loop did"
          body: "Ran `nightly` for up to 45 minutes. The trace is on the run's artifacts."
```

## Step 5 — read what happened

`hmz trace collect` with `if: always()` is the point of the whole exercise: whatever the run did —
finished, failed, or hit the timeout — the trace is on the artifacts.

`--output` is what puts it there. Left alone, a trace goes with the run it is a trace of:
`traces/` inside `~/.humanize/cycles/<workspace>/<run>/`, which is outside the checkout and named
after a run the YAML has never heard of. `--output` is for the other case — a trace as a file to
hand to somebody — and a job uploading an artifact is exactly that.

Download it and drag it into [ui.perfetto.dev](https://ui.perfetto.dev). One process per agent,
one track per row of its sessions, one slice per thing it did, with the prompts and the tool
output attached. See [tutorial 5](/guide/tutorial-trace).

The [cycle](/features/tracing#what-a-run-writes-down) says how it ended. A run is a directory, and
its record is `cycle.jsonl` inside it:

```sh
tail -1 ~/.humanize/cycles/*/*/cycle.jsonl
```

```console
{"event":"ended","at":"...","how":"done"}
```

`done`, `failed`, or `stopped`. Worth asserting on if you want the job to go red when the loop
gave up rather than finished.

## Step 6 — act on the exit status

```sh
hmz exec -f nightly -a claude@ci/claude-opus-5:high "$(cat TASK.md)" || {
    echo "::error::the loop did not finish"
    exit 1
}
```

| | |
| --- | --- |
| `0` | it did what it was asked |
| `1` | it could not — no such provider, target unreachable |
| `2` | the command line was wrong |
| `130` | interrupted |

A wrong `-a` or a miscounted flow is a `2` **before any agent runs**, which is what you want from a
scheduled job: it fails in two seconds rather than in forty minutes.

## Step 7 — make the run cheap to reproduce

Keep the line and its settings in the repository, not in the workflow:

```yaml
# ci/nightly.yaml
rounds: 12
mode: careful
```

```sh
hmz exec -f nightly -c ci/nightly.yaml -a claude@ci/claude-opus-5:high "$(cat TASK.md)"
```

Now the same line runs on your own machine. And to *look* at that setup before committing to it:

```sh
hmz -f nightly -c ci/nightly.yaml
```

opens the interface already set up, and starts nothing.

## Things that bite

**A flow that needs a feature the runner's backend has not got.** Say so in the annotation —
`Annotated[AgentBase, Goal]`, `Annotated[AgentBase, Moment.PERMISSION_REQUEST]` — and it is
refused in two seconds rather than an hour in. See [tutorial 7](/guide/tutorial-actor-reviewer).

**A flowverse that has not been fetched.** `official/...` says so rather than saying there is no
such file. Fetch it in the job, or vendor the flow into `.humanize/flows/`.

**Nothing in the working tree.** A loop that made no change should not open an empty pull request:

```sh
git diff --quiet && { echo "nothing changed"; exit 0; }
```

**A container-backed flow.** Its trajectories are in a mirror rather than in the checkout, and
they still trace: the run wrote down the ids, and its trace is gathered by those. See
[tutorial 17](/guide/tutorial-container).

## What you now know

- Bound the run three ways, and let the job timeout be the fourth.
- A provider made with `-s` is how a CLI signs in with nobody at a terminal.
- `hmz trace collect --output` with `if: always()` turns a failed run into an artifact you can
  read.
- Everything knowable up front is checked up front, which is what makes a scheduled run safe to
  leave alone.

## That is the last tutorial

For looking things up: [CLI](/reference/cli) and [TUI](/reference/tui). For a feature at a time:
[Features](/features/). For changing humanize itself:
[Architecture](/contributing/architecture).

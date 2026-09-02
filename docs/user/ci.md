# humanize in CI

Run a flow on a schedule, open a pull request with what it did, and keep a trace you can read
afterwards — an agent working through a task while nobody is watching. Only the YAML below is
specific to GitHub Actions.

## What changes when nobody is watching

| | |
| --- | --- |
| **Questions** | An agent that asks is told nobody answered and carries on. There is nothing to switch — see [Being away](/user/afk). |
| **The person** | A `Person` answers nothing, so a conversation flow does the one thing it was given and returns. |
| **Settings** | `hmz exec` reads nothing and remembers nothing. The line is the whole configuration. |
| **Stopping** | Nobody is there to stop it. A `while True` flow will run until the job's timeout, so give it a bound. |
| **The log** | A job log is not a terminal, so the run is written to stderr with no escape sequences in it. Set `FORCE_COLOR: "1"` on the job for colour a log viewer renders; `NO_COLOR` turns it off whatever else is set. |

## Watch the run from the job

The job log gets the run as it happens: which agent is working, what it said, the tools it
ran, and what each turn cost. Nothing has to be switched on.

For a step that reads the run rather than displays it, `--json` writes
[NDJSON](https://github.com/ndjson/ndjson-spec) on stdout — one object per thing an agent
says, flushed as it is said, and nothing else in the stream:

```sh
hmz exec -f nightly -a claude@ci/claude-opus-5:high --json "$(cat TASK.md)" \
    | tee run.ndjson \
    | jq -r 'select(.kind == "tool") | .text'
```

```sh
# what the whole run cost, in tokens
jq -s 'map(.spent.input // 0) | add' run.ndjson
```

The keys are in the [CLI reference](/reference/cli#watching-a-run). Without `--json`, what
each turn answered is on stdout and the run itself on stderr, so `> answer.txt` gets the
answers alone.

## Bound the run

A Ralph loop is a `while True`, and a CI job has a bill. Bound it three ways in the flow, and
take whichever fires first — this part is the [weaver's](/weaver/writing-a-flow):

```python
# .humanize/flows/nightly/__init__.py
"""One pass over TASK.md, bounded by rounds and by the clock."""

import time
from pathlib import Path

from hmz.flows import Agent, flow


@flow
def run(agents: tuple[Agent], task: str) -> None:
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

## Get a credential into the runner

humanize holds no API key. It drives the CLI you already logged in, so the question is how that
CLI is signed in on a machine nobody is sitting at. Use a [provider](/user/providers) — and make
it from Python, since the way accounts are made is a walk at the prompt and a runner has no
prompt to walk:

```python
# ci/account.py
import os

from hmz.sdk import Hmz

accounts = Hmz().accounts
accounts.make(
    "claude",
    "ci",
    accounts.way("claude", "token"),
    {"CLAUDE_CODE_OAUTH_TOKEN": os.environ["CLAUDE_TOKEN"]},
)
```

`accounts.way(cli, name)` is the way in that backend offers under that name, and
`accounts.ways(cli)` is all of them — each says which variables it has to be told, so a runner
answers them out of its secrets rather than out of a terminal. Codex is the same script with
`("codex", "ci", accounts.way("codex", "key"), {"OPENAI_API_KEY": os.environ["OPENAI_API_KEY"]})`.
Writing the account down is all it does: a way with a login command of its own would want a
browser, and a token or a key is exactly the way in that does not.

Then name the account on the agent, with `@` in front of it:

```sh
hmz exec -f nightly -a claude@ci/claude-opus-5:high "$(cat TASK.md)"
```

::: tip Why a provider rather than an exported variable
A turn under a provider is run with every **other** account's variables unset. An
`ANTHROPIC_API_KEY` in the environment is a key the CLI would rather have than the one you
meant, and the turn would be taken as the wrong account with nothing looking wrong.
:::

## Narrow what it may do

What an agent may do is declared by the flow, not by the line that runs it, so narrowing it on
a runner means writing it into the flow the runner runs:

```python
# .humanize/flows/nightly/__init__.py
class Agents(NamedTuple):
    worker: Annotated[Agent, AgentDefaults(permission="workspace-write")]
```

The line that runs it is the same line either way — an agent is a CLI, an account, a model and
an effort, and nothing on it says what the agent may do. A place that says nothing declares
`bypass`, the loosest rung, and so settles nothing. On a runner, `workspace-write` costs you
nothing and bounds the blast radius to the checkout. See [Permissions](/user/permissions).

## Write the workflow

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
        run: uv pip install --system git+https://github.com/humanfia/humanize.git

      - name: Sign the CLI in as an account of its own
        env:
          CLAUDE_TOKEN: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}
        run: python ci/account.py

      - name: Run the loop
        run: hmz exec -f nightly -a claude@ci/claude-opus-5:high "$(cat TASK.md)"

      - name: Collect the trace
        if: always()
        run: python ci/trace.py

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

## Read what happened

Gathering the trace with `if: always()` is the point of the whole exercise: it is on the
artifacts whether the run finished, failed, or hit the timeout.

At a terminal a trace is gathered from [`/epics`](/reference/tui#the-runs-that-have-already-happened),
which is a list nobody is there to read on a runner. The same thing from Python is four lines:

```python
# ci/trace.py
from hmz.sdk import Hmz

hmz = Hmz()
runs = hmz.epics.all()          # every run of this directory, oldest first
if runs:
    hmz.epics.traced(runs[-1], output="trace.json")
```

`output` is what puts it in the checkout. Left alone, a trace goes with the run it is a trace
of — `traces/` inside `~/.humanize/epics/<workspace>/<run>/`, which is outside the checkout and
named after a run the YAML has never heard of.

`traced` takes **one run**, which is why the last one is picked out rather than the directory
handed over whole: a runner that has been round this loop fifty times has fifty runs in that
directory, and a trace holding all of them is a trace of nothing anybody asked about.

Download it and drag it into [ui.perfetto.dev](https://ui.perfetto.dev): one process per agent,
one track per row of its sessions, one slice per thing it did, with the prompts and the tool
output attached. See [Tracing](/user/tracing).

The [epic](/user/tracing#what-a-run-writes-down) says how it ended — a run is a directory, and
its record is `epic.jsonl` inside it:

```sh
tail -1 ~/.humanize/epics/*/*/epic.jsonl
```

```console
{"event":"ended","at":"...","how":"done"}
```

`done`, `failed`, or `stopped`. Assert on it if you want the job to go red when the loop gave
up rather than finished.

## Act on the exit status

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

A wrong `-a` or a miscounted flow is a `2` **before any agent runs**: a scheduled job fails in
two seconds rather than in forty minutes.

## Make the run cheap to reproduce

Keep the line and its settings in the repository, not in the workflow:

```yaml
# ci/nightly.yaml
rounds: 12
mode: careful
```

```sh
hmz exec -f nightly -c ci/nightly.yaml -a claude@ci/claude-opus-5:high "$(cat TASK.md)"
```

Now the same line runs on your own machine, and the file in the repository is what both of
them were set up from. `-c` is `hmz exec`'s: at a terminal the same answers are given on the
sheet [`/flow` puts up as the flow is chosen](/reference/tui#setting-a-flow-up), and what you
answer there is what the next `hmz` in that directory opens on. The file is the version that
can be reviewed in a pull request, which is why it is the one CI reads.

## Things that bite

**A flow that needs a feature the runner's backend has not got.** The weaver says so in the
annotation: `Annotated[Agent, Goal]` or `Annotated[Agent, Moment.PERMISSION_REQUEST]`, and it
is refused up front. See [Port a project](/user/tutorials/port-a-project).

**A flowverse that has not been fetched.** `-f` says so rather than saying there is no such
file — for a name qualified by a place and for a bare one alike, humanize's own flows being
bare. Fetch it in the job, or vendor the flow into `.humanize/flows/`.

**Nothing in the working tree.** A loop that made no change should not open an empty pull
request:

```sh
git diff --quiet && { echo "nothing changed"; exit 0; }
```

**A container-backed flow.** Its trajectories are in a mirror rather than in the checkout, and
they still trace: the run wrote down the ids. See [Containers](/user/containers).

## See also

- [Being away](/user/afk)
- [Providers](/user/providers)
- [Permissions](/user/permissions)
- [Tracing](/user/tracing)
- [Port a project](/user/tutorials/port-a-project)

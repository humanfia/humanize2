# 15 · Publish a flowverse

**Ten minutes.** Put your flows in a git repository and they are offered by name, on every machine
you add them to.

::: tip Before you start
[Testing a flow](/guide/tutorial-testing-flows), and somewhere to push a git repository.
:::

## Step 1 — lay it out

A flowverse is a git repository of flows. There is **no manifest and nothing to register**:

```
my-flowverse/
├── README.md
├── review.py        →  yours/review
├── nightly.py       →  yours/nightly
└── _shared.py       →  not a flow; imported by the two above
```

| Rule | |
| --- | --- |
| one `.py` per flow | each with a function marked `@flow` |
| a file starting with `_` is not a flow | which is where shared code goes |
| the flow's docstring's first line | is what is shown beside its name |
| one file may hold several | `@flow(name="…")`, run as `<flow>:<name>` |

```python
# review.py
"""Review the current diff and write the findings to REVIEW.md."""

from hmz.agents import AgentBase
from hmz.flows import flow


@flow
def run(agents: tuple[AgentBase], task: str) -> None:
    (agent,) = agents
    agent(f"Read the diff and write what is wrong to REVIEW.md.\n\n{task}", suppress=True)
```

## Step 2 — push it

```sh
cd my-flowverse
git init -q && git add -A && git commit -qm "two flows"
git remote add origin git@github.com:you/my-flowverse.git
git push -u origin main
```

## Step 3 — add it

In `hmz`:

```
/flow
```

**ctrl+n**. It asks for a URL or an `owner/repo`, and a name to keep it under if the repository's
own name is not the one you want:

```
you/my-flowverse
yours
```

It is cloned into `~/.humanize/flowverses/yours/`, and every flow in it is then offered as
`yours/<flow>`.

| Key in `/flow` | |
| --- | --- |
| **←** **→** | walk the places flows come from, a tab apiece |
| **ctrl+n** | add one |
| **ctrl+r** | fetch the open one again, or for the first time |
| **ctrl+x** | take an added one away, flows and all |

`builtin` and `official` are always there and cannot be taken away.

## Step 4 — run one

```sh
hmz exec -f yours/review -a claude/claude-opus-4-8:high "the payments module"
```

`<flowverse>/<flow>` is **the one spelling nothing can stand in for**. A bare name is looked for
nearest first — this project's `.humanize/flows`, then yours, then everything else — so a local
flow can shadow a bare name but never a qualified one.

## Step 5 — use it as a library

`calls` takes what `-f` takes, so your flowverse is importable by name from any other flow:

```python
from hmz.runner import calls

calls("yours/review")(agents, task)
```

That is the reason to publish two small flows rather than one large one.

## Step 6 — keep it up to date

**ctrl+r** in `/flow` fetches the open flowverse again. It runs off the interface's own loop — the
screen keeps drawing while it clones — and what became of it is said under the list rather than
thrown at you.

A flow from a flowverse that has not been fetched says so, rather than saying there is no such
file: the name is right, the download has not happened.

## What to put in the README

Whoever adds your flowverse is trusting it with their machine. Earn it:

- **What each flow drives** — how many agents, and what each is for.
- **Which backends it needs.** A flow that hangs a `PERMISSION_REQUEST` hook needs Claude Code or
  Codex; one built on `pursue` needs a backend with a goal feature.
- **What it writes.** Files, branches, commits, pushes.
- **The `hmz exec` line that starts it**, verbatim. Each flow humanize ships names its own in its
  docstring; do the same.

## The one thing to be honest about

::: danger A flow is a Python file, and reading one means running it
Listing what a flowverse holds **imports every file in it**. Somebody adding yours is trusting
that repository with their machine, exactly as installing a package is.

So: no side effects at import time, nothing that reaches the network as the module loads, and no
`_shared.py` that does anything on import beyond defining things. Whatever a flow does as it is
imported is the flow's own business and fails as it would anywhere — which means it fails for
somebody who was only browsing the list.
:::

## Checking it before anybody else does

```python
from hmz.runner import drives, wanted

drives("yours/review")     # loads it exactly as `-f` would
wanted("yours/review")     # what somebody choosing the agents will be asked
```

Run that in the repository's own CI and a flow that stopped loading is a red build.

## What you now know

- A flowverse is a git repository, one `.py` per flow, `_`-prefixed files ignored.
- **ctrl+n** / **ctrl+r** / **ctrl+x** in `/flow` add, fetch and remove.
- `<flowverse>/<flow>` is the unshadowable spelling, and `calls` takes it too.
- Import-time side effects run for anyone who lists your flowverse.

## Next

[Two accounts of one CLI](/guide/tutorial-providers).

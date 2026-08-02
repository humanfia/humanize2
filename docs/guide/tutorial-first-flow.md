# 6 · Write your first flow

**Fifteen minutes.** A Python file with a loop in it, run by name from the command line and
offered in the interface.

::: tip Before you start
[Read the run back](/guide/tutorial-trace), and a project to work in.
:::

## Step 1 — write it

```sh
mkdir -p .humanize/flows
```

```python
# .humanize/flows/twice.py
"""Two passes: do the work, then read it back and fix what is wrong."""

from hmz.agents import AgentBase
from hmz.flows import flow


@flow
def run(agents: tuple[AgentBase], task: str) -> None:
    (agent,) = agents
    session = agent.new()
    session(task)
    session("Now review what you just did, and fix anything that is wrong.")
```

## Step 2 — run it

```sh
hmz exec -f twice -a claude/claude-opus-4-8:high "add a --dry-run flag to calc.py"
```

It is offered in the interface too — `/flow` lists the flows in `.humanize/flows` here, in
`~/.humanize/flows`, the ones humanize ships, and everything in every
[flowverse](/features/flowverses) fetched here, a tab apiece.

## The contract, in three rules

**1. A function marked `@flow`, taking the agents and the task.** What it is *called* is up to
you — the mark is what makes it a flow, not the name.

**2. The annotation on `agents` says how many the flow drives.** A fixed-length tuple, or a
`NamedTuple` of them.

```python
tuple[AgentBase]                 # one
tuple[AgentBase, AgentBase]      # two
tuple[AgentBase, ...]            # refused — that is not an answer
```

Its length is the one thing about a flow that the command line starting it cannot otherwise know,
so it is checked before the first turn:

```console
$ hmz exec -f twice -a claude/claude-opus-5:max -a codex/gpt-5.6-sol:high "…"
hmz exec: error: twice: the flow drives 1 agents, 2 given
```

**3. That annotation has to be readable at runtime.** Import `AgentBase` normally — **not** under
`if TYPE_CHECKING`. A count nothing can read back is not one a command line can be held to.

::: warning The most common first mistake
```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:                      # [!code error]
    from hmz.agents import AgentBase   # [!code error]
```
```console
hmz exec: error: twice: the flow's agents cannot be read here (name 'AgentBase' is not
defined) -- import what the annotation names at runtime, so the count it states can be checked
```
:::

## Step 3 — the one choice that matters

```python
agent("do the task")          # a session of its own, dropped straight after: nothing carries over
session = agent.new()
session("do the task")        # opens it
session("keep going")         # resumes it, the first turn still in context
```

`twice.py` above holds a session, so the second turn knows what the first one did. Change it to:

```python
@flow
def run(agents: tuple[AgentBase], task: str) -> None:
    (agent,) = agents
    agent(task)
    agent("Now review what you just did, and fix anything that is wrong.")
```

and the second turn arrives with no idea what "what you just did" refers to — it has to find out
from the repository. Sometimes that is exactly what you want, which is what a
[Ralph loop](/guide/tutorial-ralph-loop) is.

## Step 4 — make it a loop that survives a bad turn

A turn that fails raises `subprocess.CalledProcessError` — whatever it was actually run through,
so a flow catches turns rather than transports. In a loop, that would end the run on the first
hiccup.

`suppress=True` is `|| true` for a turn:

```python
import time

@flow
def run(agents: tuple[AgentBase], task: str) -> None:
    (agent,) = agents
    while True:
        agent(task, suppress=True)     # "" if it failed, and the loop goes round again
        time.sleep(5)
```

It catches a turn that failed and **nothing else** — not an agent that has been
[stopped](/features/stopping), and not a backend with no goal feature, which is a flow to correct
rather than a turn to retry.

## Step 5 — give it a finish line

A `while True` is only useful if something ends it. It is ordinary Python, so read the repository:

```python
import subprocess
from pathlib import Path

def green() -> bool:
    return subprocess.run(["python", "-m", "pytest", "-q"], check=False).returncode == 0

@flow
def run(agents: tuple[AgentBase], task: str) -> None:
    (agent,) = agents
    for _ in range(20):
        agent(task, suppress=True)
        if green() and "- [ ]" not in Path("TASK.md").read_text():
            return
```

There is nothing special to do here. A flow may branch, sleep, read files, shell out and give up,
because it is just a function.

## Step 6 — say what the flow is

The docstring's first line is what is shown beside the flow's name where flows are listed. Write
one:

```python
"""Two passes: do the work, then read it back and fix what is wrong."""
```

## Where a flow lives, and what it is called

| Lives at | Called |
| --- | --- |
| `.humanize/flows/twice.py` | `twice` in this project, or by path |
| `~/.humanize/flows/twice.py` | `twice` in every project |
| a [flowverse](/features/flowverses) | `<flowverse>/twice` |
| anywhere else | its path: `-f ./flows/twice.py` |

A name is looked for **nearest first**, so a flow of yours may stand in for one of humanize's by
taking its name. A file whose name starts with `_` is not a flow.

## Check your work

```python
from hmz.runner import drives

drives("twice")       # the names of the agents it declares
```

## What you now know

- `@flow`, a readable `agents` annotation, and that is the contract.
- `agent(...)` forgets; `agent.new()` remembers.
- `suppress=True` is the loop's `|| true`, and does not catch a stop.
- A flow is ordinary Python and may do anything Python can.

## Next

[Actor and reviewer](/guide/tutorial-actor-reviewer) — two agents, and giving them names.

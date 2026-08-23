# Writing a flow

A **flow** is a directory whose `__init__.py` holds a function marked `@flow`, and that
function drives the agents. Write one when you want the same agents run the same way again and
again, rather than typed out afresh each time.

## Write the flow

Create the directory, then write the flow in it.

```sh
mkdir -p .humanize/flows/twice
```

```python
# .humanize/flows/twice/__init__.py
"""Two passes: do the work, then read it back and fix what is wrong."""

from hmz.flows import Agent, flow


@flow
def run(agents: tuple[Agent], task: str) -> None:
    (agent,) = agents
    session = agent.new()
    session(task)
    session("Now review what you just did, and fix anything that is wrong.")
```

## Run the flow

Run the flow by name from the command line.

```sh
hmz exec -f twice -a claude/claude-opus-4-8:high "add a --dry-run flag to calc.py"
```

humanize also offers the flow in the interface. `/flow` lists the flows humanize ships,
everything in every [**flowverse**](/weaver/flowverses) fetched here, and your own — the ones in
`.humanize/flows` here as `local`, and the ones in `~/.humanize/flows` as `user`. A flowverse is
a place where flows live, and your own two directories are places like any other. Each place has
**←** and **→** to step between them.

## The contract, in three rules

**1. A function marked `@flow`, taking the agents and the task.** You can call it whatever you
like. The `@flow` mark is what makes it a flow, not the name.

**2. The annotation on `agents` says how many the flow drives.** It is a fixed-length tuple, or
a `NamedTuple` of them.

```python
tuple[Agent]             # one
tuple[Agent, Agent]      # two
tuple[Agent, ...]        # refused — that is not an answer
```

The command line that starts the flow cannot know its length any other way, so humanize checks
it before the first turn:

```console
$ hmz exec -f twice -a claude/claude-opus-5:max -a codex/gpt-5.6-sol:high "…"
hmz exec: error: twice: the flow drives 1 agents, 2 given
```

**3. The annotation must be readable at runtime.** Import `Agent` normally, and **not**
under `if TYPE_CHECKING`. A count that nothing can read back is not one a command line can be
held to.

::: warning The most common first mistake
```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:                      # [!code error]
    from hmz.flows import Agent   # [!code error]
```
```console
hmz exec: error: twice: the flow's agents cannot be read here (name 'Agent' is not
defined) -- import what the annotation names at runtime, so the count it states can be checked
```
:::

## Choose what the next turn remembers

Choose whether the second turn should remember the first one.

```python
agent("do the task")          # a session of its own, dropped straight after: nothing carries over
session = agent.new()
session("do the task")        # opens it
session("keep going")         # resumes it, the first turn still in context
```

A **turn** is one request to the agent. A **session** keeps its turns in context, so the second
turn knows what the first one did. The flow you wrote holds a session. Change it to:

```python
@flow
def run(agents: tuple[Agent], task: str) -> None:
    (agent,) = agents
    agent(task)
    agent("Now review what you just did, and fix anything that is wrong.")
```

The second turn arrives with no idea what "what you just did" refers to. It has to find out
from the repository. Sometimes that is exactly what you want, which is what a [Ralph
loop](/weaver/loops) is.

## Make the loop survive a bad turn

A turn that fails raises `subprocess.CalledProcessError`. This happens whatever it was actually
run through, so a flow catches turns rather than transports. In a loop, that raise would end
the run on the first hiccup.

`suppress=True` is `|| true` for a turn:

```python
import time

@flow
def run(agents: tuple[Agent], task: str) -> None:
    (agent,) = agents
    while True:
        agent(task, suppress=True)     # "" if it failed, and the loop goes round again
        time.sleep(5)
```

It catches a turn that failed and **nothing else**. It does not catch an agent that has been
[stopped](/user/stopping), and it does not catch a backend with no goal feature. A backend
with no goal feature is a flow to correct rather than a turn to retry.

## Give the loop a finish line

A `while True` is only useful if something ends it. The flow is ordinary Python, so read the
repository:

```python
import subprocess
from pathlib import Path

def green() -> bool:
    return subprocess.run(["python", "-m", "pytest", "-q"], check=False).returncode == 0

@flow
def run(agents: tuple[Agent], task: str) -> None:
    (agent,) = agents
    for _ in range(20):
        agent(task, suppress=True)
        if green() and "- [ ]" not in Path("TASK.md").read_text():
            return
```

There is nothing special to do here. A flow is just a function, so it may branch, sleep, read
files, shell out and give up.

## Say what the flow is

The first line of the docstring is shown beside the flow's name where flows are listed. Write
one:

```python
"""Two passes: do the work, then read it back and fix what is wrong."""
```

## Where a flow lives, and what it is called

| Lives at | Called |
| --- | --- |
| `.humanize/flows/twice/__init__.py` | `twice` in this project, or `local/twice` |
| `~/.humanize/flows/twice/__init__.py` | `twice` in every project, or `user/twice` |
| a [flowverse](/weaver/flowverses) | `<flowverse>/twice` |
| anywhere else | its path: `-f ./flows/twice` |

A name is looked for **nearest first**, so a flow of yours may stand in for one of humanize's
by taking its name. A file whose name starts with `_` is not a flow.

## Check your work

Check the flow itself, before anything runs it: a static reading that executes nothing, then
the flow loaded in a subprocess held to a clock. Driving it with stubs — including the world
where the reviewer never says the work is done — is `proved()`, a call of your own. See
[Checking a flow](/weaver/checking-flows).

```sh
hmz check local/twice
```

And check which agents the flow declares.

```python
from hmz.flows import drives

drives("twice")       # the names of the agents it declares
```

## A flow whose shape is known before it runs

Everything above is a flow: a Python file that may branch any way it likes, and whose shape is
whatever it does. Where the shape is known in advance — a pipeline of phases, a review loop
meant to run for a week — an [atlas](/weaver/atlas) is the stricter bargain. Its body is a
declaration rather than a program, compiled into a graph before the first turn, so it is
checked whole up front and a run of one is picked up node by node rather than started again.

## See also

- [An atlas](/weaver/atlas)
- [Read the run back](/user/tracing)
- [Flowverses](/weaver/flowverses)
- [Loops](/weaver/loops)
- [Stopping](/user/stopping)
- [Port a project](/user/tutorials/port-a-project)

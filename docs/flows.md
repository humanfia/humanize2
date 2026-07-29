# Flows

A flow is a Python file with a `run(agents, task)` in it. It is the loop: which agent is asked
what, in what order, and when to stop.

It is ordinary Python. There is no DSL, no graph to declare, no state machine — a flow may
branch, sleep, read files, shell out, and give up, because it is just a function.

## Table of Contents

- [The contract](#the-contract)
- [How many agents, and what they are for](#how-many-agents-and-what-they-are-for)
- [The person at the prompt](#the-person-at-the-prompt)
- [Running one](#running-one)
- [Where flows live](#where-flows-live)
- [The flows humanize comes with](#the-flows-humanize-comes-with)
- [Patterns](#patterns)
- [Building the agents yourself](#building-the-agents-yourself)
- [Stopping](#stopping)
- [Testing a flow](#testing-a-flow)

## The contract

Three rules, and that is the whole of it.

**1. A function called `run`, taking the agents and the task.**

```python
def run(agents: tuple[AgentBase], task: str) -> None:
    ...
```

**2. The annotation on `agents` says how many the flow drives.** A fixed-length tuple, or a
`NamedTuple` of them. `tuple[AgentBase, ...]` is any number, which is no answer to the
question, and is refused.

**3. That annotation has to be readable at runtime.** Import `AgentBase` normally, not under
`if TYPE_CHECKING` — a count nothing can read back is not one a command line can be held to.

```python
"""Two passes over the same task."""

from humanize.agents import AgentBase


def run(agents: tuple[AgentBase], task: str) -> None:
    (agent,) = agents
    session = agent.new()
    session(task)
    session("Now review what you just did, and fix anything that is wrong.")
```

Anything else the file does as it is imported is the flow's own business and fails as it would
anywhere — a flow that reads a prompt file beside it and does not find it is not reported as a
command line to correct.

## How many agents, and what they are for

The count is checked before the first turn:

```console
$ hmz exec -f rlar -a claude/claude-opus-4-8:high "fix the build"
hmz exec: error: /.../rlar.py: run() drives 2 agents, 1 given
```

which is what keeps a two-agent flow started with one from failing on an unpacking hours into a
loop, with a turn's work already behind it.

A `NamedTuple` says what each agent is *for* as well as how many there are:

```python
from typing import NamedTuple

from humanize.agents import AgentBase


class Agents(NamedTuple):
    """The two this drives: one that works in a session, and one that arrives fresh."""

    actor: AgentBase
    reviewer: AgentBase


def run(agents: Agents, task: str) -> None:
    working = agents.actor.new()
    ...
```

The names are not only for the flow's own readability. Everything that has to talk about an
agent uses them:

- `/agents` in the interface asks what *the reviewer* runs, rather than what agent 2 of 2 runs.
- The line above the prompt says `reviewer · claude/claude-opus-4-8:high`.
- A [trace](tracing.md) groups that agent's sessions under `reviewer`.
- What each agent was set to run is [remembered per role](tui.md#what-it-remembers), so a flow
  that grows an agent in the middle does not hand the reviewer's model to the builder.

An agent that was named where it was made keeps that name; one that was not takes the name the
flow gives it, before anything is written down about the run.

## The person at the prompt

A place annotated `HumanAgent` is you, driven as an agent — which is what you are to a flow.

```python
from typing import NamedTuple

from humanize.agents import AgentBase, HumanAgent


class Chat(NamedTuple):
    assistant: AgentBase
    human: HumanAgent


def run(agents: Chat, task: str) -> None:
    conversation = agents.assistant.new()
    said = task
    while said:
        answered = conversation(said, suppress=True)
        said = agents.human(answered)
```

Saying something to it is asking what to say next; what it answers with is what was typed.

**Nobody is asked what the person runs**, so a `HumanAgent` is not one of the agents `-a` names
— the flow above is started with one `-a` and drives two. Run from a command line, where nobody
is at a prompt, it answers with nothing, so the loop ends and the flow does the one thing it
was given.

## Running one

```sh
hmz exec -f <flow> -a <cli>/<model>:<effort> [-a ...] <task>
```

One `-a` for each agent the flow drives, in the order it takes them. Full syntax in the
[CLI reference](cli.md#hmz-exec).

In the [interface](tui.md), shift+tab steps through the flows and `/flow` picks one by name.
Picking one stops whatever was running — a flow is chosen in order to be run.

## Where flows live

`-f` takes a name or a path. A name is looked for in three places, nearest first:

| | |
| --- | --- |
| `.humanize/flows/*.py` | this project's own |
| `~/.humanize/flows/*.py` | yours, in every project |
| — | the ones humanize came with |

Nearest wins, so a flow of your own may stand in for one of humanize's by taking its name — a
`.humanize/flows/rlar.py` is what `-f rlar` runs *in that project*. A name appears once in the
list of flows: the nearest one answering to it is the one that runs, so the ones it stands in
for are not offered as if they still did.

Anything with a slash or an extension in it is a path, taken as given. A file whose name starts
with `_` is not a flow.

```sh
mkdir -p .humanize/flows && cp my_loop.py .humanize/flows/
hmz exec -f my_loop -a claude/claude-opus-4-8:high "fix the build"
hmz exec -f ./somewhere/else.py -a claude/claude-opus-4-8:high "fix the build"
```

## The flows humanize comes with

Six of these are flowbench's loops, written against this API. Each names the `hmz exec` line
that starts it in its own docstring.

| Flow | Agents | What it does |
| --- | --- | --- |
| `chat` | 1 + you | One agent, one session, and every line typed between turns is a turn of it. Talking to a coding agent with no loop around it. This is what the interface opens on. |
| `ralph_loop` | 1 | A fresh session every turn, so nothing carries over: the agent starts from the task and the repository each time. |
| `stateful_ralph` | 1 | One session, held for the whole run, re-sent the task every turn. |
| `continue_loop` | 1 | Sends the task once, then keeps nudging `continue`. Until a turn lands the task is sent again — `continue` on its own would open a session that never saw it. |
| `goal` | 1 | Ralph, with the task set as the agent's [own goal](agents.md#goals). The loop only starts it over when it stopped without having met it. |
| `flame_chase` | 2 | Two agents take turns on the same task. Each reads the repository, not a history. |
| `rlar` | `actor`, `reviewer` | The actor works in one session and must remember; a fresh reviewer reads its work and must not. Nothing between them parses anything — the review *is* the actor's next prompt, word for word. |
| `humanize1` | `builder`, `reviewer` | RLCR: an idea is opened, planned against review, then built against it. Anchored to the commit the plan is committed in; every review reads what came after it. Run it in a git repository. |

`humanize1` is [PolyArch/humanize](https://github.com/PolyArch/humanize) as one unattended run.
Read [Security](../README.md#security) before starting any of them.

Their source is the best documentation of this API there is — `src/humanize/flows/` in a
checkout, or wherever `pip` put it.

## Patterns

### Ralph: forget every turn

```python
while True:
    agent(task, suppress=True)
    time.sleep(5)
```

`agent(...)` opens a session of its own and drops it. That is the whole of a Ralph loop.

### Stateful: remember everything

```python
session = agent.new()
while True:
    session(task, suppress=True)
```

Same agent, opposite behaviour. The flow decides, not the agent.

### Actor and reviewer

The reviewer must arrive fresh, so it gets a new session each round while the actor keeps one:

```python
def run(agents: Agents, task: str) -> None:
    working = agents.actor.new()
    said = working(task, suppress=True)
    while True:
        review = agents.reviewer(REVIEW_PROMPT, suppress=True)
        said = working(review, suppress=True)
```

Give the two the same model and effort and they are still two agents — which is the point: a
trace reads the actor's session and the reviewer's rounds as two.

### Catching turns without wrapping every line

A flow is a loop, and a loop that catches its own turns is a `try` around every line of it. So
`|| true` is a word on the call rather than a block around it:

```python
agent(task, suppress=True)   # a turn that failed answers with nothing; the loop goes round
```

It catches a turn that failed and nothing else — not an agent that was [stopped](#stopping),
and not a backend that has no goal feature, which is a flow to correct.

### Reading the repository between turns

There is nothing special to do. It is Python:

```python
import subprocess


def head() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False
    ).stdout


before = head()
agent(task, suppress=True)
if head() == before:
    ...  # the turn changed nothing
```

## Building the agents yourself

A name, and [where the work lands](machines.md), are settings of the *agent* rather than of the
flow, so `-a` does not reach them. A flow that needs one is handed agents built in Python:

```python
from humanize.agents import ClaudeCodeAgent, ClaudeCodeAgentConfig
from humanize.runner import Runner

config = ClaudeCodeAgentConfig(model="claude-opus-4-8", effort="high")
agents = [
    ClaudeCodeAgent(config, name="actor"),
    ClaudeCodeAgent(config, name="reviewer"),
]

Runner("rlar", agents).run("fix the build")
```

`Runner` takes the same flow names and paths `-f` does, checks the count the same way, and
writes the same [cycle](tracing.md#cycles). See [Agents](agents.md) for what those objects can
do.

## Stopping

A flow ends when `run` returns — most of the built-in ones never do, and are ended from
outside:

- **esc**, or ctrl+c with nothing half-typed, in the interface.
- **ctrl+c** on a `hmz exec` command line.
- **`agent.stop()`** from anywhere.

Every agent is told to take no further turn. The turn under way is closed out, and the next
call into that agent raises `Stopped` — which `suppress=True` deliberately does not catch,
because a loop that carried on past it would never end. Let it propagate; the
[cycle](tracing.md#cycles) then records the run as stopped by hand rather than as one that
finished.

What the turn was doing is left where it got to. A stop that waited for a turn would not read
as a stop — a model can think for minutes.

## Testing a flow

A flow is a function, so drive it with something that is not a coding agent:

```python
from collections.abc import Iterator

from humanize.agents import AgentBase, AgentConfig, Event, SessionBase


class FakeSession(SessionBase):
    def _stream(self, prompt: str) -> Iterator[Event]:
        yield Event(kind="result", text=f"answered: {prompt}")


class FakeAgent(AgentBase):
    def new(self) -> FakeSession:
        return FakeSession(self)


run((FakeAgent(AgentConfig(model="m", effort="high")),), "the task")
```

humanize's own suite does this — `tests/stubs.py` has a shell-backed agent that runs the prompt
as a shell script, so a test spells out exactly what the agent it stands in for would do.

To check only that a flow *loads* and declares what it should:

```python
from humanize.runner import drives

assert drives("my_loop") == ("actor", "reviewer")
```

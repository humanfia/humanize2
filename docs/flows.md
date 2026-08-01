# Flows

A flow is a Python file with a `run(agents, task)` in it. It is the loop: which agent is asked
what, in what order, and when to stop.

It is ordinary Python. There is no DSL, no graph to declare, no state machine — a flow may
branch, sleep, read files, shell out, and give up, because it is just a function.

## Table of Contents

- [The contract](#the-contract)
- [A flow that waits for more than one thing](#a-flow-that-waits-for-more-than-one-thing)
- [How many agents, and what they are for](#how-many-agents-and-what-they-are-for)
- [Settings of the flow's own](#settings-of-the-flows-own)
- [Asking for an agent that can do something](#asking-for-an-agent-that-can-do-something)
- [Where each agent works](#where-each-agent-works)
- [Hooks in a flow](#hooks-in-a-flow)
- [The person at the prompt](#the-person-at-the-prompt)
- [Running one](#running-one)
- [Several flows in one file](#several-flows-in-one-file)
- [Where flows live](#where-flows-live)
- [Flowverses](#flowverses)
- [The flows humanize ships](#the-flows-humanize-ships)
- [The official flowverse](#the-official-flowverse)
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

`run` may also be `async def`. Everything else on this page is the same either way.

One file may hold [several flows](#several-flows-in-one-file), each marked with `@flow` and each
run as `<flow>:<name>`. `run` is the one the file holds under its own name.

## A flow that waits for more than one thing

A loop that has more than one turn going at a time has to be able to wait for several things at
once, so a flow may be written as a coroutine:

```python
import asyncio

from humanize.agents import AgentBase


async def run(agents: tuple[AgentBase, AgentBase], task: str) -> None:
    while True:
        acted, reviewed = await asyncio.gather(
            agents[0].aturn(task, suppress=True),
            agents[1].aturn(f"Read the repository and say what is wrong: {task}", suppress=True),
        )
```

Nothing about starting it changes: `hmz exec -f …` and the interface run a coroutine flow the
same way they run any other, on a loop of the flow's own, and the run is over when `run`
returns. The count of its agents, the settings it declares, the [cycle](tracing.md#cycles) it is
written down as and the way it is [stopped](#stopping) are all exactly as they are for a flow
that is a plain function.

Every call that runs a turn has an awaited twin — `agent.aturn`, `session.aturn`,
`agent.apursue` — and `agent.abatch` runs a whole fan-out of them. See
[Agents › Awaiting a turn](agents.md#awaiting-a-turn).

```python
async def run(agents: tuple[AgentBase], task: str) -> None:
    (agent,) = agents
    # One session per shard, all of them at once, answers in the order they were asked for.
    said = await agent.abatch([f"{task}\n\nShard {at} of 200." for at in range(200)])
```

Two rules of thumb: turns of *one* session are still a sequence, whoever awaits them — a
conversation is a conversation — and a flow that awaits nothing is a flow that runs one turn at
a time, which is what most of them want.

Write the flow as a plain `def run` unless it has something to wait for. Both are flows; neither
is the newer one.

## How many agents, and what they are for

The count is checked before the first turn:

```console
$ hmz exec -f official/rlar -a claude/claude-opus-4-8:high "fix the build"
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

## Settings of the flow's own

A flow that has settings says so by taking a third argument, annotated with a
[pydantic](https://docs.pydantic.dev/) model or `None`:

```python
from typing import Literal

from pydantic import BaseModel, Field

from humanize.agents import AgentBase


class Config(BaseModel):
    """What this flow takes."""

    rounds: int = Field(default=3, ge=1, le=9, description="how many times round")
    mode: Literal["fast", "slow"] = Field(default="fast", description="which way")


def run(agents: tuple[AgentBase], task: str, config: Config | None = None) -> None:
    setting = config or Config()
    ...
```

That is the whole of it. The model is what asks: the fields are the questions, their types say
how each one is answered, `description` is the line shown beside it, and whatever the model
refuses is what the flow will not run.

- `/config` in the interface is that model with a cursor on it, and `/flow` walks through it
  between choosing the flow and choosing its agents. See [TUI › Setting a flow
  up](tui.md#setting-a-flow-up).
- What you set is [remembered per flow](tui.md#what-it-remembers), so a flow of twenty
  settings is not one to answer again every morning.
- `None` means nobody set it up, and is what the flow gets from `hmz exec`. Fall back to the
  model's own defaults, as above, and the flow runs the same either way.

A flow with many settings groups them, so the sheet has parts rather than one long list:

```python
    gen_idea: bool = Field(
        default=True,
        description="open the idea into a repo-grounded draft",
        json_schema_extra={"section": "gen-idea  ·  open the idea into a draft"},
    )
```

Combinations the flow cannot run belong in the model, not in `run`:

```python
    @model_validator(mode="after")
    def _settles(self) -> "Config":
        if self.fast and self.careful:
            raise ValueError("fast and careful do not go together")
        return self
```

which is refused where it was typed rather than an hour into the run.

Two rules, both for the same reason the agents annotation has them: the model has to be
readable at runtime — import `pydantic` normally, not under `if TYPE_CHECKING` — and it is
read by running the file, so the class the interface asked with is not the same object as the
class the run is handed. What is carried across is the fields, which `Runner` reads back into
the model the flow has just declared. A flow handed a config of another model is refused
before its first turn, as a flow handed the wrong number of agents is.

## Asking for an agent that can do something

Not every backend runs every [moment](agents.md#hooks). A flow that hangs a hook on one only
some of them run says so where it declares the place, by writing the moment beside the type:

```python
from typing import Annotated, NamedTuple

from humanize.agents import AgentBase, Moment


class Agents(NamedTuple):
    """The two this drives: one that is gated, and one that reads its work."""

    builder: Annotated[AgentBase, Moment.PERMISSION_REQUEST]
    reviewer: AgentBase
```

`Annotated` is the whole of it: the type is still `AgentBase`, so the flow reads and type-checks
exactly as it did, and what is written beside it is what the place asks of whoever fills it.
Several moments are several arguments.

It is checked before the first turn, for the same reason the count is:

```console
$ hmz exec -f gated -a codex/gpt-5.6-sol:high -a codex/gpt-5.6-sol:high "fix the build"
hmz exec: error: /.../gated.py: builder has to run PermissionRequest, which codex does not
```

and the interface's `/agents` offers only the CLIs that would work for that place, so it cannot
be chosen wrong there at all.

## Where each agent works

Where an agent's turns land is declared the same way, and by the same file: the flow writes it
beside the type.

```python
from typing import Annotated, NamedTuple

from humanize.agents import AgentBase, Isolated, Remote


class Agents(NamedTuple):
    """The three this drives, and the three places they work."""

    builder: Annotated[AgentBase, Remote]                  # may be pointed at a machine
    tester: Annotated[AgentBase, Isolated("python:3.12")]  # a container of the flow's own
    reviewer: AgentBase                                    # here, and nowhere else
```

| Beside the type | Where that agent works |
| --- | --- |
| *(nothing)* | this machine, and it **cannot** be pointed anywhere else |
| `Remote` | wherever whoever chose the agent pointed it — the only kind of place that may be pointed at all — and here where nobody did |
| `Isolated("<image>")` | a [container of that image](machines.md#isolatedpython312), which nobody configures and nobody is asked about |

**This is a change.** A machine used to be a setting of the agent that anything could reach, so
any agent of any flow could be pointed anywhere. It is still a setting of the agent — that is how
a `Remote` place is filled — but a flow is written for one shape of work, and one whose agents
read *this* project cannot have one of them reading somebody else's. So the flow says which of
them may be sent elsewhere, and nothing above it can say otherwise.

Both refusals land before the first turn, for the reason the count does:

```text
/.../flow.py: reviewer runs on this machine -- this flow does not say it works anywhere else, so it cannot be pointed at one
/.../flow.py: tester works in a container of this flow's own, so there is nothing to point it at
```

`hmz exec` prints either as `hmz exec: error: …` and runs nothing; the interface shows it as a red
line and starts nothing. No `-a` spells a machine, so what runs into these is an agent
[built in Python](#building-the-agents-yourself) or one moved on the interface's `/agents` sheet.

A place may say more than one thing — `Annotated[AgentBase, Moment.STOP, Remote]` is a place that
must run that moment *and* may be moved. Several arguments, read one by one, in any order.

What the flow declared is readable without driving it:

```python
from humanize.runner import wanted

wanted("official/rlar")   # one Place per agent somebody has to choose: .name, .moments, .where
```

`where` is `None`, the `Remote` class itself, or the `Isolated` the flow wrote — which is how
whatever chooses the agents knows which of them it may offer a machine for. What each answer
comes to, and what a container of the flow's own actually is, is in
[Machines](machines.md#which-agents-may-be-moved-at-all).

## Hooks in a flow

A flow holds the agents, so it can hang a hook on one and take it down again as it goes. This
is a Ralph loop that will not let a turn stop while the task file still says there is work:

```python
from pathlib import Path

from humanize.agents import AgentBase, Moment, Occasion, Verdict


def run(agents: tuple[AgentBase], task: str) -> None:
    (agent,) = agents

    def unfinished(occasion: Occasion) -> Verdict | None:
        if occasion.again < 5 and "- [ ]" in Path("TASK.md").read_text():
            return Verdict(refused=True, because="TASK.md still has unticked boxes.")
        return None

    with agent.hooks.on(Moment.STOP, unfinished):
        while "- [ ]" in Path("TASK.md").read_text():
            agent(task, suppress=True)
```

Everything a hook can do is in [Agents › Hooks](agents.md#hooks). Two things worth saying here:

- Hooks are on the **agent**, not the session, so one covers every session that agent opens —
  including the fresh one a Ralph loop makes each turn.
- A hook runs on the turn's own thread. One that takes a while is a turn that takes a while.

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

In the [interface](tui.md), `/flow` picks one by name — tab and shift+tab are for stepping
between the agents of the flow that is running.
Picking one stops whatever was running — a flow is chosen in order to be run.

## Several flows in one file

Three phases of one thing are one thing to write and three to run. Mark each entry point, and
each is a flow of its own, called `<flow>:<name>`:

```python
"""Three phases of one thing."""

from humanize.flows import flow


@flow
def gen_idea(agents: Drafting, task: str, config: Idea | None = None) -> None:
    """Opens a loose idea into a repo-grounded draft."""


@flow
def gen_plan(agents: Planning, task: str, config: Plan | None = None) -> None:
    """Turns that draft into a plan both sides have converged on."""
```

```sh
hmz exec -f official/humanize1:gen-idea -a claude/claude-opus-5:max "add undo to the editor"
hmz exec -f official/humanize1:gen-plan -a claude/claude-opus-5:max -a codex/gpt-5.6-sol:max ""
```

The name is the function's own with its underscores turned into dashes; `@flow(name="build")`
says otherwise, and `@flow(about="…")` says what it does where flows are listed, which is
otherwise the first line of its docstring.

Each of them declares its own agents and its own settings, so `/agents` asks two questions
rather than five and `/config` shows one phase's flags rather than three phases' at once. What
passes between them is whatever they write — a file, usually.

`@flow` marks; it does not wrap. The function is called exactly as it was, and a file with a
plain `run` in it needs none of this: that is the flow the file holds under its own name, and is
what every flow was.

## Where flows live

`-f` takes a name or a path. A name is looked for nearest first:

| | |
| --- | --- |
| `.humanize/flows/*.py` | this project's own |
| `~/.humanize/flows/*.py` | yours, in every project |
| — | the ones humanize ships, and every [flowverse](#flowverses) there is |

Nearest wins, so a flow of your own may stand in for one of humanize's by taking its name — a
`.humanize/flows/chat.py` is what `-f chat` runs *in that project*.

What a flow is **called** is another question. The ones humanize ships are called by a bare
name; a flowverse's are called `<flowverse>/<flow>`, which is the one spelling nothing can stand
in for; a flow of yours is called by its path, short enough to read:

| | |
| --- | --- |
| `chat` | one humanize ships |
| `official/rlar` | one the official flowverse holds |
| `.humanize/flows/chat.py` | this project's own |
| `~/.humanize/flows/chat.py` | yours, in every project |

So yours is listed beside humanize's rather than instead of it, `-f` takes either, and what
each was [set up to run](tui.md#what-it-remembers) is remembered apart — a flow of yours cannot
quietly inherit the agents or the settings of the one it shares a name with.

Anything with a slash or an extension in it is a path, taken as given. A file whose name starts
with `_` is not a flow.

```sh
mkdir -p .humanize/flows && cp my_loop.py .humanize/flows/
hmz exec -f my_loop -a claude/claude-opus-4-8:high "fix the build"
hmz exec -f ./somewhere/else.py -a claude/claude-opus-4-8:high "fix the build"
```

## Flowverses

A flowverse is a git repository of flows: one `.py` per flow, and whatever they import beside
them under names starting with `_`. It is cloned into `~/.humanize/flowverses/<name>/`, and
every flow in it is then offered under that name.

Two are always there:

| | |
| --- | --- |
| `builtin` | the flows in the package, which are [the three below](#the-flows-humanize-ships) |
| `official` | [humanfia/flowverse](https://github.com/humanfia/flowverse), which is everything else humanize offers |

`official` is listed before it has been fetched — what there is to run is not the same question
as what has been downloaded — and neither of the two can be taken away.

In the [interface](tui.md), `/flow` is where they live: left and right walk the places flows
come from, `ctrl+n` adds one, `ctrl+r` fetches the open one again, and `ctrl+x` takes an added
one away. Adding one takes a URL or an `owner/repo`, and a name to keep it under if the
repository's own name is not the one you want.

```sh
hmz exec -f official/rlar -a claude/claude-opus-5:max -a codex/gpt-5.6-sol:max "$(cat TASK.md)"
```

A flow from a flowverse that has not been fetched says so rather than saying there is no such
file: the name is right, the download has not happened.

A flow is a Python file, and reading one means running it — so listing what a flowverse holds
imports every file in it. Adding one is trusting that repository with this machine, exactly as
installing a package is.

## The flows humanize ships

Three, which are the shapes a flow takes. Each names the `hmz exec` line that starts it in its
own docstring.

| Flow | Agents | What it does |
| --- | --- | --- |
| `chat` | 1 + you | One agent, one session, and every line typed between turns is a turn of it. Talking to a coding agent with no loop around it. This is what the interface opens on. |
| `ralph_loop` | 1 | A fresh session every turn, so nothing carries over: the agent starts from the task and the repository each time. |
| `stateful_ralph` | 1 | One session, held for the whole run, re-sent the task every turn. |

Their source is the best documentation of this API there is — `src/humanize/flows/builtin/` in
a checkout, or wherever `pip` put it.

## The official flowverse

Everything else humanize offers is in [humanfia/flowverse](https://github.com/humanfia/flowverse),
which is [fetched](#flowverses) the first time somebody wants what is in it. Five of these are
flowbench's loops, written against this API.

| Flow | Agents | What it does |
| --- | --- | --- |
| `official/fixed_juice_ralph` | 1 | Ralph with a governor on it: it [moves the effort](agents.md#moving-the-effort-while-it-runs) a rung a round to hold the agent to `juice` output tokens per turn of the model. |
| `official/continue_loop` | 1 | Sends the task once, then keeps nudging `continue`. Until a turn lands the task is sent again — `continue` on its own would open a session that never saw it. |
| `official/goal` | 1 | Ralph, with the task set as the agent's [own goal](agents.md#goals). The loop only starts it over when it stopped without having met it. |
| `official/flame_chase` | 2 | Two agents take turns on the same task. Each reads the repository, not a history. |
| `official/rlar` | `actor`, `reviewer` | The actor works in one session and must remember; a fresh reviewer reads its work and must not. The review *is* the actor's next prompt, word for word, and the reviewer is also the one that says the task is finished — which is what ends the run. |
| `official/humanize1:gen-idea` | `drafter` | Opens a loose idea into a repo-grounded draft. |
| `official/humanize1:gen-plan` | `planner`, `analyst` | Turns that draft into a plan both sides have converged on. |
| `official/humanize1:rlcr` | `builder`, `reviewer` | Builds the plan under review until nothing is left to say. Run it in a git repository. |

`humanize1` is [PolyArch/humanize](https://github.com/PolyArch/humanize), and its three commands
are [three flows in one file](#several-flows-in-one-file) — set up on their own agents, run one
at a time, and handing to each other through the file each writes: the draft, then the plan.
Every flag the plugin takes is a field on that phase's `/config`, under the plugin's own name
for it — `--max`, `--full-review-round`, `--skip-impl`, `--agent-teams`, `--yolo`, and the rest.

The loop is a hook. The plugin blocks Claude's exit and puts the round to Codex in a Stop hook;
so does this, with a [`Moment.STOP` hook](#hooks-in-a-flow) on the builder. A round is the
builder believing the whole plan is done and trying to stop, and what the reviewer says is what
it hears instead. Its tool validators are hooks too, on `Moment.PermissionRequest`, which is why
the builder has to be a backend that runs it.

It writes what the plugin writes, where the plugin writes it: `.humanize/rlcr/<timestamp>/`
with `state.md`, `goal-tracker.md`, and a prompt, summary, contract and review per round.

Read [Security](../README.md#security) before starting any of them.

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

### Fanning out: one agent, many turns at once

```python
answers = agent.batch([f"Fix the tests in {path}" for path in paths], at_once=8)
```

A session apiece, all of them going, answers in the order they were asked for. `at_once` is how
many run at a time — leave it out and they all do. In a coroutine flow it is `await
agent.abatch(...)`, which is the same fan-out with the loop left free.

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

### Asking a question rather than setting an agent to work

A loop that has to decide something — is this finished, does this plan belong to this
repository — asks for the [shape of the answer](agents.md#answering-in-a-shape) and reads a
field, rather than looking for a word at the end of a paragraph:

```python
class Review(BaseModel):
    """What one round's review comes to."""

    model_config = {"extra": "forbid"}

    done: bool = Field(description="True only if there is nothing left to do or to fix.")
    notes: str = Field(description="What to say to the agent, passed on word for word.")


review = agents.reviewer(REVIEW_PROMPT + task, suppress=True, schema=Review)
if review is not None and review.done:
    return
```

`suppress=True` covers a review that never arrived and one that came back as something other
than a `Review`: both are `None`, and both are a round to take again. This is what `rlar` ends
on, and what `humanize1` asks its analyst and its reviewer before it starts anything.

The same call to [the person](#the-person-at-the-prompt) is a questionnaire: they are asked a
question per field rather than shown a schema, and the model is built out of what they typed.
So a flow settles what only a person can settle in the model it is going to run on —
`agents.human(asked, schema=Settled, suppress=True)`. See
[Agents](agents.md#asking-them-for-a-shape-which-is-a-questionnaire).

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

`-a` reaches four of an agent's settings: the CLI, the model, the effort, and — after an `@` —
the [provider](providers.md) whose account it runs as. A name, [where the work
lands](machines.md), [which skills it has](agents.md#which-skills-an-agent-is-loaded-with) and
[what it may do](agents.md#what-an-agent-may-do) are settings of the *agent* that no `-a` spells,
so a flow that needs one is handed agents built in Python — and a machine only where the flow's
own place for that agent [said `Remote`](#where-each-agent-works):

```python
from humanize.agents import ClaudeCodeAgent, ClaudeCodeAgentConfig
from humanize.runner import Runner

config = ClaudeCodeAgentConfig(model="claude-opus-4-8", effort="high")
agents = [
    ClaudeCodeAgent(config, name="actor"),
    ClaudeCodeAgent(config, name="reviewer"),
]

Runner("official/rlar", agents).run("fix the build")
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

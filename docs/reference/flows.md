# Flows

A flow is a **directory**: an `__init__.py` with a function marked `@flow` in it, taking the
agents and the task, whatever that imports beside it, and a `skills/` of the skills the flow
works by. It is the loop: which agent is asked what, in what order, and when to stop.

```
my_loop/
├── __init__.py          the flow
├── _prompts.py          whatever it imports, which travels with it
└── skills/              what its agents are given, mounted onto every session they open
    └── review-notes/
        └── SKILL.md
```

Everything a flow needs lives in that directory, which is what makes a flow a thing you can
copy, fork and edit whole — `f` on one in `/flow` writes a copy into `.humanize/flows/`.

**A single `.py` file is a flow too.** A flow is a module, and that is the other shape one
has: `.humanize/flows/twice.py` is `-f twice`, exactly as a directory of that name would be.
It brings no skills — what is beside it is the other flows, and none of it came with that one
— so a flow that grows a `skills/` is a flow that becomes a directory. Where both exist under
one name, the directory wins.

It is ordinary Python. There is no DSL, no graph to declare, no state machine — a flow may
branch, sleep, read files, shell out, and give up, because it is just a function.

## What a flow drives

**`hmz.flows` is the only import a flow needs.** The interfaces, the mark, calling another
flow, and everything a flow legitimately reaches for that humanize writes down elsewhere — the
moments a hook hangs on, what a turn cost, what an agent is configured with, what each backend
runs — all come from that one name:

```python
from hmz.flows import Agent, Moment, Person, Session, Unrecoverable, flow, load
```

A flow that named `hmz.agents` for the type of what it drives would be a flow written against
which CLI is behind it, and it would break the day humanize moved anything. It never has to.
`Unrecoverable` is exposed here too, so bounded flows can distinguish a transient failed turn
from one whose next attempt would necessarily fail the same way.

| Name | Is |
| --- | --- |
| `Agent` | A coding agent: a turn, a session, a goal, a batch, what it has cost, what is hung on the moments of its turns. What you annotate a place with. |
| `Session` | One conversation with one agent, kept alive across turns. What `agent.new()` gives you. |
| `Person` | The person at the prompt, driven as an agent. A place nobody is asked to fill — see [the person at the prompt](#the-person-at-the-prompt). |

They are **interfaces**, not base classes. `hmz.agents.AgentBase` and `SessionBase` answer to
them, and never name them back: a flow says what it drives, and a driver is written without
ever hearing of a flow. Whatever a flow may ask of an agent is in the interface; how a turn is
spelled to a CLI, where its logs go and how it falls back to another account are not, being how
an agent is driven rather than what a flow drives. A test that stands in for a coding agent
implements the driver instead — see [testing a flow](#testing-a-flow).

## The contract

Three rules, and that is the whole of it.

**1. A function marked `@flow`, taking the agents and the task.** What it is called is up to
you — the mark is what makes it a flow, not the name.

```python
from hmz.flows import flow

@flow
def run(agents: tuple[Agent], task: str) -> None:
    ...
```

**2. The annotation on `agents` says how many the flow drives.** A fixed-length tuple, or a
`NamedTuple` of them. `tuple[Agent, ...]` is any number, which is no answer to the
question, and is refused.

**3. That annotation has to be readable at runtime.** Import `Agent` normally, not under
`if TYPE_CHECKING` — a count nothing can read back is not one a command line can be held to.

```python
"""Two passes over the same task."""

from hmz.flows import Agent, flow

@flow
def run(agents: tuple[Agent], task: str) -> None:
    (agent,) = agents
    session = agent.new()
    session(task)
    session("Now review what you just did, and fix anything that is wrong.")
```

Anything else the file does as it is imported is the flow's own business and fails as it would
anywhere — a flow that reads a prompt file beside it and does not find it is not reported as a
command line to correct.

A flow may also be `async def`. Everything else on this page is the same either way.

One flow may hold [several flows](#several-flows-in-one-file): `@flow` is the one it holds
under its directory's own name, and `@flow(name="…")` is one of the rest, run as
`<flow>:<name>`.

A flow may also name [skills](#the-skills-a-flow-brings) that live in somebody else's
repository, and everything it brings is mounted onto every session its agents open.

And a flow may say it [can be picked up](#a-flow-that-can-be-picked-up) where the last run of it
left off: `@flow(resumable=True)` is handed a dict as its last argument, holding whatever it
wrote there last time.

**What a flow may ask of an agent, and what it may not.** A flow declares `Agent`, which is
what it may ask: turns, sessions, goals, batches, what the run has cost, what is hung on the
moments of a turn, and what the agent is configured with. What an agent *is* — what it runs,
where its turns land, what it is called, which of the flow's skills it carries — is an answer
somebody already gave, so it is not on `Agent` at all. A flow that wants one set up differently
[makes one](/reference/agents#an-agent-that-is-not-quite-the-one-you-were-handed):

```python
careful = agent.clone(config=replace(agent.config, effort="max"))
```

**What a flow may hand an agent.** A conversation takes two things from the flow while it is
running: which of the flow's [skills](#which-of-them-one-conversation-carries) it carries, and
which of the flow's own **callbacks** the agent may reach for as tools —

```python
session.offers([Tool(name="review", about="…", takes=Reviewing, call=…)])
```

— which is how an agent asks the flow for something mid-turn, up to and including another
flow. See [Callbacks as tools](/weaver/tools).

## A flow that waits for more than one thing

A loop that has more than one turn going at a time has to be able to wait for several things at
once, so a flow may be written as a coroutine:

```python
import asyncio

from hmz.flows import Agent, flow

@flow
async def run(agents: tuple[Agent, Agent], task: str) -> None:
    while True:
        acted, reviewed = await asyncio.gather(
            agents[0].aturn(task, suppress=True),
            agents[1].aturn(f"Read the repository and say what is wrong: {task}", suppress=True),
        )
```

Nothing about starting it changes: `hmz exec -f …` and the interface run a coroutine flow the
same way they run any other, on a loop of the flow's own, and the run is over when `run`
returns. The count of its agents, the settings it declares, the [epic](/reference/tracing#epics) it is
written down as and the way it is [stopped](#stopping) are all exactly as they are for a flow
that is a plain function.

Every call that runs a turn has an awaited twin — `agent.aturn`, `session.aturn`,
`agent.apursue` — and `agent.abatch` runs a whole fan-out of them. See
[Agents › Awaiting a turn](/reference/agents#awaiting-a-turn).

```python
@flow
async def run(agents: tuple[Agent], task: str) -> None:
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
hmz exec: error: official/rlar: the flow drives 2 agents, 1 given
```

which is what keeps a two-agent flow started with one from failing on an unpacking hours into a
loop, with a turn's work already behind it.

A `NamedTuple` says what each agent is *for* as well as how many there are:

```python
from typing import NamedTuple

from hmz.flows import Agent

class Agents(NamedTuple):
    """The two this drives: one that works in a session, and one that arrives fresh."""

    actor: Agent
    reviewer: Agent

@flow
def run(agents: Agents, task: str) -> None:
    working = agents.actor.new()
    ...
```

The names are not only for the flow's own readability. Everything that has to talk about an
agent uses them:

- The agents page of `/flow` asks what *the reviewer* runs, rather than what agent 2 of 2 runs.
- The line above the prompt says `reviewer · claude/claude-opus-4-8:high`.
- A [trace](/reference/tracing) groups that agent's sessions under `reviewer`.
- What each agent was set to run is [remembered per role](/reference/tui#what-it-remembers), so a flow
  that grows an agent in the middle does not hand the reviewer's model to the builder.

An agent that was named where it was made keeps that name; one that was not takes the name the
flow gives it, before anything is written down about the run.

## Settings of the flow's own

A flow that has settings says so by taking a third argument, annotated with a
[pydantic](https://docs.pydantic.dev/) model or `None`:

```python
from typing import Literal

from pydantic import BaseModel, Field

from hmz.flows import Agent

class Config(BaseModel):
    """What this flow takes."""

    rounds: int = Field(default=3, ge=1, le=9, description="how many times round")
    mode: Literal["fast", "slow"] = Field(default="fast", description="which way")

@flow
def run(agents: tuple[Agent], task: str, config: Config | None = None) -> None:
    setting = config or Config()
    ...
```

That is the whole of it. The model is what asks: the fields are the questions, their types say
how each one is answered, `description` is the line shown beside it, and whatever the model
refuses is what the flow will not run.

- The sheet the interface puts up as a flow is chosen is that model with a cursor on it: `/flow`
  asks it between choosing the flow and choosing its agents. See [TUI › Setting a flow
  up](/reference/tui#setting-a-flow-up).
- What you set is [remembered per flow](/reference/tui#what-it-remembers), so a flow of twenty
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

## A flow that can be picked up

A loop meant to run for a week is a loop that will be stopped and started: a machine goes down,
somebody stops it, a turn takes the process with it. So a flow may say it can be picked up
where the last run of it left off, and one that does takes a dict as its last argument — after
the config, for a flow that takes one — holding whatever it wrote there last time.

```python
"""One pass per file, however often it is stopped."""

from pathlib import Path
from typing import Any

from hmz.flows import Agent, flow

@flow(resumable=True)
def run(agents: tuple[Agent], task: str, state: dict[str, Any]) -> None:
    (agent,) = agents
    left = state.get("left") or sorted(str(one) for one in Path("src").rglob("*.py"))
    while left:
        agent(f"{task}\n\nThis file: {left[0]}", suppress=True)
        left = left[1:]
        state["left"] = left      # writing it into the state is what saves it
```

**It is not a second copy of the transcript.** The backends keep that, and the run's
[epic](/reference/tracing#epics) already says which sessions it opened. What belongs here is
the handful of things the loop itself is keeping track of — which round it is on, which files it
has been through, what it has decided so far — which is the part of a run nothing else knows.

**It lives in the run's own epic**, as `state.json`, under the name the flow was run as. A flow
that [called another](#a-flow-that-calls-another-flow) is two flows and each keeps its own, side
by side in that one file: neither writes the other's, and each is picked up as itself.

**It is saved as the flow writes it.** Setting a key, removing one, `update`, `setdefault` —
each of them writes the file again, because a run worth picking up is one that was stopped or
killed rather than one that ended tidily, and state written only at the end is state a stopped
run has none of. Something written *inside* a value it holds — a list appended to, a dict of its
own written into — is a change no mapping can see, and is saved when the run ends.

Keep to what JSON holds. Anything else is written as its `str`, so a `Path` put in comes back
out a string; and a value that cannot be written at all leaves the last save standing rather
than ending the run, since a loop that died because it could not write down where it had got to
would be worse than one carrying on from a round ago.

**Running the flow again is what picks it up.** There is no flag for it: `hmz exec -f weekly`
twice in one directory is one loop carried on, from the last run of it here that left anything —
a run that wrote nothing is nothing to pick up, so what carries on is the run before it. In the
interface, `/epics` marks the runs whose flow said so, and enter on one offers *carry on from
here* where the flow still says it, which runs that run's own flow on that run's own agents with
what it was asked to do. From Python it is an argument:

```python
Runner("weekly", agents, resume=epic).run("go through the tests")
```

**A run that was picked up is a run of its own.** An epic is never reopened, so what carries on
is written into an epic of its own whose `began` line says which run it was `picked_up` from —
and a week of stops and starts reads as the week it was rather than as one enormous run.

Whether a flow can be picked up at all is asked of the flow rather than of the run, since a flow
may have been rewritten since it last ran:

```python
from hmz.epic import resumed, state
from hmz.flows import resumes

resumes("weekly")            # what the flow says now, read by running it
at = resumed("weekly")       # the run its next run would pick up, or None
if at is not None:
    state(at, "weekly")      # what that run left there
```

A flow that says nothing is run from the top every time, which is what every flow was before
this, and a run pointed at an epic to pick up ignores it, having nowhere to put what is there.
One that says it can be picked up and takes no such argument is handed one it has no place for,
and says so at the first call rather than starting over in silence.

## Asking for an agent that can do something

Not every backend runs every [moment](/reference/agents#hooks). A flow that hangs a hook on one only
some of them run says so where it declares the place, by writing the moment beside the type:

```python
from typing import Annotated, NamedTuple

from hmz.flows import Agent, Moment

class Agents(NamedTuple):
    """The two this drives: one that is gated, and one that reads its work."""

    builder: Annotated[Agent, Moment.PERMISSION_REQUEST]
    reviewer: Agent
```

`Annotated` is the whole of it: the type is still `Agent`, so the flow reads and type-checks
exactly as it did, and what is written beside it is what the place asks of whoever fills it.
Several moments are several arguments.

**A goal is asked for the same way.** `agent.pursue(objective)` is the backend's own goal
feature — the agent decides for itself that the objective has been met, and until it does, a
turn that would have ended starts another. Five backends have one (Claude Code, Codex, DeepSeek
Harness, Kimi Code and ZCode), so a flow built on it says so:

```python
from hmz.flows import Agent, Goal

class Agents(NamedTuple):
    """The one it drives, which has to have a goal of its own."""

    worker: Annotated[Agent, Goal]
```

Both are checked before the first turn, for the same reason the count is:

```console
$ hmz exec -f gated -a kimi/kimi-code/k3:high -a kimi/kimi-code/k3:high "fix the build"
hmz exec: error: gated: builder has to run PermissionRequest, which kimi does not

$ hmz exec -f pursuing -a pi/openai-codex/gpt-5.5:high "fix the build"
hmz exec: error: pursuing: worker is run under a goal, which pi has no feature for
```

and the agents page of `/flow` offers only the CLIs that would work for that place, so it cannot
be chosen wrong there at all.

## Where each agent works

Where an agent's turns land is declared the same way, and by the same file: the flow writes it
beside the type.

```python
from typing import Annotated, NamedTuple

from hmz.flows import Agent, Isolated, Remote

class Agents(NamedTuple):
    """The three this drives, and the three places they work."""

    builder: Annotated[Agent, Remote]                  # may be pointed at a machine
    tester: Annotated[Agent, Isolated("python:3.12")]  # a container of the flow's own
    reviewer: Agent                                    # here, and nowhere else
```

| Beside the type | Where that agent works |
| --- | --- |
| *(nothing)* | this machine, and it **cannot** be pointed anywhere else |
| `Remote` | wherever whoever chose the agent pointed it — the only kind of place that may be pointed at all — and here where nobody did |
| `Isolated("<image>")` | a [container of that image](/reference/machines#isolated-python-3-12), which nobody configures and nobody is asked about |

**This is a change.** A machine used to be a setting of the agent that anything could reach, so
any agent of any flow could be pointed anywhere. It is still a setting of the agent — that is how
a `Remote` place is filled — but a flow is written for one shape of work, and one whose agents
read *this* project cannot have one of them reading somebody else's. So the flow says which of
them may be sent elsewhere, and nothing above it can say otherwise.

Both refusals land before the first turn, for the reason the count does:

```text
onbox: reviewer runs on this machine -- this flow does not say it works anywhere else, so it cannot be pointed at one
onbox: tester works in a container of this flow's own, so there is nothing to point it at
```

`hmz exec` prints either as `hmz exec: error: …` and runs nothing; the interface shows it as a red
line and starts nothing. No `-a` spells a machine, so what runs into these is an agent
[built in Python](#building-the-agents-yourself) or one moved on the interface's `where` row.

A place may say more than one thing — `Annotated[Agent, Moment.STOP, Remote]` is a place that
must run that moment *and* may be moved. Several arguments, read one by one, in any order.

What the flow declared is readable without driving it:

```python
from hmz.flows import wanted

wanted("official/rlar")   # one Place per agent somebody has to choose:
                          # .name, .moments, .goal, .where
```

`where` is `None`, the `Remote` class itself, or the `Isolated` the flow wrote — which is how
whatever chooses the agents knows which of them it may offer a machine for. What each answer
comes to, and what a container of the flow's own actually is, is in
[Machines](/reference/machines#which-agents-may-be-moved-at-all).

## Hooks in a flow

A flow holds the agents, so it can hang a hook on one and take it down again as it goes. This
is a Ralph loop that will not let a turn stop while the task file still says there is work:

```python
from pathlib import Path

from hmz.flows import Agent, Moment, Occasion, Verdict

def run(agents: tuple[Agent], task: str) -> None:
    (agent,) = agents

    def unfinished(occasion: Occasion) -> Verdict | None:
        if occasion.again < 5 and "- [ ]" in Path("TASK.md").read_text():
            return Verdict(refused=True, because="TASK.md still has unticked boxes.")
        return None

    with agent.hooks.on(Moment.STOP, unfinished):
        while "- [ ]" in Path("TASK.md").read_text():
            agent(task, suppress=True)
```

Everything a hook can do is in [Agents › Hooks](/reference/agents#hooks). Two things worth saying here:

- Hooks are on the **agent**, not the session, so one covers every session that agent opens —
  including the fresh one a Ralph loop makes each turn.
- A hook runs on the turn's own thread. One that takes a while is a turn that takes a while.

## The person at the prompt

A place annotated `Person` is you, driven as an agent — which is what you are to a flow.

```python
from typing import NamedTuple

from hmz.flows import Agent, Person

class Chat(NamedTuple):
    assistant: Agent
    human: Person

def run(agents: Chat, task: str) -> None:
    conversation = agents.assistant.new()
    said = task
    while said:
        answered = conversation(said, suppress=True)
        said = agents.human(answered)
```

Saying something to it is asking what to say next; what it answers with is what was typed.

**Nobody is asked what the person runs**, so a `Person` is not one of the agents `-a` names
— the flow above is started with one `-a` and drives two. Run from a command line, where nobody
is at a prompt, it answers with nothing, so the loop ends and the flow does the one thing it
was given.

### The board

Asking stops the turn. **The board does not.** It is a handful of named lines kept beside the
run and drawn on [`/status`](/user/status) — the flow reads and writes it whenever it likes,
the person changes it whenever they like, and neither is ever waiting on the other:

```python
board = agents.human.board
board.put("todo", task, about="one thing a line; add more whenever you like")
board.put("doing", "nothing yet", whose="flow")  # the flow's; they read and do not write

while waiting := [one for one in board.get("todo").splitlines() if one.strip()]:
    board.put("doing", waiting[0])
    agents.builder(waiting[0], suppress=True)
    board.put("todo", "\n".join(waiting[1:]))    # either of you writes this one
board.put("doing", "nothing left")
```

Which is what makes it a work queue: you put more up while the loop is going, and the next
round takes it. `todo` is left as a line either of you writes, since taking an item off is the
flow doing its half of that; `doing` is the flow's, and a line whose `whose` is one side's is
refused to the other where it writes, with `Refused`, rather than quietly ignored. See
[The mission board](/user/board).

## Running one

```sh
hmz exec -f <flow> -a <cli>/<model>:<effort> [-a ...] <task>
```

One `-a` for each agent the flow drives, in the order it takes them. Full syntax in the
[CLI reference](/reference/cli#hmz-exec).

In the [interface](/reference/tui), `/flow` picks one by name — tab and shift+tab are for stepping
between the agents of the flow that is running.
Picking one while a flow runs is refused: ctrl+c twice stops it first, since a flow drives the agents it
was handed and must not have them swapped underneath it.

## Several flows in one file

Three phases of one thing are one thing to write and three to run. Give each mark a name, and
each is a flow of its own, called `<flow>:<name>`:

```python
"""Three phases of one thing."""

from hmz.flows import flow

@flow(name="gen-idea")
def first_pass(agents: Drafting, task: str, config: Idea | None = None) -> None:
    """Opens a loose idea into a repo-grounded draft."""

@flow(name="gen-plan")
def then_plan(agents: Planning, task: str, config: Plan | None = None) -> None:
    """Turns that draft into a plan both sides have converged on."""
```

```sh
hmz exec -f official/humanize1:gen-idea -a claude/claude-opus-5:max "add undo to the editor"
hmz exec -f official/humanize1:gen-plan -a claude/claude-opus-5:max -a codex/gpt-5.6-sol:max ""
```

The name is what you write in the mark and nothing else — a name written down where a flow is
run should not change under whoever renames the function. `@flow(about="…")` says what it does
where flows are listed, which is otherwise the first line of its docstring.

An implementation flow used only through `load()` can stay out of those lists and the `/flow`
picker without losing its name:

```python
@flow(name="engine", selectable=False)
def engine(agents: Agents, task: str) -> None:
    ...
```

It remains directly callable by `<flow>:engine`; `selectable=False` changes discovery only.

Each of them declares its own agents and its own settings, so the agents page asks two questions
rather than five and setting one up shows one phase's flags rather than three phases' at once. What
passes between them is whatever they write — a file, usually.

`@flow` marks; it does not wrap. The function is called exactly as it was. A file that marks
one function with a bare `@flow` is one flow under the file's own name, which is most of them.

## A flow that calls another flow

A flow is a loop over agents, and a loop worth having is one another loop can reach for. Ask
for it by the same name `-f` takes, and you are handed the flow itself to run with the agents
you already have:

```python
from hmz.flows import Agent, flow, load

@flow
def run(agents: tuple[Agent, Agent], task: str) -> None:
    plan = load("official/humanize1:gen-plan")
    plan(agents, f"plan this first: {task}")
    for _ in range(3):
        agents[0].new()(task)
```

`load` takes what `-f` takes — `ralph_loop`, `official/rlar`, `humanize1:gen-plan`, a path of
your own — so a flowverse is a library as well as a menu. A name nothing answers to is refused
where you ask for it rather than an hour into your loop.

**Hand it the agents it declares.** A flow that drives one is called with one, in the tuple it
declared them as — pass a list or a tuple and it arrives as that flow's own `NamedTuple`, named
the way that flow names them. A flow that [talks to the person](#the-person-at-the-prompt) may
be handed one fewer, since nobody chooses the person; hand over your own if you have one, so
that what it asks reaches whoever is at the prompt.

Nothing is renamed. The agents belong to the run that was started, and what has already been
written down about them stays true.

**It is read again at every call.** `load` holds the name rather than the function it found:
each call runs the flow's entry point afresh, so a flow rewritten between two calls of it — by
hand, or by an agent this very flow is driving — is the one that runs next. That is what makes
a loop that improves its own flow a loop that then runs the improved one. A flow that was
rewritten into something that is no longer a flow is refused at the call, the way a name that
was wrong is refused at `load`.

**It brings its own skills.** The called flow's `skills/`, and the repositories it declared,
are [mounted](#the-skills-a-flow-brings) onto the sessions its agents open while it runs — and
the agents are handed back carrying the calling flow's own when it returns, however it returns.
A call refused — for settings the flow does not take, for an agent that cannot run a moment it
declares, for a place run under a goal filled by an agent that has none — is a call that never
happened, and leaves the agents exactly as it found them.

A wrapper flow may deliberately keep its own skills available inside the called flow:

```python
load("official/rlar", inherit_skills=True)(agents, task)
```

The called flow's skills come first and win any same-name collision. Parent-only skills are
then appended, and the agents are restored to exactly what the wrapper carried when the call
returns or raises. Without the flag, calls remain isolated; a reviewer or other child flow is
not implicitly given its caller's capabilities.

**A flow that takes [settings of its own](#settings-of-the-flow-s-own) takes them here too**,
as a third argument — an instance of that flow's model, or the fields to build one from:

```python
load("official/rlar")(agents, task, {"rounds": 9})
```

They are read back through the flow's own model at the moment it is called, so a flow that
takes no settings, or takes different ones, says so rather than quietly ignoring them.

**A called flow answers with whatever it answers with**, so one written as a coroutine is
awaited by whoever called it:

```python
@flow
async def run(agents: tuple[Agent], task: str) -> None:
    await load("official/rlar")(agents, task)
```

**What is running is both of them.** `hmz.flows.running()` reports the flow that was started
and whatever it called, innermost last; the interface names them on its status line and on
`/status`, and the [epic](/reference/tracing) records each call and each return. A flow that called
another does not read as the flow somebody chose.

**And each call is written down as a run of its own.** A called flow opens sessions, keeps its
own state and calls flows of its own, so the epic gives every call a record of its own beside
the run's — `epic.<flow>_<hex>.jsonl` — and the record of whatever called it says `called` and
`returned` with that filename. What the called flow opened is in its record rather than in the
record of whatever started the run. See [Records of called
flows](/reference/tracing#records-of-called-flows).

## Where flows live

`-f` takes a name or a path. A name is looked for nearest first:

| | |
| --- | --- |
| `local` | `.humanize/flows/*` — this project's own |
| `user` | `~/.humanize/flows/*` — yours, in every project |
| — | the ones humanize ships, and every [flowverse](#flowverses) there is |

Nearest wins, so a flow of your own may stand in for one of humanize's by taking its name — a
`.humanize/flows/chat/` is what `-f chat` runs *in that project*. Which is what `f` in the
flow menu is for: it copies the flow under the cursor into `.humanize/flows/`, whole, and from
then on that name means your copy. In Python that is `hmz.flows.fork(name, into=None)`, which
copies a directory flow with its `skills/` and a single-file flow as a file, and refuses a name
you already have a copy of — in either shape, since a directory would otherwise take a
single-file flow's name without touching the file it is in — rather than writing over it. A
copy that fails partway leaves nothing behind, so the name is free to try again.

What a flow is **called** is another question, and one rule answers it for every place: the
ones humanize ships are called by a bare name, and every other by the place it came from,
which is the one spelling nothing can stand in for. Your own two places are `local` and `user`:

| | |
| --- | --- |
| `chat` | one humanize ships |
| `official/rlar` | one the official flowverse holds |
| `local/chat` | this project's own |
| `user/chat` | yours, in every project |

So yours is listed beside humanize's rather than instead of it, `-f` takes either, and what
each was [set up to run](/reference/tui#what-it-remembers) is remembered apart — a flow of yours cannot
quietly inherit the agents or the settings of the one it shares a name with.

A name no place answers to is taken as a path: a flow's directory, or a `.py` file to run as
one — `-f ./flows/mine`, `-f ./flows/mine.py` and `-f ./flows/mine/` all work, the directory
being tried first and the `.py` beside a path with the extension left off. A directory whose
name starts with `_` is not a flow.

**A flow imports what travels with it.** While one is read, its own directory and the directory
the flows are in are both on `sys.path`, and only while: `import _prompts` reaches the module
beside the flow, and `import _shared` reaches what a flowverse keeps beside all of them. What a
flow imports is not something the rest of the process can — and is forgotten as the flow is
done with, so two flows that each keep a `_prompts` beside them each read their own, and one
rewritten between two runs is read again rather than remembered.

```sh
mkdir -p .humanize/flows && cp -r my_loop .humanize/flows/
hmz exec -f my_loop -a claude/claude-opus-4-8:high "fix the build"
hmz exec -f ./somewhere/else -a claude/claude-opus-4-8:high "fix the build"
```

## The skills a flow brings

The `skills/` inside a flow is what that flow works by, laid out the way every one of these
CLIs lays a skill out — a directory apiece, each holding a `SKILL.md`. They are **mounted**
onto every session the flow's agents open: copied where that backend reads a project's own
skills for as long as the session lives, and taken away again after. Nothing is installed, and
nothing the person at this machine installed is touched.

A flow may also name skills that live in somebody else's repository, where it is declared:

```python
@flow(skills=("https://github.com/humanfia/flowverse#review-notes",))
def run(agents: Agents, task: str) -> None:
    ...
```

which is a git URL anything can clone and, after the `#`, which of that repository's
`skills/*` is wanted. Without one, every skill it holds is brought. Such a repository is
cloned under `~/.humanize/skills/` and fetched again the next time a run asks for it.

The flow's own wins a name a repository also uses: a fork that edited a skill meant the edited
one. A backend that reads no project skills of its own carries none of this — its skills are
the ones its CLI installs, and humanize does not switch those on or off.

In a directory that holds [several flows](#several-flows-in-one-file), the `skills/` is all of
theirs: it belongs to the directory, not to the entry point. What `@flow(skills=…)` names is
read off the one that was asked for.

**A repository that cannot be fetched stops the run before its first turn.** `hmz exec` exits
2 with what git said, and the interface says it where the flow was started — a flow that works
by a skill it has not got is not a flow to start and find out about an hour in. One that was
fetched before and cannot be reached now runs on the copy already here. A `#name` the
repository does not hold stops it the same way, and says what the repository does hold.

**A flow that is one file brings no `skills/` of its own, and may still name a repository.**
What is beside such a flow is the other flows; what it declares is fetched and mounted as any
other flow's is.

**A name is one skill.** Where something of that name is already where the mount goes — the
project's own, or another flow's mounted by a session that is still running — the flow's is
left where it is and the session reads what is there. A flow called by another flow does not
change what the flow that called it is working by.

### Which of them one conversation carries

Every session carries all of them unless it says otherwise, and a session may say otherwise
while it runs:

```python
reading = agent.new()
reading.loads(["reading-a-codebase"])
reading("Find where the retry logic lives.")

reading.loads(["writing-tests"])       # from the next turn on
reading("Now write the tests for it.")

reading.skills                          # ('writing-tests',)
```

An agent is what it was made as; a conversation is a thing that gets somewhere, and this is the
one thing about what it works by that changes as it does. What is put where the backend reads
it is settled as a turn opens — a session may not have a directory yet, and a turn already
running must not have what it is working by moved underneath it — so a session told between two
turns is carrying what it was told about on the turn after.

`loads(None)` is every one the flow brought, which is where a session starts. `loads([])` is
none of them: that conversation works by what the CLI already has. A name the flow does not
bring is ignored rather than refused, so a session asking for one a fork of the flow dropped
carries the rest.

Two conversations of one agent may carry different sets at once, which is what makes this the
session's answer rather than the agent's.

## Flowverses

A flowverse is a git repository with a `flows/` directory in it: one directory per flow, each
holding the `__init__.py` that is the flow, whatever it imports beside it, and the `skills/` it
brings. It is cloned into
`~/.humanize/flowverses/<name>/`, and every flow in its `flows/` is then offered under that
name. Nothing outside that directory is read, so the repository is free to have a README, a
pyproject and a test suite of its own without any of it being taken for a flow.

Four are always there:

| | |
| --- | --- |
| `builtin` | the flows in the package, which are [the three below](#the-flows-humanize-ships) |
| `official` | [humanfia/flowverse](https://github.com/humanfia/flowverse), which is everything else humanize offers |
| `local` | `.humanize/flows` where humanize is being run — this project's own |
| `user` | `~/.humanize/flows` — yours, in every project |

`official` is listed before it has been fetched — what there is to run is not the same question
as what has been downloaded — and none of the four can be taken away.

The last two are places rather than repositories: nothing fetches them, and what is in one is
whatever you put there. They are listed as flowverses all the same, so that one rule says what
a flow is called and one list says where they are. `add`, `fetch` and `remove` all refuse them.

In the [interface](/reference/tui), `/flowverses` is where they live: `a` adds one, `r` fetches
the one under the cursor again, `d` twice takes an added one away, and enter says what one
holds. Adding one takes a URL or an `owner/repo`, and a name to keep it under if the
repository's own name is not the one you want. `/flow` keeps the two keys that are about flows
rather than about places: left and right, which walk these same places because that is which
list of flows is being read, and `f`, which copies the flow under the cursor into this project.

A flow is Python, and reading one means running it — so listing what a flowverse holds runs the
entry point of every flow in its `flows/`. Adding one is trusting that repository with this
machine, exactly as installing a package is.

[`hmz flowverses`](/reference/cli#hmz-flowverses) is the same, said as arguments, for a machine
being set up or a script: `list`, `show`, `add`, `fetch`, `remove`.

```sh
hmz exec -f official/rlar -a claude/claude-opus-5:max -a codex/gpt-5.6-sol:max "$(cat TASK.md)"
```

A flow from a flowverse that has not been fetched says so rather than saying there is no such
file: the name is right, the download has not happened.

Editing a flowverse's own copy does not keep: it is somebody else's repository, and fetching it
again takes what that repository says now. `f` on a flow copies it into `.humanize/flows/`,
where it is yours — and where the name then means your copy.

## The flows humanize ships

Three, which are the shapes a flow takes. Each names the `hmz exec` line that starts it in its
own docstring, and each has a [page of its own](/flows/) with its loop drawn on it.

| Flow | Agents | What it does |
| --- | --- | --- |
| `chat` | 1 + you | One agent, one session, and every line typed between turns is a turn of it. Talking to a coding agent with no loop around it. This is what the interface opens on. |
| `ralph_loop` | 1 | A fresh session every turn, so nothing carries over: the agent starts from the task and the repository each time. |
| `stateful_ralph` | 1 | One session, held for the whole run, re-sent the task every turn. |

Both loops [can be picked up](#a-flow-that-can-be-picked-up), and what they keep is `rounds`
and `output`: one left going for days is one that will be stopped, so running it again goes on
from the round it reached rather than back at one. Nothing else carries — a session is opened
rather than reopened, so `stateful_ralph` started again is a conversation of its own. `chat`
keeps nothing: what was said is the conversation, and the backend logged it.

### What ends a loop

A loop with nothing to stop it runs until somebody stops it, which is a bill nobody agreed to
and a week of rounds nobody read. So every loop here that has no stopping condition of its own
takes a **budget**, in millions of output tokens:

```sh
hmz exec -f ralph_loop -c budget.yaml -a claude/claude-opus-5:high "$(cat TASK.md)"
```

```yaml
budget: 25    # millions of output tokens; 0 goes on until it is stopped
```

**10 million by default.** Output rather than every kind, because output is what a model is
asked to produce and the only kind a loop of its own accord grows: what goes in is the task and
the repository, and a round that read more of them is not a round that did more.

The spend is kept in the state, as `output`, because the rounds are — a budget that started
again at nothing every time the loop was picked up would be no budget at all for the loop a
week of restarts is, so what is counted is every run of that flow in that workspace. A loop that
has spent its budget is **over**, and what is over is not picked up: it clears what it kept, so
the next run there opens on a budget of its own and at round one.

`chat` and `official/rlar` have no budget, because each already ends: a conversation ends when
you stop typing, and `rlar` ends when its reviewer agrees the work is done. `humanize1:rlcr`
ends on `--max` rounds. The loops that take one are `ralph_loop`, `stateful_ralph`,
`official/continue_loop`, `official/flame_chase`, `official/goal` and
`official/fixed_juice_ralph` — where `budget` is the same quantity `juice` is, read at the
scale of the loop rather than of a turn.

Their source is the best documentation of this API there is — `src/hmz/flows/builtin/` in
a checkout, or wherever `pip` put it.

## The official flowverse

Everything else humanize offers is in [humanfia/flowverse](https://github.com/humanfia/flowverse),
which is [fetched](#flowverses) the first time somebody wants what is in it. Five of these are
flowbench's loops, written against this API. [Flows](/flows/) is the same list with the shape of
each one drawn.

| Flow | Agents | What it does |
| --- | --- | --- |
| `official/fixed_juice_ralph` | 1 | Ralph with a governor on it: it [moves the effort](/reference/agents#moving-the-effort-while-it-runs) a rung a round to hold the agent to `juice` output tokens per turn of the model. |
| `official/continue_loop` | 1 | Sends the task once, then keeps nudging `continue`. Until a turn lands the task is sent again — `continue` on its own would open a session that never saw it. |
| `official/goal` | 1 | Ralph, with the task set as the agent's [own goal](/reference/agents#goals). The loop only starts it over when it stopped without having met it. |
| `official/flame_chase` | 2 | Two agents take turns on the same task. Each reads the repository, not a history. Its [budget](#what-ends-a-loop) is what the pair spend between them. |
| `official/rlar` | `actor`, `reviewer` | The actor works in one session and must remember; a fresh reviewer reads its work and must not. The review *is* the actor's next prompt, word for word, and the reviewer is also the one that says the task is finished — which is what ends the run. |
| `official/humanize1:gen-idea` | `drafter` | Opens a loose idea into a repo-grounded draft. |
| `official/humanize1:gen-plan` | `planner`, `analyst` | Turns that draft into a plan both sides have converged on. |
| `official/humanize1:rlcr` | `builder`, `reviewer` | Builds the plan under review until nothing is left to say. Run it in a git repository. |
| `official/parallel_flame_chase` | 7 | A coordinator plans three isolated lanes and leaves; six actors alternate two to a lane and coordinate by durable report. Lane 1 alone writes the original source; lanes 2 and 3 work in snapshots and publish artifacts. |
| `official/parallel_flame_chase_mission` | 7 | The same three lanes, with a fresh coordinator returning to adjudicate outcomes, deadlines, stalls and objective revisions, and to run periodic portfolio audits. |

Every one of them but the two drafting phases [can be picked up](#a-flow-that-can-be-picked-up),
each keeping the little it honestly can. The three Ralphs keep the round they reached, as
`rounds`, and what they have spent, as `output`, which is what their
[budget](#what-ends-a-loop) is held against; `fixed_juice_ralph` keeps the rung its governor
settled at as well, since a loop started again at the top of the ladder walks back down to it a
paid turn at a time.
`flame_chase` keeps whose turn is next, two turns in a row being the one thing a pair taking
turns must not do. `rlar` keeps the review the actor is owed, word for word, which is the one
thing a restart would otherwise throw away — and keeps nothing at all where the reviewer agreed,
a run that is over being nothing to carry on. `humanize1:rlcr` keeps which `.humanize/rlcr/`
directory the loop is in and reads `state.md` back as it stands, rather than stamping a new
directory beside a week of rounds. `gen-idea` and `gen-plan` keep nothing: each writes one file,
and running one again is meant to write another. The two parallel flows keep their plan, their
snapshots and each lane's A/B alternation, and take `resume_mode: fresh` to start another run
rather than carry that one on.

`humanize1` is [PolyArch/humanize](https://github.com/PolyArch/humanize), and its three commands
are [three flows in one file](#several-flows-in-one-file) — set up on their own agents, run one
at a time, and handing to each other through the file each writes: the draft, then the plan.
Every flag the plugin takes is a field on that phase's own settings, under the plugin's own name
for it — `--max`, `--full-review-round`, `--skip-impl`, `--agent-teams`, `--yolo`, and the rest.

The loop is a hook. The plugin blocks Claude's exit and puts the round to Codex in a Stop hook;
so does this, with a [`Moment.STOP` hook](#hooks-in-a-flow) on the builder. A round is the
builder believing the whole plan is done and trying to stop, and what the reviewer says is what
it hears instead. Its tool validators are hooks too, on `Moment.PERMISSION_REQUEST`, which is why
the builder has to be a backend that runs it.

It writes what the plugin writes, where the plugin writes it: `.humanize/rlcr/<timestamp>/`
with `state.md`, `goal-tracker.md`, and a prompt, summary, contract and review per round.

The two `parallel_flame_chase` flows are one runtime under two public names. They share a hidden
sibling module so their isolation and recovery semantics cannot drift apart, and differ in
whether the coordinator comes back: the base flow stops at durable peer coordination, and the
mission flow adds scoped evidence audits, interruptions and an integration queue. Both want
exactly seven agents, in the order the flow names them.

Read [Security](/user/security) before starting any of them.

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
repository — asks for the [shape of the answer](/reference/agents#answering-in-a-shape) and reads a
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
[Agents](/reference/agents#asking-them-for-a-shape-which-is-a-questionnaire).

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
the [provider](/reference/providers) whose account it runs as. A name, [where the work
lands](/reference/machines) and
[what it may do](/reference/agents#what-an-agent-may-do) are settings of the *agent* that no `-a` spells,
so a flow that needs one is handed agents built in Python — and a machine only where the flow's
own place for that agent [said `Remote`](#where-each-agent-works):

```python
from hmz.agents import ClaudeCodeAgent, ClaudeCodeAgentConfig
from hmz.runner import Runner

config = ClaudeCodeAgentConfig(model="claude-opus-4-8", effort="high")
agents = [
    ClaudeCodeAgent(config, name="actor"),
    ClaudeCodeAgent(config, name="reviewer"),
]

Runner("official/rlar", agents).run("fix the build")
```

`Runner` takes the same flow names and paths `-f` does, checks the count the same way, and
writes the same [epic](/reference/tracing#epics). See [Agents](/reference/agents) for what those objects can
do.

## Stopping

A flow ends when `run` returns — most of the built-in ones never do, and are ended from
outside:

- **ctrl+c** twice in the interface. (One press asks. A third does not wait for the flow to
  unwind: every conversation still open is closed under its turn, which the flow reads as a
  turn that failed.)
- **ctrl+c** on a `hmz exec` command line.
- **`agent.stop()`** from anywhere.

Every agent is told to take no further turn. The turn under way is closed out, and the next
call into that agent raises `Stopped` — which `suppress=True` deliberately does not catch,
because a loop that carried on past it would never end. Let it propagate; the
[epic](/reference/tracing#epics) then records the run as stopped by hand rather than as one that
finished.

What the turn was doing is left where it got to. A stop that waited for a turn would not read
as a stop — a model can think for minutes.

## Checking a flow

Two readings, before anything runs it — what [`hmz check`](/reference/cli#hmz-check) runs
from a command line, reachable as a library for a test or a loop that writes flows.

`checked` is the static one: pure `ast` over every file the flow's directory holds (what is
under its `skills/` excepted), executing nothing, so it is safe to point at a flow nobody has
read. It answers with findings rather than raising, one per thing found:

```python
from hmz.flows import checked

for one in checked(".humanize/flows/mine"):
    print(f"{one.where}:{one.line}: {one.severity}: {one.code}: {one.said}")
```

A `Finding` carries `code`, `severity`, `where`, `line` and `said`. An **error** is a flow
that cannot run, cannot be answered, or cannot end — something no run of it survives. A
**warning** is a flow that runs, and a run of it that may be regretted.

| Code | Severity | What it found |
| --- | --- | --- |
| `unread` | error | A file that will not parse. |
| `not-a-flow` | error | No `__init__.py`, or nothing marked `@flow()`. |
| `unsized-agents` | error | An `agents` annotation that does not state a fixed count. |
| `unread-annotation` | error | The annotation's names live under `TYPE_CHECKING`, where a run cannot read them. |
| `foreign-import` | error | An import of humanize's own modules other than `hmz.flows`. |
| `unknown-name` | error | `from hmz.flows import` a name it does not offer. |
| `unknown-ask` | error | An attribute asked of an agent, session or person that is not on the interfaces. |
| `dead-loop` | error | A constant-true loop with no `break`, `return` or `raise` inside it. |
| `sleeping-loop` | error | A constant-true loop that only sleeps: alive from outside, doing nothing. |
| `stateless-resume` | error | `@flow(resumable=True)` with nowhere to be handed its state. |
| `unbounded-loop` | warning | Every way out of a loop waits on an agent's verdict, and the function holds no bound of its own. |
| `unguarded-answer` | warning | A field read off a suppressed, shaped answer nothing tested against `None`. |
| `unknown-verdict` | warning | An answer's field compared against a value its shape does not offer, so the comparison can never be what it reads as. |
| `unsaid-moment` | warning | A hook hung on a moment only some backends run that no place declares. |
| `loose-config` | warning | A config whose `model_config` neither forbids extras nor freezes. |
| `unsaid-field` | warning | A config field without a `Field(description=...)`. |
| `unsaid-flow` | warning | An entry file without a docstring, so lists of flows show nothing for it. |
| `state-kept` | warning | Kept state something writes and nothing ever clears. |
| `twice-named` | warning | Two flows in one file under one name; the first wins. |

Every rule is the proof of an absence, worked out one function at a time — no exit in this
loop, no bound in this function, no guard on this name. Nothing claims an exit reachable or
follows a value through a call: a flow that keeps its loop in one function and its bound in
another is a flow the reading trusts.

`proved` is the second reading: the flow loaded and driven for real, in a subprocess per
scenario, by stubs that claim every capability over the real driver base classes — so the
hooks it hangs fire as they would, every turn lands at once, and each adds what the scenario
says to `spent()`. The parent holds the clock, sleeps are free, and the flow works in a
scratch directory taken away with the process.

```python
from hmz.flows import ALWAYS_DONE, NEVER_DONE, SILENT, proved

proof = proved(".humanize/flows/mine", scenarios=(NEVER_DONE, ALWAYS_DONE, SILENT))
assert proof.findings == ()
assert all(one.finished for one in proof.outcomes), proof.outcomes
```

A `Scenario` says how the world answers: every boolean field of a shaped answer says its
`verdict`, every string field its `answer`, each turn climbs `climb` output tokens, and the
proof ends at `turns` turns or `seconds` seconds, whichever the flow forces. Three are named:
`NEVER_DONE` is the reviewer that never says the work is done — a loop with a bound of its
own still ends here, which is the executable proof that a run can end; `ALWAYS_DONE` is the
shortest road through; `SILENT` answers every turn with nothing, which is what a failed turn
answers, so it is every guard tried at once. A flow the loading refuses comes back as a
`refused-load` finding, and the flow's live config model is read against the config rules
whether or not the static reading could see it.

And the catalogue, for the weaver — whoever, or whatever, is writing a flow against this
installation:

```python
from hmz.flows import briefed, catalogue

catalogue()   # one Capability per thing a flow may build on, with the backends that serve it
briefed()     # the same, rendered as one page to steer by
```

Read off the live interface at call time — the moments off the enum, the backend sets off
the driver classes' own declarations — so what it promises is what this installation serves.

## An atlas

An atlas is a flow whose body is read rather than run: a narrower Python, compiled before
anything happens into a **prophecy** — the graph of what the run will do. The guide is
[An atlas](/weaver/atlas); this is the surface.

```python
from hmz.flows import Agent, atlas, canonical, digest, logic, mind, prophesied, sub
```

| Mark | What it makes |
| --- | --- |
| `@atlas` | A flow whose body is a declaration. Takes everything `@flow` takes but `resumable`, which is always on. |
| `@mind` | A node that is one turn, handed the agent its call site names. Exactly one way out. |
| `@logic` | A node that is Python and drives nothing. May have several ways out. |
| `sub("official/x")` | The atlas one supernode is, by the name `-f` takes. |

`@mind` and `@logic` take `rerun=False` for a node a run picked up inside steps past rather
than runs again; such a node answers with nothing.

Neither an atlas nor a node may be `async def`: the walk does not await, and what waits for
a model is a turn, which is what a `mind` already is.

An atlas's entry point takes its agents as a `NamedTuple` of them, then the one thing it is
called with — `str` for one a command line runs, a model for one that is only ever a
supernode — and then, for one that says it can be set up, a config:

```python
@atlas
def run(agents: Agents, task: str, config: Config | None = None) -> None: ...
```

Every field of that config needs a default: a run may be started without one, an atlas's body
has no way to write `config or Config()`, so a run nobody set up is handed the model's own
defaults.

### The body

One node per statement; the branches between them are the edges. Nothing else:

| | |
| --- | --- |
| `x = call(a, b)` | one node, bound to `x` |
| `call(a, b)` | one node whose answer nothing takes |
| `if x:` / `if not x.field:` | a node's several ways out |
| `while x:` / `while not x.field:` | that, with an edge back to the node the test reads |
| `return` / `return x` | the end of the run |
| `pass`, the docstring | nothing |

Arguments are names the body bound, one field read off one of them, or `agents.<name>`, the
name the entry point gave what it is called with, or the name it gave its config.

### The prophecy

```python
from hmz.flows import canonical, digest, prophesied

held = prophesied(".humanize/flows/mine")
if held.prophecy is not None:
    print(canonical(held.prophecy), digest(held.prophecy))
```

`prophesied` answers with `(findings, prophecy)`, the prophecy being None where anything was
an error. A `Prophecy` holds its `name`, what it `takes`, `gives` and can be set up with as a
`config`, the `agents` it drives, its `nodes`, its `edges`, the `shapes` that flow along them,
and one `Prophecy` per supernode under it. A `Node` carries `at` (its id — the callee, and
`:2`, `:3` for the second and third call to it), `kind`, `calls`, `takes`, `binds`, `gives`,
`rerun` and `under`. An `Edge` carries `out_of`, `into`, a `When` or None, and — for a way out
of the prophecy — the name the run `answers` with; `""` is the way in at one end and the way
out at the other.

`canonical` is one line of JSON with everything ordered by what it is rather than where it was
written, so two readings of one atlas are the same bytes; `digest` is what a run picked up
again checks itself against.

### What an atlas is refused for

Every one of these is an error, and every one is decidable — which is the bargain the narrower
Python makes. The warnings in the table above still come back over the node bodies, and still
do not block.

| Code | What it found |
| --- | --- |
| `not-an-atlas` | Nothing marked `@atlas`, or a `sub()` naming a flow that is not one. |
| `unstatic-body` | A statement the body may not hold — work, a call inside a call, `elif`, `try`, `async`, a graph with no nodes. |
| `unshaped-node` | A node parameter or answer annotated with something that is no shape. |
| `shape-mismatch` | What flows along an edge is not what the far end takes, or a name bound twice at two shapes. |
| `unbound-read` | A body reads a name nothing has bound. |
| `branching-mind` | A branch hung off a turn, which has one way out. |
| `dead-loop` | A loop whose body changes nothing its head reads. |
| `unnamed-agents` | Agents declared as a plain tuple, so a turn cannot name the one it drives. |
| `unknown-agent` | `agents.x` the flow does not drive, or a supernode driving one it has not got. |
| `unagented-node` | A logic handed an agent, or a mind handed none. |
| `skipped-answer` | `rerun=False` on a node that answers with something. |
| `circular-atlas` | A supernode reaching back into a graph already being compiled. |
| `dynamic-call` | An atlas importing `load`, which answers with a flow that may be anything. |
| `unset-config` | A config with a field that has no default, which a run nobody set up cannot be handed. |
| `twice-round` | A loop body ending with the node the loop reads again, which would run it twice a round. |
| `stale-prophecy` | A shipped `prophecy.pkl` that is not what the source now compiles to. |

### Shipping one

A flow's directory may hold `prophecy.pkl` beside its entry point, and where it does that is
what runs rather than the atlas compiled again:

```python
from hmz.sdk import Hmz

Hmz().flows.foretell("official/review")   # writes the prophecy beside the flow
Hmz().flows.prophecy("official/review")   # reads what the source compiles to
```

or [`hmz check --ship`](/reference/cli#hmz-check) from a command line. The flow's own Python
still has to be there: a prophecy names the functions its nodes are. The shipped-file reader
rebuilds only the seven allowlisted tuple types a prophecy uses and validates the resulting
shape. Any other class or malformed shape is refused; loading the flow's Python remains the
separate trust boundary described in [Security](/user/security).

## Testing a flow

A flow is a function, so drive it with something that is not a coding agent:

```python
from collections.abc import Iterator

from hmz.agents import AgentBase, AgentConfig, Event, SessionBase

class FakeSession(SessionBase):
    def _stream(
        self, prompt: str, *, schema: type[BaseModel] | None = None
    ) -> Iterator[Event]:
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
from hmz.flows import drives

assert drives("my_loop") == ("actor", "reviewer")
```

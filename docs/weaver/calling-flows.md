# A flow that calls a flow

`load` runs one flow from inside another, hands it the agents it declares, and passes
settings and skills through. Reach for it when one flow is a reusable step another weaver
builds on — which is what turns a flowverse into a library rather than a menu.

## Call one

`load` hands you the flow itself, which you run with the agents you already have:

```python
# .humanize/flows/planned/__init__.py
"""Plan it with humanize1, then build it three rounds."""

from hmz.flows import Agent, flow, load


@flow
def run(agents: tuple[Agent, Agent], task: str) -> None:
    plan = load("official/humanize1:gen-plan")
    plan(agents, f"plan this first: {task}")
    for _ in range(3):
        agents[0].new()(task)
```

```sh
hmz exec -f planned -a claude/claude-opus-5:max -a codex/gpt-5.6-sol:max "add undo to the editor"
```

`load` accepts `ralph_loop`, `official/rlar`, `humanize1:gen-plan`, a path of your own —
anything `-f` takes. **A name nothing answers to is refused where you ask for it**, not an hour
into your loop.

## Hand it the agents it declares

Pass a list or a tuple of the agents that flow declares, **in the order it declares them**. It
arrives as that flow's own `NamedTuple`, named the way that flow names them:

```python
load("official/rlar")([builder, checker], task)     # arrives as Agents(actor=…, reviewer=…)
```

To find out what a flow wants without driving it:

```python
from hmz.flows import drives, wanted

drives("official/rlar")     # ("actor", "reviewer")
wanted("official/rlar")     # one Place per agent: .name, .moments, .goal, .where
```

**Nothing is renamed.** The agents belong to the run you started: your `builder` is still
`builder` in the [trace](/user/tracing), whatever the called flow calls the place it filled.

## Pass settings through

A flow that takes [settings of its own](/weaver/flow-settings) takes them here too, as a third
argument. Pass an instance of that flow's model, or the fields to build one from:

```python
load("official/rlar")(agents, task, {"rounds": 9})
```

The settings are read back through the flow's own model **at the moment it is called**. A flow
that takes no settings, or different ones, says so instead of quietly ignoring them.

## Say what it is driven at

A call may also say what the flow it is calling runs at, which is `drives` — the name of one of
the called flow's places, or of the agent filling it, and the config that branch runs at:

```python
from dataclasses import replace

careful = replace(agents.reviewer.config, effort="max")
load("official/rlar")(agents, task, {"rounds": 9}, drives={"reviewer": careful})
```

What fills that place is a **clone** at that config rather than your agent set up again — an
agent is what it was made as, so two efforts are two agents, and a trace that read them as one
would read a comparison as one agent changing its mind. The clone is the call's own: written
into that call's record, carrying the called flow's skills, and gone when the call returns.
Your own agent is untouched.

A name the flow does not drive is refused where you wrote it. So is the person at the prompt,
who takes no turn anywhere and so runs nothing to be driven at.

## Await a coroutine flow

A called flow answers with whatever it answers with, and one written as `async def` is awaited
by whoever called it:

```python
@flow
async def run(agents: tuple[Agent], task: str) -> None:
    await load("official/rlar")(agents, task)
```

## Run several calls at once

Gather them. Each is a branch of the run in its own right: its own record, its own skills, its
own place on the [status line](#see-that-both-are-running), and its own unwinding when the run
is stopped.

```python
@flow
async def run(agents: tuple[Agent, Agent], task: str) -> None:
    await asyncio.gather(
        load("official/rlar")([agents[0].clone()], task),
        load("official/rlar")([agents[1].clone()], task),
    )
```

**Give each branch an agent of its own.** A conversation belongs to one agent, so two branches
driving the same agent are two flows sharing one — and a session it opens then belongs to
neither of them. humanize does not guess: an agent two calls hold at once goes on writing where
they were both called from, and carries what *that* flow gave it. `clone()` (or `drives=`) is
how a branch gets one to itself.

## Call as deep as you like

A flow may call itself, and may work out how deep to go from its own settings or from what a
model just said:

```python
@flow
async def run(agents: tuple[Agent], task: str, config: Config | None = None) -> None:
    setting = config or Config()
    if setting.left <= 0:
        agents[0].new()(task)
        return
    await asyncio.gather(*(
        load("split")([agents[0].clone()], part, {"left": setting.left - 1})
        for part in split(task)
    ))
```

Every level is tracked on the branch it is on, and the [epic](/user/tracing) reads back as the
tree it ran as: a record per call, inside the record of the call that made it.

**A chain of calls has a bottom: 64.** Deeper than that is refused, naming the flow and how it
got there. A recursion with no base case would otherwise end as a `RecursionError` out of
whatever the innermost call happened to be importing, which names no flow and blames the wrong
line.

## Pass wrapper skills through

A called flow carries its own skills by default. A wrapper whose purpose is to add a reusable
capability can keep its skills available inside the called flow:

```python
load("official/rlar", inherit_skills=True)(agents, task)
```

On a name clash the child wins. Parent-only skills follow it, and the agents return carrying
exactly what they had before the call. Keep the default isolation for reviewers and other flows
that should not receive the caller's capabilities.

## Let a flow talk to you

You may hand a flow that drives [the person](/weaver/human-agent) one fewer agent. Nobody
chooses what the person runs. Hand over your own if you have one, so that what it asks reaches
whoever is at the prompt:

```python
class Agents(NamedTuple):
    assistant: Agent
    human: Person


@flow
def run(agents: Agents, task: str) -> None:
    load("chat")((agents.assistant, agents.human), task)
```

## See that both are running

```python
from hmz.flows import running

running()                       # one Running(flow, since, depth, under) apiece
[one.flow for one in running()] # ["planned", "official/humanize1:gen-plan"]
```

Asked from inside a flow, this is **the branch you are on**: the flow somebody started, then
each flow that had to be called to get here, innermost last. Never a sibling — a call gathered
beside yours is not running under you and is none of your business — and never one level twice,
however many of that level are running at once.

Asked from outside every flow — the interface drawing its status line, a crash report being
written — it is every flow of the run, oldest first, each saying how `deep` it is and what it is
`under`. That is what the interface reads: it names them on its status line and on `/status` as
`chat ▸ official/rlar`. The [epic](/user/tracing#what-a-run-writes-down) records each call and
each return.

A flow that called another does not read as the flow somebody chose. That is the point: a
five-hour trace where phase two was `gen-plan` should say so.

## Several flows in one file

Three phases of one thing are one thing to write and three to run. Give each mark a name:

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

Each declares its own agents and its own settings: the agents page asks two questions rather
than five, and setting one up shows one phase's flags rather than three phases' at once. What
passes between them is whatever they write, usually a file.

**The name is what you write in the mark and nothing else.** A name written down where a flow
is run should not change under whoever renames the function. `@flow(about="…")` says what it
does where flows are listed, which is otherwise the first line of its docstring.

`@flow` **marks; it does not wrap.** The function is called exactly as it was.

## See also

- [Hooks](/weaver/hooks) — getting between an agent and its turn.
- [Many turns at once](/weaver/async-flows)
- [Flow settings](/weaver/flow-settings)
- [Tracing](/user/tracing)

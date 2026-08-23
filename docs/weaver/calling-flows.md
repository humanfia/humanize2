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

## Await a coroutine flow

A called flow answers with whatever it answers with, and one written as `async def` is awaited
by whoever called it:

```python
@flow
async def run(agents: tuple[Agent], task: str) -> None:
    await load("official/rlar")(agents, task)
```

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

running()                       # one Running(flow, since) apiece, in the order they started
[one.flow for one in running()] # ["planned", "official/humanize1:gen-plan"]
```

This lists the flow you started and whatever it called, **innermost last**. The interface names
them on its status line and on `/status` as `chat ▸ official/rlar`. The
[epic](/user/tracing#what-a-run-writes-down) records each call and each return.

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

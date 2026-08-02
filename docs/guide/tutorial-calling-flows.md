# 10 · A flow that calls a flow

**Ten minutes.** A loop worth having is one another loop can reach for — so a flowverse is a
library as well as a menu.

::: tip Before you start
[Many turns at once](/guide/tutorial-async-flow), and the official flowverse fetched
([tutorial 3](/guide/tutorial-two-agents)).
:::

## Step 1 — call one

`calls` takes exactly what `-f` takes, and hands you the flow itself to run with the agents you
already have:

```python
# .humanize/flows/planned.py
"""Plan it with humanize1, then build it three rounds."""

from hmz.agents import AgentBase
from hmz.flows import flow
from hmz.runner import calls


@flow
def run(agents: tuple[AgentBase, AgentBase], task: str) -> None:
    plan = calls("official/humanize1:gen-plan")
    plan(agents, f"plan this first: {task}")
    for _ in range(3):
        agents[0].new()(task)
```

```sh
hmz exec -f planned -a claude/claude-opus-5:max -a codex/gpt-5.6-sol:max "add undo to the editor"
```

`calls` takes `ralph_loop`, `official/rlar`, `humanize1:gen-plan`, a path of your own — anything
`-f` takes. **A name nothing answers to is refused where you ask for it**, rather than an hour into
your loop.

## Step 2 — hand it the agents it declares

A flow that drives one is called with one, **in the tuple it declared them as**. Pass a list or a
tuple and it arrives as that flow's own `NamedTuple`, named the way that flow names them:

```python
calls("official/rlar")([builder, checker], task)     # arrives as Agents(actor=…, reviewer=…)
```

To find out what a flow wants without driving it:

```python
from hmz.runner import drives, wanted

drives("official/rlar")     # ("actor", "reviewer")
wanted("official/rlar")     # one Place per agent: .name, .moments, .goal, .where
```

**Nothing is renamed.** The agents belong to the run that was started, and what has already been
written down about them stays true — your `builder` is still `builder` in the
[trace](/features/tracing), whatever the called flow calls the place it filled.

## Step 3 — pass settings through

A flow that takes [settings of its own](/guide/tutorial-flow-settings) takes them here too, as a
third argument — an instance of that flow's model, or the fields to build one from:

```python
calls("official/rlar")(agents, task, {"rounds": 9})
```

They are read back through the flow's own model **at the moment it is called**, so a flow that
takes no settings, or takes different ones, says so rather than quietly ignoring them.

## Step 4 — await one that is a coroutine

A called flow answers with whatever it answers with, so one written as `async def` is awaited by
whoever called it:

```python
@flow
async def run(agents: tuple[AgentBase], task: str) -> None:
    await calls("official/rlar")(agents, task)
```

## Step 5 — a flow that talks to you

A flow that drives [the person](/features/human-agent) may be handed one fewer agent, since nobody
chooses what the person runs. Hand over your own if you have one, so that what it asks reaches
whoever is at the prompt:

```python
class Agents(NamedTuple):
    assistant: AgentBase
    human: HumanAgent


@flow
def run(agents: Agents, task: str) -> None:
    calls("chat")((agents.assistant, agents.human), task)
```

## Step 6 — see that both are running

```python
from hmz.runner import running

running()                       # one Running(flow, since) apiece, in the order they started
[one.flow for one in running()] # ["planned", "official/humanize1:gen-plan"]
```

The flow that was started and whatever it called, **innermost last**. The interface names them on
its status line and on `/status` — `chat ▸ official/rlar` — and the
[cycle](/features/tracing#what-a-run-writes-down) records each call and each return.

A flow that called another does not read as the flow somebody chose. Which is the point: a
five-hour trace where phase two was `gen-plan` should say so.

## The related feature: several flows in one file

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

Each declares its own agents and its own settings, so `/agents` asks two questions rather than
five and `/config` shows one phase's flags rather than three phases' at once. What passes between
them is whatever they write — a file, usually.

**The name is what you write in the mark and nothing else.** A name written down where a flow is
run should not change under whoever renames the function. `@flow(about="…")` says what it does
where flows are listed, which is otherwise the first line of its docstring.

`@flow` **marks; it does not wrap.** The function is called exactly as it was.

## What you now know

- `calls(name)` takes what `-f` takes and is refused immediately for a name nothing answers to.
- Hand a called flow the agents it declares; nothing is renamed.
- Settings pass as a third argument, checked against that flow's model.
- `@flow(name="…")` puts three flows in one file.

## Next

[Hooks](/guide/tutorial-hooks) — getting between an agent and its turn.

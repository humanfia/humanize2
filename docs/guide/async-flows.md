# Many turns at once

Write `async def run` and a flow can have as many turns going at once as it likes. Reach for
it when you need two hundred files fixed at the same time, or when a flow has to wait for more
than one thing.

## Write the flow as a coroutine

To run more than one turn at a time, the loop has to wait for several things at once. Write
`async def run`:

```python
# .humanize/flows/fanout/__init__.py
"""One agent, one turn per file, all of them going at once."""

import asyncio
from pathlib import Path

from hmz.flows import Agent, flow


@flow
async def run(agents: tuple[Agent], task: str) -> None:
    (agent,) = agents
    paths = sorted(str(p) for p in Path("src").rglob("*.py"))
    said = await agent.abatch([f"{task}\n\nThe file is {p}." for p in paths], at_once=8)
    print(f"{len(said)} files, {sum(1 for s in said if s)} answered")
```

**Nothing about starting it changes.** `hmz exec -f fanout …` and the interface run a coroutine
flow the same way they run any other, on a loop of the flow's own. The run is over when `run`
returns. The agent count, the settings, the [cycle](/guide/tracing#what-a-run-writes-down) and
the way it is stopped are all exactly as for a plain function.

```sh
hmz exec -f fanout -a claude/claude-opus-4-8:high "add type annotations to this module"
```

::: tip A flow that awaits nothing should not be `async`
Write `def run` unless it has something to wait for. Both are flows; neither is the newer one.
:::

## Run many turns with `batch`

`batch` calls the agent once for each prompt, all at the same time. Each prompt gets **one
session apiece, none of them kept**, and the answers come back in the order you asked.

```python
answers = agent.batch([f"Review {path}" for path in paths])       # blocking
answers = await agent.abatch([...])                               # awaited
reviews = agent.batch(prompts, schema=Review, suppress=True)      # shaped, and || true
```

**How wide** a batch runs is a question about the machine, not about this library, so nothing
caps it. A batch runs at once whatever it is given. `at_once` is where a flow says otherwise,
and every prompt lands either way. The rest queue behind the ones running:

```python
agent.batch(prompts, at_once=32)
```

## Handle a failing batch

A batch that is **not** suppressing raises the first failure once every turn of it has landed.
A turn already running cannot be taken back. A batch that let the failure out early would leave
the other turns running with nobody waiting for them.

`suppress=True` answers `""` in that prompt's place and lets the rest through. With a schema,
it answers `None` instead:

```python
said = await agent.abatch(prompts, suppress=True)
failed = [p for p, s in zip(prompts, said, strict=True) if not s]
```

An agent [stopped](/guide/stopping) mid-batch raises `Stopped`, which `suppress` deliberately
does not catch.

## Gather turns that differ

`batch` is one agent over many prompts. When the turns differ, such as two agents or one agent
in several directories, use `asyncio.gather` over the awaited calls:

```python
acted, reviewed = await asyncio.gather(
    agents.actor.aturn(task, suppress=True),
    agents.reviewer.aturn(REVIEW + task, suppress=True),
)
```

Every call that runs a turn has a twin that is awaited, with the same arguments, the same
answers and the same `suppress` and `schema`:

```python
await agent.aturn(task)                  # agent(task), in a session of its own
await session.aturn("continue")          # session("continue")
await agent.apursue(objective)           # agent.pursue(objective)
await agent.abatch(prompts)              # agent.batch(prompts)
```

The difference is where the waiting happens. The turn runs on a thread of its own, and the loop
is handed straight back.

## Run one agent in several directories

This is the pattern that matters. A worktree per task, a checkout per shard: **a session
apiece**, and their turns going together.

```python
import subprocess

@flow
async def run(agents: tuple[Agent], task: str) -> None:
    (agent,) = agents
    trees = []
    for name in ("parser", "printer", "cli"):
        at = f"/tmp/work/{name}"
        subprocess.run(["git", "worktree", "add", "-B", name, at], check=True)
        trees.append(at)

    held = [agent.new(at) for at in trees]
    said = await asyncio.gather(
        *(one.aturn(task, suppress=True) for one in held)
    )
```

Either way the agent is **one agent**: one set of settings, one id, one place in the trace.
What differs is where each conversation is rooted. See [Worktrees](/guide/worktrees).

## Create ten thousand conversations up front

A session costs nothing until a turn lands in one:

```python
sessions = agent.batch_new(10_000)
await asyncio.gather(*(one.aturn(f"shard {at}") for at, one in enumerate(sessions)))
```

## The one rule that trips people

**Turns of one session are still a sequence**, whoever awaits them. Two turns awaited on one
session run one after the other, exactly as two called on it do. A conversation is a
conversation.

```python
await asyncio.gather(session.aturn("a"), session.aturn("b"))   # sequential, not parallel
await asyncio.gather(first.aturn("a"), second.aturn("b"))      # two turns at once
```

Two turns at once means two **sessions**.

## Reading a fan-out at the prompt

Above the editor, you see one agent with `1 of 200`. **tab** and **shift+tab** step between the
conversations that are working — not all two hundred, only the ones thinking right now. The
screen keeps the last eight conversations and the last two thousand lines of each. The rest is
in the [trace](/guide/tracing). See [Many conversations at once](/guide/conversations).

## See also

- [Many conversations at once](/guide/conversations) for the editor view of every conversation
  that is working.
- [Worktrees](/guide/worktrees) for rooting each conversation where you want it.
- The [trace](/guide/tracing) keeps everything a run writes down.
- An agent [stopped](/guide/stopping) mid-batch raises `Stopped`.

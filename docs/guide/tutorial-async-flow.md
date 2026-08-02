# 9 · Many turns at once

**Fifteen minutes.** Two hundred files fixed at the same time, and a flow that waits for more than
one thing.

::: tip Before you start
[Settings of its own](/guide/tutorial-flow-settings). Some Python `asyncio` familiarity helps but
is not required.
:::

## Step 1 — write the flow as a coroutine

A loop that has more than one turn going at a time has to be able to wait for several things at
once. So write `async def run`:

```python
# .humanize/flows/fanout.py
"""One agent, one turn per file, all of them going at once."""

import asyncio
from pathlib import Path

from hmz.agents import AgentBase
from hmz.flows import flow


@flow
async def run(agents: tuple[AgentBase], task: str) -> None:
    (agent,) = agents
    paths = sorted(str(p) for p in Path("src").rglob("*.py"))
    said = await agent.abatch([f"{task}\n\nThe file is {p}." for p in paths], at_once=8)
    print(f"{len(said)} files, {sum(1 for s in said if s)} answered")
```

**Nothing about starting it changes.** `hmz exec -f fanout …` and the interface run a coroutine
flow the same way they run any other, on a loop of the flow's own, and the run is over when `run`
returns. The agent count, the settings, the [cycle](/features/tracing#what-a-run-writes-down) and
the way it is stopped are all exactly as for a plain function.

```sh
hmz exec -f fanout -a claude/claude-opus-4-8:high "add type annotations to this module"
```

::: tip A flow that awaits nothing should not be `async`
Write `def run` unless it has something to wait for. Both are flows; neither is the newer one.
:::

## Step 2 — `batch`: many turns, one line

`batch` is calling the agent, as many times over as there are prompts, all of them going at the
same time — **one session apiece, none of them kept**, and the answers in the order they were
asked for.

```python
answers = agent.batch([f"Review {path}" for path in paths])       # blocking
answers = await agent.abatch([...])                               # awaited
reviews = agent.batch(prompts, schema=Review, suppress=True)      # shaped, and || true
```

**How wide** is a question about the machine, not about this library, so nothing caps it: what a
batch is given is what it runs at once. `at_once` is where a flow says otherwise, and every prompt
lands either way — the rest queue behind the ones running:

```python
agent.batch(prompts, at_once=32)
```

## Step 3 — how a batch fails

A batch that is **not** suppressing raises the first failure **once every turn of it has landed**.
A turn already running cannot be taken back, and a batch that let the failure out from under the
others would leave them running with nobody waiting for them.

`suppress=True` answers `""` — or `None`, with a schema — in that prompt's place and lets the rest
through:

```python
said = await agent.abatch(prompts, suppress=True)
failed = [p for p, s in zip(prompts, said, strict=True) if not s]
```

An agent [stopped](/features/stopping) mid-batch raises `Stopped`, which `suppress` deliberately
does not catch.

## Step 4 — `gather`, for turns that are not all the same

`batch` is one agent, many prompts. When the turns differ — two agents, or one agent in several
directories — use `asyncio.gather` over the awaited calls:

```python
acted, reviewed = await asyncio.gather(
    agents.actor.aturn(task, suppress=True),
    agents.reviewer.aturn(REVIEW + task, suppress=True),
)
```

Every call that runs a turn has a twin that is awaited, with the same arguments, the same answers
and the same `suppress` and `schema`:

```python
await agent.aturn(task)                  # agent(task), in a session of its own
await session.aturn("continue")          # session("continue")
await agent.apursue(objective)           # agent.pursue(objective)
await agent.abatch(prompts)              # agent.batch(prompts)
```

The difference is where the waiting happens: the turn runs on a thread of its own and the loop is
handed straight back.

## Step 5 — one agent, several directories

The pattern that matters. A worktree per task, a checkout per shard: **a session apiece**, and
their turns going together.

```python
import subprocess

@flow
async def run(agents: tuple[AgentBase], task: str) -> None:
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

Either way the agent is **one agent**: one set of settings, one id, one place in the trace. What
differs is where each conversation is rooted. See [Worktrees](/features/worktrees).

## Step 6 — ten thousand conversations that have not started

A session costs nothing until a turn lands in one:

```python
sessions = agent.batch_new(10_000)
await asyncio.gather(*(one.aturn(f"shard {at}") for at, one in enumerate(sessions)))
```

## The one rule that trips people

**Turns of one session are still a sequence**, whoever awaits them. Two turns awaited on one
session are one after the other, exactly as two called on it are — a conversation is a
conversation.

```python
await asyncio.gather(session.aturn("a"), session.aturn("b"))   # sequential, not parallel
await asyncio.gather(first.aturn("a"), second.aturn("b"))      # two turns at once
```

Two turns at once means two **sessions**.

## Reading a fan-out at the prompt

Above the editor, one agent with `1 of 200`. **tab** and **shift+tab** step between the
conversations that are working — not all two hundred, only the ones thinking right now. What is
kept on screen is the last eight conversations and the last two thousand lines of each; the rest
is in the [trace](/features/tracing). See
[Many conversations at once](/features/conversations).

## What you now know

- `async def run` is a flow like any other; nothing about starting it changes.
- `batch`/`abatch` for many of the same turn; `gather` over `aturn` for turns that differ.
- `at_once` bounds the width; nothing else does.
- One session is one sequence, however you await it.

## Next

[A flow that calls a flow](/guide/tutorial-calling-flows).

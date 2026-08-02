# Worktrees

One agent working in several places at once.

A session is opened **at** a directory, and every turn of it runs there. So a worktree per task, a
checkout per shard, or a package per reviewer is a session apiece — one agent, one set of
settings, one id, one [trace](/features/tracing).

```python
held = [agent.new(worktree) for worktree in worktrees]
said = await asyncio.gather(*(one.aturn(task) for one in held))
```

## Why it is a session's setting

Because that is what it is to these backends: a conversation is rooted at a directory, and every
turn of it is there. It is not a per-turn argument, and it cannot be changed once the session is
open.

Left unsaid, a session works in the directory the flow is running in — which is what every session
was before there was anywhere else to put one.

```python
session = agent.new(worktree)     # this conversation works in that directory
session("pwd")                    # and so does every turn of it
session.cwd                       # where that is, as an absolute path
```

## Every call that opens a session takes it

```python
agent.new(worktree)                          # the session, to hold and to keep talking to
agent("fix the tests", cwd=worktree)         # one turn in a session of its own, there
agent.pursue(objective, cwd=worktree)
await agent.aturn(task, cwd=worktree)        # and await agent.apursue(objective, cwd=…)
agent.batch(prompts, cwd=worktree)           # every turn of the batch, there
await agent.abatch(prompts, cwd=worktree)
agent.batch_new(200, worktree)               # two hundred conversations, all in that one
```

`cwd=` on a batch is **one** directory for all of its turns. A batch *across* directories is the
`gather` at the top of this page.

## A worked fan-out

Git worktrees, one branch each, all going at once:

```python
import asyncio
import subprocess
from pathlib import Path

from hmz.agents import AgentBase
from hmz.flows import flow

@flow
async def run(agents: tuple[AgentBase], task: str) -> None:
    (agent,) = agents
    trees = []
    for name in ("parser", "printer", "cli"):
        at = Path("/tmp/work") / name
        subprocess.run(["git", "worktree", "add", "-B", name, str(at)], check=True)
        trees.append(at)

    held = [agent.new(at) for at in trees]
    said = await asyncio.gather(
        *(one.aturn(f"{task}\n\nYou are working on the {at.name} part.", suppress=True)
          for one, at in zip(held, trees, strict=True))
    )
```

Each conversation sees its own checkout, so three agents cannot tread on each other's index — and
each is still the same agent, at the same model and effort, in one place in the trace.

## Refused before the turn runs

A directory that is not there, or one outside the workspace an
[anchored](/features/remote-execution) agent's turns land in, raises `ValueError` before anything
is run:

```text
/srv/nowhere: no directory to open a session in
/tmp/elsewhere is not inside /srv/project, which is the workspace this agent's turns land in
```

Which is a flow to correct rather than a backend that failed to start.

## For an anchored agent, the path is the target's

humanize puts the agent in this machine's mirror of the directory and tells the anchor to run the
work in the directory itself. So a flow names where the work happens in the only names the far end
has. See [Remote execution](/features/remote-execution).

## How wide to go

Nothing here caps it. How many turns a machine can carry is a question about the machine, not
about this library — so what a batch is given is what it runs at once, and `at_once` is where a
flow says otherwise:

```python
agent.batch(prompts, at_once=32)    # thirty-two going, however many prompts
```

Every prompt lands either way; the rest queue behind the ones running.

A session costs nothing until a turn lands in one, so `agent.batch_new(10_000)` is a list of ten
thousand conversations that have not started.

## See also

- [Many conversations at once](/features/conversations) — reading them at the prompt
- [Tutorial: many turns at once](/guide/tutorial-async-flow)
- [Agents › The directory a session works in](/reference/agents#the-directory-a-session-works-in)

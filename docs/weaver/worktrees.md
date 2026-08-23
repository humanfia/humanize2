# Worktrees

A **worktree** is the directory a session works in. Open each task in its own worktree when you
want one agent working in several places at once: a worktree per task, a checkout per shard, or
a package per reviewer. Each conversation is still one agent with one set of settings, one id,
and one [trace](/user/tracing).

## Try it

```python
session = agent.new(worktree)     # this conversation works in that directory
session("pwd")                    # and so does every turn of it
session.cwd                       # where that is, as an absolute path
```

Leave it unset and the session works in the directory the flow runs in — where every session
worked before there was anywhere else to put one.

## Why a worktree is a session setting

Because that is what it is to the backends. A conversation is rooted at a directory and every
turn of it runs there. It is not a per-turn argument, and you cannot change it once the session
is open.

## Every call that opens a session takes a worktree

```python
agent.new(worktree)                          # the session, to hold and to keep talking to
agent("fix the tests", cwd=worktree)         # one turn in a session of its own, there
agent.pursue(objective, cwd=worktree)
await agent.aturn(task, cwd=worktree)        # and await agent.apursue(objective, cwd=…)
agent.batch(prompts, cwd=worktree)           # every turn of the batch, there
await agent.abatch(prompts, cwd=worktree)
agent.batch_new(200, worktree)               # two hundred conversations, all in that one
```

`cwd=` on a batch is **one** directory for all of its turns. A batch *across* directories is
the `gather` below.

## A worked fan-out

Create a Git worktree per branch and run all three at once:

```python
import asyncio
import subprocess
from pathlib import Path

from hmz.flows import Agent, flow

@flow
async def run(agents: tuple[Agent], task: str) -> None:
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

Each conversation sees its own checkout, so the three agents cannot tread on each other's
index. Each is still the same agent at the same model and effort, in one place in the trace.

## Refused before the turn runs

If the directory does not exist, or it is outside the workspace an
[anchored](/user/remote-execution) agent's turns land in, humanize raises `ValueError` before
anything runs:

```text
/srv/nowhere: no directory to open a session in
/tmp/elsewhere is not inside /srv/project, which is the workspace this agent's turns land in
```

That is a flow to correct rather than a backend that failed to start.

## For an anchored agent, the path is the target's

humanize puts the agent in this machine's mirror of the directory, then tells the anchor to run
the work in the directory itself. A flow names where the work happens using the only names the
far end has. See [Remote execution](/user/remote-execution).

## How wide to go

Nothing here caps how wide you can go. How many turns a machine can carry is a question about
the machine, not about this library. A batch runs what it is given all at once, and `at_once`
is where a flow says otherwise:

```python
agent.batch(prompts, at_once=32)    # thirty-two going, however many prompts
```

Every prompt lands either way; the rest queue behind the ones running. A session costs nothing
until a turn lands in one, so `agent.batch_new(10_000)` is a list of ten thousand conversations
that have not started.

## See also

- [Many conversations at once](/user/conversations) — reading them at the prompt
- [Many turns at once](/weaver/async-flows) — a flow that awaits
- [Agents › The directory a session works
  in](/reference/agents#the-directory-a-session-works-in)

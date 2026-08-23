# Callbacks as tools

A flow drives an agent by saying things to it. This is the other direction: **a function the
flow wrote, put in front of the agent as a tool**. The agent reaches for it, your code runs —
in the flow's process, with the flow's variables — and what it answers is what the agent reads
back.

Reach for it when the agent needs something only the flow has: another agent, another flow, a
queue, a database, a decision that is yours to make.

## Try it

```python
# .humanize/flows/delegating/__init__.py
"""Build here, and let the builder call the reviewer whenever it wants one."""

from typing import NamedTuple

from pydantic import BaseModel, Field

from hmz.flows import Agent, Tool, flow


class Reviewing(BaseModel):
    """What the builder calls the review tool with."""

    path: str = Field(description="the file to have read")


class Agents(NamedTuple):
    builder: Agent
    reviewer: Agent


@flow
def run(agents: Agents, task: str) -> None:
    working = agents.builder.new()
    working.offers(
        [
            Tool(
                name="review",
                about="have the reviewer read one file and say what is wrong with it",
                takes=Reviewing,
                call=lambda said: agents.reviewer(f"Review {said.path}. Be brief."),
            )
        ]
    )
    working(f"{task}\n\nUse the review tool before you say you are done.")
```

```sh
hmz exec -f delegating -a claude/claude-opus-5:max -a codex/gpt-5.6-sol:high "write the parser"
```

The builder decides when it wants a review, and the reviewer's turn happens inside the
builder's — which is a thing no prompt can arrange.

## An agent that calls a flow

The callback is the flow's own code, so it may do whatever the flow may do. Including start
another flow and wait for it:

```python
from hmz.flows import Tool, load


class Chasing(BaseModel):
    task: str = Field(description="what to have the loop do")


working.offers(
    [
        Tool(
            name="chase",
            about="run the flame-chase loop on one task and report what it came to",
            takes=Chasing,
            call=lambda said: load("official/flame_chase")(agents, said.task),
        )
    ]
)
```

That is an agent deciding, mid-turn, that a piece of work wants a loop of its own — and getting
one. Nothing about it is written into any backend.

## What a `Tool` is

| | |
| --- | --- |
| `name` | what the agent calls it. Name it for what it does; that is what a model reaches by |
| `about` | what it is for, said to the model. The whole of what it knows about *when* to use it, so write a sentence |
| `takes` | a pydantic model of the arguments, or `None` for a tool that takes nothing. The model is the whole of what the agent is told — fields, types, which are required, and each `description` |
| `call` | what to run. Given the model (nothing where `takes` is `None`). What it answers goes back to the agent as text; `None` reads as *done* |

## Where it is said

On the **conversation**, because that is where a flow is when it has something to offer:

```python
working.offers([...])      # from the next turn on
working.offers(None)       # and now it is offering none
```

A CLI is told about its tools where it is started, and some of these are started once per
agent, so what is actually in front of the model is the **agent's** list: two conversations of
one agent offering a tool of one name are offering one tool. Changing that list between two
turns — offering one, taking one back, or swapping one for another — restarts the Claude
holding the conversation, and the Codex app server that agent holds, and resumes the same
conversation: a process that was started without the tool has never heard of it, and one
started with a tool that is gone can still reach for it. Because the list is the agent's, that
is agent-wide — every live session of the agent starts a new process at its next turn, and a
conversation closing takes its own offer back, so opening and dropping conversations in a loop
restarts a sibling once per drop.

## Which backends take one

```python
session.takes_tools      # True where the flow's callbacks can reach this backend
```

| backend | how |
| --- | --- |
| `claude` | `--mcp-config` on its own command line |
| `codex` | `-c mcp_servers.humanize…` on the app server this agent holds |
| everything else | no way of being told — `offers` raises `NotImplementedError` |

Refused rather than quietly never offered: a tool the model never sees is a flow that quietly
does not do what it says.

Nothing of the person at this machine's configuration is written either way. Their own MCP
servers stay exactly as they were, and this flow's tool goes away with this flow.

## How it actually gets there

The road is the **Model Context Protocol**, that being the one way every one of these CLIs
takes a tool it was not shipped with. What the backend is handed is a command to run:

```
hmz tools --at /tmp/humanize-tools-XXXX/tools.sock
```

which relays its pipe to a socket in the flow's process. So the function that runs is the one
the flow wrote, on this interpreter, in this process — a tool server started as a program of
its own would be a subprocess with none of the flow's variables in it.

Nothing is started until something is offered. An agent whose flow hands it no callbacks has no
socket, no thread and no bridge, and its turns are the turns they always were.

## When a callback goes wrong

**A callback that raises is the tool failing, not the flow.** The model is told what went
wrong, in words it can act on, and is free to call it again correctly. A flow must not end
because a model called one of its tools wrongly.

The callback runs on the thread serving the call, which is **not** the thread the flow is on.
A callback that touches what the flow is touching answers for that itself — the usual lock.

## See also

- [Agents › Callbacks of the flow's own](/reference/agents#callbacks-of-the-flow-s-own)
- [Hooks](/weaver/hooks) — the other direction: a word in at a moment of the turn
- [Calling flows](/weaver/calling-flows) — a flow that calls another by name
- [The mission board](/user/board) — the other thing that does not stop a turn

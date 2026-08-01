# Getting started

From nothing installed to a run you can read back, in five steps. No concept is assumed; each
one is named as it turns up and linked to [Concepts](concepts.md), where it is explained
properly.

## Table of Contents

- [What you need](#what-you-need)
- [Install](#install)
- [1. Open the prompt](#1-open-the-prompt)
- [2. Say something](#2-say-something)
- [3. Put a loop under it](#3-put-a-loop-under-it)
- [4. Run one without the interface](#4-run-one-without-the-interface)
- [5. Read the run back](#5-read-the-run-back)
- [Write a flow of your own](#write-a-flow-of-your-own)
- [Where to go next](#where-to-go-next)

## What you need

- **Python 3.12 or newer.**
- **At least one coding agent CLI on your `PATH`**, already logged in: `claude`
  ([Claude Code](https://claude.com/claude-code)), `codex`, or `kimi`. humanize drives the CLI
  you already use; it does not talk to a model provider itself and holds no API key.
- **A project directory you are willing to have rewritten.** Read
  [Security](../README.md#security) first — humanize runs every agent with permission prompts
  disabled, so an agent under it edits files without asking.

Check what you have:

```sh
command -v claude codex kimi pi opencode mimo
```

Nothing else is required. [Isolation](machines.md#a-container-of-the-agents-own) wants
`docker`, and [remote execution](remote-execution.md) wants Linux on x86-64 here plus `python3`
on the far machine — neither is needed for anything below.

## Install

```sh
pip install git+https://github.com/humanfia/humanize.git
```

Or, from a checkout with [uv](https://docs.astral.sh/uv/):

```sh
git clone https://github.com/humanfia/humanize.git
cd humanize
uv sync
```

Either way the command is `hmz`:

```sh
hmz --version
```

## 1. Open the prompt

Change into a project you want work done in, and run `hmz` with nothing after it:

```sh
cd ~/code/myproject
hmz
```

That is the only way into the terminal interface — there is no `hmz tui`. You get a transcript,
an editor under it, and a status line under that.

![The humanize TUI: a transcript, an editor under it, and a status line under that](tui.svg)

The line above the editor says what you are about to talk to, as `cli/model:effort` — the CLI
that will run the turn, the model it will ask for, and how hard it should think. The first time, it opens on
the first backend you have installed, at that backend's newest model, at
`high` — deliberately not the hardest setting, which is the one to reach for rather than the one
to spend before anybody has asked for anything. After that it opens on whatever this project was
last set up to run.

The status line's right-hand end lists the keys that do something *right now*, and nothing
else. It is the whole of what you have to remember.

## 2. Say something

Type a line and press enter:

```
Read README.md and tell me what this project is.
```

The agent takes a **turn** — one exchange with the model, which may run tools and may take
minutes. What it says arrives as it says it. Underneath, humanize is running the flow called
`chat`: one agent, one **session**, and every line you type is another turn of that same
conversation.

Three things worth trying while it is running:

- **Type another line and press enter.** It goes *into* the turn already running rather than
  starting a new one. If no turn is open, it is held for the next.
- **`/details`** toggles whether tool calls and thinking are shown, or only what the agent
  says.
- **esc** stops the flow. Two **ctrl+c** leave. One ctrl+c clears what you have half-typed.

Type `/` and the commands appear under the editor with a line about each. Tab takes the one
highlighted. The full list is in the [TUI reference](tui.md).

## 3. Put a loop under it

Talking to one agent is not the shape of most work. A **flow** is what you reach for once it
is not: a Python file that drives one or more agents in a loop.

Press **shift+tab** to step to the next flow, or type `/flow` to pick one by name. Try
`ralph_loop` — a fresh session every turn, so the agent starts from the task and the repository
each time with nothing of the last turn in context:

```
/flow ralph_loop
```

Then say what you want done. It will keep going until you stop it with esc — that is what a
Ralph loop *is*. `/status` shows who is working, who handed to whom, and what it has cost.

humanize comes with nine: `chat`, `ralph_loop`, `stateful_ralph`, `fixed_juice_ralph`,
`continue_loop`, `goal`, `flame_chase`, `rlar` and `humanize1`. Six of them are flowbench's
loops written this way. Each is described in
[Flows](flows.md#the-flows-humanize-comes-with).

## 4. Run one without the interface

The same flows run unattended:

```sh
hmz exec -f ralph_loop -a claude/claude-opus-4-8:high "fix the failing tests"
```

- `-f` is the flow, by name or by path.
- `-a` is one agent, written `cli/model:effort`. Repeat it once for each agent the flow drives,
  in the order the flow takes them — `rlar` drives two, so it takes two `-a`.
- The last argument is the task.

To narrow what one of those agents may do, use the written-out form and name one of the four
[permission rungs](agents.md#what-an-agent-may-do):

```sh
hmz exec -f ralph_loop \
    -a cli=codex,model=gpt-5.6-sol,effort=high,permission=read-only \
    "review this repository"
```

Nobody is at a prompt here, so an agent that stops to ask a question is told nobody answered
and carries on rather than waiting forever.

If you get the count wrong, it is refused before any agent runs:

```console
$ hmz exec -f rlar -a claude/claude-opus-4-8:high "fix the build"
hmz exec: error: /.../rlar.py: run() drives 2 agents, 1 given
```

## 5. Read the run back

Every run writes down what it was — the flow, the agents, and the id of every session they
opened. Turn that plus the backends' own transcripts into one timeline:

```sh
hmz collect
```

```console
.humanize/20260809T014455Z.trace.json: 3 sessions, 412 slices
```

Open that file in [ui.perfetto.dev](https://ui.perfetto.dev) (drag it in) or `chrome://tracing`.
Each agent is a process, each session a track, and each slice one thing the agent did — with
the prompt, the reasoning, the tool input and the tool output attached to it. It is the only
view of a long run that fits on a screen.

## Write a flow of your own

A flow is a Python file with a `run(agents, task)` in it. Put this in
`.humanize/flows/twice.py`:

```python
"""Two passes: do the work, then read it back and fix what is wrong."""

from humanize.agents import AgentBase


def run(agents: tuple[AgentBase], task: str) -> None:
    (agent,) = agents
    session = agent.new()
    session(task)
    session("Now review what you just did, and fix anything that is wrong.")
```

The `tuple[AgentBase]` is not decoration: its length is how many agents the flow drives, and it
is the one thing a command line starting the flow cannot otherwise know. Write `async def run`
instead, and the flow can [wait for several turns at
once](flows.md#a-flow-that-waits-for-more-than-one-thing). Run it by name:

```sh
hmz exec -f twice -a claude/claude-opus-4-8:high "add a --dry-run flag"
```

It is offered in the interface too — `/flow` lists the flows in `.humanize/flows` here, in
`~/.humanize/flows`, and the ones humanize came with.

## Where to go next

- The words used above, properly: [Concepts](concepts.md).
- Every key and `/command`: [TUI reference](tui.md).
- Every flag: [CLI reference](cli.md).
- Flows that do more than the above: [Flows](flows.md).
- The Python API behind `agent(...)` and `session(...)`: [Agents](agents.md).
- Running the work on another machine or in a container: [Machines](machines.md).

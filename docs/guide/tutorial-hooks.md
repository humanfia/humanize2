# 11 · Hooks

**Fifteen minutes.** Get between an agent and its turn: refuse a command, add to a prompt, or
refuse to let a turn end.

::: tip Before you start
[A flow that calls a flow](/guide/tutorial-calling-flows). For step 4 you need Claude Code or
Codex — they are the two backends that run `PERMISSION_REQUEST`.
:::

## Step 1 — watch a turn

The gentlest hook does nothing but look:

```python
# .humanize/flows/watched.py
"""A Ralph loop that says what its agent reached for."""

from hmz.agents import AgentBase, Moment, Occasion, Verdict
from hmz.flows import flow


def seen(occasion: Occasion) -> Verdict | None:
    print(f"  → {occasion.tool}: {occasion.about[:60]}")
    return None                          # None says nothing


@flow
def run(agents: tuple[AgentBase], task: str) -> None:
    (agent,) = agents
    with agent.hooks.on(Moment.PRE_TOOL_USE, seen):
        for _ in range(5):
            agent(task, suppress=True)
```

```sh
hmz exec -f watched -a claude/claude-opus-4-8:high "$(cat TASK.md)"
```

`on` answers with a handle, which is also a context manager — so a hook wanted only for a while
says so in one line. `hung.off()` takes one down by hand; taking down what is already down is not
an error.

Hooks are on the **agent**, so one covers every session it holds — including the fresh one a Ralph
loop makes each turn.

::: tip What a flow prints goes into the transcript
The interface captures everything printed under it, so a `print` is how a flow says something.
:::

## Step 2 — the moments

| Moment | When | What a verdict does |
| --- | --- | --- |
| `SESSION_START` | a session is about to take its first turn | — |
| `USER_PROMPT_SUBMIT` | a prompt is about to go to the agent | `refused` skips the turn; `adds` goes into the prompt |
| `PRE_TOOL_USE` | the agent has reached for a tool | — |
| `PERMISSION_REQUEST` | the backend is asking whether a tool may run | `refused` denies it, with `because` as the reason |
| `NOTIFICATION` | the agent has stopped to ask its user something | — |
| `STOP` | a turn has ended | `refused` sends the agent on, with `because` as the next prompt |
| `SESSION_END` | a session has been closed | — |

A hook is told an `Occasion` — `moment`, `agent`, `session`, `prompt`, `tool`, `about`, `input`,
`said`, `again` — and answers with a `Verdict` or with `None`.

## Step 3 — add something to every prompt

```python
def remind(occasion: Occasion) -> Verdict | None:
    return Verdict(adds="Run the tests before you say you are done.")


with agent.hooks.on(Moment.USER_PROMPT_SUBMIT, remind):
    ...
```

Two hooks on one moment are **one verdict**: refused if either refused, and adding everything
either added.

## Step 4 — refuse a command

```python
def no_force_push(occasion: Occasion) -> Verdict | None:
    if "push --force" in occasion.about:
        return Verdict(refused=True, because="not on this branch")
    return None


agent.hooks.on(Moment.PERMISSION_REQUEST, no_force_push, tool="Bash")
```

Two conditions have to hold for this to reach the agent:

1. **A backend that runs the moment.** Claude Code and Codex do; Kimi Code, pi, opencode and
   mimocode do not. `agent.moments` is
   what this one runs, and `hooks.on` **refuses** a moment that is not in it — where the hook is
   hung, rather than by quietly never firing.
2. **The [`auto` rung](/features/permissions).** It is the one setting under which a backend
   actually asks before it acts *and waits for the answer*.

```sh
hmz exec -f guarded \
    -a cli=claude,model=claude-opus-5,effort=max,permission=auto \
    "tidy the branch"
```

Say so in the flow, and it is checked before the first turn rather than by a hook that never
fires:

```python
from typing import Annotated, NamedTuple


class Agents(NamedTuple):
    builder: Annotated[AgentBase, Moment.PERMISSION_REQUEST]
```

```console
$ hmz exec -f guarded -a kimi/kimi-code/k3:high "tidy the branch"
hmz exec: error: guarded: builder has to run PermissionRequest, which kimi does not
```

## Step 5 — refuse to let the turn end

This is the useful one. **A refused `STOP` is a [goal](/features/goals) written by hand**: the
turn is not over until the hook lets it be, and `because` is what the agent hears instead.

```python
from pathlib import Path


def unfinished(occasion: Occasion) -> Verdict | None:
    if occasion.again < 5 and "- [ ]" in Path("TASK.md").read_text():
        return Verdict(refused=True, because="TASK.md still has unticked boxes.")
    return None


@flow
def run(agents: tuple[AgentBase], task: str) -> None:
    (agent,) = agents
    with agent.hooks.on(Moment.STOP, unfinished):
        while "- [ ]" in Path("TASK.md").read_text():
            agent(task, suppress=True)
```

**`occasion.again` counts how many times this turn has already been sent on**, so a hook that
keeps refusing can decide to stop. Without that bound, an agent that cannot satisfy the condition
never finishes a turn.

This is exactly how [`official/humanize1:rlcr`](/reference/flows#the-official-flowverse) works: a
round *is* the builder believing the plan is done and trying to stop, and what the reviewer says is
what it hears instead.

## Step 6 — hang one, and take it down, mid-run

The point of hooks being Python rather than a table of shell commands:

```python
@flow
def run(agents: tuple[AgentBase], task: str) -> None:
    (agent,) = agents
    agent(task, suppress=True)                    # first round: let it explore

    with agent.hooks.on(Moment.STOP, unfinished): # later rounds: hold it to the file
        for _ in range(9):
            agent(task, suppress=True)
```

## Two rules

**A hook that raises has said nothing.** A flow must not fail because something hung off it did.
The one exception is a hook that drove an agent which has been
[stopped](/features/stopping): it lets `Stopped` out, so a run ended by hand reads as ended by
hand rather than as one that finished.

**A hook runs on the turn's own thread.** One that takes a while is a turn that takes a while.
Do not run a test suite in a `PRE_TOOL_USE` hook.

## Choosing between the three ways to keep an agent going

| | Decides it is done | Works on |
| --- | --- | --- |
| a `while` loop in the flow | your code, between turns | every backend |
| a refused `STOP` hook | your code, inside the turn | every backend but `HumanAgent` |
| [`agent.pursue`](/features/goals) | the **model**, against the objective | Claude Code, Codex, DeepSeek Harness, Kimi |

## What you now know

- `agent.hooks.on(moment, fn)` returns a handle that is a context manager.
- `Verdict(refused=…, because=…, adds=…)` or `None`.
- A refused `STOP` is a goal by hand; bound it with `occasion.again`.
- `PERMISSION_REQUEST` needs a backend that runs it and the `auto` rung.

## Next

[Asking a person](/guide/tutorial-questions).

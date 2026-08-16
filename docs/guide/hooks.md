# Hooks

A [**hook**](/reference/agents#hooks) is a Python callable hung on a **moment**, one of the
points a turn passes through. Reach for one when you want to get between an agent and its turn:
refuse a command, add to a prompt, or refuse to let a turn end. Claude Code, Codex and Kimi
Code each take a table of shell commands for the same moments; hooks are the same idea, but
hung on a live agent, taken down again while it runs, and written in the language the flow is
written in.

## Try it

The gentlest hook does nothing but look. Make a flow that prints what its agent reaches for:

```python
# .humanize/flows/watched/__init__.py
"""A Ralph loop that says what its agent reached for."""

from hmz.flows import Agent, Moment, Occasion, Verdict, flow


def seen(occasion: Occasion) -> Verdict | None:
    print(f"  → {occasion.tool}: {occasion.about[:60]}")
    return None                          # None says nothing


@flow
def run(agents: tuple[Agent], task: str) -> None:
    (agent,) = agents
    with agent.hooks.on(Moment.PRE_TOOL_USE, seen):
        for _ in range(5):
            agent(task, suppress=True)
```

Run it with a task:

```sh
hmz exec -f watched -a claude/claude-opus-4-8:high "$(cat TASK.md)"
```

You see a line each time the agent reaches for a tool: an arrow, the tool name, and the first
60 characters of what it was about to do. The hook sees each `PRE_TOOL_USE` moment, prints it,
and returns `None`, so the turn goes on unchanged.

::: tip What a flow prints goes into the transcript
The interface captures everything printed under it, so a `print` is how a flow says something.
:::

## Hanging and taking down

`on` answers with a handle, and the handle is also a context manager:

```python
with agent.hooks.on(Moment.STOP, keep_going):
    agent(task)              # and it is down again after the block
```

```python
hung = agent.hooks.on(Moment.STOP, keep_going)
hung.off()                   # by hand; taking down what is already down is not an error
```

Hooks are on the **agent**, so one covers every session the agent holds, including the fresh
one a Ralph loop makes each turn. Hanging one mid-run is the point.

## The moments

| Moment | When | What a verdict does |
| --- | --- | --- |
| `SESSION_START` | a session is about to take its first turn | — |
| `USER_PROMPT_SUBMIT` | a prompt is about to go to the agent | `refused` skips the turn; `adds` goes into the prompt |
| `PRE_TOOL_USE` | the agent has reached for a tool | — |
| `PERMISSION_REQUEST` | the backend is asking whether a tool may run | `refused` denies it, with `because` as the reason |
| `NOTIFICATION` | the agent has stopped to ask its user something | — |
| `STOP` | a turn has ended | `refused` sends the agent on, with `because` as the next prompt |
| `SESSION_END` | a session has been closed | — |

A hook is told an `Occasion`, which carries `moment`, `agent`, `session`, `prompt`, `tool`,
`about`, `input`, `said` and `again`. The hook answers with a `Verdict` or with `None`, and
`None` says nothing.

Two hooks on one moment are **one verdict**: refused if either refused, and adding everything
either added.

A verdict can refuse a command:

```python
from hmz.flows import Moment, Occasion, Verdict

def no_force_push(occasion: Occasion) -> Verdict | None:
    if "push --force" in occasion.about:
        return Verdict(refused=True, because="not on this branch")
    return None

agent.hooks.on(Moment.PERMISSION_REQUEST, no_force_push, tool="Bash")
```

It can also add to a prompt:

```python
def remind(occasion: Occasion) -> Verdict | None:
    return Verdict(adds="Run the tests before you say you are done.")


with agent.hooks.on(Moment.USER_PROMPT_SUBMIT, remind):
    ...
```

## A refused `STOP` is a goal by hand

The turn is not over until the hook lets it be. `occasion.again` counts how many times this
turn has already been sent on, so a hook that keeps refusing can decide to stop:

```python
def keep_going(occasion: Occasion) -> Verdict | None:
    if occasion.again < 3 and "TODO" in Path("TASK.md").read_text():
        return Verdict(refused=True, because="There is still a TODO in TASK.md.")
    return None
```

That is what [`official/humanize1:rlcr`](/flows/humanize1) is built on:
a round *is* the builder believing the plan is done and trying to stop, and what the reviewer
says is what it hears instead. Compare [Goals](/guide/goals), where the model decides.

A refused `STOP` is one of three ways to keep an agent going:

| | Decides it is done | Works on |
| --- | --- | --- |
| a `while` loop in the flow | your code, between turns | every backend |
| a refused `STOP` hook | your code, inside the turn | every backend but `Person` |
| [`agent.pursue`](/guide/goals) | the **model**, against the objective | Claude Code, Codex, DeepSeek Harness, Kimi, ZCode |

## Not every backend runs every moment

`agent.moments` lists what a backend runs. If a moment is not in it, `hooks.on` **refuses** the
hook where it is hung, rather than hanging one that quietly never fires.

| Moment | Claude Code | Codex | Kimi Code | ZCode | you |
| --- | --- | --- | --- | --- | --- |
| everything except `PERMISSION_REQUEST` | yes | yes | yes | yes | no |
| `PERMISSION_REQUEST` | yes | yes | no | yes | no |

Claude Code, Codex and ZCode ask before they use a tool and wait for the answer. Those are the
three backends where a refusal reaches the agent. Kimi Code, pi, opencode and mimocode are
driven unattended, which is what a flow watching its agent rather than gating it means.
`Person` runs none of the moments: a moment is a point in a turn of a model, and the person
takes no such turn.

`PERMISSION_REQUEST` also wants the [`auto` rung](/guide/permissions), the one setting under
which a backend asks and waits.

## Saying so in the flow

A flow that hangs a hook on a moment only some backends run declares the moment beside the
type. If you give it a backend that cannot run the moment, the flow is refused before its first
turn:

```python
from typing import Annotated, NamedTuple

from hmz.flows import Agent, Moment

class Agents(NamedTuple):
    """The two this drives: one that is gated, and one that reads its work."""

    builder: Annotated[Agent, Moment.PERMISSION_REQUEST]
    reviewer: Agent
```

```console
$ hmz exec -f gated -a kimi/kimi-code/k3:high -a kimi/kimi-code/k3:high "fix the build"
hmz exec: error: gated: builder has to run PermissionRequest, which kimi does not
```

The agents page of `/flow` then offers only the CLIs that would work for that place.

## Two rules

**A hook that raises has said nothing.** A flow must not fail because something hung off it
did. The one exception is a hook that drove an agent which has been [stopped](/guide/stopping):
it lets `Stopped` out, so a run ended by hand reads as ended by hand.

**A hook runs on the turn's own thread.** One that takes a while is a turn that takes a while.
Do not run a test suite in a `PRE_TOOL_USE` hook.

## See also

- [Goals](/guide/goals) — the same shape, decided by the model
- [Permissions](/guide/permissions)
- [Agents › Hooks](/reference/agents#hooks)
- [Asking a person](/guide/questions)

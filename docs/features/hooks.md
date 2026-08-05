# Hooks

A turn passes through a handful of **moments**, and a hook is a Python callable hung on one of
them.

Claude Code, Codex and Kimi Code each take a table of shell commands for the same moments. These
are the same idea held here instead: hung on a live agent, taken down again while it runs, and
written in the language the flow is written in.

```python
from hmz.agents import Moment, Occasion, Verdict

def no_force_push(occasion: Occasion) -> Verdict | None:
    if "push --force" in occasion.about:
        return Verdict(refused=True, because="not on this branch")
    return None

agent.hooks.on(Moment.PERMISSION_REQUEST, no_force_push, tool="Bash")
```

## Hanging and taking down

`on` answers with a handle, which is also a context manager:

```python
with agent.hooks.on(Moment.STOP, keep_going):
    agent(task)              # and it is down again after the block
```

```python
hung = agent.hooks.on(Moment.STOP, keep_going)
hung.off()                   # by hand; taking down what is already down is not an error
```

Hooks are on the **agent**, so one covers every session it holds — including the fresh one a
Ralph loop makes each turn — and hanging one mid-run is the point.

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

A hook is told an `Occasion` — `moment`, `agent`, `session`, `prompt`, `tool`, `about`, `input`,
`said`, `again` — and answers with a `Verdict` or with `None`, which says nothing.

Two hooks on one moment are **one verdict**: refused if either refused, and adding everything
either added.

## A refused `STOP` is a goal by hand

The turn is not over until the hook lets it be. `occasion.again` counts how many times this turn
has already been sent on, so a hook that keeps refusing can decide to stop:

```python
def keep_going(occasion: Occasion) -> Verdict | None:
    if occasion.again < 3 and "TODO" in Path("TASK.md").read_text():
        return Verdict(refused=True, because="There is still a TODO in TASK.md.")
    return None
```

That is what [`official/humanize1:rlcr`](/reference/flows#the-official-flowverse) is built on: a
round *is* the builder believing the plan is done and trying to stop, and what the reviewer says
is what it hears instead. Compare [Goals](/features/goals), where the model decides.

## Not every backend runs every moment

`agent.moments` is what this one runs, and `hooks.on` **refuses** a moment that is not in it —
where the hook is hung, rather than by quietly never firing.

| Moment | Claude Code | Codex | Kimi Code | you |
| --- | --- | --- | --- | --- |
| everything except `PERMISSION_REQUEST` | yes | yes | yes | no |
| `PERMISSION_REQUEST` | yes | yes | no | no |

Claude Code and Codex ask before they use a tool and wait for the answer, so those are the two
backends where a refusal reaches the agent. Kimi Code, pi, opencode and mimocode are driven
unattended, which is what a flow watching its agent rather than gating it means. `HumanAgent`
runs none of them: a moment is a point in a turn of a model, and the person takes no such turn.

`PERMISSION_REQUEST` also wants the [`auto` rung](/features/permissions), which is the one setting
under which a backend asks and waits.

## Saying so in the flow

A flow that hangs a hook on a moment only some backends run declares it beside the type, and is
refused before its first turn if given one that cannot:

```python
from typing import Annotated, NamedTuple

from hmz.agents import AgentBase, Moment

class Agents(NamedTuple):
    """The two this drives: one that is gated, and one that reads its work."""

    builder: Annotated[AgentBase, Moment.PERMISSION_REQUEST]
    reviewer: AgentBase
```

```console
$ hmz exec -f gated -a kimi/kimi-code/k3:high -a kimi/kimi-code/k3:high "fix the build"
hmz exec: error: gated: builder has to run PermissionRequest, which kimi does not
```

The agents page of `/flow` then offers only the CLIs that would work for that place.

## Two rules

**A hook that raises has said nothing.** A flow must not fail because something hung off it did.
The one exception is a hook that drove an agent which has been [stopped](/features/stopping): it
lets `Stopped` out, so a run ended by hand reads as ended by hand.

**A hook runs on the turn's own thread.** One that takes a while is a turn that takes a while.

## See also

- [Goals](/features/goals) — the same shape, decided by the model
- [Permissions](/features/permissions)
- [Agents › Hooks](/reference/agents#hooks)

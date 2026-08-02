# Goals

A session can be given a **goal** instead of a prompt. The agent then decides for itself when the
objective has been met, and until it does, a turn that would have ended starts another.

```python
agent.pursue("the suite passes and nothing has been stubbed out")
```

This is the backend's **own** goal feature — the one its `/goal` command reaches — not a prompt
that asks for one. The backend starts the extra turns itself.

## What `pursue` answers with

A goal is as many turns of the model as it takes. `pursue` follows the goal across all of them and
answers with the last.

A session that has gone quiet is a goal that has stopped **only once the goal itself says so**.
So a flow that loops over `pursue` is running the objective again, rather than nudging an agent
that stopped early:

```python
while True:
    agent.pursue(objective, suppress=True)
```

The awaited twin is `agent.apursue(objective)`, and a session has both as well:
`session.pursue(...)`, `await session.apursue(...)`.

## Which backends have one

| Backend | |
| --- | --- |
| Claude Code | yes |
| Codex | yes |
| Kimi Code | yes |
| pi, opencode, mimocode | no |

On a backend without one, `pursue` raises `NotImplementedError` — **whether or not `suppress` is
set**. Asking for a feature that is not there is a flow to correct, not a turn to retry.

## Asking for an agent that has one

A flow built on `pursue` says so where it declares its agents, and is refused before its first
turn rather than an hour into a loop:

```python
from typing import Annotated, NamedTuple

from hmz.agents import AgentBase, Goal

class Agents(NamedTuple):
    """The one it drives, which has to have a goal of its own."""

    worker: Annotated[AgentBase, Goal]
```

```console
$ hmz exec -f pursuing -a pi/openai-codex/gpt-5.5:high "fix the build"
hmz exec: error: pursuing: worker is run under a goal, which pi has no feature for
```

The interface's `/agents` sheet then offers only the CLIs that have one, so it cannot be chosen
wrong there at all.

## A goal by hand: refusing `STOP`

A refused `STOP` [hook](/features/hooks) is what a goal is, written by hand — the turn is not
over until the hook lets it be. That is the way to do it on a backend with no goal feature, and
the way to do it when the condition is something a Python function can check rather than something
the model should judge:

```python
def unfinished(occasion: Occasion) -> Verdict | None:
    if occasion.again < 5 and "- [ ]" in Path("TASK.md").read_text():
        return Verdict(refused=True, because="TASK.md still has unticked boxes.")
    return None

with agent.hooks.on(Moment.STOP, unfinished):
    agent(task, suppress=True)
```

`occasion.again` counts how many times this turn has already been sent on, so a hook that keeps
refusing can decide to stop.

| | Decides it is done | Costs |
| --- | --- | --- |
| `pursue` | the **model**, against the objective in its own words | turns you did not ask for, until it says so |
| a refused `STOP` | **your code**, against whatever it can read | one extra turn per refusal, bounded by `again` |

## The flow that is this

[`official/goal`](/reference/flows#the-official-flowverse) is Ralph with the task set as the
agent's own goal. The loop only starts it over when it stopped **without** having met it.

```sh
hmz exec -f official/goal -a claude/claude-opus-5:max "$(cat TASK.md)"
```

## See also

- [Hooks](/features/hooks)
- [Agents › Goals](/reference/agents#goals)
- [Flows › Asking for an agent that can do something](/reference/flows#asking-for-an-agent-that-can-do-something)

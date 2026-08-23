# Goals

A session can be given a **goal** instead of a prompt. The agent decides for itself when it has
met the objective, and until it does, a turn that would have ended starts another. Reach for a
goal when the stopping condition is something the model should judge, not something you can put
in a single prompt.

## Try it

```python
agent.pursue("the suite passes and nothing has been stubbed out")
```

That is the backend's own goal feature — the one its `/goal` command reaches — not a prompt
asking for one. The backend starts the extra turns itself; `pursue` follows the goal across all
of them and returns the last. Four spellings, and every one of them exists: `agent.pursue`,
`await agent.apursue`, `session.pursue`, `await session.apursue`.

A goal that goes quiet has stopped because the goal itself said so. A flow that loops over
`pursue` runs the objective again; it does not nudge an agent that stopped early:

```python
while True:
    agent.pursue(objective, suppress=True)
```

## Which backends have one

| Backend | |
| --- | --- |
| Claude Code | yes |
| Codex | yes |
| DeepSeek Harness | yes |
| Kimi Code | yes |
| ZCode | yes |
| pi, opencode, mimocode | no |

On a backend without one, `pursue` raises `NotImplementedError`, whether or not `suppress` is
set. A missing feature is a flow to correct, not a turn to retry.

## Disabling goals

If your flow owns every continuation, suggest `off` for each agent it declares:

```python
from typing import Annotated, NamedTuple

from hmz.flows import Agent, AgentDefaults

class Agents(NamedTuple):
    actor: Annotated[Agent, AgentDefaults(goals=False)]
    reviewer: Annotated[Agent, AgentDefaults(goals=False)]
```

The marker only supplies the model picker's initial value. The `goals` row switches the
selected agent between `on` and `off`, and the resolved value is saved on that agent's
`AgentConfig`. There is no third state, and the flow does not change an agent after it is made.
Python callers set the same policy directly:

```python
agent = CodexAgent(CodexAgentConfig(model="gpt-5.6-sol", effort="high", goals=False))
```

`agent.disable_goals()` does the same thing imperatively before the first turn.

Ordinary turns still work. Later calls to `pursue` raise `RuntimeError`, even with
`suppress=True`, and each backend is held to that its own way:

| | |
| --- | --- |
| **Codex** | that agent's app server starts with its goal tools disabled |
| **Claude Code** | no such switch, so humanize refuses the goal before it invokes the CLI |

Claude is also refused the tools that would carry work past the turn it is holding: `Agent`,
`ScheduleWakeup`, `CronCreate`, `CronDelete` and `CronList`, as one `--disallowedTools`
argument written in that order. Everything else the agent may reach for is what its
[permission](/user/permissions) rung says it may, exactly as before. Neither path changes your
global backend configuration, and an agent whose goals are on keeps the command it always had.

## Asking for an agent that has one

A flow built on `pursue` says so where it declares its agents, and is refused before its first
turn rather than an hour into a loop:

```python
from typing import Annotated, NamedTuple

from hmz.flows import Agent, Goal

class Agents(NamedTuple):
    """The one it drives, which has to have a goal of its own."""

    worker: Annotated[Agent, Goal]
```

```console
$ hmz exec -f pursuing -a pi/openai-codex/gpt-5.5:high "fix the build"
hmz exec: error: pursuing: worker is run under a goal, which pi has no feature for
```

The agents page of `/flow` then offers only the CLIs that have one, so there is no wrong choice
to make.

## A goal by hand: refusing `STOP`

A goal written by hand is a refused `STOP` [hook](/weaver/hooks): the turn is not over until
the hook lets it be. Do this on a backend with no goal feature, and when the condition is
something a Python function can check rather than something the model should judge:

```python
def unfinished(occasion: Occasion) -> Verdict | None:
    if occasion.again < 5 and "- [ ]" in Path("TASK.md").read_text():
        return Verdict(refused=True, because="TASK.md still has unticked boxes.")
    return None

with agent.hooks.on(Moment.STOP, unfinished):
    agent(task, suppress=True)
```

`occasion.again` counts how many times this turn has already been sent on, so a hook that keeps
refusing can use it to decide when to stop.

| | Decides it is done | Costs |
| --- | --- | --- |
| `pursue` | the **model**, against the objective in its own words | turns you did not ask for, until it says so |
| a refused `STOP` | **your code**, against whatever it can read | one extra turn per refusal, bounded by `again` |

## The flow that is this

[`official/goal`](/flows/goal) is Ralph with the task set as the agent's own goal. The loop
starts it over only when it stopped without having met it.

```sh
hmz exec -f official/goal -a claude/claude-opus-5:max "$(cat TASK.md)"
```

## See also

- [Hooks](/weaver/hooks)
- [Agents › Goals](/reference/agents#goals)
- [Flows › Asking for an agent that can do
  something](/reference/flows#asking-for-an-agent-that-can-do-something)

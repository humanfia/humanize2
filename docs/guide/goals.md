# Goals

A session can be given a **goal** instead of a prompt. The agent decides for itself when it has
met the objective, and until it does, a turn that would have ended starts another. Reach for a
goal when the stopping condition is something the model should judge, not something you can put
in a single prompt.

## Try it

Give an agent a goal with one call:

```python
agent.pursue("the suite passes and nothing has been stubbed out")
```

The agent keeps going until it decides the objective has been met, and `pursue` returns the
final turn. This is the backend's own goal feature, the one its `/goal` command reaches, not a
prompt that asks for one. The backend starts the extra turns itself.

## Give a goal more context

Keep source material separate when it is larger than the completion condition, or simply is
not part of what decides that the work is done:

```python
agent.pursue(
    "answer the question, return only the requested JSON, then mark the goal complete",
    context=f"""Keep this complete question in context for the goal that follows.
Do not answer it yet.

{question}
""",
)
```

`context` is an ordinary turn in the same conversation immediately before the native goal
starts. Its answer is not returned; the goal's last answer still is. This lets a backend keep
the complete task in conversation while receiving only the short completion condition through
its goal interface. Because this first turn is ordinary, tell the agent what to retain and what
to defer if work must not start until the goal is active.

## What `pursue` answers with

A goal takes as many turns of the model as it needs. `pursue` follows the goal across all of
them and returns the last one.

When a session goes quiet, the goal has stopped because the goal itself said so. A flow that
loops over `pursue` runs the objective again. It does not nudge an agent that stopped early:

```python
while True:
    agent.pursue(objective, suppress=True)
```

The awaited twin is `agent.apursue(objective, context=...)`. A session has both:
`session.pursue(...)` and `await session.apursue(...)`.

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

If your flow owns every continuation, you can suggest `off` for each agent it declares:

```python
from typing import Annotated, NamedTuple

from hmz.flows import Agent, AgentDefaults

class Agents(NamedTuple):
    actor: Annotated[Agent, AgentDefaults(goals=False)]
    reviewer: Annotated[Agent, AgentDefaults(goals=False)]
```

The marker only supplies the model picker's initial value. The `goals` row switches the
selected agent between `on` and `off`, and the resolved value is saved on that agent's
`AgentConfig`. The picker and config have no third state, and the flow does not change an agent
after it is made.

Python callers set the same policy directly when they construct an agent:

```python
agent = CodexAgent(CodexAgentConfig(model="gpt-5.6-sol", effort="high", goals=False))
```

`agent.disable_goals()` does the same thing imperatively before the first turn.

Ordinary turns still work. Later calls to `pursue` raise `RuntimeError`, even with
`suppress=True`. Codex starts that agent's app server with its goal tools disabled. Claude Code
has no such switch, so humanize refuses the goal before it invokes the CLI. It also refuses the
tools that would carry work past the turn it is holding: `Agent`, `ScheduleWakeup`,
`CronCreate`, `CronDelete` and `CronList`, as one `--disallowedTools` argument written in that
order. Everything else the agent may reach for is what its [permission](/guide/permissions)
rung says it may, exactly as before. Neither path changes your global backend configuration. An
agent whose goals are on keeps the command it always had.

## Asking for an agent that has one

A flow built on `pursue` says so where it declares its agents. It is refused before its first
turn, not an hour into a loop:

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

A goal, written by hand, is a refused `STOP` [hook](/guide/hooks). The turn is not over until
the hook lets it be. Do this on a backend with no goal feature. Do it when the condition is
something a Python function can check, not something the model should judge:

```python
def unfinished(occasion: Occasion) -> Verdict | None:
    if occasion.again < 5 and "- [ ]" in Path("TASK.md").read_text():
        return Verdict(refused=True, because="TASK.md still has unticked boxes.")
    return None

with agent.hooks.on(Moment.STOP, unfinished):
    agent(task, suppress=True)
```

`occasion.again` counts how many times this turn has already been sent on. A hook that keeps
refusing can use it to decide when to stop.

| | Decides it is done | Costs |
| --- | --- | --- |
| `pursue` | the **model**, against the objective in its own words | turns you did not ask for, until it says so |
| a refused `STOP` | **your code**, against whatever it can read | one extra turn per refusal, bounded by `again` |

## The flow that is this

[`official/goal`](/flows/goal) is Ralph with the task set as the
agent's own goal. The loop starts it over only when it stopped without having met it.

```sh
hmz exec -f official/goal -a claude/claude-opus-5:max "$(cat TASK.md)"
```

## See also

- [Hooks](/guide/hooks)
- [Agents › Goals](/reference/agents#goals)
- [Flows › Asking for an agent that can do
  something](/reference/flows#asking-for-an-agent-that-can-do-something)

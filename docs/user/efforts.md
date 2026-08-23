# Efforts

An agent is a backend, a model and an **[effort](/reference/agents#efforts)**: how hard to
think. Set one when a task needs more or less thought than the agent's default.

```
claude / claude-opus-4-8 : high
  │           │            └── effort
  │           └── model
  └── backend
```

The word belongs to each backend rather than to humanize, so the values differ.

## Try it

```sh
hmz exec -f ralph_loop -a claude/claude-opus-4-8:high "fix the build"
```

The `effort` row of the agent's sheet shows `high`. Press **←/→** to adjust it; the `swarm` row
turns swarm mode on for a model that has one.

## Set the effort

`backend/model:effort` is the short spelling. The written-out form of `-a` takes the same
thing, and so does a flow's Python config:

::: code-group

```sh [command line]
hmz exec -f ralph_loop -a cli=kimi,model=kimi-code/k3,effort=swarmmax "fix the build"
```

```python [Python]
ClaudeCodeAgentConfig(model="claude-opus-4-8", effort="high")
```

:::

## Efforts by backend

humanize does not check an effort against a list: a value your account has but this page does
not still works. These are the backends whose ladders need explaining; the whole set is in
[Agents › Efforts](/reference/agents#efforts).

| Backend | Efforts, hardest first |
| --- | --- |
| Claude Code | `ultracode`, `max`, `xhigh`, `high`, `medium`, `low` |
| Codex | `ultra`, `max`, `xhigh`, `high`, `medium`, `low` — each model takes its own subset |
| Kimi Code | `max`, `high`, `medium`, `low`, each also as `swarm…` |
| pi | `max`, `xhigh`, `high`, `medium`, `low`, `minimal`, `off` |
| opencode, mimocode | the model variant: `xhigh`, `high`, `medium`, `low`, `minimal` |
| ZCode | `max`, `high`, `low`, `enabled`, `nothink`, `disabled` — two vocabularies, and a model takes one of them |

- **`ultracode`** is Claude Code's `xhigh` thinking with the turn opted into orchestrating a
  fleet of its own, so it sits above `max`. It is real and undocumented, and no listing the CLI
  answers with will ever name it. humanize keeps it anyway.
- **Kimi Code's effort says how wide as well as how hard.** `max` is one agent; `swarmmax` is
  the same thinking at the width of a fleet of subagents. The prefix is exported as
  `hmz.flows.SWARM`, which is where a flow steering by it reads it.
- **pi's `off`** is the model asked not to think at all — the least of the efforts, not the
  absence of a setting.
- **Codex's models differ from each other.** `gpt-5.6-sol` takes `ultra`; `gpt-5.5` does not,
  so the interface offers each model only the efforts it takes.
- **ZCode's ladder is two vocabularies in one.** The models that take a thinking budget answer
  `max`, `high` and `low`, with `nothink` at the bottom; the ones that only take
  thinking-or-not answer `enabled` and `disabled`. Each model is offered the rungs it said it
  takes, and no model takes both halves.

## Change the effort while the flow runs

The rest of this page is the weaver's — whoever wrote the flow.

A config is frozen. A session resumes under the settings it opened with, and a config that
changed mid-flow would silently split one conversation across two models. The effort is the one
setting a flow may move as it goes:

```python
agents.builder.effort = "low"       # every session of this agent, from its next turn
session.effort = "max"              # this conversation alone
session.effort = ""                 # and back to whatever the agent runs at
```

A `swarm` prefix moves with it: `agent.effort = "swarmmax"`. Read it back through the same
property:

| | |
| --- | --- |
| `agent.config.effort` | what the agent was **configured** with |
| `agent.effort` | what its turns actually **run at** |

**The change takes hold on the next turn.** The turn already under way keeps the effort it
started at: a model does not think harder halfway through an answer. How it lands is the
backend's own business:

| Backend | How the new effort reaches the model |
| --- | --- |
| Codex, Kimi Code, opencode, mimocode | sent with each turn |
| Claude Code | an argument of the process it is held open as, so that process ends and the conversation resumes in one started at the new effort |
| pi | it has a command for it, and is told |
| ZCode | its app server keeps the level on the session, and is told the new one before the next turn |

## What to steer by

The reading that responds to effort is **`juice()`**: output tokens an average turn *of the
model* came out with. A model asked to think harder writes more in each answer, so that average
is what an effort moves.

```python
agent.juice(over=60)
```

[`official/fixed_juice_ralph`](/flows/fixed-juice-ralph) governs on it — a Ralph loop that
moves the effort a rung a round to hold the agent to a target.

## See also

- [Cost and rate](/user/tally)
- [Permissions](/user/permissions) — the other thing set on the model sheet
- [Agents › Efforts](/reference/agents#efforts)

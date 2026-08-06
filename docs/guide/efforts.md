# Efforts

An agent is a backend, a model and an **[effort](/reference/agents#efforts)**: how hard to
think.

```
claude / claude-opus-4-8 : high
  │           │            └── effort
  │           └── model
  └── backend
```

You set an effort when a task needs more or less thought than the agent's default. The word
belongs to each backend, not to humanize, so the values differ.

## Try it

Run an agent with `high` as the effort:

```sh
hmz exec -f ralph_loop -a claude/claude-opus-4-8:high "fix the build"
```

The `effort` row of the agent's sheet shows `high`. Press **←/→** to adjust it.

## Efforts by backend

humanize does not check an effort against a list: a value your account has but this page does
not still works. Backends take these efforts:

| Backend | Efforts, hardest first |
| --- | --- |
| Claude Code | `ultracode`, `max`, `xhigh`, `high`, `medium`, `low` |
| Codex | `ultra`, `max`, `xhigh`, `high`, `medium`, `low` — each model takes its own subset |
| Kimi Code | `max`, `high`, `medium`, `low`, each also as `swarm…` |
| pi | `max`, `xhigh`, `high`, `medium`, `low`, `minimal`, `off` |
| opencode, mimocode | the model variant: `xhigh`, `high`, `medium`, `low`, `minimal` |

**`ultracode`** is Claude Code's `xhigh` thinking with the turn opted into orchestrating a
fleet of its own. It is more work than any single-agent effort, so it sits above `max`. It is
real and undocumented, and no listing the CLI answers with will ever name it. humanize keeps it
anyway.

**Kimi Code's effort says how wide as well as how hard.** `max` is one agent; `swarmmax` is the
same thinking at the width of a fleet of subagents. The prefix is exported as
`hmz.agents.SWARM`.

**pi's `off`** is the model asked not to think at all. It is an effort like any other here: the
least of them, not the absence of a setting.

**Codex's models differ from each other.** `gpt-5.6-sol` takes `ultra`; `gpt-5.5` does not. So
the interface offers each model only the efforts it takes.

## Set the effort

You set the effort when you name an agent, or in its Python config:

::: code-group

```sh [command line]
hmz exec -f ralph_loop -a claude/claude-opus-4-8:high "fix the build"
hmz exec -f ralph_loop -a cli=kimi,model=kimi-code/k3,effort=swarmmax "fix the build"
```

```python [Python]
ClaudeCodeAgentConfig(model="claude-opus-4-8", effort="high")
```

:::

At the prompt, the `effort` row of the sheet shows it. Press **←/→** to adjust it, and the
`swarm` row turns swarm mode on for a model that has one.

## Change the effort while the flow runs

A config is frozen. A session resumes under the settings it opened with, and a config that
changed mid-flow would silently split one conversation across two models. The effort is the one
setting a flow may move as it goes:

```python
agents.builder.effort = "low"       # every session of this agent, from its next turn
session.effort = "max"              # this conversation alone
session.effort = ""                 # and back to whatever the agent runs at
```

Read it back through the same property:

| | |
| --- | --- |
| `agent.config.effort` | what the agent was **configured** with |
| `agent.effort` | what its turns actually **run at** |

**The change takes hold on the next turn.** The turn already under way keeps the effort it
started at: a model does not think harder halfway through an answer.

Each backend carries the effort in its own way. Codex, Kimi Code, opencode and mimocode take
the effort with each turn, so the next turn carries the new one. Claude Code takes it as an
argument of the process it is held open as, so moving it ends that process and resumes the
conversation in one started at the new effort. pi has a command for it, and is told.

A `swarm` prefix moves with it: `agent.effort = "swarmmax"`.

## What to steer by

The reading that responds to effort is **`juice()`**: output tokens an average turn *of the
model* came out with. A model asked to think harder writes more in each answer and takes longer
over it. So that average is what an effort moves.

```python
agent.juice(over=60)
```

`juice()` is what [`official/fixed_juice_ralph`](/reference/flows#the-official-flowverse)
governs on. It is a Ralph loop that moves the effort a rung a round to hold the agent to a
target. See [Cost and rate](/guide/tally).

## See also

- [Cost and rate](/guide/tally)
- [Permissions](/guide/permissions) — the other thing set on the model sheet
- [Agents › Efforts](/reference/agents#efforts)

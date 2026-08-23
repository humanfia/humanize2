---
pageClass: hmz-feature
---

# Flows

A **flow** is a directory of Python that drives one or more coding agents: which agents, what
each is asked, in what order, and when to stop. humanize runs flows and has no opinion about
what a good one is — so a flow is content rather than product, whoever writes one is a
**weaver**, and the list below is something to read, fork, publish and beat.

Eleven ship with humanize or with the flowverse it fetches — thirteen by name, since
[`official/humanize1`](/flows/humanize1) is three phases. Between them they are most of the
loop shapes the field has converged on.

<HmzFlowShape pick="ralph_loop,stateful_ralph,flame_chase,rlar,goal,parallel_flame_chase" />

## Every flow there is

<HmzFlows />

## Picking one

What a flow decides is *what the agent sees at the start of a round*, and there are only a few
honest answers.

| If you want | Reach for |
| --- | --- |
| To talk to an agent, with no loop at all | [`chat`](/flows/chat) |
| A long unattended run that cannot poison itself with its own context | [`ralph_loop`](/flows/ralph-loop) |
| A long run where the agent has to remember what it tried | [`stateful_ralph`](/flows/stateful-ralph), [`official/continue_loop`](/flows/continue-loop) |
| The model, rather than your loop, to decide a turn is not over | [`official/goal`](/flows/goal) |
| Each round to cost about the same | [`official/fixed_juice_ralph`](/flows/fixed-juice-ralph) |
| Two agents to check each other by working on the same tree | [`official/flame_chase`](/flows/flame-chase) |
| A reviewer that reads the work and writes the next prompt | [`official/rlar`](/flows/rlar) |
| A plan agreed first, then built under review | [`official/humanize1`](/flows/humanize1) |
| Three streams of work at once, only one of them touching your tree | [`official/parallel_flame_chase`](/flows/parallel-flame-chase) |

Seven name a [FlowBench](https://humanfia.ai/projects/flowbench) loop in their own docstring,
so that comparing one method against another is a flag rather than a reimplementation.

## Running one

`-f` takes the flow, and `-a` one agent per agent the flow wants, in the order it wants them:

```sh
hmz exec -f official/rlar \
    -a claude/claude-opus-5:high -a codex/gpt-5.6-sol:high "$(cat TASK.md)"
```

Without `-f` the terminal interface opens on [`chat`](/flows/chat), and `/flow` changes it.
Settings come from a YAML file with `-c`, and `/config` is the same fields at the prompt:

```sh
hmz exec -f ralph_loop -c budget.yaml -a claude/claude-opus-5:high "$(cat TASK.md)"
```

Every flag is in the [CLI reference](/reference/cli).

## What ends a loop

A loop with nothing to stop it runs until somebody stops it, which is a bill nobody agreed to
and a week of rounds nobody read. So every loop here without a stopping condition of its own
takes a **budget**, in millions of output tokens:

```yaml
budget: 25    # millions of output tokens; 0 goes on until it is stopped
```

**Ten million by default**, kept in the flow's state, so a loop restarted forty times has one
budget between the forty. Output rather than every kind, because output is the only kind a loop
of its own accord grows.

The rest stop themselves: [`chat`](/flows/chat) when you stop typing,
[`official/rlar`](/flows/rlar) when its reviewer agrees the work is done,
[`official/humanize1`](/flows/humanize1)'s loop on `--max` rounds, and the two [lane
flows](/flows/parallel-flame-chase) when the lanes run out of work.

## Where they come from

| | |
| --- | --- |
| `builtin` | the three in the package: [`chat`](/flows/chat), [`ralph_loop`](/flows/ralph-loop), [`stateful_ralph`](/flows/stateful-ralph) |
| `official` | [humanfia/flowverse](https://github.com/humanfia/flowverse), fetched the first time somebody wants what is in it |
| `local` · `user` | `.humanize/flows/` here, and `~/.humanize/flows/` everywhere |

Any git repository with a `flows/` directory in it is a **flowverse**, and adding one offers
its flows by name on every machine you add it to. To put one of your own on that list:
[Writing a flow](/weaver/writing-a-flow) is the first flow a weaver writes, and
[Flowverses](/weaver/flowverses) is how it gets published.

::: danger Adding a flowverse is trusting that repository with this machine
A flow is Python, and reading one means **running** it: listing what a flowverse holds imports
every file in its `flows/`. Add the ones you would clone and run. Every flow here also runs its
agents with permission prompts disabled, and nothing turns them back on — read
[Security](/user/security) first.
:::

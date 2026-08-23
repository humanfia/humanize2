---
pageClass: hmz-feature
---

# Flows

A **flow** is a directory of Python that drives one or more coding agents: which agents, what
each is asked, in what order, and when to stop. humanize runs flows and has no opinion about
what a good one is — which is why the flows are content rather than product, and why the list
below is something you can read, fork, publish and beat.

Eleven of them come with humanize or with the flowverse it fetches — thirteen by name, since
[`official/humanize1`](/flows/humanize1) is three phases run one at a time. They are, between
them, most of the loop shapes the field has converged on: forget every turn, remember every
turn, alternate two agents, let the model decide when it is done, put a reviewer between the
rounds.

<HmzFlowShape pick="ralph_loop,stateful_ralph,flame_chase,rlar,goal,parallel_flame_chase" />

## Every flow there is

<HmzFlows />

## Picking one

The question a flow answers is *what does the agent see at the start of a round*, and there are
only a few honest answers.

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

Seven of them name a [FlowBench](https://humanfia.ai/projects/flowbench) loop in their own
docstring, written against this API so that comparing one method against another is a flag
rather than a reimplementation.

## Running one

`-f` takes the flow and `-a` takes one agent per agent the flow wants, in the order it wants
them:

```sh
hmz exec -f official/rlar \
    -a claude/claude-opus-5:high -a codex/gpt-5.6-sol:high "$(cat TASK.md)"
```

Without `-f` the terminal interface opens on [`chat`](/flows/chat), and `/flow` changes it. A
flow that takes settings takes them from a YAML file with `-c`, and `/config` is the same
fields at the prompt:

```sh
hmz exec -f ralph_loop -c budget.yaml -a claude/claude-opus-5:high "$(cat TASK.md)"
```

The whole of it is in [Calling flows](/weaver/calling-flows) and the [CLI
reference](/reference/cli).

## What ends a loop

A loop with nothing to stop it runs until somebody stops it, which is a bill nobody agreed to
and a week of rounds nobody read. So every loop here that has no stopping condition of its own
takes a **budget**, in millions of output tokens:

```yaml
budget: 25    # millions of output tokens; 0 goes on until it is stopped
```

**Ten million by default.** Output rather than every kind, because output is what a model is
asked to produce and the only kind a loop of its own accord grows. The spend is kept in the
flow's state, so a loop restarted forty times still has one budget between the forty.

The flows that end themselves instead: [`chat`](/flows/chat) ends when you stop typing,
[`official/rlar`](/flows/rlar) when its reviewer agrees the work is done, and
[`official/humanize1`](/flows/humanize1)'s loop on `--max` rounds.

## Where they come from

| | |
| --- | --- |
| `builtin` | the three in the package: [`chat`](/flows/chat), [`ralph_loop`](/flows/ralph-loop), [`stateful_ralph`](/flows/stateful-ralph) |
| `official` | [humanfia/flowverse](https://github.com/humanfia/flowverse), fetched the first time somebody wants what is in it |
| `local` · `user` | `.humanize/flows/` here, and `~/.humanize/flows/` everywhere |

Any git repository with a `flows/` directory in it is a **flowverse**, and adding one offers
its flows by name on every machine you add it to. [Flowverses](/weaver/flowverses) is how, and
[Writing a flow](/weaver/writing-a-flow) is how to write one worth publishing.

::: danger Adding a flowverse is trusting that repository with this machine
A flow is Python, and reading one means **running** it: listing what a flowverse holds imports
every file in its `flows/`. Add the ones you would clone and run. Every flow here also runs its
agents with permission prompts disabled, and nothing turns them back on — read
[Security](/user/security) first.
:::

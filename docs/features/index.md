---
pageClass: hmz-feature
---

# Features

humanize runs **flows**: directories of Python that drive one or more coding agents in a loop
and write down everything they did. It does not talk to a model provider — it drives the coding
agent CLI you already have, logged in the way you already log in.

These pages are what there is and how it works. Nothing here is a command to type: the
[tutorials](/tutorials/) teach it in order, and the [guides](/guide/) answer "how do I use
this?".

<HmzMap />

## The deep end

The five that are worth reading even if you never install it.

| | |
| --- | --- |
| [The anchor](/features/anchor) | The agent runs here. Every syscall it makes is decided one at a time — replayed on another machine, or answered on this one. It is told none of it. |
| [Two accounts of one CLI](/features/accounts) | A CLI signs in once. humanize runs it as an account it was never signed into, by answering the paths it opens with other paths. |
| [One timeline](/features/tracing) | Every agent, every sub-agent and every program those turns ran, on one clock, in one document you open in Perfetto. |
| [A line typed mid-turn](/features/steering) | It goes *into* the turn that is running. Not queued behind it, and never quietly counted as said. |
| [Answers in a shape](/features/shapes) | A turn given a pydantic model answers with that model. The model is the whole of the question, and the answer is read back through it. |

## The shape of a run

| | |
| --- | --- |
| [Ten CLIs, one agent](/features/backends) | Ten coding agents and anything speaking the Agent Client Protocol, each driven through whatever it actually offers. |
| [A flow is Python](/features/flows) | A loop, a subprocess call, a file read between turns. The agents are its arguments, and the shapes a loop takes are few. |
| [Many turns at once](/features/concurrency) | Turns are sequential only inside one session. Two hundred conversations are two hundred turns. |
| [Picked up where it stopped](/features/resuming) | A loop meant to run for a week is a loop that will be stopped. What it was keeping track of survives; the conversation does not. |

## Who is at the other end

| | |
| --- | --- |
| [It decides when it is done](/features/goals) | The backend's own goal feature: a turn that would have ended starts another, until the model says the objective is met. |
| [The moments of a turn](/features/hooks) | Seven points a turn passes through, and Python callables hung on them — and taken down again while it runs. |
| [You, as one of the agents](/features/human) | A flow puts a decision to a person the way it puts one to a model, in the same shape, with the same branch for an answer that never came. |

## And the rest

Everything above is one page because it is unusual. The ordinary parts of humanize have a guide
apiece and no page here: [efforts](/guide/efforts) and [permissions](/guide/permissions),
[skills](/guide/skills) and [questions](/guide/questions), [containers](/guide/containers) and
[worktrees](/guide/worktrees), [cost and rate](/guide/tally), [flowverses](/guide/flowverses),
[history](/guide/history), [completion](/guide/completion) and [what a project
remembers](/guide/settings).

::: warning Before you point one at a repository you care about
humanize runs every agent with permission prompts disabled, and nothing turns them back on. A
flow is a directory of Python, and reading one means running it. Read
[Security](/guide/security).
:::

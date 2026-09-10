---
pageClass: hmz-feature
---

# Many turns at once

Turns are sequential inside **one conversation** and nowhere else. So a flow that needs two
hundred files fixed at the same time opens two hundred conversations, and one agent holds all
of them.

<HmzTurns />

## Two turns at once means two sessions

Two turns awaited on one session run one after the other, exactly as two called on it do. A
conversation is a conversation, and nothing about awaiting one changes that — which is the rule
the switch above is there to make concrete.

## A conversation is rooted at a directory

Where a session works is a setting of the session rather than of the turn, because that is what
it is to these backends: a conversation is opened at a directory and every turn of it runs
there. It cannot be moved once the session is open.

Which is exactly what makes one agent working in several places at once a **session apiece** —
a worktree per task, a checkout per shard, a package per reviewer — with their turns going
together. And either way it is one agent: one set of settings, one id, one process in the
[trace](/features/tracing), holding several conversations.

## A session costs nothing until a turn lands in one

Ten thousand conversations opened up front are a list, not a bill.

## How many of them go at once is the CLI's answer, not this library's

Nothing here caps a fan-out. What does is the coding agent underneath it, and the shape it comes
in: one held open for the life of a session pays for starting once, and one run again for every
turn pays for starting on every turn. So the number of conversations that still go at speed on a
given machine is a fact about the backend rather than about this library, and it is measured
rather than guessed: [the concurrency
benchmark](https://github.com/humanfia/humanize2/blob/main/bench/cli-concurrency/MOCK-RESULTS.md)
reports, per backend, how many conversations still run at **half the speed each of them runs
alone** — every turn still doing its own real work, with its own files changed, its own command
executed and its own thread of the conversation recalled.

Those are four CPUs against a **loopback model that answers instantly**, so what they measure is
the CLI's own overhead rather than how many conversations a real provider will keep fed; the
[real-provider record](https://github.com/humanfia/humanize2/blob/main/bench/cli-concurrency/RESULTS.md)
is separate and establishes no global maximum.

One of those ceilings is not about speed at all. **opencode keeps every conversation of every
workspace in one database**, and several of its processes opening one at the same moment can
collide on it and fail before the model is ever asked. humanize leaves that database where the
CLI put it — a conversation belongs to the CLI you can open it in, not to humanize — so that
ceiling is opencode's own, and the way past it is opencode's own `OPENCODE_DB`.

## Every call that runs a turn has an awaited twin

Same arguments, same answers, same shapes, same suppression. The difference is only where the
waiting happens: the turn runs on a thread of its own and the loop is handed straight back — so
a flow written as a coroutine can hold as many turns as it likes without any one of them
stopping the rest. The agents, the settings, the run it writes down and the way it is stopped
are all as they are for a plain function.

## Whole flows go at once too

`load` gives you a flow to run, and a coroutine flow is awaited by whoever called it — so a
flow gathers whole flows exactly as it gathers turns, as deep as it likes and as wide.

- **Each gathered call is a branch of the run in its own right**: its own record in the epic,
  its own skills, its own settings, its own unwinding when the run is stopped. Neither of two
  siblings is under the other, and neither can see the other — what is running, asked from
  inside a flow, is the branch that flow is on.
- **A run of flows calling flows reads back as the tree it ran as.** A record per call, inside
  the record of the call that made it, however deep it went.
- **Give each branch an agent of its own.** A conversation belongs to one agent, so two
  branches driving one agent are two flows sharing one — and what it opens then belongs to the
  flow they were both called from rather than to either of them. `clone()` is how a branch gets
  one to itself.
- **A chain of calls has a bottom**, at 64, so that a recursion with no base case is named
  where it went wrong rather than becoming a `RecursionError` somewhere else entirely.

## A batch is one agent over many prompts

One session apiece, none of them kept, and the answers come back in the order they were asked
for.

- **How wide it runs is a question about the machine**, not about this library, so nothing caps
  it. A batch runs at once whatever it is given, unless the flow says otherwise — and every
  prompt lands either way.
- **A batch that is not suppressing raises the first failure once every turn of it has
  landed.** A turn already running cannot be taken back, and a batch that let the failure out
  early would leave the rest running with nobody waiting for them.
- **Being stopped is not a failure**, and is not caught by suppression. A run ended by hand has
  to read as ended by hand.

## Where each of them lands

The same fan-out, aimed anywhere:

| | |
| --- | --- |
| **this machine** | every session rooted at the directory the flow runs in |
| **a worktree apiece** | one agent, several checkouts, all of them going |
| **a container apiece** | brought up on the first turn and taken down with the agent |
| **an ssh target** | the agent stays here; its commands land there — [the anchor](/features/anchor) |

A machine started for an agent is given the project directory itself rather than a copy, and a
container runs as the calling user, so the work outlives the machine and the workspace stays
yours. **What is isolated is the tools a command finds, not the work:** the agent goes on
running here, with its own credentials and its own trajectory, and only what it does reaches
the container.

## Reading two hundred conversations

Above the editor you see one agent and `1 of 200`. Stepping moves between the conversations
that are **working** — not all two hundred, only the ones thinking right now. The screen keeps
the last eight and the last two thousand lines of each; the rest of it is in the trace, which
is where a fan-out is meant to be read.

## Where the detail is

- [Many turns at once](/weaver/async-flows) — writing the coroutine, and gathering
- [Worktrees](/weaver/worktrees) · [Containers](/user/containers) · [Remote
  execution](/user/remote-execution)
- [Many conversations at once](/user/conversations) — the editor view

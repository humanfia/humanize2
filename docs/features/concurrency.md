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

What multiplies is sessions, not calls.

## A conversation is rooted at a directory

Where a session works is a setting of the session rather than of the turn, because that is what
it is to these backends: a conversation is opened at a directory and every turn of it runs
there. It cannot be moved once the session is open.

Which is exactly what makes one agent working in several places at once a **session apiece** —
a worktree per task, a checkout per shard, a package per reviewer — with their turns going
together. And either way it is one agent: one set of settings, one id, one process in the
[trace](/features/tracing), holding several conversations.

## A session costs nothing until a turn lands in one

Ten thousand conversations opened up front are a list, not a bill. Nothing is spent until
something is said in one.

## Every call that runs a turn has an awaited twin

Same arguments, same answers, same shapes, same suppression. The difference is only where the
waiting happens: the turn runs on a thread of its own and the loop is handed straight back — so
a flow written as a coroutine can hold as many turns as it likes without any one of them
stopping the rest.

Nothing about starting such a flow is different. The agents, the settings, the run it writes
down and the way it is stopped are all as they are for a plain function.

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

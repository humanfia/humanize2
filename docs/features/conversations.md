# Many conversations at once

A flow drives several agents, and each of them holds as many conversations as it likes — a Ralph
loop opens one a turn, a fan-out holds one per worktree. All of them written down the same screen
is none of them readable.

So **the transcript is one conversation**, and **tab** and **shift+tab** step between them.

## The keys

| | |
| --- | --- |
| **tab** | The next agent that is working, and its conversation. |
| **shift+tab** | The one before it. Both wrap. |

**They step between the ones that are working.** With ten agents going, what you step between is
the ones thinking right now, not the ones that have stopped. A conversation between its turns is
still read once you are on it — what you are reading stays put until you press one of these —
but it is not stepped onto. With nothing working at all, both keys do nothing.

## What "the conversation you are reading" decides

- What the transcript shows. Moving writes a line saying which one is being read from there
  down, and draws what it has said under that.
- Where [a line you type](/features/steering) goes.
- What the line above the editor marks as `2 of 5`.

```
   builder · claude/claude-opus-5:max · ● 2 of 5
   reviewer · codex/gpt-5.6-sol:high · ○ 1 · unread
```

`●` is an agent with a turn open, `○` one that has stopped. **`unread`** marks an agent holding a
conversation that has said something since you last looked at it — so a flow of ten conversations
is not nine nobody knows to look at.

## Nothing is taken off the screen

Moving to another conversation carries on under the line saying so, and so does a conversation
ending under you — a Ralph loop drops one a turn, and the line then says `that conversation has
gone`. Only `/clear` clears.

**What is being read is held by the conversation itself**, not by where it comes in the list. The
list churns. When the one you were reading goes, the newest of that agent's is read instead —
since a loop that dropped one has already opened the next — and where that agent has none left,
whatever is nearest to where it was.

What is kept is bounded, a flow being a thing that runs for days: **the last eight conversations,
and the last two thousand lines of each**. Older lines and older conversations are gone from the
screen, not from the [trace](/features/tracing).

## Where the conversations come from

In the flow. Every one of these is a session, and the flow decides how many:

```python
agent("do the task")                     # a conversation of its own, dropped straight after
session = agent.new()                    # one held across turns
sessions = agent.batch_new(200)          # two hundred that have not started
held = [agent.new(tree) for tree in trees]   # one per worktree
```

A session costs nothing until a turn lands in one. See [Worktrees](/features/worktrees) for the
several-directories case, and [Concepts › Session](/guide/concepts#session) for why this is the
single most important choice a flow makes.

## Two things this is not

**Not the person.** A flow that talks to you is talking to you here, so the conversation with
[the person](/features/human-agent) is not one of the ones these keys move between.

**Not agents.** Two agents at one model and effort are two agents, each with its own
conversations. `tab` steps between *conversations of agents that are working*, which usually
amounts to stepping between agents — but a fan-out is one agent and many conversations.

## See also

- [Talking to a running turn](/features/steering)
- [Exporting a transcript](/features/export) — it writes the one being read
- [Worktrees](/features/worktrees)

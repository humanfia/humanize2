# Many conversations at once

When a flow drives several agents, each agent holds as many conversations as it likes. A Ralph
loop opens one conversation each turn, and a fan-out holds one per worktree. The transcript
shows **one conversation**, and **tab** and **shift+tab** step between them.

## Try it

Open a flow where more than one agent is working, then press **tab**. The transcript moves to
the next working agent and shows its conversation. Press **shift+tab** to move back. Both keys
wrap around the list, and both do nothing when no agent is working.

## The keys

| | |
| --- | --- |
| **tab** | The next agent that is working, and its conversation. |
| **shift+tab** | The one before it. Both wrap. |

The keys step between the conversations that are working. With ten agents going, you step
between the ones thinking right now, not the ones that have stopped. A conversation between its
turns stays readable once you are on it. What you are reading stays put until you press one of
these keys, but it is not stepped onto. With nothing working, both keys do nothing.

## What "the conversation you are reading" decides

- What the transcript shows. When you move, the transcript writes a line naming the
  conversation being read from there down, and draws what it has said under that.
- Where [a line you type](/guide/steering) goes.
- What the line above the editor marks as `2 of 5`.

```
   builder · claude/claude-opus-5:max · ● 2 of 5
   reviewer · codex/gpt-5.6-sol:high · ○ 1 · unread
```

`●` marks an agent with a turn open, and `○` marks one that has stopped. **`unread`** marks an
agent holding a conversation that has said something since you last looked at it. That way a
flow of ten conversations is not nine that nobody knows to look at.

## Nothing is taken off the screen

When you move to another conversation, it carries on under the line that says so. A
conversation ending under you also carries on, because a Ralph loop drops one a turn and the
line then says `that conversation has gone`. Only `/clear` clears.

**The conversation itself holds what is being read**, not where it comes in the list. The list
churns. When the one you were reading goes, the newest conversation of that agent is read
instead, because a loop that dropped one has already opened the next. Where that agent has none
left, the read moves to whatever is nearest to where it was.

What is kept is bounded, because a flow runs for days. You keep **the last eight conversations,
and the last two thousand lines of each**. Older lines and older conversations are gone from
the screen, not from the [trace](/guide/tracing).

## Where the conversations come from

Every conversation is a session, and the flow decides how many. They all come from the flow:

```python
agent("do the task")                     # a conversation of its own, dropped straight after
session = agent.new()                    # one held across turns
sessions = agent.batch_new(200)          # two hundred that have not started
held = [agent.new(tree) for tree in trees]   # one per worktree
```

A session costs nothing until a turn lands in one. See [Worktrees](/guide/worktrees) for the
several-directories case, and [Concepts › Session](/guide/concepts#session) for why this is the
single most important choice a flow makes.

## Two things this is not

**Not the person.** A flow that talks to you talks to you here, so the conversation with [the
person](/guide/human-agent) is not one of the ones these keys move between.

**Not agents.** Two agents at one model and effort are two agents, each with its own
conversations. `tab` steps between *conversations of agents that are working*, which usually
amounts to stepping between agents. A fan-out is one agent and many conversations.

## See also

- [Talking to a running turn](/guide/steering)
- [Exporting a transcript](/guide/export), which writes the conversation being read
- [Worktrees](/guide/worktrees)

# Many conversations at once

When a flow drives several agents, each agent holds as many conversations as it likes. A Ralph
loop opens one conversation each turn, and a fan-out holds one per worktree. There is a
transcript **per agent**, all of its conversations running down it, and one more where **every
agent's work appears together** — which is the one the interface opens on. **tab** and
**shift+tab** step round them.

## Try it

Open a flow where more than one agent is working. You are watching all of them: each part says
which agent it is from as that changes. Press **tab** and the screen becomes the first working
agent's own transcript, drawn from the top. Press **tab** again for the next, and again to come
back round to all of them. **shift+tab** goes the other way.

## The keys

| | |
| --- | --- |
| **tab** | The next agent that is working, and round to the one they all appear on. |
| **shift+tab** | The one before it. Both wrap. |

The keys step between the agents that are working. With ten going, you step between the ones
thinking right now, not the ones that have stopped. An agent between its turns stays readable
once you are on it — what you are reading stays put until you press one of these keys — but it
is not stepped onto.

**Every agent there is can still be read**, from the diagram
[`/status`](/reference/tui#how-the-run-is-going) draws. **esc** opens it, and enter or a click
on a box reads that agent whether or not it is working. That is where the one that has stopped,
or has not started, is picked out by name rather than stepped past.

## What "the agent you are reading" decides

- What the transcript shows: that agent's own, drawn from the top under a line saying so.
- Where [a line you type](/user/steering) goes — of that agent's conversations, the one with a
  turn open. Reading all of them, there is no one agent you can have meant, so it goes to
  whichever has a turn open.
- What the line above the editor marks as `reading`.

A word you put into a turn is kept against the agent that took it, wherever you were looking
when it went: it is part of that conversation, so it reads back as part of it.

```
   builder · claude/claude-opus-5:max · ● 2 · reading
   reviewer · codex/gpt-5.6-sol:high · ○ 1 · unread
```

`●` marks an agent with a turn open, and `○` marks one that has stopped. **`unread`** marks an
agent that has said something since you last looked at it. That way a flow of ten agents is not
nine that nobody knows to look at. Nothing is marked unread while you are reading all of them
at once — what an agent said is on that screen too, and you have just read it there.

## One agent is one screen, however many conversations it opens

A Ralph loop opens a conversation a turn. All of them run down that agent's one transcript,
and nothing is redrawn when the next one opens — a screen wiped every turn would take with it
the turn you were reading, the line you typed and whatever went wrong. Which conversation a
turn is in is said where the turn begins, for an agent holding more than one:

```
● claude#a1b2 is working · conversation 3 of 3
```

Stepping onto *another agent* is the one thing that draws from the top, because what that agent
has done is that agent's, and a screen that only ever appended would be every agent's lines
shuffled into one another. Only `/clear` clears, and it clears the one you are reading rather
than reaching into ones you were not looking at.

What is kept is bounded, because a machine runs one flow after another. You keep **the last
sixteen transcripts, and the last two thousand lines of each**. Older lines and the agents of
older runs are gone from the screen, not from the [trace](/user/tracing).

## Where the conversations come from

Every conversation is a session, and the flow decides how many. They all come from the flow:

```python
agent("do the task")                     # a conversation of its own, dropped straight after
session = agent.new()                    # one held across turns
sessions = agent.batch_new(200)          # two hundred that have not started
held = [agent.new(tree) for tree in trees]   # one per worktree
```

A session costs nothing until a turn lands in one. See [Worktrees](/weaver/worktrees) for the
several-directories case, and [Concepts › Session](/user/concepts#session) for why this is the
single most important choice a flow makes.

## Two things this is not

**Not the person.** A flow that talks to you talks to you here, so the conversation with [the
person](/weaver/human-agent) is not one of the ones these keys move between.

**Not one conversation each.** Two agents at one model and effort are two agents, each with its
own conversations and its own transcript. A fan-out is one agent and many conversations, which
is one transcript.

## See also

- [Talking to a running turn](/user/steering)
- [Exporting a transcript](/user/export), which writes the one being read
- [Worktrees](/weaver/worktrees)

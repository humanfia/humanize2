---
pageClass: hmz-feature
---

# A line typed mid-turn

A line typed while a turn is running goes **into** that turn. Not after it, and not as a turn
of its own: the agent takes the words into account rather than being restarted with them.

That is the difference between saying "actually, use pathlib" four minutes into a refactor and
saying it once the refactor has finished.

<HmzSteer />

## Landing is not hearing

Every backend that can be talked to answers a word put in twice over: once to say it has been
taken from us, and again, later, to say it is in front of the model. Only the second one is the
agent having heard.

humanize counts the second. Until it arrives, your line is **pinned** against the agent it went
to rather than written into the transcript — the transcript is what happened, and the line has
not happened yet. A turn that ends without ever saying the words were in front of it puts the
line back **as never sent**. A line typed at an agent that was not listening is never quietly
counted as said.

## One queue, a line at a time

Everything typed joins one queue and leaves it one line at a time. The next line goes only once
the turn has said it has the one before it, and a turn takes one waiting line rather than the
whole queue. Three lines in a row are three things said, and they come back as three answers.

If no turn is open, the line is held for the next one. A line said to a running flow is never
dropped.

## It reaches the agent you are reading

Not whichever agent happens to be working. A flow drives several, and a line said to the one
that is not on the screen is a line said to somebody else — so the line goes where you are
looking. See [Many turns at once](/features/concurrency) for what "several conversations"
means here.

## Why some backends can take one and some cannot

A session that is one process, held open across its turns and spoken to a line at a time, is a
session there is something there to talk to. A session that is one run of a command line per
turn has ended by the time there is anything to say to it — so on those backends putting a word
in is not a thing that can be done at all, rather than a thing that is done late.

Between the two sit the backends driven through the app server they serve their own client
from: the turn stays open, and the word is steered into the run already going.

A session held open is not by itself somewhere to say something, though. ZCode's app server
keeps the turn open and still refuses a second prompt while one is running: what its own
terminal puts a word in over is a channel that terminal holds rather than anything the
protocol offers the rest of us.

One subtlety decides whether this works or corrupts the transcript. A backend that answers each
thing it is told with a turn of its own has to be read until it has answered **everything**
said in the turn, the words put in mid-turn included. Reading only as far as the first answer
loses what was put in, and leaves the rest for the next turn to take as its own.

| Backend | What a mid-turn line does |
| --- | --- |
| **Claude Code** | Answered inside the same turn. The turn is over once the agent has answered everything it was told, not when it first stops. |
| **Codex** | A steer on the turn its app server is running. |
| **Kimi Code** | Queued, then steered into the turn already running. |
| **pi** | A steer on the run it is making, taken into it rather than answered after it. |
| **ZCode** | Nothing: its app server holds the turn open and still refuses a second prompt while one is running. |
| **opencode**, **mimocode**, and every other backend given a turn's whole prompt up front | Nothing: there is nothing there to hear it. |

## The anchored exception

An [anchored](/features/anchor) Claude ends its process with each turn, so that what the agent
wrote reaches the target before the turn says it landed. It hears you during a turn as any
Claude does; between two turns there is nothing there, so putting a word in fails until the
next turn opens. An anchored Codex keeps one app server for the life of the agent and can be
steered throughout, at the cost of that same guarantee.

## The same road, from a flow

A flow says a word into a running turn the same way, and two hooks of the driver's own are what
the pinned line at the prompt is made of: one is asked as each turn starts for anything said
while no turn was open, and the other is asked between turns for the next thing to say — so a
flow can be a conversation rather than a loop.

## Where the detail is

- [Talking to a running turn](/user/steering) — the keys, the pin, and the Python
- [Many conversations at once](/user/conversations) — which agent a line reaches
- [Stopping](/user/stopping) — when a steer is not enough

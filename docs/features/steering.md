---
pageClass: hmz-feature
---

# A line typed mid-turn

A line typed while a turn is running goes **into** that turn — not after it, and not as a turn
of its own. The agent takes the words into account rather than being restarted with them: the
difference between saying "actually, use pathlib" four minutes into a refactor and saying it
after.

<HmzSteer />

## Landing is not hearing

Every backend that can be talked to answers a word put in twice over: once to say it has been
taken, and again, later, to say it is in front of the model. Only the second is the agent
having heard, and humanize counts the second.

Until it arrives the line is **pinned** against the agent it went to rather than written into
the transcript, which is what happened. A turn that ends without ever saying the words were in
front of it puts the line back **as never sent**.

## One queue, a line at a time

Everything typed joins one queue and leaves it a line at a time: a turn takes one waiting line
rather than the whole queue, and the next goes only once the turn has said it has the one
before. Three lines in a row are three things said, and three answers. If no turn is open the
line waits for the next one rather than being dropped.

## It reaches the agent you are reading

Not whichever agent happens to be working. A flow drives several, and a line said to the one
that is not on the screen is a line said to somebody else — so it goes where you are looking.
See [Many turns at once](/features/concurrency) for what that means here.

## Why some backends can take one and some cannot

A session that is one process, held open across its turns and spoken to a line at a time, has
something there to talk to. A session that is one run of a command line per turn has ended by
the time there is anything to say to it — so on those backends it cannot be done at all, rather
than done late. Between the two sit the backends driven through the app server they serve their
own client from: the turn stays open, and the word is steered into the run already going.

A session held open is not by itself somewhere to say something, though: ZCode's app server
keeps the turn open and still refuses a second prompt. What its own terminal steers over is a
channel that terminal holds, not anything the protocol offers the rest of us.

One subtlety decides whether this works or corrupts the transcript. A backend that answers each
thing it is told with a turn of its own has to be read until it has answered **everything**
said in the turn, the words put in mid-turn included. Reading only as far as the first answer
loses what was put in and leaves the rest for the next turn to take as its own.

| Backend | What a mid-turn line does |
| --- | --- |
| **Claude Code** | Answered inside the same turn. The turn is over once the agent has answered everything it was told, not when it first stops. |
| **Codex** | A steer on the turn its app server is running. |
| **Kimi Code** | Queued, then steered into the turn already running. |
| **pi** | A steer on the run it is making, taken into it rather than answered after it. |
| **ZCode** | Nothing: a second prompt is refused while one is running. |
| **opencode**, **mimocode**, and every other backend given a turn's whole prompt up front | Nothing: there is nothing there to hear it. |

## The anchored exception

An [anchored](/features/anchor) Claude ends its process with each turn, so what the agent wrote
reaches the target before the turn says it landed. It hears you during a turn as any Claude
does; between two turns there is nothing there to hear. An anchored Codex holds one app server
for the life of the agent and can be steered throughout, at the cost of that guarantee.

## The same road, from a flow

A flow says a word into a running turn the same way, and the pinned line at the prompt is made
of two hooks of the driver's own: one asked as each turn starts for anything said while no turn
was open, the other between turns for the next thing to say — so a flow can be a conversation
rather than a loop.

## Where the detail is

- [Talking to a running turn](/user/steering) — the keys, the pin, and the Python
- [Many conversations at once](/user/conversations) — which agent a line reaches
- [Stopping](/user/stopping) — when a steer is not enough

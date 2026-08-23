# Talking to a running turn

A line you type while a turn is running goes **into** that turn instead of starting another.
The agent takes the line into account rather than being restarted with it. That is the
difference between saying "actually, use pathlib" four minutes into a refactor and saying it
after the refactor has finished.

## Try it

While a turn is running, type a line at the prompt and press enter. There is no separate mode
and no separate key. Your line stays pinned against the agent it went to:

```
❯ and fix the tests too · with claude#3a15
```

It comes off the pin only when that agent's own turn says the words are in front of it.

## At the prompt

If no turn is open, the line is **held for the next one**. A line to a running flow is never
dropped. A held line is pinned onto the editor rather than written into the transcript, dimmed,
behind the same `❯`:

```
❯ and fix the tests too                    assistant · claude-opus-5:high
❯ then push                                     12.3k tokens · 84/s
────────────────────────────────────────────────────────────────────────
❯ █
```

The line has not been said to anybody yet; the transcript is what happened. When something
takes the line, it comes off the pin and into the transcript, in front of the turn that took
it.

### Handed to a backend is not the same as taken

A turn that ends without ever saying the words are in front of it puts the line back into the
transcript **as never sent**. A line typed at an agent that was not listening is never quietly
counted as said.

### One at a time, in order

Everything you type joins one queue and leaves it a line at a time. The next line goes only
once the turn has said it has the one before it, and a turn takes one waiting line rather than
the whole queue. Three `hi` in a row are three things said, and they come back as three
answers.

### It reaches the agent you are reading

Your line reaches the agent you are reading, not whichever happens to be working: a flow drives
several, and a line said to the one that is not on the screen is a line said to somebody else.
Of that agent's conversations it goes to the one with a turn open. Reading all of them at once
there is no one agent you can have meant, so it goes to whichever has a turn open — which is
the one the screen is showing anyway. See [Many conversations at once](/user/conversations).

## What each backend does with it

| Backend | What a mid-turn line does |
| --- | --- |
| **Claude Code** | Answered within the same turn. The turn is over once the agent has answered everything it was told, not when it first stops. |
| **Codex** | A steer on the turn its app server is running. |
| **Kimi Code** | Queued, then steered into the turn already running. |
| **pi** | A steer on the run it is making, taken into it rather than answered after it. |
| **opencode**, **mimocode** | Nothing: a run per turn has ended by the time there is anything to say to it. |
| **ZCode** | Nothing: its app server refuses a second prompt while one is running, and the channel its own terminal steers with is that terminal's. |

An [anchored](/user/remote-execution) Claude ends its process with each turn so its work
reaches the target before the turn says it landed. It hears you during a turn as any Claude
does; between two turns there is nothing there to hear, so `interject` raises `RuntimeError`
until the next turn opens. An anchored Codex keeps one app server for the life of the agent and
can be steered throughout, at the cost of that same guarantee.

A turn is steered on the server it is running on, not on whichever one the agent holds when you
type. The two are the same unless something moved underneath — another account, or a change to
the [callbacks](/weaver/tools) the agent offers, either of which starts a fresh server — and a
line sent to a server that never ran the turn would be a line the turn never hears.

## From Python

`session.interject` sends a line from Python:

```python
session.interject("actually, use pathlib")
```

- On a backend that takes a turn's whole prompt up front, this raises `NotImplementedError`.
- On a backend that can be talked to, it raises `RuntimeError` when nothing is running to hear
  it.

Two related hooks, both set by the flow driving the agent:

| | |
| --- | --- |
| `agent.waiting` | Asked as each turn starts for anything said to this agent while no turn was open. What it returns goes into that turn. |
| `agent.prompting` | Asked between turns for the next thing to say, so a flow can be a conversation rather than a loop. `None` once there will be nothing more. |

That pair is how the pin in the interface works.

## See also

- [Many conversations at once](/user/conversations) — which agent a line reaches
- [Stopping](/user/stopping) — when a steer is not enough
- [The person as an agent](/weaver/human-agent)

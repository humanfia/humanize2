# Talking to a running turn

A line typed while a turn is running goes **into** that turn rather than starting another. The
agent takes it into account instead of being restarted with it.

This is the difference between "actually, use pathlib" arriving four minutes into a refactor and
arriving after it.

## At the prompt

Type and press enter. There is no separate mode and no separate key — the editor means both
things at once.

If no turn is open, what you typed is **held for the next one**. A line to a running flow is
never dropped.

A held line is pinned onto the editor rather than written into the transcript, dimmed, behind
the same `❯`:

```
❯ and fix the tests too                    assistant · claude-opus-5:high
❯ then push                                     12.3k tokens · 84/s
────────────────────────────────────────────────────────────────────────
❯ █
```

It has not been said to anybody yet, and the transcript is what happened. The moment something
takes it, it comes off the pin and into the transcript, in front of the turn that took it.

### Handed to a backend is not the same as taken

A line put into a turn that is already running stays pinned too, now against the agent it went
to:

```
❯ and fix the tests too · with claude#3a15
```

It comes off only when that agent's own turn says the words are in front of it. A turn that ends
without ever saying so puts the line back into the transcript **as never sent** — a line typed at
an agent that was not listening is never quietly counted as said.

### One at a time, in order

Everything typed joins one queue and leaves it a line at a time. The next goes only once the
turn has said it has the one before it, and a turn takes one waiting line rather than the whole
queue. Three `hi` in a row are three things said and come back as three answers.

### It reaches the conversation you are reading

Not whichever agent happens to be working. An agent may be holding one conversation you are
reading and taking a turn in another, and a line said to the wrong one is a line said to
somebody else. See [Many conversations at once](/features/conversations).

## What each backend does with it

| Backend | What a mid-turn line does |
| --- | --- |
| **Claude Code** | Answered within the same turn. The turn is over once the agent has answered everything it was told, not when it first stops. |
| **Codex** | A steer on the turn its app server is running. |
| **Kimi Code** | Queued, then steered into the turn already running. |
| **pi** | A steer on the run it is making, taken into it rather than answered after it. |
| **opencode**, **mimocode** | Nothing: a run per turn has ended by the time there is anything to say to it. |

An [anchored](/features/remote-execution) Claude ends its process with each turn so that its
work reaches the target before the turn says it landed — so it hears you during a turn as any
Claude does, and between two there is nothing there to hear: `interject` raises `RuntimeError`
until the next turn opens. An anchored Codex keeps one app server for the life of the agent and
can be steered throughout, at the cost of that same guarantee.

## From Python

```python
session.interject("actually, use pathlib")
```

- On a backend that takes a turn's whole prompt up front, this raises `NotImplementedError`.
- On a backend that can be talked to, it raises `RuntimeError` when nothing is running to hear
  it.

Two related hooks, both set by whatever is driving the agent:

| | |
| --- | --- |
| `agent.waiting` | Asked as each turn starts for anything said to this agent while no turn was open. What it returns goes into that turn. |
| `agent.prompting` | Asked between turns for the next thing to say, so a flow can be a conversation rather than a loop. `None` once there will be nothing more. |

That pair is how the interface's pin works: `waiting` drains the queue into the turn that is
starting, `prompting` hands the flow the next thing to say.

## See also

- [Many conversations at once](/features/conversations) — which agent a line reaches
- [Stopping](/features/stopping) — when a steer is not enough
- [The person as an agent](/features/human-agent)

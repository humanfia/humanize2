---
pageClass: hmz-feature
---

# A turn can be cut off

A turn can be given a **budget** — how many output tokens it may come out with, how long it may
run for — and when the budget is spent, the turn stops. Not the next turn: this one, the one
that is running now.

::: tip Two caps, and they are not the same cap
This page is the **per-turn** one. It shortens an answer, it can be reached a thousand times in
an afternoon, and its tokens are counted one by one.

What a whole **run** may spend is the [allowance](/features/allowances): hours on the clock,
*millions* of output tokens, dollars. It ends the run rather than an answer, and every flow has
one whether or not it says so.

The two are deliberately two types with two vocabularies, because the confusion between them is
a factor of a million: `Budget(output=2)` is two output tokens and `Allowance(tokens=2)` is two
million.
:::

Without it there is nothing to do about a turn that has gone wrong. Stopping an agent prevents
its *next* turn, and a session that is one run of a command line per turn has nothing
listening: an agent six minutes into an answer nobody wants goes on writing it for as long as
it takes, and the flow finds out when it is over.

```python
session.budget = Budget(output=4_000, seconds=300, when="immediately", then="end")
```

## Per turn, not per session

Every turn starts with the whole of it. A cap over the whole conversation would cut a tenth
round off for what the first round wrote, which is a budget nobody can reason about — so what
is measured is the rise across the turn now running, and the round after a cut-off round gets
the same room the first one did.

`Budget()` with nothing named in it caps nothing, which is how one conversation opts out of a
budget its agent carries.

## Read while the turn is still running

This is the whole reason it works. Most backends here say what each request to the model cost
as that request lands, and humanize's meter moves then rather than when the turn ends — the
same reading `session.rate()` and `session.juice()` are off. So a turn that has written its
four thousand tokens is stopped in the middle of the turn, not congratulated after it.

The three that state a whole turn's cost only at the end — Antigravity, Grok Build and Qwen
Code — can only be held to a token budget at the end of a turn, which is the same thing their
[rate](/reference/agents#what-it-has-cost-and-how-fast) already reads as.

A token budget is **output tokens**, read off `session.spent().output`, so it depends on the
backend counting them under that name. Every backend humanize drives does; which kinds each
reports is declared as `counts` — see [Cost and rate](/user/tally) — and served by the
catalogue as `counts:output`, so a flow can be refused an agent that would read nought and
never be cut off at all.

A cap on the clock has no such gap: it bites whether or not anything is arriving, which is what
makes it the one that catches a turn that has gone quiet, and the one to reach for on a backend
that does not count as it goes.

## When it takes hold

| `when` | What happens |
| --- | --- |
| `"next-response"` | The answer the model is in the middle of is let land, and the turn stops on it. What comes back is a whole thought, and the tokens already paid for are the ones you get to read. It waits a minute at most: on a backend that lands nothing mid-turn there is no answer coming, and the wait ending is the cut-off. |
| `"immediately"` | The turn ends where it stands. Whatever the agent was in the middle of saying is what the turn answers with. |

`next-response` is paid out by a response landing rather than by the turn ending — a budget
that waited for the turn would never bite, the turn being the thing it is there to shorten.

## What it leaves behind

| `then` | What the turn comes to |
| --- | --- |
| `"end"` | It answers with what has been said. A loop reads a short turn rather than an exception, which is what a flow that summarises, drafts or explores would rather have. |
| `"fail"` | It raises `Unrecoverable`. A flow that cannot use half an answer stops instead of feeding one forward. |

`Unrecoverable` rather than an ordinary failure, and so not caught by `suppress`: the same
budget is spent again on the next try, so a loop that took the turn over on a schedule would be
cut off at the same word every round and never get anywhere.

**A turn ended by its budget landed; it did not fail.** Its edits are on disk and its
conversation is open to the next turn, so the round after a short round carries the same
session on rather than starting another — which is the whole difference between a cap and a
kill. That is why `end` is the default: read as a failure, the turn would be taken again on a
budget refilled for the retry, and a cap a loop refills every time it is reached is not a cap.

## Cutting one off by hand

The same primitive is there on its own:

```python
session.interrupt(why="it has been reading the same file for four minutes")
```

It ends the turn now running and leaves the session usable — the next turn is an ordinary turn.
A session with no turn running is left alone, since a reason left standing would end the next
turn before it had said anything.

A turn cut off still ends the way every turn ends: on exactly one answer, holding what the
agent got as far as saying. A stream that stopped mid-sentence would leave whatever is reading
it waiting for an answer nobody is going to give.

"What has been said" is what the backend has said **to humanize**, which is not always the same
as what the model has written. A CLI that streams a message only once the message is complete
has said nothing yet, so a turn cut off in the middle of its first paragraph answers with
nothing rather than with half a sentence nobody was shown. One that streams as it goes — a
block, a step, a message at a time — answers with everything that landed.

A [goal](/features/goals) is not a turn — it is the backend's own loop, started by the backend
and followed rather than held — so a budget does not apply to one and this does not reach one.
Stopping the agent is what ends a goal.

## What is actually ended

Whichever process is holding the turn, and everything it started — a CLI that was in the middle
of a test run does not leave the test run behind.

| How the backend is driven | What a cut-off reaches |
| --- | --- |
| One command per turn — Cursor, Grok Build, opencode, MiMo, and the shaped turns of Antigravity and Qwen Code | The command the turn is running in. Ended, with everything it started. |
| One process held open across its turns — Claude Code, pi, Antigravity, Qwen Code | The process the session is spoken to. Ended; the next turn starts another and resumes the conversation. |
| An app server serving every session of an agent at once — Codex, Kimi Code, ZCode, DeepSeek Harness | Nothing is taken down. The turn stops at the next answer instead: cutting one turn off must not end every other conversation on the same server. |

`agent.stop()` reaches the same place, which is what makes it mean what it always said it
meant: on a command-per-turn backend it ends the turn under way rather than only preventing
the next one.

## Set on the agent, or on one conversation

A budget is a setting of the agent, so every session it opens runs its turns under it:

```python
AgentConfig(model="…", effort="high", budget=Budget(seconds=600))
```

and a conversation may be given one of its own, said again as often as a flow likes — which is
where a loop watching what a round is costing is when it decides the next one is to be shorter.
The turn already under way keeps the budget it opened with: what has been spent is measured
against the cap the turn started on, and one swapped halfway through would cut a turn off for
tokens it was allowed when it wrote them.

## Where the moments of a turn stop being enough

A `Stop` [hook](/features/hooks) fires *between* completed turns of the model and can refuse
and send the agent on again. That is the right shape for deciding whether a turn is finished
and the wrong shape for stopping one: it never runs while the model is writing. A budget's
cut-off also wins over a hook that would have sent the agent on — a spent budget is not a
question.

See [What it has cost, and how fast](/reference/agents#what-it-has-cost-and-how-fast) for the
readings a budget is held to, [Every run has an allowance](/features/allowances) for the cap on
the run rather than on the turn, and [Stopping](/user/stopping) for ending a run by hand.

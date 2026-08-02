# Cost and rate

Every session and every agent says what it has spent, how fast it is spending it, and how hard it
is thinking.

```python
session.spent()          # Usage(input=41230, output=2180, cache_read=980100)
session.rate()           # tokens a second, by kind, over the last five minutes
session.rate(over=60)    # over the last minute instead
session.juice(over=60)   # output tokens an average turn of the model came out with
agent.spent()            # every session this agent has opened, dropped ones included
agent.rate(over=60)
agent.juice()
```

## Three readings, three questions

| | Answers | Moves with |
| --- | --- | --- |
| `spent()` | what has this cost | everything |
| `rate()` | how fast is the bill running up | how many turns are going at once |
| `juice()` | how hard is it thinking | the [effort](/features/efforts) |

## `spent` — a mapping of kind to tokens

`input` and `output` are the two every backend counts, and are on it as attributes. The rest —
a cache read, a cache write, the reasoning a backend counts beside the output rather than inside
it — differ from CLI to CLI, so **a kind that is not there is one that backend does not report**:

```python
spent = session.spent()
spent.input, spent.output, spent.total       # always
spent.get("cache_read", 0)                   # for a backend that counts one
dict(spent)                                  # everything it does count
```

The `result` event a turn ends on carries the same reckoning, beside the per-model `tokens` it
already carried: `result.spent.total` is what `result.tokens` comes to.

## `rate` — seconds on the clock

**A rate is tokens a second over seconds on the clock**, not seconds an agent was talking. A flow
sleeps between rounds, commits, and reads what the last turn wrote, and that time is time the
tokens were spent over. That is the honest reading of what a run is costing per hour.

The window defaults to five minutes — `hmz.agents.WINDOW`, the same one the interface's readout
is over. A run younger than the window is measured **over the run**, so a rate read a minute in is
what that minute came to rather than a fifth of it.

**It moves while the turn is still running.** A turn is minutes long, so a number that only moved
when one ended would stand still for all of them. Every backend here is read as it says what each
request to the model cost:

| Backend | Read from |
| --- | --- |
| Claude Code, pi | the message it answered with |
| Codex | `thread/tokenUsage/updated` |
| opencode, mimocode | each step |
| Kimi Code | the session it is polling anyway |

## `juice` — and it is not a clock at all

It is what **one turn of the model** came out with: one request and the answer to it, of which a
turn a flow asks for is many.

A model asked to think harder writes more in each answer and takes longer over it — so that
average is what an [effort](/features/efforts) moves, and it is the number to steer by when what
you are holding is *how hard the thing is thinking* rather than how fast a bill is running up.

```python
if agent.juice(over=120) < target:
    agent.effort = harder(agent.effort)
```

That is [`official/fixed_juice_ralph`](/reference/flows#the-official-flowverse), which moves the
effort a rung a round to hold the agent to a target.

A window with no turn in it reads as `0.0`: nothing to go on, which a flow tells apart from a turn
that said nothing.

A backend that states a whole turn's cost **after** having said what each request in it came to is
settling up rather than taking another turn, and is not counted as one — or the average would be
halved by the accounting.

## At the prompt

Under the agent lines, above the editor:

```
              builder · claude/claude-opus-4-8:high · ● 2 of 5
              reviewer · codex/gpt-5.6-sol:high · ○ 3 · unread
                       48.2k tokens · 91/s
```

**Per model**, since two agents at one model are one bill. **Over a recent window only**, so a
flow that has stopped reads as stopped. [`/status`](/features/status) is the fuller version, with
the handover graph beside it.

## Two backends that report nothing

opencode and mimocode keep a session in a database rather than in a log file, so there is nothing
for the interface to read a running cost out of and nothing for
[`hmz collect`](/features/tracing) to gather.

What their turns cost still reaches a flow: each says it as the turn lands.

## See also

- [Efforts](/features/efforts) — what `juice` responds to
- [The shape of a run](/features/status)
- [Agents › What it has cost, and how fast](/reference/agents#what-it-has-cost-and-how-fast)

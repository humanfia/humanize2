# Cost and rate

Every session and every agent tells you what it has spent, how fast it is spending it, and how
hard it is thinking. Reach for this when you want to know what a run is costing while it is
still running.

## Try it

The readout sits under the agent lines, above the editor:

```
              builder · claude/claude-opus-4-8:high · ● 2 · reading
              reviewer · codex/gpt-5.6-sol:high · ○ 3 · unread
                       48.2k tokens · 91/s
```

It is **per model**, since two agents at one model are one bill, and it covers **a recent
window only**, so a flow that has stopped reads as stopped. [`/status`](/user/status) is the
fuller version, with the handover graph beside it.

## Three readings, three questions

The rest of this page is the weaver's — whoever wrote the flow. Every session and every agent
answers the same three:

| | Answers | Moves with |
| --- | --- | --- |
| `spent()` | what has this cost | everything |
| `rate()` | how fast is the bill running up | how many turns are going at once |
| `juice()` | how hard is it thinking | the [effort](/user/efforts) |

```python
session.spent()          # Usage(input=41230, output=2180, cache_read=980100)
session.rate()           # tokens a second, by kind, over the last five minutes
session.rate(over=60)    # over the last minute instead
session.juice(over=60)   # output tokens an average turn of the model came out with
agent.spent()            # every session this agent has opened, dropped ones included
agent.rate(over=60)
agent.juice()
```

## `spent` — a mapping of kind to tokens

`input` and `output` are the two that every backend counts, and they sit on the mapping as
attributes. The rest differ from CLI to CLI: a cache read, a cache write, or the reasoning a
backend counts beside the output rather than inside it. So **a kind that is not there is one
that backend does not report**:

```python
spent = session.spent()
spent.input, spent.output, spent.total       # always
spent.get("cache_read", 0)                   # for a backend that counts one
dict(spent)                                  # everything it does count
```

The `result` event a turn ends on carries the same reckoning, beside the per-model `tokens` it
already carried. `result.spent.total` is what `result.tokens` comes to.

## `rate` — seconds on the clock

**A rate is tokens a second over seconds on the clock**, not seconds an agent was talking. A
flow sleeps between rounds, commits and reads what the last turn wrote. That time is time the
tokens were spent over, and it is the honest reading of what a run costs per hour.

The window defaults to five minutes — `hmz.flows.WINDOW`, the same window the interface's
readout uses. A run younger than the window is measured **over the run**, so a rate read a
minute in is what that minute came to, not a fifth of it.

**The rate moves while the turn is still running.** A turn is minutes long, so a number that
only moved when one ended would stand still for all of them. Each backend is read where it says
what a request to the model cost:

| Backend | Read from |
| --- | --- |
| Claude Code, pi | the message it answered with |
| Codex | `thread/tokenUsage/updated` |
| opencode, mimocode | each step |
| Kimi Code | the session it is polling anyway |
| ZCode | its `model-io` log, a row per request the turn made |

## `juice` — and it is not a clock at all

`juice()` is what **one turn of the model** came out with: one request and the answer to it. A
turn a flow asks for is many of these.

A model asked to think harder writes more in each answer and takes longer over it, so that
average is what an [effort](/user/efforts) moves. It is the number to steer by when you hold
*how hard the thing is thinking*, rather than how fast a bill is running up.

```python
if agent.juice(over=120) < target:
    agent.effort = harder(agent.effort)
```

That is what [`official/fixed_juice_ralph`](/flows/fixed-juice-ralph) does, a rung a round, to
hold the agent to a target.

A window with no turn in it reads as `0.0`. There is nothing to go on, and a flow tells that
apart from a turn that said nothing.

A backend that states a whole turn's cost **after** having said what each request in it came to
is settling up rather than taking another turn. It is not counted as one, or the average would
be halved by the accounting.

## Two backends that report nothing

opencode and mimocode keep a session in a database rather than in a log file. So the interface
has nothing to read a running cost out of, and [`hmz trace collect`](/user/tracing) has nothing
to gather. What their turns cost still reaches a flow: each says it as the turn lands.

## See also

- [Efforts](/user/efforts) — what `juice` responds to
- [The shape of a run](/user/status)
- [Agents › What it has cost, and how fast](/reference/agents#what-it-has-cost-and-how-fast)

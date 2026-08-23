---
pageClass: hmz-feature
---

# official/fixed_juice_ralph

[`ralph_loop`](/flows/ralph-loop) with a governor on it: a fresh session every round, and
between the rounds the [effort moved](/reference/agents#moving-the-effort-while-it-runs) a rung
to hold the agent to `juice` output tokens per turn of the model.

```sh
hmz exec -f official/fixed_juice_ralph -a claude/claude-opus-5:high "$(cat TASK.md)"
```

<HmzFlowShape flow="fixed_juice_ralph" />

## A governor is not a brake

What it holds steady is the size of an answer. A loop held to 2000 output tokens a turn is a
loop that goes on producing 2000 output tokens a turn for as long as anybody leaves it running;
what ends it is still the budget.

The two are one quantity read at two scales: `juice` is what a turn is worth, and `budget` is
what the loop is.

Per turn of the **model** — one request and the answer to it — rather than per turn of the
flow, which is many of those and as many again of whatever the tools took. That average is what
an effort actually moves: a model asked to think harder writes more in each answer and takes
longer over it. So an agent under the target is asked to think harder and one over it to think
less, one rung of its own model's ladder per round, so that the loop settles rather than
swings.

Nothing here is a clock. How long a round takes and what it costs an hour are what the model
and the work make of it.

## What it takes

```yaml
juice: 2000     # output tokens an average turn of the model is to come out with
over: 300       # how far back that average is taken, in seconds
slack: 0.15     # how far off it may be before the effort moves
rest: 5         # seconds between rounds
budget: 10      # millions of output tokens the whole loop may come to
```

| | |
| --- | --- |
| `juice` | What a turn of the model is to come out with, in output tokens. **2000.** |
| `over` | How far back the average is taken, in seconds. **300.** |
| `slack` | How far off the average may be before the effort moves, as a fraction of the target — 0.15 leaves it alone between 85% and 115%. |
| `rest` | Seconds between rounds. **5.** |
| `budget` | Millions of output tokens the whole loop may come to. **10**, `0` for no limit. |

## What it keeps

`rounds`, `output`, and `effort` — the rung the governor settled at. A loop started again at
the top of the ladder walks back down to that rung one paid turn at a time, which is the thing
worth keeping.

The rung is kept as the effort's **own word** rather than as a place on the ladder, because the
ladder is whatever the account says its CLI runs today: a model retired and an effort added
both move the places. A word that is no longer on the ladder is read as no rung, and leaves the
agent where a first run would start it.

The answer size is not kept. It is an average over the last few minutes of turns, and a run
starting today has none of yesterday's minutes to average.

## See also

- [Efforts](/user/efforts) — what a rung is, and which ladder each model has
- [Cost and rate](/user/tally) — reading what a run is spending while it runs
- [ralph_loop](/flows/ralph-loop) — the same loop, ungoverned

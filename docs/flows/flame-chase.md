---
pageClass: hmz-feature
---

# flame_chase

Two agents take turns on the same task, in one working directory, each starting from the
repository rather than from a history. Neither is told what the other said; the tree is the
only account of the last turn there is.

```sh
hmz exec -f flame_chase \
    -a claude/claude-opus-5:max -a codex/gpt-5.6-sol:max "$(cat TASK.md)"
```

<HmzFlowShape flow="flame_chase" />

## Why two

Two different models fail differently. A loop over one agent compounds that agent's blind spot;
a loop that alternates gives every round to somebody who did not write what they are looking
at.

Give the two the same model and effort and they are still two agents, which is sometimes the
point: a [trace](/features/tracing) reads the run as two sets of sessions rather than one.

## What ends it

The flow takes no settings of its own. What ends a run of it is the run's
[allowance](/features/allowances) — hours, millions of output tokens, dollars. The **two spend
it between them** rather than apiece, and that is the ordinary case rather than this flow's own
arithmetic: an allowance is the run's money, and every agent of a run spends out of the one
reckoning whichever of them was writing. It declares **ten million output tokens** as what a run
of it is worth by default; `-c budget.yaml` with a `budget:` mapping in it, or the **budget** row
in `/flow`, says otherwise.

## What it keeps

`turn` and `rounds`. The turn is the half that has to be kept: a run that always opened at the
first agent would hand it the turn the other was owed — two turns in a row, the one thing a flow
built on alternating must not do.

A round is a turn each, and the turn that *finishes* one counts it, so a round the first agent
was cut off in is finished, and counted once, by the run that picks that turn up.

## See also

- [rlar](/flows/rlar) — two agents, but one of them reviews rather than works
- [parallel_flame_chase](/flows/parallel-flame-chase) — three of these at once, in isolation
- [Many backends, one agent](/features/backends) — what you can put on either side of it

---
pageClass: hmz-feature
---

# official/flame_chase

Two agents take turns on the same task, in the same working directory, each starting from the
repository rather than from a history. Neither is told what the other said; what passes between
them is the tree, which is the only account of the last turn there is.

```sh
hmz exec -f official/flame_chase \
    -a claude/claude-opus-5:max -a codex/gpt-5.6-sol:max "$(cat TASK.md)"
```

<HmzFlowShape flow="flame_chase" />

## Why two

Two different models fail differently. A loop over one agent compounds that agent's blind spot;
a loop that alternates gives every round to somebody who did not write what they are looking
at, and has to read the tree to find out what happened.

Give the two the same model and effort and they are still two agents, which is sometimes the
point: a [trace](/features/tracing) reads the run as two sets of sessions rather than one.

## What it takes

`budget`, in millions of output tokens the **two may spend between them** across every run of
it in this workspace. **10 by default**, `0` for no limit. Between them rather than apiece,
because the loop is the two of them: a pair that alternates spends what it spends whichever of
them was writing at the time.

## What it keeps

`turn`, `rounds` and `output`. The turn is the half that has to be kept: a run that always
opened at the first agent would hand it the turn the other one was owed, and two turns in a row
is the one thing a flow whose whole shape is two agents alternating must not do.

A round is a turn each, so it is the turn that *finishes* one that counts it — a round the
first agent was cut off in is finished by the run that picks that turn up, and a round finished
once is counted once.

## See also

- [official/rlar](/flows/rlar) — two agents, but one of them reviews rather than works
- [official/parallel_flame_chase](/flows/parallel-flame-chase) — three of these at once, in isolation
- [Many backends, one agent](/features/backends) — what you can put on either side of it

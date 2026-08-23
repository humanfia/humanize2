---
pageClass: hmz-feature
---

# ralph_loop

A fresh session every round, so nothing carries over but the repository: the agent starts from
the task each time, and what the round before it did is whatever it left in the working
directory. The oldest trick in unattended agent work, and still the one that survives the
longest runs — a loop that cannot poison itself with its own context.

```sh
hmz exec -f ralph_loop -a claude/claude-opus-5:high "$(cat TASK.md)"
```

<HmzFlowShape flow="ralph_loop" />

## Why it holds up

A session that runs for a day accumulates every wrong turn it took. A round that starts clean
reads the repository as it is — the tests the last round broke, the file it left half-written —
with no memory of the reasoning that got it there.

The cost is real: an agent that forgets will re-derive things, and sometimes undo a decision it
made an hour ago because nothing in the tree records that it was a decision. Write the
decisions into the repository, and the loop reads them back.
[`stateful_ralph`](/flows/stateful-ralph) is the same loop with the opposite trade.

## What it takes

```yaml
budget: 25    # millions of output tokens; 0 goes on until it is stopped
```

**10 million by default**, [counted across every run of it here](/flows/). Pass it with `-c
budget.yaml`, or `/config` at the prompt; see [Settings of its own](/weaver/flow-settings).

## What it keeps

`rounds` and `output`. A loop left going for days will be stopped — esc, a machine that goes
down, a turn that takes the process with it — so running it again goes on from the round it
reached rather than back at one.

A loop that has spent its budget is **over**, and what is over is not picked up: it clears what
it kept, so the next run here opens at round one on a budget of its own rather than stopping
before it has taken a turn. See [Picking a run up](/user/resuming).

## What else ends it

**Three rounds in a row that answered with nothing.** A round whose turn failed answers with
nothing and spends nothing, so a loop whose account was refused — or whose model that account
may not run — would sit under a budget that never moves, going round on the same failure for as
long as it was left. What it kept is left alone rather than cleared: a loop that stalled is one
to fix and carry on from, not one that is over.

## See also

- [stateful_ralph](/flows/stateful-ralph) — one session instead, re-sent the task each round
- [official/fixed_juice_ralph](/flows/fixed-juice-ralph) — this loop with a governor on it
- [official/goal](/flows/goal) — this loop, with each round run as the agent's own goal
- [Loops](/weaver/loops) — writing one of these yourself

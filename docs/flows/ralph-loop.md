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

## What ends it

The run's [allowance](/features/allowances) — hours on the clock, millions of output tokens,
dollars — which is humanize's rather than this flow's: it is held to at the edges of every turn
of every session, so a round taken once it is spent raises rather than answering and the loop
needs no exit of its own. The flow itself takes no settings at all.

**Ten million output tokens by default**, which is what the flow declares a run of it is worth.
`-c budget.yaml` with a `budget:` mapping in it says otherwise, and so does the **budget** row
on the page `/flow` puts a flow's agents on.

## What it keeps

`rounds`. A loop left going for days will be stopped — esc, a machine that goes down, a turn
that takes the process with it — so running it again goes on from the round it reached rather
than back at one.

A run stopped by its allowance is one to **pick up**, not one that is over. The allowance is
that run's and the next run gets one of its own, so what was kept is left exactly where it is
rather than cleared. See [Picking a run up](/user/resuming).

## What else ends it

**Three rounds in a row that answered with nothing.** A round whose turn failed answers with
nothing and spends nothing, so a loop whose account was refused — or whose model that account
may not run — would sit under a token allowance that never moves, going round on the same
failure for as long as it was left. Hours are the dimension that moves for it anyway; three
stalled rounds end it sooner. What it kept is left alone here too: a loop that stalled is one to
fix and carry on from, not one that is over.

## See also

- [stateful_ralph](/flows/stateful-ralph) — one session instead, re-sent the task each round
- [fixed_juice_ralph](/flows/fixed-juice-ralph) — this loop with a governor on it
- [goal](/flows/goal) — this loop, with each round run as the agent's own goal
- [Loops](/weaver/loops) — writing one of these yourself

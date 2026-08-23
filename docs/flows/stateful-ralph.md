---
pageClass: hmz-feature
---

# stateful_ralph

One session, held for the whole run, re-sent the task every round. The opposite trade to
[`ralph_loop`](/flows/ralph-loop): the agent remembers every round it has taken, including the
approaches it has already ruled out.

```sh
hmz exec -f stateful_ralph -a kimi/kimi-code/k3:high "$(cat TASK.md)"
```

<HmzFlowShape flow="stateful_ralph" />

## What grows

Two things, and only one of them is money. The spend is the budget's business. The other is the
context window: one session is one conversation, and a conversation that has been going for six
hours is one the backend is compacting, summarising or refusing. That is the ceiling this flow
runs into, and it is the backend's ceiling rather than humanize's.

Reach for it when the work is exploratory — when *what has already been tried* is the expensive
thing to rediscover — and reach for `ralph_loop` when the work is long.

## What it takes

| | |
| --- | --- |
| `budget` | Millions of output tokens the loop may spend, across every run of it in this workspace. **10 by default**, `0` for no limit. |

## What it keeps

`rounds` and `output` — and not the session, which is the one thing this flow is and the one
thing a run picked up cannot have back. No backend reopens a named session, so running this
again is a conversation of its own, starting from the task and the repository with none of the
rounds before it in context. A loop stopped on its fortieth round says round 41 when it is
started again, and remembers nothing else about the forty.

## What else ends it

**Three rounds in a row that answered with nothing.** A round whose turn failed answers with
nothing and spends nothing, so a loop whose account was refused — or whose model that account
may not run — would sit under a budget that never moves and go round on the same failure for as
long as it was left. What it kept is left alone when it stops this way, rather than cleared: a
loop that stalled is one to fix and carry on from, not one that is over.

## See also

- [ralph_loop](/flows/ralph-loop) — a session of its own each round
- [official/continue_loop](/flows/continue-loop) — one session too, nudged rather than re-sent the task
- [Picking a run up](/guide/resuming) — what a resumable flow may and may not carry

---
pageClass: hmz-feature
---

# official/goal

Ralph, with the task set as the agent's own [goal](/features/goals): a turn that would have
ended starts another instead, until the model itself says the objective is met. The loop is
only what starts it over where it stopped without having met it.

```sh
hmz exec -f official/goal -a claude/claude-opus-5:max "$(cat TASK.md)"
```

<HmzFlowShape flow="goal" />

## Two things decide, and only one of them is your code

The ticks inside one box above are turns the *backend* started. `agent.pursue(task)` hands the
objective to the backend's own goal feature; what comes back is one call, with as many turns of
the model inside it as it thought the objective needed.

That is why you reach for this rather than [`ralph_loop`](/flows/ralph-loop): "is this done?"
is asked by something that has just read the work, every turn, rather than by a `while True`
that cannot tell. The cost is that it is asked by the same thing that did the work, which
[`official/rlar`](/flows/rlar) fixes by asking somebody else.

A backend without a goal feature cannot run this flow, and says so before the first turn rather
than an hour in. [Which backends have one](/weaver/goals#which-backends-have-one).

## What it takes

`budget`, millions of output tokens [counted across every run of it here](/flows/) — **10 by
default**, `0` for no limit. It counts **every turn of the model the goal took**, not one per
round: the backend started them, and the agent counted them all.

## What it keeps

`rounds` and `output`. A goal is pursued in a session of its own and nothing of it carries into
the next, so a round begun by a run picked up starts from the task and the repository exactly
as the first round did.

## See also

- [It decides when it is done](/features/goals) — what a goal is
- [ralph_loop](/flows/ralph-loop) — the same loop, with your code deciding a turn is over
- [official/rlar](/flows/rlar) — somebody other than the worker deciding

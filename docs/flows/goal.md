---
pageClass: hmz-feature
---

# goal

Ralph, with the task set as the agent's own [goal](/features/goals): a turn that would have
ended starts another instead, until the model itself says the objective is met. The loop is
only what starts it over where it stopped without having met it.

```sh
hmz exec -f goal -a claude/claude-opus-5:max "$(cat TASK.md)"
```

<HmzFlowShape flow="goal" />

## Two things decide, and only one of them is your code

The ticks inside one box above are turns the *backend* started. `agent.pursue(task)` hands the
objective to the backend's own goal feature; what comes back is one call, with as many turns of
the model inside it as it thought the objective needed.

That is why you reach for this rather than [`ralph_loop`](/flows/ralph-loop): "is this done?"
is asked by something that has just read the work, every turn, rather than by a `while True`
that cannot tell. The cost is that it is asked by the same thing that did the work, which
[`rlar`](/flows/rlar) fixes by asking somebody else.

A backend without a goal feature cannot run this flow, and says so before the first turn rather
than an hour in. [Which backends have one](/weaver/goals#which-backends-have-one).

## What ends it

The run's [allowance](/features/allowances) — hours, millions of output tokens, dollars. It
counts **every turn of the model the goal took**, not one per round: the backend started them,
and the agent counted them all. The flow itself takes no settings; it declares **ten million
output tokens** as what a run of it is worth by default, and `-c budget.yaml` with a `budget:`
mapping in it, or the **budget** row in `/flow`, says otherwise.

An allowance is read at the edges of the session a goal runs in rather than inside it, so a goal
that burns for an hour inside one call is not cut off mid-call. It stops at the next round.

## What it keeps

`rounds`. A goal is pursued in a session of its own and nothing of it carries into the next, so
a round begun by a run picked up starts from the task and the repository exactly as the first
round did.

## See also

- [It decides when it is done](/features/goals) — what a goal is
- [ralph_loop](/flows/ralph-loop) — the same loop, with your code deciding a turn is over
- [rlar](/flows/rlar) — somebody other than the worker deciding

---
pageClass: hmz-feature
---

# official/goal

Ralph, with the task set as the agent's own [goal](/features/goals). A turn that would have
ended starts another instead, until the model itself says the objective is met — and the loop
is only what starts it over where it stopped without having met it.

```sh
hmz exec -f official/goal -a claude/claude-opus-5:max "$(cat TASK.md)"
```

<HmzFlowShape flow="goal" />

## Two things decide, and only one of them is your code

The ticks inside one box above are turns the *backend* started. `agent.pursue(task)` hands the
objective to the backend's own goal feature; what comes back is one call, and inside it are as
many turns of the model as the model thought the objective needed.

That is the whole reason to reach for this rather than [`ralph_loop`](/flows/ralph-loop): the
question "is this done?" is asked by something that has just read the work, every turn, rather
than by a `while True` that cannot tell. The cost is that it is asked by the same thing that
did the work — which is exactly what [`official/rlar`](/flows/rlar) fixes by asking somebody
else.

A backend without a goal feature cannot run this flow, and says so before the first turn rather
than an hour in. [Which backends have one](/weaver/goals#which-backends-have-one).

## What it takes

| | |
| --- | --- |
| `budget` | Millions of output tokens the loop may spend, across every run of it in this workspace. **10 by default**, `0` for no limit. |

The budget counts **every turn of the model the goal took**, not one per round: the backend
started them itself, and the agent counted all of them.

## What it keeps

`rounds` and `output`, and there is nothing else it could honestly keep. A goal is pursued in a
session of its own and nothing of it carries into the next one, so a round begun by a run
picked up starts from the task and the repository exactly as the first round of the first run
did.

## See also

- [It decides when it is done](/features/goals) — what a goal is, and which backends have one
- [ralph_loop](/flows/ralph-loop) — the same loop, with your code deciding a turn is over
- [official/rlar](/flows/rlar) — somebody other than the worker deciding

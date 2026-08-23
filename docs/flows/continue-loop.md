---
pageClass: hmz-feature
---

# official/continue_loop

Sends the task once, then keeps nudging `continue` at the session that heard it. The same one
session as [`stateful_ralph`](/flows/stateful-ralph), told to carry on rather than told what to
do again — which is what a person at a prompt actually types, and is a different prompt from
the task however similar it looks.

```sh
hmz exec -f official/continue_loop -a kimi/kimi-code/k3:high "$(cat TASK.md)"
```

<HmzFlowShape flow="continue_loop" />

## Until a turn lands, the task is sent again

`continue` means something only to a session that heard what it is continuing. So the flow
sends the task, and only once a turn has actually landed does the prompt become `continue`:

```python
answered = session(prompt, suppress=True)
if answered:
    prompt = "continue"
```

A turn that failed — a backend that fell over before it said anything — answers with nothing,
and the next round sends the task rather than nudging a session that never got it.

## What it takes

`budget`, in millions of output tokens the loop may spend across every run of it in this
workspace. **10 by default**, `0` for no limit.

## What it keeps

`rounds` and `output`. That the task has been sent is **not** kept: a picked-up run opens a
session that has heard nothing, and starts it on the task exactly as the first run did. What
the agent went on to say is the backend's own log to keep, not this flow's.

## See also

- [stateful_ralph](/flows/stateful-ralph) — the same session, re-sent the task rather than nudged
- [official/goal](/flows/goal) — the backend's own way of not stopping

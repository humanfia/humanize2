# Examples

The flow loops from [flowbench-internal](https://github.com/humanfia), rewritten on
`amflows.janus`. Each is a bare `while True` loop that takes the agent(s) or session(s) as
arguments, so swapping the backend never touches the loop. Like flowbench, the loops run forever
(stop them with Ctrl-C) and survive a failed turn.

Which of the two the loop takes *is* the flow's memory model: an agent hands every turn a new
session, a session carries the turns of one conversation.

| Example | flowbench flow | takes | loop |
|---|---|---|---|
| [ralph_loop.py](ralph_loop.py) | `ralph_loop` | agent | run the task |
| [goal.py](goal.py) | `goal` | agent | hand the task to the agent's own `/goal` feature |
| [flame_chase.py](flame_chase.py) | `flame_chase` | agents | two backends take turns |
| [stateful_ralph.py](stateful_ralph.py) | `stateful_ralph` | session | keep re-sending the task |
| [continue_loop.py](continue_loop.py) | `continue_loop` | session | send the task once, then "continue" |
| [rlar.py](rlar.py) | `rlar` | session + agent | executor works; fresh reviewer judges; verdict fed back |

Run one (needs the relevant agent CLI installed and a `TASK.md` in the working directory):

```sh
uv run python examples/ralph_loop.py
```

## Notes

- flowbench spells each flow out per backend and effort (`ralph_loop/opus48_max`,
  `ralph_loop/k3_max`, …). Here both are constructor arguments, so one file per flow covers
  every one of its variants.
- `goal/gpt56sol_max` is the one variant with no equivalent here: Codex only exposes `/goal`
  through its app-server JSON-RPC API, not through `codex exec`, so it is out of reach of a
  CLI-exec facade. The Claude variant is [goal.py](goal.py)'s `__main__`, and the Kimi variant
  is the same call with `prefix="/goal -- "`.
- flowbench's `k3_swarm` variants change the runtime under a flow, not the flow, so they map
  onto the same files.

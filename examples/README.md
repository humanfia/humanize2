# Examples

The flow loops from [flowbench-internal](https://github.com/humanfia), rewritten on flowjanus. Each
is a bare `while True` loop that takes the agent(s) as arguments, so swapping the backend never
touches the loop. Like flowbench, the loops run forever (stop them with Ctrl-C).

| Example | flowbench origin | loop |
|---|---|---|
| [ralph_loop.py](ralph_loop.py) | `ralph_loop` | run the task |
| [ultra_ralph.py](ultra_ralph.py) | `ultra_ralph` | run the task (max-effort agent) |
| [stateful_ralph.py](stateful_ralph.py) | `always_prompt` | run the task, keep re-sending it |
| [continue_loop.py](continue_loop.py) | `always_continue` | run the task once, then send "continue" |
| [arar.py](arar.py) | `arar` | executor runs; reviewer judges; feed the verdict back |
| [flame_chase.py](flame_chase.py) | `flame_chase` | two backends take turns |

Run one (needs the relevant agent CLI installed and a `TASK.md` in the working directory):

```sh
uv run python examples/ralph_loop.py
```

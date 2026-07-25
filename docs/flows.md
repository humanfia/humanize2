# Flows

A flow is a Python file with a `run(agents, task)` in it, and `amflows run` runs one in this
directory:

```sh
amflows run -f|--flow <flow> -a|--agents <backend>/<model>/<effort>[,<backend>/<model>/<effort>...] <task>
```

```sh
amflows run -f examples/ralph_loop.py -a claude/claude-opus-4-8/high "$(cat TASK.md)"
amflows run -f examples/flame_chase.py -a claude/claude-opus-4-8/max,codex/gpt-5.6-sol/max "fix the build"
```

`-a` takes as many agents as the flow drives, in the order it takes them; the option may be
repeated instead of comma separated. A flow says how many it drives in the tuple it annotates them
with, and a command line that names a different number is refused before anything runs:

```python
def run(agents: tuple[AgentBase, AgentBase], task: str) -> None:  # two agents, and only two
```

`AgentBase` has to be imported at runtime rather than under `TYPE_CHECKING`, so that the count it
states can be read back.

[examples/](../examples/) has the flow loops from flowbench written this way: `ralph_loop`, `goal`,
`flame_chase`, `stateful_ralph`, `continue_loop` and `rlar`. See
[Security](../README.md#security) before running one.

A name, an [anchor](remote-execution.md#anchoring-a-flow) and a
[machine of the agent's own](isolation.md) are settings of the agent rather than of the flow, so
`-a` does not reach them. A flow that needs one is handed [agents](agents.md) built in Python:

```python
from amflows.janus import ClaudeCodeAgent, ClaudeCodeAgentConfig, Runner

config = ClaudeCodeAgentConfig(model="claude-opus-4-8", effort="high")
agents = [
    ClaudeCodeAgent(config, name="actor"),
    ClaudeCodeAgent(config, name="reviewer"),
]

Runner("examples/rlar.py", agents).run("fix the build")
```

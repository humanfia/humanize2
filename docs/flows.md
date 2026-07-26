# Flows

A flow is a Python file with a `run(agents, task)` in it, and `amflows run` runs one in this
directory:

```sh
amflows run -f|--flow <flow> -a|--agents <backend>/<model>/<effort>[,<backend>/<model>/<effort>...] <task>
```

```sh
amflows run -f ralph_loop -a claude/claude-opus-4-8/high "$(cat TASK.md)"
amflows run -f flame_chase -a claude/claude-opus-4-8/max,codex/gpt-5.6-sol/max "fix the build"
```

`-a` takes as many agents as the flow drives, in the order it takes them; the option may be
repeated instead of comma separated. A flow says how many it drives in the tuple it annotates them
with, and a command line that names a different number is refused before anything runs:

```python
def run(agents: tuple[AgentBase, AgentBase], task: str) -> None:  # two agents, and only two
```

`AgentBase` has to be imported at runtime rather than under `TYPE_CHECKING`, so that the count it
states can be read back.

A running flow can be talked to. `amflows tui` opens a prompt where tab picks a flow, the first
thing you say starts it, and anything said after that goes to the agent taking its turn — held
for the next one if none is open, so a line to a running flow is never dropped. Esc stops it.
Claude Code answers each thing it is told with a turn of its own, so a word put in mid-turn is read within the same turn and
the answer that comes back is the answer to it — the turn is over once the agent has answered
everything it was told, not when it first stops. Codex takes it as a steer on the turn its app
server is running, and Kimi queues it and then steers it into the turn already running — which
is why neither goes through a command line run per turn any more: such a run has ended by the
time there is anything to say to it. An [anchored](remote-execution.md) Claude ends its process with
each turn, so its work reaches the target before the turn says it landed; it is therefore
between turns rather than during one that it hears you. An anchored Codex keeps one app server
for the life of the agent and can be steered throughout, at the cost of the same guarantee: its
work reaches the target whenever a command runs there, which for a coding agent is constantly,
rather than at the end of every turn.

Beside the transcript is what the flow is doing: which agent has the turn, the handovers
between them as they happen, and what each model has cost with the rate it is costing it at.
None of that is asked of the flow — a flow is a Python file that may branch any way it likes,
so the turns going past are the only place its shape is ever visible.

amflows comes with the flow loops from flowbench written this way, run by name: `ralph_loop`, `goal`,
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

Runner("rlar", agents).run("fix the build")
```

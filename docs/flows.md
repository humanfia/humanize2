# Flows

A flow is a Python file with a `run(agents, task)` in it, and `hmz exec` runs one in this
directory:

```sh
hmz exec -f|--flow <flow> -a|--agent <cli>/<model>:<effort> [-a ...] <task>
```

```sh
hmz exec -f ralph_loop -a claude/claude-opus-4-8:high "$(cat TASK.md)"
hmz exec -f flame_chase -a claude/claude-opus-4-8:max -a codex/gpt-5.6-sol:max "fix the build"
```

One `-a` is one agent, repeated once for each the flow drives, in the order it takes them. An
agent is a CLI, a model and an effort, and may be written out instead when a model or an effort
holds the punctuation the short form separates on:

```sh
hmz exec -f ralph_loop -a cli=claude,model=claude-opus-4-8,effort=high "$(cat TASK.md)"
```

A flow says how many agents it drives in the tuple it annotates them with, and a command line
that names a different number is refused before anything runs:

```python
def run(agents: tuple[AgentBase, AgentBase], task: str) -> None:  # two agents, and only two
```

`AgentBase` has to be imported at runtime rather than under `TYPE_CHECKING`, so that the count it
states can be read back.

A `NamedTuple` says what each of them is for as well as how many there are. The flow then reaches
them by name, and so does everything else: `/agents` asks what the reviewer runs rather than what
agent 2 of 2 runs, and a trace groups each one's sessions under the same word.

```python
class Agents(NamedTuple):
    actor: AgentBase
    reviewer: AgentBase


def run(agents: Agents, task: str) -> None:
    working = agents.actor.new()
```

## Where flows live

`-f` takes a name or a path. A name is looked for in three places, nearest first:

| | |
| --- | --- |
| `.humanize/flows/*.py` | this project's own |
| `~/.humanize/flows/*.py` | yours, in every project |
| — | the ones humanize came with |

Nearest wins, so a flow of your own may stand in for one of humanize' by taking its name — a
`.humanize/flows/rlar.py` is what `-f rlar` runs in that project. Anything with a slash or an
extension in it is a path, taken as given:

```sh
mkdir -p .humanize/flows && cp my_loop.py .humanize/flows/
hmz exec -f my_loop -a claude/claude-opus-4-8:high "fix the build"
hmz exec -f ./somewhere/else.py -a claude/claude-opus-4-8:high "fix the build"
```

A running flow can be talked to. `hmz` opens a prompt where shift+tab steps through the flows, the first
thing you say starts it, and anything said after that goes to the agent taking its turn — held
for the next one if none is open, so a line to a running flow is never dropped. Esc stops it, and
so does ctrl+c with nothing half-typed; two ctrl+c leave. An agent that stops to ask you something
gets the next line you type as its answer, unless `/afk` has said you are not there — in which
case it is told nobody answered and carries on rather than waiting.
Claude Code answers each thing it is told with a turn of its own, so a word put in mid-turn is
read within the same turn and the answer that comes back is the answer to it — the turn is over
once the agent has answered everything it was told, not when it first stops. Codex takes it as a
steer on the turn its app server is running, and Kimi queues it and then steers it into the turn
already running — which is why neither goes through a command line run per turn any more: such a
run has ended by the time there is anything to say to it. An [anchored](remote-execution.md)
Claude ends its process with each turn, so its work reaches the target before the turn says it
landed; it is therefore between turns rather than during one that it hears you. An anchored
Codex keeps one app server for the life of the agent and can be steered throughout, at the cost
of the same guarantee: its work reaches the target whenever a command runs there, which for a
coding agent is constantly, rather than at the end of every turn.

Beside the transcript is what the flow is doing: which agent has the turn, the handovers
between them as they happen, and what each model has cost with the rate it is costing it at.
None of that is asked of the flow — a flow is a Python file that may branch any way it likes,
so the turns going past are the only place its shape is ever visible.

`chat` is the flow `hmz` opens on: one agent, one session, and every line typed between turns
is a turn of it — which is talking to a coding agent, with no loop around it. It is why saying
something is all it takes to start, and why picking a flow is what you do once talking to one
agent is not the shape of the work. Picking one stops whatever was running.

humanize comes with the flow loops from flowbench written this way too, run by name:
`ralph_loop`, `goal`, `flame_chase`, `stateful_ralph`, `continue_loop` and `rlar` — and with
`humanize1_rlcr`,
which is [PolyArch/humanize](https://github.com/PolyArch/humanize) as one unattended run: an idea
opened from six directions and picked on evidence, a plan converged between the builder and a
reviewer that has to accept it, then built under a reviewer that checks first the claim and then
the code. See [Security](../README.md#security) before running one.

A name, an [anchor](remote-execution.md#anchoring-a-flow) and a
[machine of the agent's own](isolation.md) are settings of the agent rather than of the flow, so
`-a` does not reach them. A flow that needs one is handed [agents](agents.md) built in Python:

```python
from humanize.janus import ClaudeCodeAgent, ClaudeCodeAgentConfig, Runner

config = ClaudeCodeAgentConfig(model="claude-opus-4-8", effort="high")
agents = [
    ClaudeCodeAgent(config, name="actor"),
    ClaudeCodeAgent(config, name="reviewer"),
]

Runner("rlar", agents).run("fix the build")
```

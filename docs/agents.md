# Agents

An agent runs at a model and an effort; a session is one conversation with it. Which of the two a
[flow](flows.md) holds decides what it remembers.

```python
from amflows.janus import ClaudeCodeAgent, ClaudeCodeAgentConfig

agent = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="claude-opus-4-8", effort="high"))

agent.launch().run(
    "Read TASK.md and get started."
)  # a new session: nothing carries over

session = agent.launch()
session.run("Read TASK.md and get started.")  # opens the session
session.run("continue")  # resumes it, task still in context
```

`CodexAgent` and `KimiCodeCLIAgent` take the same calls. What a turn says is passed through as it
arrives, and a turn that fails raises `subprocess.CalledProcessError` without opening the session,
so the next call retries it.

## Goals

A session can be given a goal instead of a prompt. This is the backend's own goal feature, the one
its `/goal` command reaches: the agent decides for itself when the objective has been met, and
until it does, a turn that would have ended starts another.

```python
agent.launch().pursue("the suite passes and nothing has been stubbed out")
```

## Efforts

Kimi Code's effort says how wide to run as well as how hard to think: `max` is one agent, and
`swarmmax` is the same thinking at the width of a fleet of subagents.

## Names

Two agents at one model and one effort are still two agents — an actor and the reviewer that reads
its work. Name them, and each reports the sessions it opened, which is what tells a
[trace](tracing.md) apart:

```python
from amflows.oronyx import collect

config = ClaudeCodeAgentConfig(model="claude-opus-4-8", effort="high")
actor = ClaudeCodeAgent(config, name="actor")
reviewer = ClaudeCodeAgent(config, name="reviewer")
...
collect(agents={a.id: a.opened for a in (actor, reviewer)})
```

`opened` is the backend's id for every session the agent ever opened, including the ones a Ralph
loop dropped a turn later — ids, so a flow running for days remembers them in a list of strings.

## Machines

A config also says where the agent's turns land: an `anchor` puts them on
[another machine](remote-execution.md#anchoring-a-flow), an `isolation` puts them in a
[container of the agent's own](isolation.md). One or the other, never both — a config given both
is refused.

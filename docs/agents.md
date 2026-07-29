# Agents

An agent runs at a model and an effort; a session is one conversation with it. Which of the two a
[flow](flows.md) holds decides what it remembers.

```python
from humanize.agents import ClaudeCodeAgent, ClaudeCodeAgentConfig

agent = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="claude-opus-4-8", effort="high"))

agent("Read TASK.md and get started.")  # a session of its own: nothing carries over

session = agent.new()
session("Read TASK.md and get started.")  # opens the session
session("continue")  # resumes it, task still in context
```

`CodexAgent` and `KimiCodeCLIAgent` take the same calls. What a turn says is passed through as it
arrives, and a turn that fails raises `subprocess.CalledProcessError` without opening the session,
so the next call retries it.

A flow is a loop, and a loop that catches its own turns is a `try` around every line of it — so
`|| true` is a word on the call rather than a block around it:

```python
# A turn that failed answers with nothing, and the loop goes round again.
agent(task, suppress=True)
```

It catches a turn that failed and nothing else. An agent that has been told to stop still raises,
since a loop that carried on past that would never end.

## Goals

A session can be given a goal instead of a prompt. This is the backend's own goal feature, the one
its `/goal` command reaches: the agent decides for itself when the objective has been met, and
until it does, a turn that would have ended starts another.

```python
agent.pursue("the suite passes and nothing has been stubbed out")
```

## Questions

An agent may stop mid-turn to ask its user something. Set `ask` and it reaches you; leave it unset
— as a flow run from the command line does — and the backend is told nobody answered, so the turn
carries on rather than waiting on a reply that is not coming.

```python
agent.ask = lambda question: input(f"{question.text} {question.options} ")
```

## The person as an agent

A flow that is a conversation rather than a loop has two sides, and the second of them is you.
Declare a `HumanAgent` among the agents the flow drives and it is handed one: saying something to
it is asking what to say next, and what it answers with is what was typed.

```python
class Chat(NamedTuple):
    assistant: AgentBase
    human: HumanAgent


def run(agents: Chat, task: str) -> None:
    conversation = agents.assistant.new()
    said = task
    while said:
        answered = conversation(said, suppress=True)
        said = agents.human(answered)
```

Nobody is asked what the person runs, so a `HumanAgent` is not one of the agents `-a` names: the
flow above is run with one `-a` and drives two. Run from a command line, where nobody is at a
prompt, they answer with nothing — so the flow does the one thing it was given and stops.

## Efforts

Claude Code takes `ultracode` as well as the efforts it documents: `xhigh` thinking with the turn
opted into orchestrating a fleet of its own.

Kimi Code's effort says how wide to run as well as how hard to think: `max` is one agent, and
`swarmmax` is the same thinking at the width of a fleet of subagents.

## Names

Two agents at one model and one effort are still two agents — an actor and the reviewer that reads
its work. Name them, and each reports the sessions it opened, which is what tells a
[trace](tracing.md) apart. A [flow](flows.md) that declares its agents as a `NamedTuple` names
them for you, so this is for the ones built by hand:

```python
from humanize.tracing import collect

config = ClaudeCodeAgentConfig(model="claude-opus-4-8", effort="high")
actor = ClaudeCodeAgent(config, name="actor")
reviewer = ClaudeCodeAgent(config, name="reviewer")
...
collect(agents={a.id: a.opened for a in (actor, reviewer)})
```

`opened` is the backend's id for every session the agent ever opened, including the ones a Ralph
loop dropped a turn later — ids, so a flow running for days remembers them in a list of strings.

## Machines

A config also says where the agent's turns land, as one `machine`: an `AnchoredConfig` puts them
on [another machine](remote-execution.md#anchoring-a-flow) that is already running, a
`DockerConfig` puts them in a [container of the agent's own](isolation.md). One setting, because
it is one question.

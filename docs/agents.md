# Agents

Driving a coding agent from Python. An agent is settings; a
[session](concepts.md#session) is memory. Which of the two a [flow](flows.md) holds decides what
it remembers.

Everything here is importable from `humanize.agents`.

## Table of Contents

- [Making one](#making-one)
- [Turns](#turns)
- [Sessions](#sessions)
- [Watching a turn as it happens](#watching-a-turn-as-it-happens)
- [Talking to a turn already running](#talking-to-a-turn-already-running)
- [Goals](#goals)
- [Questions](#questions)
- [Stopping](#stopping)
- [Names, and what a run left behind](#names-and-what-a-run-left-behind)
- [The person as an agent](#the-person-as-an-agent)
- [Efforts](#efforts)
- [What each backend can do](#what-each-backend-can-do)
- [Where the turns land](#where-the-turns-land)
- [API summary](#api-summary)

## Making one

Each backend has an agent class and a config class, and they take the same calls:

```python
from humanize.agents import ClaudeCodeAgent, ClaudeCodeAgentConfig

agent = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="claude-opus-4-8", effort="high"))
```

| Backend | Agent | Config | Session |
| --- | --- | --- | --- |
| Claude Code | `ClaudeCodeAgent` | `ClaudeCodeAgentConfig` | `ClaudeCodeSession` |
| Codex | `CodexAgent` | `CodexAgentConfig` | `CodexSession` |
| Kimi Code | `KimiCodeCLIAgent` | `KimiCodeCLIAgentConfig` | `KimiCodeCLISession` |
| you | `HumanAgent` | — (takes only `name=`) | `HumanSession` |

A config takes `model`, `effort`, an optional [`machine`](#where-the-turns-land), and nothing
else. It is frozen, because a session resumes under the settings it opened with — a config that
changed mid-flow would silently split one conversation across two models.

An agent takes an optional `name=`:

```python
actor = ClaudeCodeAgent(config, name="actor")
```

## Turns

Calling the agent runs one turn in a session of its own and keeps nothing:

```python
agent("Read TASK.md and get started.")   # a Ralph turn: nothing carries over
```

Calling a session runs one turn *in* that session:

```python
session = agent.new()
session("Read TASK.md and get started.")   # opens the session
session("continue")                        # resumes it, the task still in context
```

Both return what the agent answered, stripped.

A turn that fails raises `subprocess.CalledProcessError` — whatever it was actually run
through, so a flow catches turns rather than transports — and leaves the session unopened, so
the next call retries the turn rather than resuming something that may not exist.

`suppress=True` turns a failed turn into an empty answer:

```python
agent(task, suppress=True)   # "" if it failed, and the loop goes round again
```

It catches a turn that failed and **nothing else**: not an agent that has been
[stopped](#stopping), and not a backend with no [goal](#goals) feature, which is a flow to
correct rather than a turn to retry.

## Sessions

```python
session = agent.new()        # nothing has been opened with the backend yet
session("first turn")        # now it has
session.id                   # the backend's id for it, e.g. "0a1b2c3d-…"
session.named                # the same id, or None before the backend has said one
session.close()              # ends whatever it was holding
```

`id` raises `RuntimeError` before a turn has landed, because the backend has not named the
session yet. `named` answers `None` instead — which is earlier and therefore more useful while
a first turn is still running, since that is when the backend is already writing the log.

A session runs one turn at a time. Two threads calling one session hold one conversation rather
than interleaving two.

Discarding a session is how a flow forgets. They are held weakly by the agent, so a Ralph loop
running for days does not grow one by a session a turn.

## Watching a turn as it happens

`stream` is the primitive; calling the session is a shell around it.

```python
for event in session.stream("write the tests"):
    print(event.kind, event.text)
```

An `Event` has `kind`, `text`, and — on a `result` from a backend that says — `tokens`, a
mapping of model to tokens spent.

| `kind` | |
| --- | --- |
| `text` | The agent talking. |
| `reasoning` | The agent thinking aloud. |
| `tool` | The agent using one. |
| `result` | The answer the turn ends on. **Exactly one closes a turn**, and it is what calling the session returns. |
| `failed` | The turn closed the other way, carrying what went wrong in place of an answer. |

A watcher sees three more that a stream does not: `begins` and `ends`, which bracket the turn,
and `asks`, which is the agent stopping to ask its user something.

```python
def looking(agent, event):
    if event.kind in ("begins", "ends"):
        print(f"--- {agent.id} {event.kind}")

agent.watch(looking)
```

A watcher that raises is the watcher's own problem: a flow must not fail because something
looking at it did.

This is the only place a run is visible. A flow drives the sessions and answers to nobody, so
the turns going past are all there is — which is what the interface's status column is built
from.

## Talking to a turn already running

```python
session.interject("actually, use pathlib")
```

The agent reads it when it next looks, so the turn already under way takes it into account
rather than being restarted with it.

- On a backend that takes a turn's whole prompt up front, this raises `NotImplementedError`.
- On a backend that can be talked to, it raises `RuntimeError` when nothing is running to hear
  it.

What "into the turn" means per backend is in [What each backend can do](#what-each-backend-can-do).

## Goals

A session can be given a goal instead of a prompt. This is the backend's *own* goal feature —
the one its `/goal` command reaches — not a prompt that asks for one:

```python
agent.pursue("the suite passes and nothing has been stubbed out")
```

The agent decides for itself when the objective has been met, and until it does, a turn that
would have ended starts another. A goal is as many turns of the model as it takes, and the
backend starts them itself; `pursue` follows the goal across all of them and answers with the
last. A session that has gone quiet is a goal that has stopped only once the goal itself says
so.

A flow that loops over `pursue` is running the objective again, rather than nudging an agent
that stopped early.

On a backend with no goal feature it raises `NotImplementedError`, whether or not `suppress` is
set: asking for a feature that is not there is a flow to correct.

## Questions

An agent may stop mid-turn to ask its user something. Set `ask` and it reaches you:

```python
agent.ask = lambda question: input(f"{question.text} {question.options} ")
```

A `Question` has `text` and `options` — the answers the agent offered, if it offered any. An
answer is not held to them; every backend that offers options takes something else too. But
they are what the agent expects, and what an interface has to show for the question to read as
one.

Leave `ask` unset — as a flow run from the command line does — and the backend is told **nobody
answered** rather than being left waiting. A turn waiting on an answer that is not coming is a
flow that has stopped.

Whatever happens, the question also reaches anything [watching](#watching-a-turn-as-it-happens)
the agent as an `asks` event.

Two more hooks, both set by whatever is driving the agent and both left unset on a command
line:

| | |
| --- | --- |
| `agent.waiting` | Asked as each turn starts for anything said to this agent while no turn was open. What it returns goes into that turn. |
| `agent.prompting` | Asked between turns for the next thing to say, so a flow can be a conversation rather than a loop. `None` once there will be nothing more. |

`agent.prompted()` is the call a flow makes; it raises [`Stopped`](#stopping) for an agent
stopped while it waited, so a run ended by hand is written down as ended by hand rather than as
one that finished.

## Stopping

```python
agent.stop()      # take no further turn, and end the one being taken
agent.stopped     # whether that has happened
```

The turn under way is closed out and every later call raises `Stopped`. What the turn was doing
is left where it got to; what ends is the agent's part in it. A stop that waited for a turn
would not read as a stop — a model can think for minutes.

`Stopped` is not a `CalledProcessError`, so the loops that carry on past a turn that failed do
not carry on past this.

## Names, and what a run left behind

Two agents at one model and one effort are still two agents — an actor and the reviewer that
reads its work. `id` is what tells them apart, and what a [trace](tracing.md) groups their
sessions under:

```python
agent.id       # the name you gave it, the name the flow calls it, or one nothing else answers to
agent.backend  # "claude", "codex" or "kimi"
agent.opened   # the backend's id for every session this agent ever opened, oldest first
agent.sessions # the ones somebody still holds
agent.config   # what it runs at
```

`opened` is ids rather than sessions, so a flow running for days remembers them in a list of
strings — including the ones a Ralph loop dropped a turn later. It is what a trace is handed to
say which trajectories were this agent's:

```python
from humanize.tracing import collect

collect(agents={a.id: a.opened for a in (actor, reviewer)})
```

A [flow](flows.md#how-many-agents-and-what-they-are-for) that declares its agents as a
`NamedTuple` names them for you, and a run started through `Runner` writes all of this into its
[cycle](tracing.md#cycles) — so this is only needed for agents built and driven by hand.

## The person as an agent

A flow that is a conversation rather than a loop has two sides, and the second is you.

```python
from humanize.agents import HumanAgent

person = HumanAgent()                      # takes only an optional name=, defaulting to "human"
person("Here is what I did. What next?")   # asks, and answers with what was typed
```

It is not a coding agent: it runs no model, spends nothing, and its turns are not bracketed by
the `begins`/`ends` that say whose turn it is — counting them would put the person in the graph
of who handed to whom and spin a clock at them while they thought.

In a flow, declare one among the agents and it is handed over like the rest — see
[Flows](flows.md#the-person-at-the-prompt). Nobody is asked what it runs, so it is not one of
the agents `-a` names.

## Efforts

`effort` is passed to the backend in the backend's own wording. humanize does not check it
against a list, so a value your account has and this page does not still works.

| Backend | Efforts |
| --- | --- |
| Claude Code | `low`, `medium`, `high`, `xhigh`, `max`, and `ultracode` |
| Codex | `low`, `medium`, `high`, `xhigh`, and `max`/`ultra` on the models that take them |
| Kimi Code | `low`, `medium`, `high`, `max`, each also as `swarm…` |

**`ultracode`** is Claude Code's `xhigh` thinking with the turn opted into orchestrating a fleet
of its own. It is more work than any single-agent effort, which is why it sits above `max`.

**Kimi Code's effort says how wide to run as well as how hard to think.** `max` is one agent;
`swarmmax` is the same thinking at the width of a fleet of subagents. The prefix is exported as
`humanize.agents.SWARM` for anything that has to take it apart.

Codex's models differ from each other — `gpt-5.6-sol` takes `ultra`, `gpt-5.5` does not — so
the interface offers each model only the efforts it takes.

## What each backend can do

| | Claude Code | Codex | Kimi Code |
| --- | --- | --- | --- |
| Driven through | its command line, held open | its app server | its app server |
| [`interject`](#talking-to-a-turn-already-running) | yes — answered within the same turn | yes — a steer on the running turn | yes — queued, then steered in |
| [`pursue`](#goals) | yes | yes | yes |
| Sub-agents in a trace | yes | yes | yes |

A backend is driven through its command line where that can express what an agent is configured
with, and through the app server it serves its own client from where it cannot. A model, an
effort, a mode or a goal that has no flag is a setting of a session there — and asking the model
for it in the prompt is not the same feature.

A turn that must stay open to be talked to is such a case: a command line run per turn has ended
by the time there is anything to say to it.

## Where the turns land

A config's `machine` says where an agent's work goes. `None` — the default — is this machine.

```python
from humanize.machines import AnchoredConfig, DockerConfig

ClaudeCodeAgentConfig(model=…, effort=…, machine=DockerConfig(image="python:3.12"))
```

`agent.anchor` is where its turns land, and brings the machine up the first time it is asked
for — which is the first turn. Constructing an agent pulls no image and starts no container.
See [Machines](machines.md).

## API summary

```python
class AgentBase:
    id: str                 # what this agent is called
    backend: str            # "claude", "codex", "kimi"
    config: AgentConfig     # model, effort, machine
    opened: list[str]       # the backend's id for every session it ever opened
    sessions: list[SessionBase]
    stopped: bool
    anchor: AnchorConfig | None

    def __call__(prompt: str, *, suppress: bool = False) -> str
    def pursue(objective: str, *, suppress: bool = False) -> str
    def new() -> SessionBase
    def rename(name: str) -> None
    def stop() -> None
    def watch(listener: Callable[[AgentBase, Event], None]) -> None
    def asked(question: Question) -> str | None
    def prompted() -> str | None

    ask: Callable[[Question], str | None] | None
    waiting: Callable[[], list[str]] | None
    prompting: Callable[[], str | None] | None


class SessionBase:
    id: str                 # raises until a turn has landed
    named: str | None       # the same, or None

    def __call__(prompt: str, *, suppress: bool = False) -> str
    def stream(prompt: str) -> Iterator[Event]
    def pursue(objective: str, *, suppress: bool = False) -> str
    def interject(text: str) -> None
    def close() -> None


@dataclass(frozen=True)
class Event:
    kind: str               # text | reasoning | tool | result | failed | begins | ends | asks
    text: str
    tokens: Mapping[str, int]


@dataclass(frozen=True)
class Question:
    text: str
    options: tuple[str, ...]


class Stopped(Exception): ...
```

`CommandSessionBase` and `StreamSessionBase` are the two shapes a backend is driven in — one
command per turn, or one long-lived process spoken to a line at a time. Subclass them to add a
backend; `src/humanize/agents/SPEC.md` is the contract they have to keep.

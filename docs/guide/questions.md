# Questions

An agent can stop mid-turn to ask you a question: which approach to take, which file to change,
whether it understood you. A flow can ask you the other way, treating the person at the prompt
as an agent. Use questions whenever a run needs an answer only a person should give.

## Try it

A **`Person`** is the person at the prompt, declared among the agents. See [the person as
an agent](/guide/human-agent).

**Step 1.** Write a flow that pairs an assistant with one. It runs the assistant, then asks you
what to say next, and repeats.

```python
# .humanize/flows/pairing/__init__.py
"""An agent and you, taking turns."""

from typing import NamedTuple

from hmz.flows import Agent, Person, flow


class Agents(NamedTuple):
    """The agent, and whoever is at the prompt."""

    assistant: Agent
    human: Person


@flow
def run(agents: Agents, task: str) -> None:
    conversation = agents.assistant.new()
    said = task
    while said:
        answered = conversation(said, suppress=True)
        said = agents.human(answered)
```

Saying something to a `Person` is asking what to say next; what it answers with is what you
typed. This flow is [`chat`](/flows/chat), the flow the interface
opens on.

**Step 2.** Run it from a command line.

```sh
hmz exec -f pairing -a claude/claude-opus-5:high "Read README.md and tell me what this is."
```

One `-a`, and the flow drives two agents. Nobody is asked what the person runs, so a
`Person` is not one of the agents `-a` names. On a command line nobody is at a prompt, so
`agents.human(...)` answers with nothing. `said` is falsy, so the loop ends and the flow does
the one thing it was given.

**Step 3.** Run it in the interface to see the asking.

```
/flow pairing
```

Now it is a conversation: you and the agent take turns.

## At the prompt

The agent shows the question and whatever it offered. The next line you type is **the answer**,
not a word put into the turn. The status line reads `enter answer` while that is so.

You are not held to the options. Every backend that offers options also takes something else.
The options are what the agent expects, and what an interface shows so the question reads as
one.

If the flow ends or is stopped while a question is still up, the question ends with it.
Stopping a flow is never blocked on a question.

## When nobody is there

`hmz exec` has nobody at a prompt. [`/afk`](/guide/afk) says the same thing on purpose:

```
/afk on
```

In both cases the backend is told **nobody answered**, and the agent carries on.

A turn waiting on an answer that is not coming is a flow that has stopped. So this is the
default everywhere except an interface with `/afk` off.

This is why every questionnaire wants `suppress=True` and a `None` branch. A flow that assumed
somebody was there would hang forever exactly when nobody was. Asking starts **allowed**: an
agent that really needs a person gets one unless it has been said that none is there.

## From Python

From Python, the hook is `agent.ask`:

```python
agent.ask = lambda question: input(f"{question.text} {question.options} ")
```

The question it receives is:

```python
@dataclass(frozen=True)
class Question:
    text: str
    options: tuple[str, ...]
```

Return a string to answer, or `None` for "nobody answered". Leave `ask` unset and it is `None`
every time.

Whatever happens, the question also reaches anything
[watching](/reference/agents#watching-a-turn-as-it-happens) the agent, as an `asks` event. A
flow can record that its agent wanted to ask without answering it:

```python
def looking(agent, session, event):
    if event.kind == "asks":
        Path("questions.log").open("a").write(f"{agent.id}: {event.text}\n")

agent.watch(looking)
```

An unattended run can collect everything its agents wanted to ask, and you can read it in the
morning.

The session on an `asks` event is `None`, whichever backend asked. A question belongs to the
agent, not to one conversation. `ask` is set on the agent, and the agent is what a stopped turn
reaches. So a watcher can say which agent wanted to ask, as the one above does, but not which
of its conversations did.

## The other direction: a flow asking you

The *flow* asking you is [the person as an agent](/guide/human-agent):

```python
said = agents.human("Here is what I did. What next?")
```

With a [schema](/guide/shapes), the same call is a questionnaire. The person is not shown a
JSON Schema. They are asked **a question per field**, and the model is built out of what they
typed:

```python
from typing import Literal

from pydantic import BaseModel, Field


class Settled(BaseModel):
    """What has to be agreed before anything is built."""

    approach: Literal["fast", "careful"] = Field(description="Which way should this be built?")
    tests: bool = Field(description="Write tests for it?")
    rounds: int = Field(default=3, description="How many rounds may it take?")


@flow
def run(agents: Agents, task: str) -> None:
    settled = agents.human("How should I do this?", schema=Settled, suppress=True)
    if settled is None:
        return                                    # nobody was there
    working = agents.assistant.new()
    for _ in range(settled.rounds):
        working(f"{task}\n\nBuild this the {settled.approach} way."
                f"{' Write tests.' if settled.tests else ''}", suppress=True)
```

Each field becomes a question, and what the person types is built into the model:

| In the model | What they are asked |
| --- | --- |
| `description=` | the question itself, or the field's name where it has none |
| `Literal[…]` | those words, as the answers it offers |
| `bool` | `yes` and `no` |
| a default | "or `-` for 3" — and a dash takes it |
| `list[str]` | one line, separated by commas |

So a flow settles what only a person can settle in the model it is going to run on, once,
rather than by parsing a sentence. What the model refuses is put back on the field it was
refused for, in the model's own words, a bounded number of times.

Each of those goes the same road a coding agent's own question takes, so `/afk` answers it the
same way: nobody is there.

The person is not:

- a coding agent — it runs no model and spends nothing;
- in [`/status`](/guide/status)'s handover graph or the cost readout — its turns are not
  bracketed by the events that say whose turn it is;
- one of the conversations **tab** steps between;
- able to run [moments](/guide/hooks) — a moment is a point in a turn of a model.

## The moment, for a hook

`NOTIFICATION` is the [moment](/guide/hooks) that fires when the agent stops to ask you
something. A hook on it cannot answer, because a verdict does nothing there. It can log, notify
or wake something up instead:

```python
agent.hooks.on(Moment.NOTIFICATION, lambda occasion: ring_a_bell(occasion.said))
```

## See also

- [Side questions](/guide/btw)
- [Being away](/guide/afk)
- [Answers in a shape](/guide/shapes)
- [The person as an agent](/guide/human-agent)
- [Hooks](/guide/hooks)

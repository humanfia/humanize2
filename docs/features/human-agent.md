# The person as an agent

A flow that is a conversation rather than a loop has two sides, and the second is you.

```python
from hmz.agents import HumanAgent

person = HumanAgent()                      # takes only an optional name=, defaulting to "human"
person("Here is what I did. What next?")   # asks, and answers with what was typed
```

Saying something to a `HumanAgent` is **asking what to say next**; what it answers with is what
was typed.

## In a flow

Declare one among the agents and it is handed over like the rest:

```python
from typing import NamedTuple

from hmz.agents import AgentBase, HumanAgent
from hmz.flows import flow

class Chat(NamedTuple):
    assistant: AgentBase
    human: HumanAgent

@flow
def run(agents: Chat, task: str) -> None:
    conversation = agents.assistant.new()
    said = task
    while said:
        answered = conversation(said, suppress=True)
        said = agents.human(answered)
```

That is [`chat`](/reference/flows#the-flows-humanize-ships) — what the interface opens on.

**Nobody is asked what the person runs**, so a `HumanAgent` is not one of the agents `-a` names.
The flow above drives two agents and is started with one `-a`:

```sh
hmz exec -f chat -a claude/claude-opus-5:high "Read README.md and tell me what this is."
```

Run from a command line, where nobody is at a prompt, it answers with nothing — so the loop ends
and the flow does the one thing it was given. Which is exactly what you want from `chat` in a
script.

## What it is not

It is not a coding agent. It runs no model and spends nothing.

Its turns are **not bracketed** by the `begins`/`ends` events that say whose turn it is. Counting
them would put the person in the graph of who handed to whom, and spin a clock at them while they
thought. So the person appears in neither [`/status`](/features/status)'s handover graph nor the
[cost readout](/features/tally), and the conversation with them is not one of the ones
[tab steps between](/features/conversations).

It runs no [moments](/features/hooks) either: a moment is a point in a turn of a model, and the
person takes no such turn.

## Asking them for a shape — a questionnaire

Given a [`schema`](/features/shapes), the person is asked **a question per field**, and the model
is built out of what they typed:

```python
class Settled(BaseModel):
    approach: Literal["fast", "careful"] = Field(description="Which way should this be built?")
    tests: bool = Field(description="Write tests for it?")
    rounds: int = Field(default=3, description="How many rounds may it take?")

settled = agents.human("How should I do this?", schema=Settled, suppress=True)
if settled is not None and settled.tests:
    ...
```

So a flow settles what only a person can settle **in the model it is going to run on**, once,
rather than by parsing a sentence. This is the same thing a coding agent's `AskUserQuestion` is,
reachable from a flow — and more, since the shape of the whole answer is stated once.

Each question goes the road [a coding agent's own question](/features/questions) takes, so
[`/afk`](/features/afk) answers it the way it answers any other: nobody is there, and the
questionnaire comes back as `None` under `suppress`.

## When another flow calls yours

A flow that [calls another](/reference/flows#a-flow-that-calls-another-flow) may hand it one
fewer agent, since nobody chooses the person. Hand over your own if you have one, so that what it
asks reaches whoever is at the prompt:

```python
calls("chat")((assistant, agents.human), task)
```

## See also

- [Questions](/features/questions)
- [Answers in a shape](/features/shapes)
- [Flows › The person at the prompt](/reference/flows#the-person-at-the-prompt)

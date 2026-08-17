# The person as an agent

**Person** is the person's side of a conversation inside a flow. Add one to a flow when it
needs a human to answer, and it asks for input and returns what you type. `Person` is what a
flow declares the place as; `HumanAgent` is what fills it.

## Try it

Create one and say something to it:

```python
from hmz.flows import HumanAgent

person = HumanAgent()                      # takes only an optional name=, defaulting to "human"
person("Here is what I did. What next?")   # asks, and answers with what was typed
```

Saying something to it asks **what to say next**. It answers with whatever you type.

## In a flow

Declare a `Person` among the agents, and it is handed over like the rest:

```python
from typing import NamedTuple

from hmz.flows import Agent, Person, flow

class Chat(NamedTuple):
    assistant: Agent
    human: Person

@flow
def run(agents: Chat, task: str) -> None:
    conversation = agents.assistant.new()
    said = task
    while said:
        answered = conversation(said, suppress=True)
        said = agents.human(answered)
```

That is [`chat`](/flows/chat), the flow the interface opens on.

A `Person` is not one of the agents you name with `-a`, because **nobody is asked what the
person runs**. The flow above drives two agents, so you start it with one `-a`:

```sh
hmz exec -f chat -a claude/claude-opus-5:high "Read README.md and tell me what this is."
```

When you run it from a command line, nobody is at a prompt, so it answers with nothing. The
loop ends and the flow does the one thing it was given. That is what you want from `chat` in a
script.

## What it is not

A `Person` is not a coding agent. It runs no model and spends nothing.

Its turns are **not bracketed** by the `begins`/`ends` events that say whose turn it is. If you
counted them, you would put the person in the graph of who handed to whom. You would also spin
a clock at them while they thought. So the person appears in neither the handover graph of
[`/status`](/guide/status) nor the [cost readout](/guide/tally). The conversation with them is
not one of the ones [tab steps between](/guide/conversations).

It runs no [moments](/guide/hooks) either. A **moment** is a point in a turn of a model, and
the person takes no such turn.

## Asking them for a shape — a questionnaire

Give the person a [`schema`](/guide/shapes), and they are asked **a question per field**. The
model is built out of what they typed:

```python
class Settled(BaseModel):
    approach: Literal["fast", "careful"] = Field(description="Which way should this be built?")
    tests: bool = Field(description="Write tests for it?")
    rounds: int = Field(default=3, description="How many rounds may it take?")

settled = agents.human("How should I do this?", schema=Settled, suppress=True)
if settled is not None and settled.tests:
    ...
```

A flow settles what only a person can settle **in the model it is going to run on**, once
rather than by parsing a sentence. This is the same thing as a coding agent's
`AskUserQuestion`, reachable from a flow. It does more, because the shape of the whole answer
is stated once.

Each question takes the road [a coding agent's own question](/guide/questions) takes. So
[`/afk`](/guide/afk) answers it the way it answers any other: nobody is there, and the
questionnaire comes back as `None` under `suppress`.

## The board: the half that does not wait

Saying something to the person **stops the turn** until they answer. That is right for a
question and wrong for everything else a run wants from them, so they carry a board as well:
named lines the flow and the person both write on, drawn on [`/status`](/guide/status), where
neither waits on the other.

```python
board = agents.human.board
board.put("todo", task)                          # either of you writes this one
board.put("doing", "nothing yet", whose="flow")  # the flow's; they read it

while waiting := [one for one in board.get("todo").splitlines() if one.strip()]:
    board.put("doing", waiting[0])
    agents.builder(waiting[0], suppress=True)
    board.put("todo", "\n".join(waiting[1:]))
```

A line whose `whose` is one side's is refused to the other where it writes rather than quietly
ignored. Run where nobody is at a prompt, the board is still a board — the flow writes it and
reads it, and nothing changes it from outside. See [The mission board](/guide/board).

## When another flow calls yours

When a flow [calls another](/reference/flows#a-flow-that-calls-another-flow), it may hand it
one fewer agent, because nobody chooses the person. If you have your own, hand it over, so what
it asks reaches whoever is at the prompt:

```python
load("chat")((assistant, agents.human), task)
```

## See also

- [Questions](/guide/questions)
- [Answers in a shape](/guide/shapes)
- [The mission board](/guide/board)
- [Flows › The person at the prompt](/reference/flows#the-person-at-the-prompt)

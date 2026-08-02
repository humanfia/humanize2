# 12 · Asking a person

**Ten minutes.** A flow with two sides, where the second is you.

::: tip Before you start
[Hooks](/guide/tutorial-hooks).
:::

## Step 1 — declare a person among the agents

```python
# .humanize/flows/pairing.py
"""An agent and you, taking turns."""

from typing import NamedTuple

from hmz.agents import AgentBase, HumanAgent
from hmz.flows import flow


class Agents(NamedTuple):
    """The agent, and whoever is at the prompt."""

    assistant: AgentBase
    human: HumanAgent


@flow
def run(agents: Agents, task: str) -> None:
    conversation = agents.assistant.new()
    said = task
    while said:
        answered = conversation(said, suppress=True)
        said = agents.human(answered)
```

Saying something to a `HumanAgent` is **asking what to say next**; what it answers with is what
was typed.

That flow is [`chat`](/reference/flows#the-flows-humanize-ships) — what the interface opens on.

## Step 2 — run it

```sh
hmz exec -f pairing -a claude/claude-opus-5:high "Read README.md and tell me what this is."
```

**One `-a`, and the flow drives two agents.** Nobody is asked what the person runs, so a
`HumanAgent` is not one of the agents `-a` names.

On a command line, where nobody is at a prompt, `agents.human(...)` answers with **nothing** — so
`said` is falsy, the loop ends, and the flow does the one thing it was given. Which is exactly
what you want from a conversation flow in a script.

Now run the same thing in the interface:

```
/flow pairing
```

and it is a conversation.

## Step 3 — ask for a whole answer at once

The interesting call. Given a [schema](/features/shapes), the person is not shown a JSON Schema —
they are asked **a question per field**, and the model is built out of what they typed:

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

What the person sees:

| In the model | What they are asked |
| --- | --- |
| `description=` | the question itself, or the field's name where it has none |
| `Literal[…]` | those words, as the answers it offers |
| `bool` | `yes` and `no` |
| a default | "or `-` for 3" — and a dash takes it |
| `list[str]` | one line, separated by commas |

So a flow settles what only a person can settle **in the model it is going to run on**, once,
rather than by parsing a sentence.

What the model refuses is put back on the field it was refused for, in the model's own words, a
bounded number of times.

## Step 4 — the other direction: the agent asking you

An agent may stop mid-turn to ask its user something. In the interface, the question and whatever
it offered are shown, and the next line you type is **the answer** rather than a word put into the
turn — the status line says `enter answer` while that is so.

An answer is not held to the options. Every backend that offers them takes something else too.

From Python, the hook is `agent.ask`:

```python
agent.ask = lambda question: input(f"{question.text} {question.options} ")
```

Leave it unset — as a flow run from a command line does — and the backend is told **nobody
answered** rather than being left waiting. A turn waiting on an answer that is not coming is a
flow that has stopped.

## Step 5 — say you are not there

```
/afk on
```

Now an agent that wants to ask is told nobody answered and carries on. Note what this does to the
flow you wrote in step 3: `agents.human(...)` answers nothing, so `settled` is `None` and the flow
returns.

That is correct, and it is why every questionnaire wants `suppress=True` and a `None` branch. A
flow that assumed somebody was there would hang forever exactly when nobody was.

Asking starts **allowed**: an agent that really needs a person gets one unless it has been said
that none is there. See [Being away](/features/afk).

## Step 6 — record a question without answering it

Whatever happens, a question also reaches anything
[watching](/reference/agents#watching-a-turn-as-it-happens) the agent, as an `asks` event:

```python
from pathlib import Path


def looking(agent, session, event):
    if event.kind == "asks":
        with Path("questions.log").open("a") as log:
            log.write(f"{agent.id}: {event.text}\n")


agent.watch(looking)
```

So an unattended run can collect everything its agents wanted to ask, and you can read it in the
morning. The `NOTIFICATION` [moment](/features/hooks) is the same signal as a hook.

## What the person is not

- Not a coding agent: it runs no model and spends nothing.
- Not in [`/status`](/features/status)'s handover graph, and not in the cost readout — its turns
  are not bracketed by the events that say whose turn it is.
- Not one of the conversations **tab** steps between.
- Not able to run [moments](/features/hooks): a moment is a point in a turn of a model.

## What you now know

- `HumanAgent` is declared among the agents and is not one `-a` names.
- `person(prompt)` asks what to say next; `person(prompt, schema=…)` is a questionnaire.
- Always `suppress=True` and a `None` branch — nobody may be there.
- `agent.ask` is the other direction, and `/afk` is the switch for both.

## Next

[Answers in a shape](/guide/tutorial-shapes), for the agent side of the same idea.

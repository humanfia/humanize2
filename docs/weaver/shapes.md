# Answers in a shape

A turn given a `schema` answers with that pydantic model instead of with text. Reach for it
whenever a flow has to decide something before it acts.

## Try it

Declare the answer as a pydantic model:

```python
from pydantic import BaseModel, Field


class Review(BaseModel):
    """What one round's review comes to."""

    model_config = {"extra": "forbid"}

    done: bool = Field(description="True only if there is nothing left to do or to fix.")
    notes: str = Field(description="What to say to the agent, passed on word for word.")
```

**The model *is* the question.** Its fields, their types, which are required, and the line each
was declared with are what the backend is given, so nothing has to be repeated in the prompt.

Ask for it:

```python
review = agents.reviewer(REVIEW, schema=Review)   # a Review, not a str
if review.done:
    return
working(review.notes, suppress=True)
```

You read `review.done` as a bool instead of searching the agent's prose for a word.

## Why a loop wants this

Is this finished? Does this plan belong to this repository? A loop asks that of a field rather
than of the end of a paragraph:

```python
review = agents.reviewer(REVIEW_PROMPT + task, suppress=True, schema=Review)
if review is not None and review.done:
    return
```

That is what [`official/rlar`](/flows/rlar) ends on, and what `humanize1` asks its analyst and
its reviewer before it starts anything. Here is a whole flow built on it:

```python
# .humanize/flows/reviewed/__init__.py
"""Build under review, and stop when the reviewer says there is nothing left."""

from typing import NamedTuple

from pydantic import BaseModel, Field

from hmz.flows import Agent, flow

REVIEW = """Read the repository and the current diff.
Decide whether there is anything left to do or to fix."""


class Review(BaseModel):
    """What one round's review comes to."""

    model_config = {"extra": "forbid"}

    done: bool = Field(description="True only if there is nothing left to do or to fix.")
    notes: str = Field(description="What to say to the agent, passed on word for word.")


class Agents(NamedTuple):
    actor: Agent
    reviewer: Agent


@flow
def run(agents: Agents, task: str) -> None:
    working = agents.actor.new()
    working(task, suppress=True)
    for _ in range(12):
        review = agents.reviewer(REVIEW, suppress=True, schema=Review)
        if review is None:
            continue
        if review.done:
            print("the reviewer says it is finished")
            return
        working(review.notes, suppress=True)
    print("twelve rounds and it is still not done")
```

It asks the reviewer for a `Review` up to twelve times and stops as soon as `review.done` is
true:

```sh
hmz exec -f reviewed -a claude/claude-opus-5:max -a codex/gpt-5.6-sol:high "$(cat TASK.md)"
```

## How each backend is held to it

| | |
| --- | --- |
| **Claude Code** | `--json-schema`; it validates the answer itself |
| **Antigravity**, **Grok Build**, **Qwen Code** | `--json-schema` on the run |
| **Codex** | the turn's `outputSchema` |
| anything else — `dsh`, `kimi`, `pi`, `opencode`, `mimo`, `zcode` | asked in the prompt, and what it says is read back |

`Session.shapes` records which of the two a backend is. Either way the answer arrives as the
model, or not at all.

Claude's schema is an argument of the process rather than of the turn. Asking one session for a
shape it was not started with ends that process and starts one that **resumes** the
conversation — the conversation is not restarted, only the process is. It is the same thing
[moving the effort](/user/efforts) does.

## Failing

```python
review = agent(asked, schema=Review, suppress=True)   # a Review, or None
```

`suppress=True` answers `None` rather than `""`, and covers **both**:

- a turn that failed, and
- a turn whose answer is not the shape it was asked for.

An answer that is not what was asked for is a turn that did not do what it was told. Without
`suppress`, the second raises `ValueError`. Write the `None` branch as "take this round again".
That is almost always right.

## Asking a person: a questionnaire

Given a schema, [the person](/weaver/human-agent) is not shown a JSON Schema. They are asked a
question per field, and the model is built out of what they typed:

```python
class Settled(BaseModel):
    approach: Literal["fast", "careful"] = Field(description="Which way should this be built?")
    tests: bool = Field(description="Write tests for it?")
    rounds: int = Field(default=3, description="How many rounds may it take?")

settled = person("How should I do this?", schema=Settled, suppress=True)
```

| In the model | What they are asked |
| --- | --- |
| `description=` | the question itself, or the field's name where it has none |
| `Literal[…]` | those words, as the answers it offers |
| `bool` | `yes` and `no` |
| a default | "or `-` for 3" — and a dash takes it |
| `list[str]` | one line, separated by commas |

Each question goes the road [a coding agent's own question](/user/questions) takes, so it is a
real question in the interface, options and all. [`/afk`](/user/afk) or a command line answers
it the way it answers any other: nobody is there. What the model refuses is put back on the
field it was refused for, in the model's own words, a bounded number of times. A questionnaire
nobody filled in answers with `None` under `suppress`.

This is a coding agent's `AskUserQuestion`, reachable from a flow — and more, because the flow
states the shape of the whole answer once, in the model it is going to use. The same decision
goes to a model or to a person in the same shape, with the same `None` branch.

## Where it works

Everywhere a turn is run:

```python
agent(prompt, schema=Review)
session(prompt, schema=Review)
await agent.aturn(prompt, schema=Review)
agent.batch(prompts, schema=Review, suppress=True)      # a list of Review | None
```

## Writing the model

- `model_config = {"extra": "forbid"}`. An answer with a field nobody asked for is an answer to
  a different question.
- A `description` on every field. It is the only wording the model sees for that field, and it
  does the work the prompt would otherwise do.
- Keep it small. A model with thirty fields is a form, and a turn that fills in a form is a
  turn that did not do the work. Two or three fields is usually the whole of a decision.
- Booleans for decisions, strings for what to pass on. `done` steers the loop; `notes` becomes
  the next prompt word for word.

## See also

- [Questions](/user/questions)
- [The person as an agent](/weaver/human-agent)
- [Agents › Answering in a shape](/reference/agents#answering-in-a-shape)
- [Testing a flow](/weaver/testing-flows)

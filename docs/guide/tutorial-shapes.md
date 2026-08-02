# 13 · Answers in a shape

**Ten minutes.** Stop grepping the agent's prose for the word "done".

::: tip Before you start
[Asking a person](/guide/tutorial-questions).
:::

## The problem

```python
said = agents.reviewer(REVIEW, suppress=True)
if "looks good" in said.lower():          # [!code error]
    return                                # [!code error]
```

That is a coin flip. The reviewer will one day write "this does not look good", and the loop will
stop on the round it should have carried on.

## Step 1 — declare the answer

```python
from pydantic import BaseModel, Field


class Review(BaseModel):
    """What one round's review comes to."""

    model_config = {"extra": "forbid"}

    done: bool = Field(description="True only if there is nothing left to do or to fix.")
    notes: str = Field(description="What to say to the agent, passed on word for word.")
```

**The model *is* the question.** Its fields, their types, which are required, and the line each was
declared with are what the backend is given — so nothing has to be repeated in the prompt.

## Step 2 — ask for it

```python
review = agents.reviewer(REVIEW, schema=Review)   # a Review, not a str
if review.done:
    return
working(review.notes, suppress=True)
```

Any call that runs a turn takes `schema`:

```python
agent(prompt, schema=Review)
session(prompt, schema=Review)
await agent.aturn(prompt, schema=Review)
agent.batch(prompts, schema=Review, suppress=True)      # list[Review | None]
```

## Step 3 — handle it not arriving

```python
review = agents.reviewer(REVIEW, suppress=True, schema=Review)
if review is None:
    continue                     # the turn failed, or answered something that was not a Review
```

`suppress=True` answers `None` rather than `""`, and covers **both**:

- a turn that failed, and
- a turn whose answer is not the shape it was asked for.

An answer that is not what was asked for is a turn that did not do what it was told. Without
`suppress`, the second raises `ValueError`.

Write the `None` branch as "take this round again". That is almost always right.

## Step 4 — see how each backend is held to it

| | |
| --- | --- |
| **Claude Code** | `--json-schema`; it validates the answer itself |
| **Codex** | the turn's `outputSchema` |
| anything else | asked in the prompt, and what it says is read back |

`SessionBase.shapes` is which of the two a backend is. Either way the answer arrives as the model
or not at all — so a flow does not have to care, but it explains why the same prompt is more
reliable on some backends than others.

::: warning Claude restarts its process for a shape
Claude's schema is an argument of the process rather than of the turn, so asking one session for a
shape it was not started with ends that process and starts one that **resumes** the conversation.
The conversation is not restarted; only the process is. It is the same thing
[moving the effort](/features/efforts) does.
:::

## Step 5 — a whole flow built on it

```python
# .humanize/flows/reviewed.py
"""Build under review, and stop when the reviewer says there is nothing left."""

from typing import NamedTuple

from pydantic import BaseModel, Field

from hmz.agents import AgentBase
from hmz.flows import flow

REVIEW = """Read the repository and the current diff.
Decide whether there is anything left to do or to fix."""


class Review(BaseModel):
    """What one round's review comes to."""

    model_config = {"extra": "forbid"}

    done: bool = Field(description="True only if there is nothing left to do or to fix.")
    notes: str = Field(description="What to say to the agent, passed on word for word.")


class Agents(NamedTuple):
    actor: AgentBase
    reviewer: AgentBase


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

```sh
hmz exec -f reviewed -a claude/claude-opus-5:max -a codex/gpt-5.6-sol:high "$(cat TASK.md)"
```

## Step 6 — the same call to a person

The identical call to a [`HumanAgent`](/features/human-agent) is a **questionnaire**: a question
per field, and the model built out of what they typed.

```python
settled = agents.human("How should I do this?", schema=Settled, suppress=True)
```

Which means a flow can put the same decision either to a model or to a person, in the same shape,
with the same `None` branch. See [tutorial 12](/guide/tutorial-questions).

## Writing a model that works

- **`model_config = {"extra": "forbid"}`.** An answer with a field nobody asked for is an answer
  to a different question.
- **A `description` on every field.** It is the only wording the model sees for that field, and
  it is doing the work the prompt would otherwise do.
- **Keep it small.** A model with thirty fields is a form, and a turn that fills in a form is a
  turn that did not do the work. Two or three fields is usually the whole of a decision.
- **Booleans for decisions, strings for what to pass on.** `done` steers the loop; `notes` becomes
  the next prompt word for word.

## What you now know

- `schema=` on any turn; the model is the question.
- `suppress=True` gives `None` for both failure modes, and `None` means "go again".
- The backend is held to it where it can be, and asked in the prompt where it cannot.
- The same call to a person is a questionnaire.

## Next

[Testing a flow](/guide/tutorial-testing-flows) — without spending a token.

# Answers in a shape

A turn given a `schema` answers with that pydantic model instead of with text.

```python
from pydantic import BaseModel, Field

class Review(BaseModel):
    """What a review comes to."""

    model_config = {"extra": "forbid"}

    done: bool = Field(description="True only if there is nothing left to do or to fix.")
    notes: str = Field(description="What to say to the agent, word for word.")

review = agent(asked, schema=Review)   # a Review, not a str
if review.done:
    ...
```

**The model *is* the question.** Its fields, their types, which are required, and the line each
was declared with are what the backend is given — so nothing has to be repeated in the prompt.

## Why a loop wants this

A flow that has to decide something — is this finished, does this plan belong to this repository
— reads a field rather than looking for a word at the end of a paragraph.

```python
review = agents.reviewer(REVIEW_PROMPT + task, suppress=True, schema=Review)
if review is not None and review.done:
    return
```

That is what [`official/rlar`](/reference/flows#the-official-flowverse) ends on, and what
`humanize1` asks its analyst and its reviewer before it starts anything.

## How each backend is held to it

| | |
| --- | --- |
| **Claude Code** | `--json-schema`; it validates the answer itself |
| **Codex** | the turn's `outputSchema` |
| anything else | asked in the prompt, and what it says is read back |

`SessionBase.shapes` is which of the two a backend is. Either way the answer arrives as the model
or not at all.

Claude's is an argument of the process rather than of the turn, so asking one session for a shape
it was not started with ends that process and starts one that **resumes** the conversation. The
conversation is not restarted with it.

## Failing

```python
review = agent(asked, schema=Review, suppress=True)   # a Review, or None
```

`suppress=True` answers `None` rather than `""`, and covers **both**:

- a turn that failed, and
- a turn whose answer is not the shape it was asked for.

An answer that is not what was asked for is a turn that did not do what it was told. Without
`suppress`, the second raises `ValueError`.

## Asking a person: a questionnaire

Given a schema, [the person](/features/human-agent) is not shown a JSON Schema. They are asked
**a question per field**, and the model is built out of what they typed:

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

Each question goes the road [a coding agent's own question](/features/questions) takes, so it is a
real question in the interface, options and all — and [`/afk`](/features/afk) or a command line
answers it the way it answers any other: nobody is there. What the model refuses is put back on
the field it was refused for, in the model's own words, a bounded number of times. A questionnaire
nobody filled in answers with `None` under `suppress`.

This is the same thing a coding agent's `AskUserQuestion` is, reachable from a flow — and more,
since the flow states the shape of the whole answer once, in the model it is going to use.

## Where it works

Everywhere a turn is run:

```python
agent(prompt, schema=Review)
session(prompt, schema=Review)
await agent.aturn(prompt, schema=Review)
agent.batch(prompts, schema=Review, suppress=True)      # a list of Review | None
```

## Writing the model

- `model_config = {"extra": "forbid"}` — an answer with a field nobody asked for is an answer to
  a different question.
- A `description` on every field. It is the only wording the model sees for that field.
- Keep it small. A model with thirty fields is a form, and a turn that fills in a form is a turn
  that did not do the work.

## See also

- [Questions](/features/questions)
- [The person as an agent](/features/human-agent)
- [Agents › Answering in a shape](/reference/agents#answering-in-a-shape)

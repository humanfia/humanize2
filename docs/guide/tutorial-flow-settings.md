# 8 · Settings of its own

**Ten minutes.** Declare a pydantic model and your flow grows a settings sheet, a YAML file and a
set of refusals — with no interface code.

::: tip Before you start
[Actor and reviewer](/guide/tutorial-actor-reviewer).
:::

## Step 1 — take a third argument

```python
# .humanize/flows/pair/__init__.py
from typing import Literal

from pydantic import BaseModel, Field

from hmz.agents import AgentBase
from hmz.flows import flow


class Config(BaseModel):
    """What this flow takes."""

    rounds: int = Field(default=3, ge=1, le=9, description="how many times round")
    mode: Literal["fast", "slow"] = Field(default="fast", description="which way")


@flow
def run(agents: tuple[AgentBase], task: str, config: Config | None = None) -> None:
    setting = config or Config()
    for _ in range(setting.rounds):
        ...
```

That is the whole of it.

**The model is what asks**: the fields are the questions, their types say how each one is
answered, `description` is the line shown beside it, and whatever the model refuses is what the
flow will not run.

## Step 2 — set it at the prompt

```
/flow
```

Choose the flow, and the sheet comes up: it is that model with a cursor on it — one row per
setting, its name, what it is set to, and the line the flow declared it with.

```
   ❯ 1. rounds                       3            how many times round
     2. mode                         fast         which way
```

| Key | |
| --- | --- |
| **↑ ↓** | move between settings |
| **← →** | move the one under the cursor along: a switch flips, a choice steps, a number goes up or down by one |
| letters | write the one under the cursor, for the ones that are written rather than stepped |
| **enter** | take the lot, and go on to the agents |
| **esc** | back, changing nothing |

A setting that is **written** carries a caret under the cursor, where the next letter would land;
one that is **stepped** does not — otherwise a blank setting would read as one nothing can be
typed into.

`/flow` walks through this between choosing the flow and choosing its agents, which is the only
place it can: only the flow just chosen says what there is to set. `/agents` never does — the two
are halves of one question, and each asks only its own.

## Step 3 — set it from a file

```yaml
# setup.yaml
rounds: 9
mode: slow
```

```sh
hmz exec -f pair -c setup.yaml -a claude/claude-opus-5:max "$(cat TASK.md)"
```

Or open the interface already set up, without starting anything:

```sh
hmz -f pair -c setup.yaml
```

## Step 4 — `None` is not a bug

`None` means **nobody set it up**, and is what the flow gets from `hmz exec` with no `-c`. Fall
back to the model's own defaults and the flow runs the same either way:

```python
setting = config or Config()
```

Do that in one line at the top and never think about it again.

## Step 5 — refuse the combinations you cannot run

Put them in the **model**, not in `run`:

```python
from pydantic import model_validator


class Config(BaseModel):
    fast: bool = Field(default=False, description="skip the review round")
    careful: bool = Field(default=False, description="review twice")

    @model_validator(mode="after")
    def _settles(self) -> "Config":
        if self.fast and self.careful:
            raise ValueError("fast and careful do not go together")
        return self
```

Now it is refused **where it was typed** — in the sheet, in the YAML file — rather than an hour
into the run. Nothing in the interface knows what any of your settings mean: the types say how a
value moves, and your model says which combinations it will not take.

## Step 6 — group them, once there are many

A flow with twenty settings is a wall. Each field says which part of the sheet it belongs under,
and the sheet draws a heading above each group:

```python
    gen_idea: bool = Field(
        default=True,
        description="open the idea into a repo-grounded draft",
        json_schema_extra={"section": "gen-idea  ·  open the idea into a draft"},
    )
```

```
   gen-idea  ·  open the idea into a draft
     1. gen_idea                     on           open the idea into a repo-grounded draft
     2. n                            6            --n: how many directions explore the idea
   ❯ 3. idea_output                  docs/d.md▏   --output: where the draft goes

   gen-plan  ·  turn the draft into a plan
     4. gen_plan                     on           turn the draft into a plan, against review
```

The arrows walk the settings and step over the headings.

## Two rules

**The model has to be readable at runtime.** Import `pydantic` normally, not under
`if TYPE_CHECKING` — same rule as the `agents` annotation.

**It is read by running the file**, so the class the interface asked with is not the same object
as the class the run is handed. What is carried across is the *fields*, which `Runner` reads back
into the model the flow has just declared. A flow handed a config of another model is refused
before its first turn, as one handed the wrong number of agents is.

## What you get for free

- A sheet, with the right widget per type.
- `-c setup.yaml` on both `hmz exec` and `hmz`.
- Validation, in your own words, at the moment somebody types it.
- [Remembered per flow](/features/settings), so twenty settings are not twenty questions every
  morning.
- A third argument when another flow [calls yours](/guide/tutorial-calling-flows):
  `calls("pair")(agents, task, {"rounds": 9})`.

## Try this

`official/humanize1` takes twenty-three settings, grouped into three phases. Fetch the official
flowverse, `/flow` it, choose it, and look at what a large one of these is:

```
/flow official/humanize1:gen-idea
```

## What you now know

- A pydantic model on the third argument *is* the settings UI.
- Refusals belong in the model, where they are enforced everywhere at once.
- `None` means nobody asked; fall back to defaults.

## Next

[Many turns at once](/guide/tutorial-async-flow).

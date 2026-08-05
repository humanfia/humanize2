# 7 · Actor and reviewer

**Fifteen minutes.** The two-agent shape, written from scratch: one that remembers and one that
must not.

::: tip Before you start
[Write your first flow](/guide/tutorial-first-flow).
:::

## Step 1 — name the agents

A fixed-length tuple says *how many*. A `NamedTuple` says what each one is **for**:

```python
# .humanize/flows/pair/__init__.py
"""One agent builds; a fresh one reads its work and says what is wrong."""

from typing import NamedTuple

from hmz.agents import AgentBase
from hmz.flows import flow


class Agents(NamedTuple):
    """The two this drives: one that works in a session, and one that arrives fresh."""

    actor: AgentBase
    reviewer: AgentBase


@flow
def run(agents: Agents, task: str) -> None:
    ...
```

The names are not decoration. Everything that has to talk about an agent uses them:

- The agents page of `/flow` asks what **the reviewer** runs, rather than what agent 2 of 2 runs.
- The line above the prompt says `reviewer · claude/claude-opus-4-8:high`.
- A [trace](/features/tracing) groups that agent's sessions under `reviewer`.
- What each was set to run is [remembered per role](/features/settings), so a flow that grows an
  agent in the middle does not hand the reviewer's model to the builder.

## Step 2 — the loop

The reviewer must arrive **fresh**, so it gets a new session each round while the actor keeps one:

```python
REVIEW = """Read the repository and the current diff. Say what is still wrong with it.
Be specific and concrete. Do not change anything."""


@flow
def run(agents: Agents, task: str) -> None:
    working = agents.actor.new()            # one session, held
    working(task, suppress=True)
    for _ in range(10):
        review = agents.reviewer(REVIEW, suppress=True)     # a session of its own, dropped
        working(review, suppress=True)                      # the review IS the next prompt
```

`agents.reviewer(...)` opens a session of its own and drops it. `agents.actor.new()` is held for
the whole run. Same call shapes, opposite memory — and the flow decides, not the agent.

## Step 3 — run it

```sh
hmz exec -f pair -a claude/claude-opus-5:max -a codex/gpt-5.6-sol:high "$(cat TASK.md)"
```

Two `-a`, in the order the `NamedTuple` declares them: `actor` first, `reviewer` second.

Give them **the same** CLI, model and effort and they are still two agents — which is the point.
A trace reads the actor's session and the reviewer's rounds as two.

## Step 4 — end on a decision, not a paragraph

The loop above runs ten rounds whatever happens. A loop that has to decide something should ask
for [the shape of the answer](/features/shapes) and read a field, rather than looking for a word
at the end of a paragraph:

```python
from pydantic import BaseModel, Field


class Review(BaseModel):
    """What one round's review comes to."""

    model_config = {"extra": "forbid"}

    done: bool = Field(description="True only if there is nothing left to do or to fix.")
    notes: str = Field(description="What to say to the agent, passed on word for word.")


@flow
def run(agents: Agents, task: str) -> None:
    working = agents.actor.new()
    working(task, suppress=True)
    for _ in range(10):
        review = agents.reviewer(REVIEW, suppress=True, schema=Review)
        if review is None:
            continue                 # the turn failed, or answered the wrong shape: go again
        if review.done:
            return
        working(review.notes, suppress=True)
```

`suppress=True` with a schema answers `None` for **both** a turn that failed and a turn whose
answer was not a `Review`. Both are a round to take again.

This is what [`official/rlar`](/reference/flows#the-official-flowverse) ends on.

## Step 5 — make the reviewer unable to touch anything

Two ways, and they are different in kind:

**On the command line**, per run:

```sh
hmz exec -f pair \
    -a claude/claude-opus-5:max \
    -a cli=codex,model=gpt-5.6-sol,effort=high,permission=read-only \
    "$(cat TASK.md)"
```

**In the flow**, so nobody can run it any other way — see
[building the agents yourself](/reference/flows#building-the-agents-yourself).

The first is a setting of the run; the second is a property of the flow. Prefer the first while
you are experimenting.

## Step 6 — ask for a backend that can do the job

If your reviewer needs a feature only some backends have — a [goal](/features/goals), or the
`PERMISSION_REQUEST` [moment](/features/hooks) — say so beside the type, and it is checked before
the first turn:

```python
from typing import Annotated

from hmz.agents import AgentBase, Goal, Moment


class Agents(NamedTuple):
    builder: Annotated[AgentBase, Moment.PERMISSION_REQUEST]
    reviewer: Annotated[AgentBase, Goal]
```

```console
$ hmz exec -f pair -a kimi/kimi-code/k3:high -a pi/openai-codex/gpt-5.5:high "fix the build"
hmz exec: error: pair: builder has to run PermissionRequest, which kimi does not
```

And the agents page of `/flow` then offers only the CLIs that would work for that place, so it
cannot be chosen wrong there at all.

## Three variations worth trying

**Flame chase** — two agents take turns on the same task, neither holding a session:

```python
while True:
    agents.first(task, suppress=True)
    agents.second(task, suppress=True)
```

**A reviewer that reads the diff rather than the repository:**

```python
import subprocess

diff = subprocess.run(["git", "diff"], capture_output=True, text=True, check=False).stdout
review = agents.reviewer(f"{REVIEW}\n\n```diff\n{diff}\n```", suppress=True, schema=Review)
```

**A reviewer at a different effort** — `low` for a cheap gate that only catches obvious things,
`max` for one whose judgement you will act on. See [Efforts](/features/efforts).

## What you now know

- A `NamedTuple` names the agents, and everything downstream uses those names.
- `agent.new()` held versus `agent(...)` dropped is the whole actor/reviewer distinction.
- A schema turns "the reviewer said something" into `review.done`.
- `Annotated[..., Goal]` and `Annotated[..., Moment.…]` are checked before the first turn.

## Next

[Settings of its own](/guide/tutorial-flow-settings) — a flow you can configure.

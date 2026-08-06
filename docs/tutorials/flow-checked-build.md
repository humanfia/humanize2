# 5 · Write a flow: build under test

**Thirty minutes.** You will write a flow of about forty lines. One agent writes code, the flow
runs `pytest` between its turns, and a second agent reviews whatever passed. The loop ends when
the reviewer is satisfied, not when the writer says it is finished.

By the end you will have used the four things every flow is made of: agents, a session, a
schema, and a loop.

::: tip Before you start
Finish the [Quickstart](/tutorials/quickstart). You need one backend; this tutorial uses
DeepSeek Harness, which needs only an API key.
:::

## What a flow actually is

A flow is a directory with an `__init__.py` in it, and that file has one function marked
`@flow`:

```python
from hmz.agents import AgentBase
from hmz.flows import flow

@flow
def run(agents: tuple[AgentBase], task: str) -> None:
    (agent,) = agents
    agent(task)
```

That is a complete flow. `agents` is what the person running it named on the command line, one
`-a` apiece; `task` is the last argument they typed. The type annotation is not decoration —
its length is how many `-a` flags humanize requires, and it is the only way a command line can
know before the first turn is taken.

Flows are looked for in three places, nearest first: `.humanize/flows/` in the project you are
in, `~/.humanize/flows/` for your own, and then the ones humanize ships and every
[flowverse](/guide/flowverses) you have added. This tutorial writes one into the project.

## Step 1 — make a project to work in

```sh
mkdir -p ~/tmp/flowlab && cd ~/tmp/flowlab
git init -q
```

Something for the agent to extend — Roman numerals, one direction only:

```sh
cat > roman.py <<'PY'
"""Roman numerals."""

VALUES = [
    (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"),
    (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
    (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"),
]


def to_roman(n: int) -> str:
    """The Roman numeral for 1 <= n <= 3999."""
    if not 1 <= n <= 3999:
        raise ValueError(f"out of range: {n}")
    out = []
    for value, sign in VALUES:
        while n >= value:
            out.append(sign)
            n -= value
    return "".join(out)
PY
cat > test_roman.py <<'PY'
import pytest

from roman import to_roman


@pytest.mark.parametrize(
    ("n", "sign"),
    [(1, "I"), (4, "IV"), (9, "IX"), (14, "XIV"), (40, "XL"), (1990, "MCMXC"), (3999, "MMMCMXCIX")],
)
def test_to_roman(n, sign):
    assert to_roman(n) == sign


@pytest.mark.parametrize("n", [0, -1, 4000])
def test_to_roman_refuses(n):
    with pytest.raises(ValueError):
        to_roman(n)
PY
python -m pytest -q
```

```console
..........                                                               [100%]
10 passed in 0.29s
```

Ten green tests. That is the baseline the flow will hold the agent to.

```sh
git add -A && git commit -qm "roman numerals, one way"
```

## Step 2 — say who the agents are

```sh
mkdir -p .humanize/flows/checked_build
```

Open `.humanize/flows/checked_build/__init__.py` and start with the two agents:

```python
from typing import NamedTuple

from hmz.agents import AgentBase


class Agents(NamedTuple):
    """The two this drives: one that writes, and one that reads what it wrote."""

    builder: AgentBase
    reviewer: AgentBase
```

You could have written `tuple[AgentBase, AgentBase]` and got the same count. A `NamedTuple`
buys you names, and the names are used everywhere something has to talk about one of these
agents: the agents page of `/flow` asks what *the reviewer* runs rather than what agent 2 of 2
runs, the line above the prompt says `reviewer · dsh/deepseek-v4-pro:high`, and a
[trace](/guide/tracing) groups that agent's sessions under `reviewer`.

## Step 3 — say what the reviewer has to answer

A reviewer that replies in prose leaves the flow reading paragraphs for a phrase like "looks
good to me". Ask for a shape instead:

```python
from pydantic import BaseModel, Field


class Review(BaseModel):
    """What one round's review comes to: whether it is over, and what the builder is told."""

    model_config = {"extra": "forbid"}

    good: bool = Field(
        description="True only if the task is done and the code is worth keeping: no "
        "duplication left behind, no dead code, names that say what they hold, and no test "
        "weakened or special-cased to pass. False if anything is left to do or to tidy."
    )
    notes: str = Field(
        description="The review, written as a message to the coding agent: what is done, "
        "what to change, and where. It is passed on word for word and is all the agent will "
        "hear from you."
    )
```

Those `description` strings are not comments. They are handed to the backend as the shape it
must answer in, so they *are* the instruction. Everything you want the reviewer to weigh goes
in there — this is the file you edit when you want reviews to be stricter. See [Answers in a
shape](/guide/shapes).

## Step 4 — run the tests yourself

The flow is Python, so anything Python can do between turns, it can do:

```python
import subprocess

#: How much of a failing suite the builder is shown. The end of pytest's output is the part
#: that says what failed; the front of it is a list of dots.
TAIL = 4000


def suite() -> tuple[bool, str]:
    """Run the tests. Answers with whether they passed and the end of what they said."""
    ran = subprocess.run(
        ["python", "-m", "pytest", "-q"],
        capture_output=True,
        text=True,
        check=False,
    )
    return ran.returncode == 0, (ran.stdout + ran.stderr)[-TAIL:]
```

This is the part worth being deliberate about. You could ask the agent to run the tests and
tell you how it went. Running them yourself means the flow's decisions rest on an exit code
rather than on a report, and the exit code cannot be optimistic.

## Step 5 — write the loop

```python
REVIEW = """You are reviewing a coding agent's work in the directory you are running in. \
`python -m pytest -q` passes -- that is not in question. Read what it actually wrote, with \
`git diff`, `git status` and the files themselves, and judge whether the task below is done \
and the code is worth keeping. Be sceptical: a test weakened, a case special-cased, or a \
function stubbed to make the suite green is the thing you are most here to catch.

Task:
"""


@flow
def run(agents: Agents, task: str) -> None:
    working = agents.builder.new()
    prompt = task
    while True:
        # A turn that failed answers with nothing: take the round again rather than test a
        # working tree the builder never got to write to.
        if not working(prompt, suppress=True):
            continue
        passed, said = suite()
        if not passed:
            prompt = f"`python -m pytest -q` fails. Read this and fix it.\n\n{said}"
            continue
        review = agents.reviewer(REVIEW + task, suppress=True, schema=Review)
        if review is not None and review.good:
            print(review.notes)
            return
        prompt = (review.notes if review else "") or prompt
```

Four decisions are packed into those fifteen lines.

**`agents.builder.new()` sits outside the loop.** That opens one session and keeps it, so the
builder remembers every round. **`agents.reviewer(...)` inside the loop** calls the agent
rather than a session, which opens a fresh conversation each time: the reviewer reads the
repository, never the builder's account of it.

**A red suite never reaches the reviewer.** It becomes the builder's next prompt instead. The
reviewer's turn is expensive and there is nothing to review while the tests are failing.

**`suppress=True` means a failed turn answers with `""`** instead of raising. A loop meant to
run for hours should survive one rate limit. The `if not working(...)` line catches that case
and takes the round again rather than testing a tree nobody wrote to.

**The loop ends on `review.good`,** a boolean the reviewer filled in — not on a phrase in a
paragraph.

::: details The whole file
Everything above, in order: the imports, `Agents`, `Review`, `TAIL`, `REVIEW`, `suite`, and
`run`. Add a module docstring at the top — its first line is what `/flow` shows beside the
flow's name.

```python
"""Build under test: one agent writes, pytest judges, a reviewer reads what passed."""

import subprocess
from typing import NamedTuple

from hmz.agents import AgentBase
from hmz.flows import flow
from pydantic import BaseModel, Field
```
:::

## Step 6 — run it

```sh
export DEEPSEEK_API_KEY=sk-…
hmz exec -f checked_build \
    -a dsh/deepseek-v4-flash:high \
    -a dsh/deepseek-v4-pro:high \
    "Add from_roman(s: str) -> int to roman.py, the exact inverse of to_roman, refusing anything that is not a canonical numeral. Add tests for it in test_roman.py, including a round-trip over 1..3999."
```

`-f checked_build` finds the flow by name, because `.humanize/flows/` is the first place
humanize looks. A cheap fast model builds and a stronger one reviews, which is usually the
right way round: reviewing is the harder judgement and it is one turn per round.

The run ends by itself, printing the review it ended on:

```console
Done and worth keeping. from_roman is a genuine inverse: greedy descent over VALUES
followed by `to_roman(n) != s` rejection accepts exactly the canonical numerals, and
the round-trip over 1..3999 plus the non-canonical refusal cases in test_roman.py
cover the contract. No existing test was weakened, no special-casing, and no dead
code or duplication. Nothing to change.
```

## Step 7 — check the work

```sh
python -m pytest -q
```

```console
..............................                                           [100%]
30 passed in 0.23s
```

Ten tests became thirty. Look at what it actually wrote:

```sh
git diff
```

```python
def from_roman(s: str) -> int:
    """The exact inverse of to_roman: the int for canonical numeral s."""
    if not isinstance(s, str):
        raise TypeError(f"expected str, got {type(s).__name__}")

    n = 0
    rest = s
    for value, sign in VALUES:
        while rest.startswith(sign):
            n += value
            rest = rest[len(sign):]

    if rest or not 1 <= n <= 3999 or to_roman(n) != s:
        raise ValueError(f"not a canonical Roman numeral: {s!r}")
    return n
```

Note `to_roman(n) != s` on the last line. Greedy descent alone would accept `IIII` and `VV`;
round-tripping through the existing function is what makes "canonical" mean something. That is
the kind of thing the reviewer's turn is for.

## What to change

**Swap `pytest` for whatever your project uses.** `suite()` is one `subprocess.run`. Point it
at `npm test`, `cargo test`, `go test ./...`, or a shell script that runs all three.

**Gate on more than tests.** Add a linter to `suite()` and hand the agent both outputs.
Anything you can run is something the loop can hold the agent to, and holding it to a command
is stronger than asking it in a prompt.

**Give the flow settings of its own.** A third argument annotated with a pydantic model turns
into fields on `/config` and lines in a `-c setup.yaml` file. See [A flow with settings of its
own](/guide/flow-settings).

**Stop it running for ever.** This loop has no round limit. Adding one is two lines, and
[testing a flow](/guide/testing-flows) shows how to check it without spending a turn.

## Next

That flow has one loop and two agents. The last tutorial has four kinds of agent, several turns
running at once, and a problem where nothing can tell you whether the answer is right: [Four
agents on a maths problem](/tutorials/flow-prove).

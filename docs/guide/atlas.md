# An atlas

A flow is a Python file, and the one thing nothing can ask it is what it is about to do. An
atlas is the other bargain: a narrower Python whose body is read rather than run, compiled
before anything happens into a graph called a **prophecy** — the nodes, the edges between
them, and the shapes that flow along each edge.

What you get for the narrowness is everything a graph makes possible. The flow is checked
whole before its first turn, not hours in. What it will do can be printed, diffed and
reviewed. And a run of one can be stopped and picked up in the middle, because a graph is a
list of nodes with an answer apiece and the run writes those answers down as they arrive.

## One that writes and reviews

```python
"""Writes a draft, reviews it, and goes round until the review says it is done."""

from typing import NamedTuple

from pydantic import BaseModel, Field

from hmz.flows import Agent, atlas, logic, mind


class Agents(NamedTuple):
    """Who this drives."""

    writer: Agent
    reviewer: Agent


class Draft(BaseModel):
    """What the writer produced."""

    model_config = {"extra": "forbid"}

    text: str = Field(description="the draft itself")


class Verdict(BaseModel):
    """What the reviewer made of it."""

    model_config = {"extra": "forbid"}

    done: bool = Field(description="whether the work is finished")
    notes: str = Field(default="", description="what to fix next")


@mind
def write(agent: Agent, task: str) -> Draft:
    """One turn of writing."""
    return agent(task, schema=Draft)


@mind
def review(agent: Agent, draft: Draft) -> Verdict:
    """One turn of reviewing."""
    return agent(f"review this:\n\n{draft.text}", schema=Verdict)


@logic
def settled(said: Verdict) -> Verdict:
    """Reads the review, which is what the loop branches on."""
    return said


@atlas
def run(agents: Agents, task: str) -> None:
    """Writes and reviews until the review says it is done."""
    draft = write(agents.writer, task)
    seen = review(agents.reviewer, draft)
    verdict = settled(seen)
    while not verdict.done:
        draft = write(agents.writer, task)
        seen = review(agents.reviewer, draft)
```

It is run exactly as any other flow is:

```sh
hmz exec -f review_loop -a claude/sonnet:high -a codex/gpt-5.6-sol "$(cat TASK.md)"
```

## The two kinds of node

A **mind** is a turn: real work by a real agent, handed the agent the call site names. A
**logic** is a Python function: no agent, no turn, and a decision anything can read.

A mind has exactly one way out; a logic may have several. That is the whole of why the two
are told apart. A branch is a decision, and a decision nothing but a model made is a decision
no reading of the flow can state — so the node a branch hangs off is a logic node, and what a
model said reaches a branch by being read by one. Writing the `if` straight off the turn is
refused:

```
…/__init__.py:71: error: branching-mind: review is a turn, and a turn has one way out --
read what it answered with a logic node, and branch on that
```

That is what `settled` is for above. In a real flow it would earn its keep — counting the
rounds, holding the loop to a budget, deciding that three passes is enough however the
reviewer feels about it.

## The Python an atlas is written in

The body of an atlas is a declaration, and holds only these:

| | |
| --- | --- |
| `x = call(a, b)` | one node, whose answer is bound to `x` |
| `call(a, b)` | one node whose answer nothing takes |
| `if x:` / `if not x.field:` | a node's several ways out |
| `while x:` / `while not x.field:` | that, with an edge back to the node the test reads |
| `return` / `return x` | where the run ends |
| `pass`, the docstring | nothing at all |

Arguments are names the body has bound, fields read off them, or one of the flow's own three:
`agents`, what it was called with, and — for an atlas that takes one — its config.

Everything else is refused, because everything else is a thing a node does:

```python
n = draft.round + 1          # unstatic-body: work is what a logic node is for
said = write(agents.writer, judge(draft))   # a call inside a call is two nodes
if verdict.done and enough:  # a compound test is a decision a logic node makes
```

The rest of the file is ordinary Python. Only the `@atlas` body is narrowed — a mind or a
logic may do whatever a Python function may do, and is read by the same rules as any other
flow's code. One exception: a node may not be `async def`, since the walk over the graph does
not await. What waits for a model is a turn, and a `mind` already is one.

## What flows between nodes

Every node says what it takes and what it answers with, and both are pydantic models the flow
declares or one of `str`, `int`, `float`, `bool`. Each edge is checked before anything runs:

```
…/__init__.py:70: error: shape-mismatch: write takes task: str, and draft is Draft
```

A model may flow into a parameter of another model's type when it holds every field that one
requires, at the same shape apiece. A name keeps the shape it was first bound with, so an edge
that fits on the first round of a loop fits on every round.

## Loops

The node above a `while` is its **head**: it answers the name the test reads, the body runs
while that holds, and the body's last node wires back to the head — which answers again with
whatever the round changed. So the loop above reads as:

```
write → review → settled ──[done]──▶ (end)
                    │ ▲
        [not done]  │ │
                    ▼ │
              write:2 → review:2
```

A loop whose body changes nothing the head reads would answer the same thing every round, and
is refused as a `dead-loop` rather than run for a week.

Don't write the head again at the bottom of the body. It is the natural Python and the wrong
graph — the edge back runs the head anyway, so the copy would run first and have its answer
thrown away. `twice-round` refuses it:

```
…/__init__.py:71: error: twice-round: the body of this loop ends with settled, which is what
the loop reads again each round -- so it would run twice a round and the body's answer be
thrown away; take it out of the body
```

## Stopping and starting

An atlas can always be picked up where the last run of it left off, and says so without being
asked. Every node's answer is written into the run's state as it arrives:

```json
{
  "prophecy": "06ebb726641e4a5f",
  "at": "review:2#3",
  "done": {"write#1": {"text": "…"}, "settled#1": {"done": false, "notes": "…"}}
}
```

Picking the run up walks the same graph over the same answers until it reaches the visit that
has none. That node **runs again** — work cut off partway is work that was not done. A node
that has already had its effect by the time anything could interrupt it can say otherwise:

```python
@logic(rerun=False)
def announce(said: Verdict) -> None:
    """Says it once, and is stepped past rather than said twice."""
    post_to_slack(said.notes)
```

Such a node answers with nothing — the compiling refuses one that does not, since a run
stepping past it would have no answer for what comes next.

A run is picked up into the same graph or not at all. What was written down is written down
against the prophecy's digest, so an atlas rewritten between two runs starts from the top
rather than resuming into somewhere it has never been. Rewriting a node's *body* changes
nothing about the graph, and such a run picks up as it should.

## An atlas inside an atlas

A node may be a whole atlas — a **supernode**. One beside it is called by name:

```python
@atlas(name="review", selectable=False)
def reviewing(agents: Agents, draft: Draft) -> Verdict:
    """A graph of its own, reached as one node."""
    seen = review(agents.reviewer, draft)
    return settled(seen)


@atlas
def run(agents: Agents, task: str) -> None:
    """Says it."""
    draft = write(agents.writer, task)
    verdict = reviewing(agents, draft)
```

and one in another flow is named with `sub`, which is the counterpart of
[`load`](/guide/calling-flows):

```python
reviewing = sub("official/review")
```

An atlas reaches an atlas and reaches an ordinary flow through nothing at all: `load` answers
with a flow that may be anything, and a graph with one of those in it is a graph with a hole
where a node should be. Importing `load` in an atlas is a `dynamic-call` error.

A supernode's own nodes are written down beneath the node it is, so a run stopped three graphs
deep is picked up three graphs deep. A supernode that reaches back into a graph already being
compiled is refused, however it is spelled.

## Reading what it compiles to

```sh
hmz check --prophecy review_loop
```

prints the canonical prophecy — one line of JSON, everything ordered by what it is rather than
where it was written, so two readings of the same atlas are the same bytes and a diff of two
prophecies is a diff of two graphs. `hmz check` on an atlas is the stricter reading
automatically:

```sh
hmz check review_loop
```

## Shipping the prophecy

A flowverse may ship what compiling came to, beside the flow:

```sh
hmz check --ship official/review     # writes official/review/prophecy.pkl
```

Where there is one, that is what runs. The compiling is where an atlas is refused, and a
repository that has been through it once has an answer worth carrying rather than working out
again at every run. The flow's own Python still has to be there — a prophecy names the
functions its nodes are.

`hmz check` says when a shipped prophecy and the source it came from have drifted apart:

```
…/prophecy.pkl:0: error: stale-prophecy: the prophecy shipped here is d1f27db7dffd22e3 and
this source compiles to 4c9a01ab2f7e5510 -- a run walks the shipped one, so the flow does one
thing and reads as another
```

::: warning
A shipped prophecy uses pickle's format, but humanize does not open it with a general-purpose
pickle reader. It rebuilds only the seven allowlisted tuple types that make up a prophecy,
checks their canonical shape, and refuses anything else. The flow's Python is still trusted
code when it is loaded, as [the security guide](/guide/security) explains.
:::

## When to write one, and when not to

An atlas is worth it when the shape of the work is known and the run is long: a pipeline of
phases, a review loop meant to run for a week, anything a machine going down should not send
back to the start. It is worth it when somebody other than its author has to be able to say
what the flow will do before it does it.

An ordinary [flow](/guide/writing-a-flow) is right for everything else — a loop that decides
its own shape as it goes, a flow that fans out over whatever it found, one that is thirty
lines and does one thing. Nothing here replaces that; the two live side by side, are named the
same way, and are run by the same line.

# Checking a flow

Check a flow before anything runs it: a static reading that executes nothing, then the flow
driven by stubs against a clock. Together they catch the mistakes that otherwise surface
hours into a run — the loop nothing can end, the field read off an answer that failed, the
name the interface does not answer to.

## One line

```sh
hmz check official/rlar
```

```
…/rlar/__init__.py:125: warning: unbounded-loop: every way out of this loop waits for an
agent to say so, and an agent may never say it -- give the loop a bound of its own: a budget
read off spent(), a cap on the rounds, a range
hmz check: 0 errors, 1 warning
```

A flow is named the way `-f` names one — `chat`, `official/rlar`, a path of your own — and
everything wrong is said at once, one finding a line. The full table of codes is in the
[reference](/reference/flows#checking-a-flow).

## What an error is, and what a warning is

An **error** is a flow no run survives: it cannot run, cannot be answered, or cannot end.
`hmz check` exits `1` on any of those. A **warning** is a flow that runs, and a run of it
that may be regretted — rlar's warning above is real and documented: its loop is ended by its
reviewer alone, which is the flow's own shape. Warnings print and pass; `--strict` holds a
flow to the whole bar, which is the right setting for a flowverse's CI:

```sh
hmz check --strict local/mine
```

## The reading that runs nothing

The static reading is pure `ast` over every file the flow holds. Nothing is imported and
nothing is executed, so it is safe to point at a flow nobody has read — one an agent just
wrote, one fetched off the internet, one about to be forked:

```sh
hmz check --static somebody-elses/flow
```

## The reading that runs it against the worst day

Without `--static`, the flow is also loaded — in a subprocess held to a clock, never in your
process — and its live config model is read. The same machinery is a library, and the
scenarios are the questions worth asking of a loop:

```python
from hmz.flows import NEVER_DONE, SILENT, proved

proof = proved(".humanize/flows/mine", scenarios=(NEVER_DONE, SILENT))
assert all(one.finished for one in proof.outcomes), proof.outcomes
```

`NEVER_DONE` is the reviewer that never says the work is done. The stubs answer every turn at
once — every boolean verdict `False`, every turn adding 100k output tokens to `spent()` — so
a loop held to a budget walks to the end of it in milliseconds, and one whose only exit is
the verdict is caught by the turn cap. That is the executable proof that a run of your flow
can end. `SILENT` answers every turn with nothing, which is what a failed turn answers: a
flow that reads a field off an unguarded answer falls over here rather than at hour three.

## In a script

`--json` says the same findings one JSON object a line, and the exit status is the answer:
`0` with nothing blocking, `1` with something, `2` for a line to correct.

```sh
hmz check --json local/mine | jq -r .code
```

## See also

- [`hmz check`](/reference/cli#hmz-check) — the command and its flags
- [Checking a flow](/reference/flows#checking-a-flow) — the library API and the rule table
- [Testing a flow](/guide/testing-flows) — driving a flow with stand-ins of your own
- [Writing a flow](/guide/writing-a-flow)

## An atlas is read more strictly

A flow marked [`@atlas`](/guide/atlas) gets the stricter of the two readings automatically:
its body is a declaration rather than a program, so `hmz check` compiles it and holds every
edge, every branch and every shape to what a graph can be held to. `--prophecy` prints the
graph it compiled; `--ship` writes it beside the flow for runs of it to walk.

```sh
hmz check --prophecy local/mine
```

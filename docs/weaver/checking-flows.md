# Checking a flow

Check a flow before anything runs it. Two readings, in their order: a static one that runs
nothing, then the flow loaded in a subprocess held to a clock — and, when you ask for it,
driven by stubs through the worlds worth asking of a loop. Together they catch what otherwise
surfaces hours in: the loop nothing can end, the field read off an answer that failed, the name
the interface does not answer to.

## One call

```python
from hmz.sdk import Hmz

for one in Hmz().flows.check("official/rlar"):
    print(f"{one.where}:{one.line}: {one.severity}: {one.code}: {one.said}")
```

```text
…/rlar/__init__.py:125: warning: unbounded-loop: every way out of this loop waits for an
agent to say so, and an agent may never say it -- give the loop a bound of its own: a budget
read off spent(), a cap on the rounds, a range
```

A flow is named the way `-f` names one — `chat`, `official/rlar`, a path of your own — and
everything wrong comes back at once, one finding per thing found rather than the first of them
raised. The full table of codes is in the [reference](/reference/flows#checking-a-flow).

**There is nothing to type for this, and no sheet to open.** Checking a flow belongs to the
hours you are writing one — in an editor, in a test, in the repository's own CI — and in all
three of those Python is already what you are holding, so a call is the whole of the interface.
What `hmz exec` refuses before a run is the smaller question of whether *this* flow can take
*these* agents, and that is [answered there](/reference/cli#what-is-refused-before-anything-runs).

What comes back is a tuple of findings, each one saying what was found and where:

| A finding | |
| --- | --- |
| `code` | which rule found it, as one hyphenated word — `dead-loop`, `unknown-ask` |
| `severity` | `"error"` or `"warning"` |
| `where` | the file it is in, as a `Path` |
| `line` | the line, 1-based, or `0` for a finding about the whole file |
| `said` | what is wrong, said the way `NotAFlow` says it |

## What an error is, and what a warning is

An **error** is a flow no run survives: it cannot run, cannot be answered, or cannot end. A
**warning** is a flow that runs, and a run of it that may be regretted — rlar's warning above
is real and documented: its loop is ended by its reviewer alone, which is the flow's own shape.
Which of the two is worth stopping a build for is the caller's to say, since the caller is the
one holding them. See [In a script](#in-a-script).

## The reading that runs nothing

Pure `ast` over every file the flow holds. Nothing is imported and nothing is executed, so it
is safe to point at a flow nobody has read — one an agent just wrote, one fetched off the
internet, one about to be forked:

```python
Hmz().flows.check("somebody-elses/flow", static=True)
```

## The reading that loads it, and the one that drives it

Without `static=True` the flow is also loaded — in a subprocess held to a clock, never in your
process — and its live config model is read. It is left out where the first reading already
found an error: a flow that cannot run is not one to run to find out more about. Driving the
flow against the worlds worth asking of a loop is the same machinery a step further, and is a
call of your own:

```python
from hmz.flows import NEVER_DONE, SILENT, proved

proof = proved(".humanize/flows/mine", scenarios=(NEVER_DONE, SILENT))
assert all(one.finished for one in proof.outcomes), proof.outcomes
```

`NEVER_DONE` is the reviewer that never says the work is done. The stubs answer every turn at
once — every boolean verdict `False`, every turn adding 100k output tokens to `spent()` — so a
loop held to a budget walks to the end of it in milliseconds, and one whose only exit is the
verdict is caught by the turn cap. That is the executable proof that a run of your flow can
end. `SILENT` answers every turn with nothing, which is what a failed turn answers: a flow that
reads a field off an unguarded answer falls over here rather than at hour three.

## An atlas is read more strictly

A flow marked [`@atlas`](/weaver/atlas) gets the stricter of the two static readings
automatically: its body is a declaration rather than a program, so it is compiled and every
edge, every branch and every shape held to what a graph can be held to. What it compiled to is
`prophecy`, and `foretell` writes that beside the flow for every run of it to walk from then
on:

```python
from hmz.flows import canonical
from hmz.sdk import Hmz

hmz = Hmz()
print(canonical(hmz.flows.prophecy("local/mine")))    # the graph, one line of JSON
hmz.flows.foretell("local/mine")                      # writes prophecy.pkl beside the flow
```

`prophecy` answers `None` for a flow that is not an atlas or does not compile, and `check` is
where the reasons are.

## In a script

Nothing is printed and nothing has to be parsed: the findings are objects, so what a build does
about them is written rather than read back off a stream. A CI job holding a flowverse's flows
to the whole bar is the whole of it:

```python
from hmz.sdk import Hmz

hmz = Hmz()
found = [one for name in ("yours/review", "yours/nightly") for one in hmz.flows.check(name)]
for one in found:
    print(f"{one.where}:{one.line}: {one.severity}: {one.code}: {one.said}")
raise SystemExit(1 if found else 0)
```

Keep only `one.severity == "error"` for the looser bar — the one that lets a flow's own shape
through, which is what a flowverse holding something like `rlar` has to do.

## See also

- [Checking a flow](/reference/flows#checking-a-flow) — the library API and the rule table
- [SDK reference](/reference/sdk#flows) — `check`, `prophecy` and `foretell` beside the rest
- [Testing a flow](/weaver/testing-flows) — driving a flow with stand-ins of your own
- [Writing a flow](/weaver/writing-a-flow)

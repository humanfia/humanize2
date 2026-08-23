# Picking a run up

A loop that runs for a week will be stopped and started: a machine goes down, somebody presses
by hand, or a turn takes the process with it. A **flow** is a file on disk, and the weaver who
wrote it may say it can be picked up where its last run left off.

## Try it

Run a resumable flow twice with the same command:

```sh
hmz exec -f nightly -a claude/claude-opus-5:high "keep the tests green"
hmz exec -f nightly -a claude/claude-opus-5:high "keep the tests green"   # round 2, not round 1
```

The second run finds what the first left behind, and carries on from round 2.

## Saying so

**For the weaver.** To make a flow resumable, give it `resumable=True` and a dict. The dict is
where the flow keeps what the loop itself knows: which round it is on, which files it has been
through, what it has decided so far. It is not a second copy of the transcript — the backends
keep that, and the run's **[epic](/user/tracing#what-a-run-writes-down)** already says which
sessions it opened.

```python
"""A Ralph loop that knows which round it is on."""

from typing import Any

from hmz.flows import Agent, flow


@flow(resumable=True)
def run(agents: tuple[Agent], task: str, state: dict[str, Any]) -> None:
    (agent,) = agents
    while True:
        state["round"] = state.get("round", 0) + 1   # writing it into the state saves it
        agent(f"{task}\n\nRound {state['round']}.", suppress=True)
```

The dict is the flow's **last** argument, after the config for a flow that takes one. A flow
that says `resumable=True` but declares no such argument says so at the first call, before a
turn has been taken, rather than starting over in silence. A flow that says nothing runs from
the top every time. See [Writing a flow](/weaver/writing-a-flow).

## Where it lives

What a flow keeps goes in the epic of the run that wrote it, as `state.json`:

![one run's directory listed: epic.jsonl, profile.jsonl, sessions and
state.json](/demo/run.png)

The state is keyed by flow, so a flow that calls [another
one](/reference/flows#a-flow-that-calls-another-flow) is two flows, each keeping its own state
side by side in the one file and neither writing the other's:

```json
{"nightly": {"round": 12}, "official/rlar": {"seen": ["src/pay.py"]}}
```

The key is the name the flow was run under, so `-f nightly` and the path to that same file are
two names and two states.

## When it is saved

**As the flow writes it.** Setting a key, removing one, or calling `update` or `setdefault`
writes the file again. A run worth picking up is one that was stopped or killed, and state
written only at the end is state such a run has none of.

Writing *inside* a value the state holds is a change no mapping can see: appending to a list,
or writing into a dict of its own, is saved when the run ends.

Keep to what JSON holds. Anything else is written as its `str`, so a `Path` put in comes back
out a string. A value that cannot be written at all leaves the last save standing rather than
ending the run: a loop that died for want of writing down where it got to would be worse than
one carrying on from a round ago.

## Running it again

There is no flag for it: running the flow again is what picks it up, as in [Try it](#try-it)
above. It carries on from the last run of that flow **in this directory** that left anything —
a run that wrote nothing is skipped for the one before it. Runs are kept under the workspace
they ran in, so another checkout carries on from its own last run there.

It is found by what the state holds rather than by what the run was of — which is what lets a
flow that was *called* by another be picked up too, under its own name.

## Carrying an older one on

`/epics` is every run of a flow in this directory, newest first: when it happened, which flow
it was, what it was asked to do, how many sessions it opened, and a mark on the runs whose flow
says it can be picked up. Enter opens what there is to do with the run under the cursor:

![the /epics list with the run that can be picked up marked, the menu that opens under one
run, and a trace collected from it](/demo/epics.gif)

| | |
| --- | --- |
| **carry on from here** | Run the flow again on what this run left behind |
| **collect a trace** | Its sessions, and the [programs it ran](/user/tracing#profiling-a-run), as one [trace](/user/tracing) |
| **where it is** | The directory the run is written in, sessions and all |

The mark in the list and that first row are one question, asked of the **flow** rather than of
the run. The weaver may have rewritten it since, so what can happen next is what it says today:

- A flow marked `resumable=True` after a run of it has that older run marked and offered too.
  Carrying that one on runs its flow, its agents and its task on nothing — taken while the flow
  still said nothing, it left no state to pick up.
- A flow that has since dropped the mark has neither the mark nor the row, whatever the run
  wrote down at the time; where the row is gone, the reason stands under the list.
- A flow that will not load at all reads as one that says no — a flow that cannot be read
  cannot be run.

Collecting a trace is offered for every run, whatever its flow says.

Carrying one on is refused while a flow is running, on the sheet rather than on the way out;
[stopping](/user/stopping) is what stops a flow.

Naming a run rather than taking the last one is the same thing from Python:

```python
from hmz.runner import Runner

Runner("nightly", agents, resume=at).run("keep the tests green")
```

`at` is that run's own directory: what *where it is* prints, and what
[`hmz.epic.epics()`](/reference/tracing#epics) lists.

## What carrying on runs

The flow, its agents and what it was asked to do all come off the run rather than off whatever
the interface happens to be set up on — an agent swapped under it would be a different run
wearing its name. Each agent starts at the backend, model, effort,
[permission](/user/permissions) and [account](/user/providers) the run wrote down.

Two things are not the run's. The person at the prompt is not an agent anybody chose, so a flow
that talks to one is handed a fresh one. How the flow was set up is not written in the run, so
that is [what this project remembers](/user/settings) for the flow now.

## An epic is never reopened

What carries on is written into an epic of its own, and its `began` line says which run it was
`picked_up` from. The run being picked up is read and left exactly as it was, so carrying the
same run on twice is two runs from one starting point rather than one record with two runs
inside it.

A week of stops and starts therefore reads as a run per stretch — its own sessions, its own
trace, its own end — rather than one enormous epic claiming to have begun on Monday.

## An atlas picks itself up

Everything above is a flow keeping what it wants to carry by hand. An [atlas](/weaver/atlas)
does not have to: its body is compiled into a graph, every node's answer is written down as it
arrives, and picking a run up is walking that graph over the answers it already has until it
reaches the node that has none.

## See also

- [Tracing](/user/tracing) — what else a run writes down, and reading one back
- [Stopping](/user/stopping) — what makes a run worth picking up
- [Flows › A flow that can be picked up](/reference/flows#a-flow-that-can-be-picked-up)
- [TUI › Commands](/reference/tui#commands)

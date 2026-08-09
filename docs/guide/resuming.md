# Picking a run up

A loop that runs for a week will be stopped and started: a machine goes down, somebody presses
by hand, or a turn takes the process with it. A **flow** (a file on disk) may say it can be picked
up where its last run left off. A flow that says so keeps what it is tracking in a dict.

## Try it

Run a resumable flow twice with the same command:

```sh
hmz exec -f nightly -a claude/claude-opus-5:high "keep the tests green"
hmz exec -f nightly -a claude/claude-opus-5:high "keep the tests green"   # round 2, not round 1
```

The second run finds the state the first run left behind. It carries on from round 2, not round
1.

## Saying so

To make a flow resumable, give it `resumable=True` and a dict. The dict is where you keep what
the loop itself knows: which round it is on, which files it has been through, what it has
decided so far. It is not a second copy of the transcript. The backends keep that, and the
run's **[cycle](/guide/tracing#what-a-run-writes-down)** (what the run writes down) already
says which sessions it opened.

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
that says `resumable=True` but declares no such argument is handed a dict it has nowhere to
put. It says so at the first call, before a turn has been taken, rather than starting over in
silence.

A flow that says nothing runs from the top every time, which is what every flow did before
this.

## Where it lives

What a flow keeps goes in the cycle of the run that wrote it, as `state.json`. It sits beside
that run's own record and the links to its sessions:

![one run's directory listed: cycle.jsonl, profile.jsonl, sessions and
state.json](/demo/run.png)

The state is keyed by flow. A flow that calls [another
one](/reference/flows#a-flow-that-calls-another-flow) is two flows, and each keeps its own
state side by side in the one file, neither writing the other's:

```json
{"nightly": {"round": 12}, "official/rlar": {"seen": ["src/pay.py"]}}
```

The key is the name the flow was run under. So `-f nightly` and the path to that same file are
two names and two states.

## When it is saved

**As the flow writes it.** Setting a key, removing one, or calling `update` or `setdefault`
writes the file again. A run worth picking up is one that was stopped or killed rather than one
that ended tidily. State written only at the end is state such a run has none of.

Writing *inside* a value the state holds is a change no mapping can see. Appending to a list,
or writing into a dict of its own, is saved when the run ends.

Keep to what JSON holds. Anything else is written as its `str`, so a `Path` put in comes back
out a string. A value that cannot be written at all leaves the last save standing rather than
ending the run. A loop that died because it could not write down where it had got to would be
worse than one carrying on from a round ago.

## Running it again

Running the flow again is what picks it up. There is no flag for it:

```sh
hmz exec -f nightly -a claude/claude-opus-5:high "keep the tests green"
hmz exec -f nightly -a claude/claude-opus-5:high "keep the tests green"   # round 2, not round 1
```

It carries on from the last run of that flow **in this directory** that left anything. A run
that wrote nothing is nothing to pick up, so what carries on is the run before it. Runs are
kept under the workspace they ran in. The same flow in another checkout carries on from that
checkout's own last run.

It is found by what the state holds rather than by what the run was of. That is what lets a
flow that was *called* by another be picked up too: it wrote under its own name, and that is
where it is looked for.

## Carrying an older one on

`/cycles` is every run of a flow in this directory, newest first. It shows when the run
happened, which flow it was, what it was asked to do, how many sessions it opened, and a mark
on the runs whose flow says it can be picked up. Enter opens what there is to do with the run
under the cursor:

![the /cycles list with the run that can be picked up marked, the menu that opens under one
run, and a trace collected from it](/demo/cycles.gif)

| | |
| --- | --- |
| **carry on from here** | Run the flow again on what this run left behind |
| **collect a trace** | Its sessions, and the [programs it ran](/guide/tracing#profiling-a-run), as one [trace](/guide/tracing) |
| **where it is** | The directory the run is written in, sessions and all |

The mark in the list and that first row are one question, asked of the **flow** rather than of
the run. A flow is a file on disk and may have been rewritten since. What can happen next is
what it says today, rather than what it said when the run happened.

A flow marked `resumable=True` after a run of it has that older run marked and offered too.
Carrying that one on runs its flow, its agents and its task, on nothing: a run taken while the
flow still said nothing left no state behind to pick up.

A flow that has since dropped the mark has neither the mark nor the row, whatever the run wrote
down at the time. Where the row is gone, the reason for it stands under the list.

A flow that will not load at all reads as one that says no. A flow that cannot be read cannot
be run, which is what carrying on would come to.

Collecting a trace is offered for every run, whatever its flow says.

Carrying one on is refused while a flow is running, and the refusal is said on the sheet rather
than on the way out. The question is still worth answering, and [stopping](/guide/stopping) is what
stops a flow.

Naming a run rather than taking the last one is the same thing from Python:

```python
from hmz.runner import Runner

Runner("nightly", agents, resume=at).run("keep the tests green")
```

`at` is that run's own directory: what *where it is* prints, and what
[`hmz.cycle.cycles()`](/reference/tracing#cycles) lists.

## What carrying on runs

The flow, its agents and what it was asked to do all come off the run, rather than off whatever
the interface happens to be set up on. Picking a run up means running what ran. An agent
swapped under it would be a different run wearing its name.

Each agent starts at the backend, model, effort, [permission](/guide/permissions) and
[account](/guide/providers) the run wrote down.

Two things are not the run's. The person at the prompt is not an agent anybody chose, so a flow
that talks to one is handed a fresh one. How the flow was set up is not written in the run, so
that is [what this project remembers](/guide/settings) for the flow now.

## A cycle is never reopened

What carries on is written into a cycle of its own. Its `began` line says which run it was
`picked_up` from.

The run being picked up is read and left exactly as it was. Carrying the same run on twice is
two runs from one starting point, rather than one record with two runs inside it.

This is what makes a week of stops and starts readable afterwards. Each stretch is a run, with
its own sessions, its own trace and its own end, rather than one enormous cycle claiming to
have begun on Monday.

## See also

- [Tracing](/guide/tracing) — what else a run writes down, and reading one back
- [Stopping](/guide/stopping) — what makes a run worth picking up
- [Flows › A flow that can be picked up](/reference/flows#a-flow-that-can-be-picked-up)
- [TUI › Commands](/reference/tui#commands)

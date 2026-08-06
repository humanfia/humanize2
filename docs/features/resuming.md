---
pageClass: hmz-feature
---

# Picked up where it stopped

A loop meant to run for a week is a loop that will be stopped: somebody presses escape, a
machine goes down, a turn takes the process with it. So a flow may say that it can be picked up
where its last run left off — and then running it again is what picks it up. There is no flag.

<HmzResume />

## What a flow keeps is its own handful of things

A flow that says so is handed a dict holding what it wrote there last time. Which round it is
on, which files it has been through, what it has decided so far.

Deliberately not a second copy of the transcript: the backends already keep that, and the run's
own record already says which sessions it opened. What the flow keeps is what only the flow
knows.

## Saved as it is written, not when the run ends

Setting a key writes the file again. That is the whole design decision, and it follows from
what resuming is for: **a run worth picking up is one that was stopped or killed**, and state
saved only at the end is state such a run has none of.

Writing *inside* a value the state holds — appending to a list, filling in a dict of its own —
is a change no mapping can see, so that is saved again when the run ends.

Nothing about keeping it may stop a run. A value JSON has no shape for is written as its text;
a value that cannot be written at all leaves the last save standing rather than ending the run.
A loop that died because it could not write down where it had got to would be worse than one
carrying on from a round ago.

## Kept in the run that wrote it, keyed by the flow

State goes in the record of the run **doing the writing**, not in the one it was picked up
from: a closed run is never reopened, and a run is what that run did.

It is keyed by the flow, so a [flow that called another](/features/flows) is two flows, each
keeping its own state side by side in one file and neither writing the other's. The key is the
name the flow was run under — so a flow run by name and the same file run by path are two names
and two states.

What a run picks up from is the last run of that flow in this workspace, unless one is named. A
flow that **emptied** what it had written is where the search stops rather than a run to look
past: clearing it says the next run starts clean, and answering that with the state of the run
before would be answering the opposite.

Whether a flow can be picked up at all is read by running the flow rather than off what a run
of it recorded. A flow is a directory on disk, and what can happen next is what it says today.

## What does not come back

The conversation. A session is opened rather than reopened, so a run picked up again starts
from the task and the repository with none of the rounds before it in context. A stateful loop
stopped on its fortieth round says round 41 when it is started again — and remembers nothing
else about the forty.

Which is the argument for keeping little: the repository is the memory, and the handful of
things the flow tracks is what has to survive.

## Where the detail is

- [Picking a run up](/guide/resuming) — declaring it, and where the file lives
- [Tracing](/guide/tracing#what-a-run-writes-down) — what else a run writes down
- [Stopping](/guide/stopping) — what escape does to a turn

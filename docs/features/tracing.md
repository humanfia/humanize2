---
pageClass: hmz-feature
---

# One timeline

A run leaves several trajectories, in several formats, under several home directories, plus a
record of its own. Collecting turns all of it into **one Chrome trace**: a process per agent, a
track per row of that agent's sessions, a slice per thing it did — and, for a profiled run, the
programs those turns actually ran, drawn the same way underneath.

You open it in [Perfetto](https://ui.perfetto.dev). Nothing is uploaded; it is a file.

<HmzTimeline />

## Three words, and they carry over

| In the trace | Is |
| --- | --- |
| a **process** | one agent and everything it drove — or, for a profiled run, one program it ran |
| a **track** | one row of that agent's sessions: the ones somebody started, and the sub-agents a turn reached for. Sessions of one agent that never run at the same time share a track; root sessions and sub-agents stay apart. For a program, a track is one of its threads. |
| a **slice** | one action — a tool call, a message, or waiting for reasoning — carrying as much as the backend wrote down: the prompt, the reasoning, the tool input, the tool output |

## Why the backends' own logs are not enough

A backend logs a session under an id and never says whose it was. To anything reading the logs
alone, two agents at one configuration are one agent, and two accounts of one CLI are one
account.

So the run writes down what only the run knows: which flow, on what, by which agents, and for
each session — whose it was, what took its turns, which account those turns ran as, and what
the backend called it. A session is also given a name of its own holding all four, because an
id alone says nothing and a directory of forty of them is one nobody can read.

That record is **not** a second copy of the transcript. The backend's own log is the
turn-by-turn record, and each session's logs are pointed at from inside the run by a link
apiece — a link rather than a copy, and for reading rather than for running, so nothing here
can be the reason a log is written twice or read from the wrong place. The links are made again
when the run ends, which is when a sub-agent's transcript is finally there.

## A trace of a run holds that run's sessions

Which sessions belong to a trace is answered by the **ids the run wrote down**, not by the
directory it ran in. A directory is run in over and over, and a trace filed inside one run
holding the work of the others is a trace of nothing anybody asked about.

By id and not by directory, so a flow that worked in a [machine's mirror](/features/anchor) is
in its own trace as well. A run that opened no sessions is a trace of nothing. And a session no
flow ever drove is still a session to read back — it is just not part of any run, so it has to
be asked for outright and is never written inside one.

## The programs are the point

A turn is mostly other programs — the tests, the build, the greps — and none of them appears in
a backend's log, which records the tool call rather than the process. A timeline with the turns
on it and not what they ran is a timeline that stops exactly where the time went.

So a profiled run samples the programs its agents start while they run, and each one is drawn
beside the turn that started it. Three rules hold it:

- **It samples rather than intercepts.** Nothing goes between an agent and what it runs.
- **Nothing here can stop a run.** A machine whose processes cannot be read, a process that
  went while it was being read, a profile that cannot be written — each leaves the run as it
  was.
- **What it saw is appended as each program goes** rather than held to the end. A run that died
  is a run whose profile has to say what it got to.

## Half a second is a mile

A program's start time, as the operating system reports it, is worked out from an estimate of
when the machine booted — which is about half a second out on an ordinary machine. On a
timeline where a tool call is timed to the millisecond, that is enough to put `pytest` outside
the `Bash` that ran it, as the second switch above shows.

So the offset is not taken from the operating system at all. It is measured from the profile
itself: a program is seen within one sample of starting, so the smallest gap anywhere between
what was reported and when it was first seen is as close to the truth as sampling can get.
Every slice in the document is then timed against one clock.

## What a run is, on disk

One run is one directory, opening when the flow starts and closing however it stops — finished,
failed or interrupted. A closed run is never reopened. It holds the run's own record, a
directory per session it opened, whatever a [resumable](/features/resuming) flow left behind,
and the traces collected of it. Runs are named so that they sort in the order they were run,
**to the millisecond**: two started inside one second would otherwise be ordered at random, and
what a flow is picked up from is the last run of it.

## Which backends can be read back

Four backends have a reader today, and so are what a trace is made of: Claude Code, Codex,
DeepSeek Harness and Kimi Code. A reader is one per backend, because a backend is driven one
way and logs another — and where the logs are is not written down here either: that is a fact
about the backend, kept where every other fact about it is.

Several more write a log humanize reads *as a run happens*, which is where the running cost and
rate come from. And a backend that keeps its conversation in a database — rows rather than
files, with protobuf payloads — has nothing to read either way: no slices afterwards, and no
tally while it runs. Which of them is which is on [Twelve CLIs, one agent](/features/backends).

## Where the detail is

- [Tracing](/guide/tracing) — collecting one, and what to look for in your first
- [Tracing reference](/reference/tracing) — the cycle format, the trace format, what a slice
  carries
- [Many turns at once](/features/concurrency) — why a fan-out is one process and many tracks

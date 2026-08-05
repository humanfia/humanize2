# 5 · Read the run back

**Ten minutes.** Turn everything the agents left behind into one timeline, and find the four
minutes they wasted.

::: tip Before you start
Any of the runs from tutorials 1–4. This works on sessions no flow ever drove, too.
:::

## Step 1 — collect

In the project you have been running in:

```sh
hmz trace collect
```

```console
~/.humanize/cycles/-home-you-code-myproject/20260809T014455.212Z-9f21ab/traces/20260809T014455Z.trace.json of 20260809T014455.212Z-9f21ab: 3 sessions, 412 slices
```

The file, then which run it is a trace of, then what is in it. A trace lands **with that run** —
in `traces/` inside the run's own directory, where the record of what happened and the links to
its sessions already are — rather than in whatever directory you were standing in. Which run that
is, without a `--cycle` saying otherwise, is the last one of this workspace.

The name is the UTC moment it was collected, so collecting twice keeps both traces rather than
writing over the first. `--output` writes it somewhere of your own instead, which is what to
reach for when the trace is going into an issue or a CI artifact.

![hmz trace collect three times: the last run of this directory, one named with --cycle, and one
sent elsewhere with --output](/demo/collect.gif)

::: details `0 sessions, 0 slices`
Three usual reasons: you are in a different directory from the one the run happened in; the
backend was `opencode` or `mimocode`, which keep sessions in a database and have nothing to
gather; or the run was on a [machine of its own](/features/containers), in which case its
trajectories are found by `--session` rather than by workspace. See
[Troubleshooting](/guide/troubleshooting#_0-sessions-0-slices).
:::

## Step 2 — open it

Go to [ui.perfetto.dev](https://ui.perfetto.dev) and **drag the file in**. Nothing is uploaded;
Perfetto opens it in the browser. `chrome://tracing` works too, as does anything that reads a
Chrome JSON trace.

## Step 3 — read it

```
process   agent          actor · claude-opus-5 · max
  track     session ──▶ ▓▓▓ ▓ ▓▓▓▓▓▓ ▓▓  ▓▓▓▓▓  ▓ ▓▓▓▓▓▓▓▓▓▓
  track     sub-agent ─▶      ▓▓▓▓▓▓▓▓▓▓▓
process   agent          reviewer · gpt-5.6-sol · high
  track     session ──▶            ▓▓▓▓        ▓▓▓▓        ▓▓▓▓
```

| | |
| --- | --- |
| a **process** | one agent |
| a **track** | one session. Sessions of one agent that never overlap share a track; sub-agents stay apart. |
| a **slice** | one action — a tool call, a message, or waiting for reasoning |

**Click a slice.** Its arguments are there: the prompt, the reasoning, the tool input, the tool
output — as much as the backend wrote down.

Things worth looking for on your first trace:

- **A wide gap on every track.** Nobody was working. That is the flow sleeping, committing, or
  reading what the last turn wrote.
- **One very long slice.** A single tool call that took minutes — usually a test suite, sometimes
  a `find` over the whole disk.
- **A reviewer whose tracks all start after the actor's stop.** That is the loop working as
  designed. If they overlap, it is not.
- **Two hundred short tracks on one process.** A Ralph loop, one session per turn.

The first two of those are guesses until the run is **profiled**. A directory can ask for the
programs its runs start to be sampled into the same trace — a process per program, a track per
thread — and then the long slice has the `pytest` that made it drawn beside it, at the same
scale. It is the `profile` row on the second page of `/settings`, and a trace of a profiled run
counts them: `3 sessions, 412 slices, 61 programs`. See
[Tracing](/features/tracing#profiling-a-run).

## Step 4 — why your two agents are named

The backends log a session under an id and **never say whose it was**. So by default an agent in
a trace is one configuration — a backend at a model at an effort — and an actor and a reviewer at
the same model would read as one agent.

Every run of a flow writes a **cycle** that fixes this. One run is one directory:

```sh
run=$(ls -dt ~/.humanize/cycles/*/*/ | head -1)   # the one that just finished
ls "$run"
```

```console
cycle.jsonl  sessions  traces
```

`traces/` is there because of step 1. `state.json` joins them for a flow that says it can be
picked up again, and `profile.jsonl` for a run that was profiled.

![one run's directory, the session it opened by name, the link to the log the backend itself wrote,
and the state its flow left behind](/demo/run.gif)

`cycle.jsonl` is what happened, a line at a time:

```sh
head -3 "$run"cycle.jsonl
```

```console
{"event":"began","at":"...","flow":"official/rlar","task":"...","workspace":"...","resumable":false,"agents":[{"agent":"actor",...}]}
{"event":"opened","at":"...","agent":"actor","backend":"claude","provider":"local","session":"0a1b2c3d-...","name":"actor-claude@local-0a1b2c3d-...","where":"sessions/actor-claude@local-0a1b2c3d-..."}
{"event":"ended","at":"...","how":"done"}
```

`hmz trace collect` reads the run it is tracing, which is why `rlar` traces as `actor` and
`reviewer` without being told anything.

Under `sessions/` is a directory per session, named the way the `opened` line names it — whose
session it was, what took its turns, which account they ran as and what the backend called it —
holding a link to each file that backend logged it to. Links for reading: humanize itself reads
and writes every log where the backend keeps it.

Note `how`: `done`, `failed`, or `stopped`. A run you ended with esc is written down as one you
ended.

`/cycles` is the same list at the prompt: every run of this directory, newest first. Enter on one
offers to collect a trace of it and to say where it is — and, where its flow says a run can be
picked up, to carry that one on.

## Step 5 — narrow it

```sh
hmz trace collect --cycle 20260809T0144              # one run of this workspace, by name
hmz trace collect --start "3 days ago"               # recent history only
hmz trace collect --end "yesterday 18:00"
hmz trace collect --session 0a1b2c3d                 # one session, wherever it ran
hmz trace collect ~/code/other                       # another workspace
hmz trace collect --output /tmp/before.json          # somewhere of your own
```

- Naming **sessions alone** collects them wherever they were recorded.
- Adding a **workspace** keeps only the named sessions recorded there.
- Naming **neither** collects the current directory.

`--cycle` takes a run's directory name or a leading part of it, and settles which run the trace is
**of**: where it is written, and whose agents its processes are named after. What is read is still
the workspace's sessions, so cut those down with `--session`, `--start` and `--end`.

A session is named by its whole id, by the key the trace shows it under, or by a leading part of
either — and the sub-agents it started come with it.

`--start` / `--end` take anything [dateparser](https://dateparser.readthedocs.io/) understands, so
`"3 days ago"`, `"yesterday 18:00"` and `"2026-08-01"` all work.

## Step 6 — a trace of something humanize never drove

This is the part people miss. Run `claude` on its own, then:

```sh
hmz trace collect
```

It reads the backends' own home directories, so yesterday's session is a trace away. That is also
why a trace is not a second copy of anything: humanize keeps the ids, and the backend keeps the
words.

In a directory no flow has ever run in there is no run to put the trace with, so it goes where
that directory's runs would be kept — `~/.humanize/cycles/<workspace>/` — and the line names no
run.

## Step 7 — from Python

```python
from hmz.tracing import collect

document = collect(
    "~/code/myproject",
    sessions=["0a1b2c3d"],
    agents={"actor": actor.opened, "reviewer": reviewer.opened},
    output="trace.json",       # omit and nothing is written
    start="3 days ago",
)
```

Returns the document. Writing a file only when `output` is given is the one thing the library does
that the command line does not let you skip.

## While it is still running

A trace is for after. For the same shape live, [`/status`](/features/status) — who is working,
every handover, and what each model has cost.

## What you now know

- `hmz trace collect` needs nothing set up and works on any session the backends logged.
- A trace lands with the run it is a trace of, and `--output` is how it goes anywhere else.
- A cycle is a directory, and it is what turns "a configuration" into "the reviewer".
- Perfetto is the viewer; the slices carry the prompts and the tool output.

## Next

You have driven the flows humanize offers. Now [write one](/guide/tutorial-first-flow).

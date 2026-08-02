# 5 · Read the run back

**Ten minutes.** Turn everything the agents left behind into one timeline, and find the four
minutes they wasted.

::: tip Before you start
Any of the runs from tutorials 1–4. This works on sessions no flow ever drove, too.
:::

## Step 1 — collect

In the project you have been running in:

```sh
hmz collect
```

```console
.humanize/20260809T014455Z.trace.json: 3 sessions, 412 slices
```

The name is the UTC moment it was collected, so collecting twice keeps both traces rather than
writing over the first.

![hmz collect writing a trace, and finding nothing inside a one-minute window](/demo/collect.gif)

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

## Step 4 — why your two agents are named

The backends log a session under an id and **never say whose it was**. So by default an agent in
a trace is one configuration — a backend at a model at an effort — and an actor and a reviewer at
the same model would read as one agent.

Every run of a flow writes a **cycle** that fixes this:

```sh
ls ~/.humanize/cycles/*/
```

```console
20260809T014455Z-a4a089.jsonl
```

```sh
head -3 ~/.humanize/cycles/*/20260809T014455Z-a4a089.jsonl
```

```console
{"event":"began","at":"...","flow":"official/rlar","task":"...","agents":[{"agent":"actor",...}]}
{"event":"opened","at":"...","agent":"actor","backend":"claude","session":"0a1b2c3d-..."}
{"event":"ended","at":"...","how":"done"}
```

`hmz collect` reads the last cycle in the workspace, which is why `rlar` traces as `actor` and
`reviewer` without being told anything.

Note `how`: `done`, `failed`, or `stopped`. A run you ended with esc is written down as one you
ended.

## Step 5 — narrow it

```sh
hmz collect --start "3 days ago"               # recent history only
hmz collect --end "yesterday 18:00"
hmz collect --session 0a1b2c3d                 # one session, wherever it ran
hmz collect ~/code/other                       # another workspace
hmz collect --output /tmp/before.json
```

- Naming **sessions alone** collects them wherever they were recorded.
- Adding a **workspace** keeps only the named sessions recorded there.
- Naming **neither** collects the current directory.

A session is named by its whole id, by the key the trace shows it under, or by a leading part of
either — and the sub-agents it started come with it.

`--start` / `--end` take anything [dateparser](https://dateparser.readthedocs.io/) understands, so
`"3 days ago"`, `"yesterday 18:00"` and `"2026-08-01"` all work.

## Step 6 — a trace of something humanize never drove

This is the part people miss. Run `claude` on its own, then:

```sh
hmz collect
```

It reads the backends' own home directories, so yesterday's session is a trace away. That is also
why a trace is not a second copy of anything: humanize keeps the ids, and the backend keeps the
words.

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

- `hmz collect` needs nothing set up and works on any session the backends logged.
- A cycle is what turns "a configuration" into "the reviewer".
- Perfetto is the viewer; the slices carry the prompts and the tool output.

## Next

You have driven the flows humanize offers. Now [write one](/guide/tutorial-first-flow).

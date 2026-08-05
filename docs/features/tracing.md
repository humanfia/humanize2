# Tracing

A long run is thousands of tool calls across several agents. `hmz trace collect` turns what they
left behind into one timeline you can actually look at.

```sh
hmz trace collect
```

```console
~/.humanize/cycles/-home-you-code/20260809T014455.212Z-9f21ab/traces/20260809T014455Z.trace.json of 20260809T014455.212Z-9f21ab: 3 sessions, 412 slices
```

Drag that file into [ui.perfetto.dev](https://ui.perfetto.dev), or load it in `chrome://tracing`.
It is a Chrome JSON trace, so anything that reads one will do.

It works **whether or not a flow drove them** — a trace of yesterday's `claude` session is one
command away.

It lands **with the run it is a trace of** — `traces/<datetime>.trace.json` inside that run's own
directory, where the run's record and the links to its sessions already are — rather than in
whatever directory you happened to be standing in. What it prints is that path, then which run it
is a trace of, then what went into it — and the programs as well, for a run that was
[profiled](#profiling-a-run).

![hmz trace collect writing into the last run's own directory: the path, the run it is of, and 2
sessions, 17 slices, 3 programs](/demo/collect.png)

In the interface the same thing is a row of
[`/cycles`](/features/resuming#carrying-an-older-one-on): pick a run, press enter, collect it.

## What you get

```
process   agent          builder · 4 sessions
  track     main ──────────────▶ ▓▓▓ ▓ ▓▓▓▓▓▓ ▓▓  ▓▓▓▓▓  ▓ ▓▓▓▓
  track     subagent · explore ▶      ▓▓▓▓▓▓▓▓▓▓▓
process   agent          reviewer · 2 sessions
  track     main ──────────────▶            ▓▓▓▓        ▓▓▓▓
```

A process is an agent and everything it drove; a track is one row of that agent's sessions.
For a [profiled](#profiling-a-run) run the same two words carry over to the programs the agents
ran: a process is a program, a track is one of its threads.

| In the trace | Is |
| --- | --- |
| a **process** | one [agent](/guide/concepts#agent), called `<agent> · <n> sessions` — or, for a profiled run, one program it ran, called `<program> · <pid>` |
| a **track** | one row of that agent's [sessions](/guide/concepts#session): `main` for the ones somebody started, `subagent` for what a turn reached for, named after the kind where a row is all of one kind. Sessions of one agent that never run at the same time share a track; root sessions and sub-agents stay apart. |
| a **slice** | one action — a tool call, a message, or waiting for reasoning |

Click a slice and its arguments are there: the prompt, the reasoning, the tool input, the tool
output. As much as the backend wrote down.

## Why two agents do not read as one

The backends log a session under an id and **never say whose it was**. By default an agent in a
trace is one configuration — a backend at a model at an effort — plus every sub-agent it started.
So a Ralph loop of a hundred one-shot sessions reads as one agent, which is right; but an actor
and a reviewer at the same model and effort would read as one agent, which is not.

That is what a [cycle](#what-a-run-writes-down) is for. `hmz trace collect` reads the run it is
tracing, so `official/rlar` traces as `actor` and `reviewer` without being told anything.

Driving agents by hand, say so yourself:

```python
collect(agents={a.id: a.opened for a in (actor, reviewer)})
```

Sessions nobody claims are read as the configuration they ran at.

## What a run writes down

Every run of a flow is one **cycle**, which is a directory:

```
~/.humanize/cycles/<workspace>/<datetime>-<hex>/
    cycle.jsonl                     what happened, a line at a time
    state.json                      what a flow that can be picked up again left behind
    profile.jsonl                   the programs it ran, for a run that was profiled
    sessions/<session>/…            a link per file the backend logged that session to
    traces/<datetime>.trace.json    what was gathered of it afterwards
```

Not all of it every time: `state.json` is there for a flow that
[can be picked up](/reference/flows#a-flow-that-can-be-picked-up), `profile.jsonl` for a
directory that asked to be [profiled](#profiling-a-run), and `traces/` from the first time a
trace is collected.

![ls of one run's directory: cycle.jsonl, profile.jsonl, sessions and state.json, and no traces
yet](/demo/run.png)

`cycle.jsonl` is JSON lines, appended and flushed as it goes — so a run that died is a run whose
cycle still says what it got to.

| `event` | Written | Carries |
| --- | --- | --- |
| `began` | when the flow starts | `flow`, `task`, `workspace`, whether the flow can be picked up again and which run this one was picked up from, and one entry per agent with its id, backend, model, effort, account, what it may do, whether it could use goals and whether it was the person at the prompt |
| `opened` | each time an agent opens a session | `agent`, `backend`, `provider`, `session`, the name the run gives it and where inside the cycle its links are |
| `ended` | when the flow stops | `how`: `done`, `failed`, or `stopped` |

Each session's own logs are pointed at from `sessions/<name>/`, under a name that says whose
session it was, what took its turns, which account they ran as and what the backend called it —
`builder-claude@work-0a1b2c3d`, and `@local` where the turns ran as the account this machine is
already signed into. Links for reading: humanize reads and writes every log where the backend
keeps it. They are made again when the run ends, because a sub-agent's transcript is written
whenever that sub-agent ran, and a filesystem that will not make one is a run without links
rather than a run that stops.

![one run's sessions/ directory, its name saying agent, CLI and account, holding a symlink to Claude
Code's own log](/demo/run-linked.png)

`/cycles` is the same list at the prompt — every run of this directory, newest first, with a
mark on the ones whose flow says it can be picked up. Enter opens what there is to do with the
run under the cursor: carry on from here, collect a trace, where it is. The mark and that first
row are one question, and it is asked of the **flow** as it stands rather than of the run: a flow
marked `resumable=True` after a run of it has that older run marked and offered too, and one that
has since dropped the mark has neither, whatever the run wrote down at the time. Carrying one on
is [picking a run up](/features/resuming); collecting a trace is offered for every run, whatever
its flow says.

**It is not a transcript.** The backend's own log is the turn-by-turn record; a cycle is the
*shape* of the run — enough to gather a trace afterwards out of the ids alone.

A cycle covers one run and is never reopened. Carrying a flow on is another run, with sessions
of its own, written into a cycle that says which run it was picked up from.

An agent [stopped by hand](/features/stopping) makes the run `stopped` rather than `failed`,
whatever the turn under way made of it.

```python
from hmz.cycle import cycles, opened

for cycle in cycles():                 # this workspace, oldest first
    print(cycle, opened(cycle))        # {"actor": ["0a1b…"], "reviewer": [...]}
```

## Narrowing it

```sh
hmz trace collect                                    # this workspace, all of its history
hmz trace collect ~/code/other                       # another workspace
hmz trace collect --cycle 20260809T0144              # filed with that run, and named by it
hmz trace collect --session 0a1b2c3d,5f6e            # two sessions, wherever they ran
hmz trace collect ~/code/other --session 0a1b2c3d    # that session, only if it ran there
hmz trace collect --start "3 days ago"               # recent history only
hmz trace collect --end "yesterday 18:00" --output /tmp/before.json
```

- Naming **sessions alone** collects them wherever they were recorded.
- Adding a **workspace** keeps only the named sessions recorded there.
- Naming **neither** collects the current working directory.

A session is named by its whole id, by the key the trace shows it under, or by a leading part of
either — and the sub-agents it started come with it. `--start` and `--end` take anything
[dateparser](https://dateparser.readthedocs.io/) understands.

`--cycle` takes a run's directory name or a leading part of it, and settles which run the trace
is **of**: where it is written, whose agents its processes are named after, and whose profile is
drawn beside them. What is read is still the workspace's sessions, so cut those with `--session`,
`--start` and `--end`. Without a `--cycle` that is the last run of the workspace; for a workspace
nothing has been run in, the trace goes where that workspace's runs would be kept. `--output`
wins over both, a trace being also a thing to attach to an issue.

The default output is named after the UTC moment it was collected, so collecting twice keeps both.

![hmz trace collect three times: the last run of this directory, one named with --cycle, and one
sent elsewhere with --output](/demo/collect.gif)

## Profiling a run

An agent's turn is mostly other programs — the tests, the build, the greps — and none of them
is in a backend's log, which records the tool call rather than the process. So a directory may
ask for its runs to be **profiled** as well as traced: the `profile` row on the second page of
[`/settings`](/features/settings), which is the page for this directory.

![the /settings page for this directory, with the profile row switched on beside workspace, flow and
forget](/demo/profiling.png)

While a flow runs there, every process underneath it is sampled — the agent CLIs themselves, and
the tests, the builds and the greps their turns start — as each is seen: what it was, what
started it, how long it took, into `profile.jsonl` in that run's cycle. Collecting the run draws
them in the same document as its sessions, at the same scale, so *what was this run doing at
09:41* has one answer:

```
process   agent          builder · 4 sessions
  track     main ──────▶ ▓▓▓ ▓ ▓▓▓▓▓▓ ▓▓  ▓▓▓▓▓  ▓ ▓▓▓▓▓▓▓▓▓▓
process   program        pytest · 41207
  track     main ──────▶       ▓▓▓▓▓▓▓▓▓▓
```

Off until a directory asks for it, since it is a sampler running for as long as the flow does,
and what a run costs in processes is a question about the project rather than about the machine:
a repository whose tests take an hour is a different question from one whose tests take a minute.
What it costs is a thread reading the process tree twenty times a second, and two lines of JSON
per program — one when it is first seen, one when it has gone.

Sampled rather than intercepted: nothing goes between an agent and what it runs, a program that
lived for thirty milliseconds may be missed, and a machine whose processes cannot be read is a
run with no profile rather than a run that stops.

The switch is read where a run starts, so turning it on holds from the next run rather than the
one under way, and a run `hmz exec` starts in that directory is profiled too — it says nothing
about what runs, only about whether what runs is watched. From Python it is one property and one
call:

```python
from hmz.settings import Settings

Settings().profiling            # whether a run in this directory is profiled
Settings().profiles(on=True)    # written down for it, from now on
```

## Where it reads from

The backends' own home directories, which humanize only ever reads:

| Backend | Variable | Default |
| --- | --- | --- |
| Claude Code | `CLAUDE_CONFIG_DIR` | `~/.claude` |
| Codex | `CODEX_HOME` | `~/.codex` |
| DeepSeek Harness | `DSH_HOME` | `~/.dsh` |
| Kimi Code | `KIMI_CODE_HOME` | `~/.kimi-code` |

Those four, and no others. **opencode, mimocode and Antigravity keep a session in a database
rather than in a log file, and nothing here reads pi's, Grok Build's or Qwen Code's own logs
yet**, so there is nothing to gather for those: a run of theirs is watched as it happens rather
than collected after.

A home that does not exist is skipped rather than being an error, and so is a backend humanize
has no reader for — its home being there changes nothing.

A flow that ran on a [machine of its own](/features/containers) worked in a mirror rather than in
this directory, so find its trajectories with `--session` rather than by workspace.

## Watching instead

A trace is for after. While a run is going, [`/status`](/features/status) shows the same shape
live — and it is read off the turns going past, never by asking the flow.

## See also

- [Tutorial: read the run back](/guide/tutorial-trace)
- [Picking a run up](/features/resuming) — carrying one of these runs on where it stopped
- [Tracing reference](/reference/tracing)
- [CLI › `hmz trace`](/reference/cli#hmz-trace)

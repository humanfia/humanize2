# Tracing

`hmz trace collect` turns everything a run's agents left behind into one timeline. Reach for it
after a long run, when you want to see what each agent did and where the time went. It works on
any session the backends logged, whether or not a flow drove it.

## Try it

In the project you have been running in, run:

```sh
hmz trace collect
```

```console
~/.humanize/epics/-home-you-code-myproject/20260809T014455.212Z-9f21ab/traces/20260809T014455Z.trace.json of 20260809T014455.212Z-9f21ab: 3 sessions, 412 slices
```

The line prints the file, then the run it is a trace of, then what went into it. The file lands
in `traces/` inside that run's own directory, next to the run's record and the links to its
sessions.

![hmz trace collect writing into the last run's own directory: the path, the run it is of, and
1 session, 10 slices, 3 programs](/demo/collect.png)

Now open it. Go to [ui.perfetto.dev](https://ui.perfetto.dev) and drag the file in. Nothing is
uploaded; Perfetto opens it in the browser. `chrome://tracing` works too, as does anything that
reads a Chrome JSON trace.

## What you get

```
process   agent          builder · 4 sessions
  track     main ──────────────▶ ▓▓▓ ▓ ▓▓▓▓▓▓ ▓▓  ▓▓▓▓▓  ▓ ▓▓▓▓
  track     subagent · explore ▶      ▓▓▓▓▓▓▓▓▓▓▓
process   agent          reviewer · 2 sessions
  track     main ──────────────▶            ▓▓▓▓        ▓▓▓▓
```

| In the trace | Is |
| --- | --- |
| a **process** | one [agent](/user/concepts#agent) and everything it drove, called `<agent> · <n> sessions` — or, for a [profiled](#profiling-a-run) run, one program it ran, called `<program> · <pid>` |
| a **track** | one row of that agent's [sessions](/user/concepts#session): `main` for the ones somebody started, `subagent` for what a turn reached for, named after the kind where a row is all of one kind. Sessions of one agent that never run at the same time share a track; root sessions and sub-agents stay apart. For a profiled run, one of a program's threads. |
| a **slice** | one action — a tool call, a message, or waiting for reasoning |

Click a slice and its arguments are there: the prompt, the reasoning, the tool input, the tool
output. As much as the backend wrote down.

On your first trace, look for:

- **A wide gap on every track.** Nobody was working. That is the flow sleeping, committing, or
  reading what the last turn wrote.
- **One very long slice.** A single tool call that took minutes — usually a test suite,
  sometimes a `find` over the whole disk.
- **A reviewer whose tracks all start after the actor's stop.** That is the loop working as
  designed. If they overlap, it is not.
- **Two hundred short tracks on one process.** A Ralph loop, one session per turn.

The first two are guesses until the run is [profiled](#profiling-a-run).

## Why two agents do not read as one

The backends log a session under an id and **never say whose it was**. By default an agent in a
trace is one configuration: a backend at a model at an effort, plus every sub-agent it started.
A Ralph loop of a hundred one-shot sessions reads as one agent, which is right. An actor and a
reviewer at the same model and effort would read as one agent, which is not.

That is what an [epic](#what-a-run-writes-down) is for. `hmz trace collect` reads the run it is
tracing, so `official/rlar` traces as `actor` and `reviewer` without being told anything.

Driving agents by hand from Python, say so yourself:

```python
collect(agents={a.id: a.opened for a in (actor, reviewer)})
```

Sessions nobody claims are read as the configuration they ran at.

## What a run writes down

Every run of a flow is one **epic**, which is a directory:

```
~/.humanize/epics/<workspace>/<datetime>-<hex>/
    epic.jsonl                      what happened, a line at a time
    epic.<flow>_<hex>.jsonl         the same, for one flow the run called
    state.json                      what a flow that can be picked up again left behind
    profile.jsonl                   the programs it ran, for a run that was profiled
    sessions/<session>/…            a link per file the backend logged that session to
    traces/<datetime>.trace.json    what was gathered of it afterwards
```

Not all of it every time: `state.json` is there for a flow that [can be picked
up](/reference/flows#a-flow-that-can-be-picked-up), `profile.jsonl` for a directory that asked
to be [profiled](#profiling-a-run), `traces/` from the first time a trace is collected, and a
`epic.<flow>_<hex>.jsonl` for each flow the run [called](#what-a-called-flow-writes-down).

Find the run that just finished and list it:

```sh
run=$(ls -dt ~/.humanize/epics/*/*/ | head -1)   # the one that just finished
ls "$run"
```

```console
epic.jsonl  sessions  traces
```

![ls of one run's directory: epic.jsonl, profile.jsonl, sessions and state.json, and no traces
yet](/demo/run.png)

`epic.jsonl` is JSON lines, appended and flushed as it goes. A run that died is a run whose
epic still says what it got to:

```sh
head -3 "$run"epic.jsonl
```

```console
{"event":"began","at":"...","flow":"official/rlar","task":"...","workspace":"...","resumable":false,"agents":[{"agent":"actor",...}]}
{"event":"opened","at":"...","agent":"actor","backend":"claude","provider":"local","session":"0a1b2c3d-...","name":"actor-claude@local-0a1b2c3d-...","where":"sessions/actor-claude@local-0a1b2c3d-..."}
{"event":"ended","at":"...","how":"done"}
```

| `event` | Written | Carries |
| --- | --- | --- |
| `began` | when the flow starts | `flow`, `task`, `workspace`, whether the flow can be picked up again and which run this one was picked up from, and one entry per agent with its id, backend, model, effort, account, what it may do, whether it could use goals and whether it was the person at the prompt |
| `opened` | each time an agent opens a session | `agent`, `backend`, `provider`, `session`, the name the run gives it and where inside the epic its links are |
| `called` | when the flow calls another flow | `flow`, `task`, and the `epic` — the record that call was written to |
| `returned` | when that call returns, however it ended | `flow` and the same `epic` |
| `ended` | when the flow stops | `how`: `done`, `failed`, or `stopped` |

Each session's own logs are pointed at from `sessions/<name>/`, under a name that says whose
session it was, what took its turns, which account they ran as and what the backend called it:
`builder-claude@work-0a1b2c3d`, and `@local` where the turns ran as the account this machine is
already signed into. Links for reading: humanize reads and writes every log where the backend
keeps it. They are made again when the run ends, because a sub-agent's transcript is written
whenever that sub-agent ran, and a filesystem that will not make one is a run without links
rather than a run that stops.

![one run's sessions/ directory, its name saying agent, CLI and account, holding a symlink to
Claude Code's own log](/demo/run-linked.png)

`/epics` is the same list at the prompt: every run of this directory, newest first, with a mark
on the ones whose flow says it can be picked up. Enter opens what there is to do with the run
under the cursor — carry on from here, collect a trace, where it is. Collecting a trace is
offered for every run, whatever its flow says; the rest is [picking a run
up](/user/resuming#carrying-an-older-one-on).

**It is not a transcript.** The backend's own log is the turn-by-turn record. An epic is the
*shape* of the run: enough to gather a trace afterwards out of the ids alone. It covers one run
and is never reopened, so carrying a flow on is another run, with sessions of its own, written
into an epic that says which run it was picked up from.

An agent [stopped by hand](/user/stopping) makes the run `stopped` rather than `failed`,
whatever the turn under way made of it. A run you stopped by hand is written down as `stopped`
too.

```python
from hmz.epic import epics, opened

for epic in epics():                   # this workspace, oldest first
    print(epic, opened(epic))          # {"actor": ["0a1b…"], "reviewer": [...]}
```

### What a called flow writes down

A flow can [call another](/reference/flows#a-flow-that-calls-another-flow), and a called flow
opens sessions and calls flows of its own. Each call is written to a record of its own beside
the run's, named for the flow and for that call of it:

```sh
ls "$run"epic.*.jsonl
```

```console
epic.jsonl  epic.gen-plan_0a1b2c.jsonl
```

The run's own record says what it called and which file to read it in:

```console
{"event":"called","at":"...","flow":"official/humanize1:gen-plan","task":"...","epic":"epic.official-humanize1-gen-plan_0a1b2c.jsonl"}
{"event":"returned","at":"...","flow":"official/humanize1:gen-plan","epic":"epic.official-humanize1-gen-plan_0a1b2c.jsonl"}
```

A called flow's own record holds the same events, its `began` says which record is `under` it,
and its `ended` says how the call ended rather than how the run did. Still one run and still
one directory: a called flow is part of the run that called it.

## Which run, and what else there is to trace

```sh
hmz trace collect                                    # the last run of this workspace
hmz trace collect ~/code/other                       # the last run of another workspace
hmz trace collect --epic 20260809T0144               # that run of it, by name
hmz trace collect --start "3 days ago"               # and only what it did since
hmz trace collect --end "yesterday 18:00" --output /tmp/before.json
```

A trace is **of a run**. It holds the sessions that run opened and no others, by the ids the
run wrote down as it went, so a directory run in fifty times has fifty traces to collect and
none of them holds another's work. A run that opened nothing is a trace of nothing. It goes by
id rather than by directory, so a flow that ran on a [machine of its
own](/user/remote-execution) is in its own trace too, though the backend logged it under a
mirror this directory has never heard of.

::: details `0 sessions, 0 slices`
Three usual reasons. You are in a different directory from the one the run happened in. The
backend was opencode or mimocode, which keep sessions in a database and have nothing to
gather. Or the run being traced died before it opened a session. See
[Troubleshooting](/user/troubleshooting#_0-sessions-0-slices).
:::

A directory also holds sessions no run of a flow ever opened: your own afternoon at a coding
agent. Ask for those outright:

```sh
hmz trace collect --all                              # every session of this workspace
hmz trace collect --session 0a1b2c3d,5f6e            # two sessions, wherever they ran
hmz trace collect ~/code/other --session 0a1b2c3d    # that session, only if it ran there
```

Neither is a trace of any run, so neither is filed inside one. They go beside that workspace's
runs, in `~/.humanize/epics/<workspace>/`. Asking for `--epic` with `--all` or `--session` is
a usage error rather than one of them quietly winning. Neither is offered in the interface,
because `/epics` is a list of runs with nothing to hang them on.

A session is named by its whole id, by the key the trace shows it under, or by a leading part
of either, and the sub-agents it started come with it. `--start` and `--end` take anything
[dateparser](https://dateparser.readthedocs.io/) understands. `--output` wins over where any of
these would otherwise land; a trace is also a thing to attach to an issue. The default output
is named after the UTC moment it was collected, so collecting twice keeps both.

![hmz trace collect three times: the last run of this directory, one named with --epic, and
one sent elsewhere with --output](/demo/collect.gif)

From Python the same choices are one call:

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

It returns the document. Writing a file only when `output` is given is the one thing the
library does that the command line does not let you skip.

## Profiling a run

An agent's turn is mostly other programs: the tests, the build, the greps. None of them is in a
backend's log, which records the tool call rather than the process. So a directory may ask for
its runs to be **profiled** as well as traced. The switch is the `profile` row on the second
page of [`/settings`](/user/settings), which is the page for this directory.

![the /settings page for this directory, with the profile row switched on beside workspace,
flow and forget](/demo/profiling.png)

While a flow runs there, every process underneath it is sampled as each is seen: the agent CLIs
themselves, and the tests, the builds and the greps their turns start. Each sample says what it
was, what started it, and how long it took, into `profile.jsonl` in that run's epic.
Collecting the run draws them in the same document as its sessions, at the same scale, so *what
was this run doing at 09:41* has one answer. A trace of a profiled run counts them: `3
sessions, 412 slices, 61 programs`.

```
process   agent          builder · 4 sessions
  track     main ──────▶ ▓▓▓ ▓ ▓▓▓▓▓▓ ▓▓  ▓▓▓▓▓  ▓ ▓▓▓▓▓▓▓▓▓▓
process   program        pytest · 41207
  track     main ──────▶       ▓▓▓▓▓▓▓▓▓▓
```

Off until a directory asks for it: it is a sampler running for as long as the flow does, and a
repository whose tests take an hour is a different question from one whose tests take a minute.
What it costs is a thread reading the process tree twenty times a second, and two lines of JSON
per program — one when it is first seen, one when it has gone.

Sampled rather than intercepted: nothing goes between an agent and what it runs, a program that
lived for thirty milliseconds may be missed, and a machine whose processes cannot be read is a
run with no profile rather than a run that stops.

The switch is read where a run starts, so turning it on holds from the next run rather than the
one under way. A run `hmz exec` starts in that directory is profiled too: the switch says
nothing about what runs, only about whether what runs is watched. From Python it is one
property and one call:

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
rather than in a log file, and nothing here reads pi's, Grok Build's, Qwen Code's or ZCode's
own logs yet.** So there is nothing to gather for those: a run of theirs is watched as it
happens rather than collected after.

A home that does not exist is skipped rather than being an error. So is a backend humanize has
no reader for; its home being there changes nothing.

A flow that ran on a [machine of its own](/user/containers) worked in a mirror rather than in
this directory. Find its trajectories with `--session` rather than by workspace.

## Watching instead

A trace is for after. While a run is going, [`/status`](/user/status) shows the same shape
live. It is read off the turns going past, never by asking the flow.

## See also

- [Picking a run up](/user/resuming) — carrying one of these runs on where it stopped
- [Tracing reference](/reference/tracing)
- [CLI › `hmz trace`](/reference/cli#hmz-trace)
- [Troubleshooting](/user/troubleshooting#_0-sessions-0-slices)

# Tracing

A long run is thousands of tool calls across several agents. `hmz trace collect` turns what they
left behind into one timeline you can actually look at.

It works whether or not a [flow](/reference/flows.md) drove them — a trace of yesterday's `claude` session
is one command away.

## Collecting

```sh
hmz trace collect
```

```console
~/.humanize/cycles/-home-you-code/20260809T014455.212Z-9f21ab/traces/20260809T014455Z.trace.json of 20260809T014455.212Z-9f21ab: 3 sessions, 412 slices
```

Drag that file into [ui.perfetto.dev](https://ui.perfetto.dev), or open `chrome://tracing` and
load it. It is a Chrome JSON trace, so anything that reads one will do.

A trace goes with the run it is a trace of. A [cycle](#cycles) already holds what happened, a
link to every log each session was written to, and whatever the flow left behind, so the trace
belongs there rather than in whatever directory you happened to be standing in. The default
name is the UTC moment it was collected, so collecting twice keeps both traces rather than
writing over the first; `--output` puts it somewhere else, its directory created if it is not
there.

The same thing is a row of `/cycles` in the interface: pick the run, press enter, and collect
it there.

Full syntax in the [CLI reference](/reference/cli.md#hmz-trace).

## Reading the trace

```
process   agent          builder · claude-opus-4-8 · high
  track     session ──▶ ▓▓▓ ▓ ▓▓▓▓▓▓ ▓▓  ▓▓▓▓▓  ▓ ▓▓▓▓▓▓▓▓▓▓
  track     sub-agent ─▶      ▓▓▓▓▓▓▓▓▓▓▓
process   agent          reviewer · claude-opus-4-8 · high
  track     session ──▶            ▓▓▓▓        ▓▓▓▓        ▓▓▓▓
```

| In the trace | Is |
| --- | --- |
| a **process** | one [agent](/guide/concepts.md#agent) and everything it drove — or, for a [profiled](#profiling-a-run) run, one program it ran |
| a **track** | one sub-agent of that agent, named after what kind it was — or one thread of that program. Sessions of one agent that never run at the same time share a track; root sessions and sub-agents stay apart. |
| a **slice** | one action — a tool call, a message, or waiting for reasoning |

Click a slice and its arguments are there: the prompt, the reasoning, the tool input, the tool
output. As much as the backend wrote down.

The document's `otherData` says what was asked for and what was collected — the workspace, the
sessions named, the agents and backends found, how many sessions, slices and tracks there are,
and the first and last moment in it.

## What counts as one agent

An **agent** is one configuration — a backend at a model at an effort — together with every
sub-agent it started. So a Ralph loop of a hundred one-shot sessions reads as one agent rather
than a hundred, and a sub-agent belongs to the agent of the session that started it, whatever it
ran at itself.

That default is a guess, and it has a blind spot: two agents at the same configuration are
indistinguishable, because the backends log a session under an id and never say whose it was.
An actor and its reviewer at one model and one effort would read as one agent.

A run that drove the sessions itself knows better. `hmz trace collect` reads that from the run
it is tracing, so `rlar` traces as `actor` and `reviewer` without being told anything. Driving
agents by hand, say so yourself:

```python
collect(agents={a.id: a.opened for a in (actor, reviewer)})
```

Sessions nobody claims are read as the configuration they ran at.

## Cycles

Every run of a flow is one **cycle**, written as it happens, and a cycle is a directory:

```
~/.humanize/cycles/<workspace>/<datetime>-<hex>/
    cycle.jsonl                     what happened, a line at a time
    state.json                      what a flow that can be picked up again left behind
    profile.jsonl                   the programs it ran, for a run that was profiled
    sessions/<session>/…            a link per file the backend logged that session to
    traces/<datetime>.trace.json    what was gathered of it afterwards
```

`<workspace>` is the absolute path with everything that is not a letter or a digit flattened to
`-`, the way the backends flatten a workspace into the folder they log it under. `<hex>` is six
characters, because two flows may be started in one millisecond and neither is the other's run.

`cycle.jsonl` is JSON lines, one line per thing that happened to the run, appended and flushed
as it goes — a run that died is a run whose cycle still says what it got to.

| `event` | Written | Carries |
| --- | --- | --- |
| `began` | when the flow starts | `flow`, `task`, `workspace`, whether the flow is `resumable`, which run it was `picked_up` from, and one entry per agent with its `agent` id, `backend`, `model`, `effort`, `permission`, `provider`, `goals` and whether it was the `person` at the prompt |
| `opened` | each time an agent opens a session | `agent`, `backend`, `provider`, `session`, the `name` the run gives it and `where` its links are |
| `ended` | when the flow stops | `how`: `done`, `failed`, or `stopped` |

`sessions/<session>/` is a link per file that session was logged to, named for whose session it
was, what took its turns, which account they ran as and what the backend called it —
`builder-claude@work-0a1b2c3d`. They are there to be read: humanize itself reads and writes
every log where the backend keeps it.

**It is not a transcript.** The backend's own log is the turn-by-turn record, and a cycle is not
a second copy of it. What is kept here is the shape of the run — enough to gather a trace
afterwards out of the ids alone.

A cycle covers one run. It closes when the flow finishes, fails or is interrupted, and a closed
cycle is never reopened: running the flow again is another run, with sessions of its own, and so
another cycle.

An agent stopped by hand makes the run `stopped` rather than `failed`, whatever the turn under
way made of it — so a run you ended is written down as one you ended.

```python
from hmz.cycle import cycles, opened

for cycle in cycles():                 # this workspace, oldest first
    print(cycle, opened(cycle))        # {"actor": ["0a1b…", "5f6e…"], "reviewer": [...]}
```

## Profiling a run

An agent's turn is mostly other programs. It runs the tests, it builds the thing, it greps the
repository — and none of that is in a backend's log, which records the tool call rather than
the process. So a workspace may ask for its runs to be **profiled** as well as traced, on the
second page of `/settings`:

```
profile   on   profile the programs a run here starts, into its own trace
```

While the flow runs, the programs underneath it are sampled — what each was, what started it,
and how long it took — into `profile.jsonl` in that run's own cycle. Collecting the run puts
them in the same document as its sessions, drawn the same way: a process is a program and a
track is one of its threads, exactly as a process is an agent and a track is one of its
sub-agents.

That is the point of one document rather than two. An agent's timeline and a profiler's
timeline at one scale means *what was this run doing at 09:41* has one answer:

```
process   agent          builder · claude-opus-4-8 · high
  track     main ──────▶ ▓▓▓ ▓ ▓▓▓▓▓▓ ▓▓  ▓▓▓▓▓  ▓ ▓▓▓▓▓▓▓▓▓▓
process   program        pytest · 41207
  track     main ──────▶       ▓▓▓▓▓▓▓▓▓▓
```

It is sampled rather than intercepted: nothing goes between an agent and what it runs. A
program that lived for thirty milliseconds may be missed, and a machine whose processes cannot
be read is a run with no profile rather than a run that stops.

## Where the trajectories come from

The backends' own home directories, which humanize only reads:

| Backend | Environment variable | Default |
| --- | --- | --- |
| Claude Code | `CLAUDE_CONFIG_DIR` | `~/.claude` |
| Codex | `CODEX_HOME` | `~/.codex` |
| DeepSeek Harness | `DSH_HOME` | `~/.dsh` |
| Kimi Code | `KIMI_CODE_HOME` | `~/.kimi-code` |

Those four, and no others. opencode, mimocode and Antigravity keep a session in a database
rather than in a log file, and nothing here reads pi's, Grok Build's or Qwen Code's own logs
yet, so there is nothing to gather for those: a run of theirs is watched as it happens rather
than collected after.

A home that does not exist is skipped rather than being an error, so collecting on a machine
with only one backend installed works — and so is a backend humanize has no reader for, whose
home being there changes nothing.

## Narrowing what is collected

A workspace and a set of sessions narrow the trace together:

```sh
hmz trace collect                                    # this workspace, all of its history
hmz trace collect ~/code/other                       # another workspace
hmz trace collect --cycle 20260809T0144              # one run of this workspace, by name
hmz trace collect --session 0a1b2c3d,5f6e            # two sessions, wherever they ran
hmz trace collect ~/code/other --session 0a1b2c3d    # that session, only if it ran there
hmz trace collect --start "3 days ago"               # recent history only
hmz trace collect --end "yesterday 18:00"
```

- **Naming sessions alone** collects them wherever they were recorded.
- **Adding a workspace** keeps only the named sessions recorded there.
- **Naming neither** collects the current working directory.

A session is named by its whole id, by the key the trace shows it under, or by a leading part of
either — and the sub-agents it started come with it.

`--start` and `--end` take anything [dateparser](https://dateparser.readthedocs.io/) understands
and cut records outside the range. A time that cannot be read is a usage error.

**A flow that ran on a [machine of its own](/reference/machines.md) worked in a mirror rather than in this
directory**, so its trajectories are found by `--session` rather than by workspace.

## From Python

```python
from hmz.tracing import collect

document = collect(
    "~/code/myproject",
    sessions=["0a1b2c3d"],          # a string or an iterable of ids
    agents={"actor": [...]},        # what each agent opened
    output="trace.json",            # omit and nothing is written
    start="3 days ago",
    end=None,
    profile=cycle / "profile.jsonl",  # the programs that run started, if it was profiled
)
```

Returns the trace document. Writes a file only when `output` is given — which is the one thing
the library does that the command line does not let you skip.

Raises `ValueError` if a time cannot be read or a named session is empty; the command line
reports both as usage errors.

## Watching a run instead

A trace is for after. While a run is going, the interface's `/status` shows the same shape
live: who is working, every handover between agents with how often it happened, and what each
model has cost with the rate it is costing it at.

That is read from the turns going past and from the logs the backends write as they go — never
by asking the flow, which is a Python file that may branch any way it likes. See
[TUI](/reference/tui.md#the-screen).

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

It lands **with the run it is a trace of**, which is where the run's own record and the links
to its sessions already are. In the interface the same thing is a row of `/cycles`: pick a run,
press enter, collect it.

![a trace being written, and nothing found inside a one-minute window](/demo/collect.gif)

## What you get

```
process   agent          builder · claude-opus-4-8 · high
  track     main ──────▶ ▓▓▓ ▓ ▓▓▓▓▓▓ ▓▓  ▓▓▓▓▓  ▓ ▓▓▓▓▓▓▓▓▓▓
  track     subagent ──▶      ▓▓▓▓▓▓▓▓▓▓▓
process   agent          reviewer · claude-opus-4-8 · high
  track     main ──────▶            ▓▓▓▓        ▓▓▓▓        ▓▓▓▓
```

A process is an agent and everything it drove; a track is one of that agent's sub-agents, named
after what kind it was. For a [profiled](#profiling-a-run) run the same two words carry over to
the programs the agents ran: a process is a program, a track is one of its threads.

| In the trace | Is |
| --- | --- |
| a **process** | one [agent](/guide/concepts#agent) |
| a **track** | one [session](/guide/concepts#session). Sessions of one agent that never run at the same time share a track; root sessions and sub-agents stay apart. |
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

`cycle.jsonl` is JSON lines, appended and flushed as it goes — so a run that died is a run whose
cycle still says what it got to.

| `event` | Written | Carries |
| --- | --- | --- |
| `began` | when the flow starts | `flow`, `task`, `workspace`, whether the flow can be picked up again, and one entry per agent with its id, backend, model, effort, account and what it may do |
| `opened` | each time an agent opens a session | `agent`, `backend`, `provider`, `session`, and the name the run gives it |
| `ended` | when the flow stops | `how`: `done`, `failed`, or `stopped` |

Each session's own logs are pointed at from `sessions/<name>/`, under a name that says whose
session it was, what took its turns, which account they ran as and what the backend called it —
`builder-claude@work-0a1b2c3d`. Links for reading: humanize reads and writes every log where
the backend keeps it.

`/cycles` is the same list at the prompt — every run of this directory, newest first, and what
there is to do with one.

**It is not a transcript.** The backend's own log is the turn-by-turn record; a cycle is the
*shape* of the run — enough to gather a trace afterwards out of the ids alone.

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
hmz trace collect --cycle 20260809T0144              # one run of it, by name
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

The default output is named after the UTC moment it was collected, so collecting twice keeps both.

## Profiling a run

An agent's turn is mostly other programs — the tests, the build, the greps — and none of them
is in a backend's log, which records the tool call rather than the process. Turn **profile** on
for a directory on the second page of `/settings`, and while a flow runs there the programs
underneath it are sampled into that run's cycle. Collecting the run draws them beside its
sessions, at the same scale, so *what was this run doing at 09:41* has one answer:

```
process   agent          builder · claude-opus-4-8 · high
  track     main ──────▶ ▓▓▓ ▓ ▓▓▓▓▓▓ ▓▓  ▓▓▓▓▓  ▓ ▓▓▓▓▓▓▓▓▓▓
process   program        pytest · 41207
  track     main ──────▶       ▓▓▓▓▓▓▓▓▓▓
```

Sampled rather than intercepted: nothing goes between an agent and what it runs, a program that
lived for thirty milliseconds may be missed, and a machine whose processes cannot be read is a
run with no profile rather than a run that stops.

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
- [Tracing reference](/reference/tracing)
- [CLI › `hmz trace`](/reference/cli#hmz-trace)

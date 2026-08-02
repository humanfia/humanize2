# Tracing

A long run is thousands of tool calls across several agents. `hmz collect` turns what they left
behind into one timeline you can actually look at.

It works whether or not a [flow](/reference/flows.md) drove them — a trace of yesterday's `claude` session
is one command away.

## Collecting

```sh
hmz collect
```

```console
.humanize/20260809T014455Z.trace.json: 3 sessions, 412 slices
```

Drag that file into [ui.perfetto.dev](https://ui.perfetto.dev), or open `chrome://tracing` and
load it. It is a Chrome JSON trace, so anything that reads one will do.

The default name is the UTC moment it was collected, so collecting twice keeps both traces
rather than writing over the first. It is written relative to the current directory, not to the
workspace you named. `--output` puts it somewhere else; its directory is created if it is not
there.

Full syntax in the [CLI reference](/reference/cli.md#hmz-collect).

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
| a **process** | one [agent](/guide/concepts.md#agent) |
| a **track** | one [session](/guide/concepts.md#session). Sessions of one agent that never run at the same time share a track; root sessions and sub-agents stay apart. |
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

A run that drove the sessions itself knows better. `hmz collect` reads that from the last
[cycle](#cycles) in the workspace, so `rlar` traces as `actor` and `reviewer` without being told
anything. Driving agents by hand, say so yourself:

```python
collect(agents={a.id: a.opened for a in (actor, reviewer)})
```

Sessions nobody claims are read as the configuration they ran at.

## Cycles

Every run of a flow is one **cycle**, written as it happens to:

```
~/.humanize/cycles/<workspace>/<datetime>-<hex>.jsonl
```

`<workspace>` is the absolute path with everything that is not a letter or a digit flattened to
`-`, the way the backends flatten a workspace into the folder they log it under. `<hex>` is six
characters, because two flows may be started in one second and neither is the other's run.

It is JSON lines, one line per thing that happened to the run, appended and flushed as it goes —
a run that died is a run whose cycle still says what it got to.

| `event` | Written | Carries |
| --- | --- | --- |
| `began` | when the flow starts | `flow`, `task`, `workspace`, and one entry per agent with its `agent` id, `backend`, `model` and `effort` |
| `opened` | each time an agent opens a session | `agent`, `backend`, `session` |
| `ended` | when the flow stops | `how`: `done`, `failed`, or `stopped` |

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

## Where the trajectories come from

The backends' own home directories, which humanize only reads:

| Backend | Environment variable | Default |
| --- | --- | --- |
| Claude Code | `CLAUDE_CONFIG_DIR` | `~/.claude` |
| Codex | `CODEX_HOME` | `~/.codex` |
| Kimi Code | `KIMI_CODE_HOME` | `~/.kimi-code` |

Those three, and no others. opencode and mimocode keep a session in a database rather than in a
log file, and nothing here reads pi's own log yet, so there is nothing to gather for any of the
three: a run of theirs is watched as it happens rather than collected after.

A home that does not exist is skipped rather than being an error, so collecting on a machine
with only one backend installed works. A pi home that *does* exist is the exception, and a bug:
`hmz collect` looks for a reader for every backend whose home is there, finds none for pi, and
exits `KeyError: 'pi'`. Until that is fixed, collect with `PI_CODING_AGENT_DIR` pointed at a
directory that is not there.

## Narrowing what is collected

A workspace and a set of sessions narrow the trace together:

```sh
hmz collect                                    # this workspace, all of its history
hmz collect ~/code/other                       # another workspace
hmz collect --session 0a1b2c3d,5f6e            # two sessions, wherever they ran
hmz collect ~/code/other --session 0a1b2c3d    # that session, only if it ran there
hmz collect --start "3 days ago"               # recent history only
hmz collect --end "yesterday 18:00"
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

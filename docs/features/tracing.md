# Tracing

A long run is thousands of tool calls across several agents. `hmz collect` turns what they left
behind into one timeline you can actually look at.

```sh
hmz collect
```

```console
.humanize/20260809T014455Z.trace.json: 3 sessions, 412 slices
```

Drag that file into [ui.perfetto.dev](https://ui.perfetto.dev), or load it in `chrome://tracing`.
It is a Chrome JSON trace, so anything that reads one will do.

It works **whether or not a flow drove them** — a trace of yesterday's `claude` session is one
command away.

![hmz collect writing a trace, and finding nothing inside a one-minute window](/demo/collect.gif)

## What you get

```
process   agent          builder · claude-opus-4-8 · high
  track     session ──▶ ▓▓▓ ▓ ▓▓▓▓▓▓ ▓▓  ▓▓▓▓▓  ▓ ▓▓▓▓▓▓▓▓▓▓
  track     sub-agent ─▶      ▓▓▓▓▓▓▓▓▓▓▓
process   agent          reviewer · claude-opus-4-8 · high
  track     session ──▶            ▓▓▓▓        ▓▓▓▓        ▓▓▓▓
```

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

That is what a [cycle](#what-a-run-writes-down) is for. `hmz collect` reads the last one in the
workspace, so `official/rlar` traces as `actor` and `reviewer` without being told anything.

Driving agents by hand, say so yourself:

```python
collect(agents={a.id: a.opened for a in (actor, reviewer)})
```

Sessions nobody claims are read as the configuration they ran at.

## What a run writes down

Every run of a flow is one **cycle**:

```
~/.humanize/cycles/<workspace>/<datetime>-<hex>.jsonl
```

JSON lines, appended and flushed as it goes — so a run that died is a run whose cycle still says
what it got to.

| `event` | Written | Carries |
| --- | --- | --- |
| `began` | when the flow starts | `flow`, `task`, `workspace`, and one entry per agent with its id, backend, model and effort |
| `opened` | each time an agent opens a session | `agent`, `backend`, `session` |
| `ended` | when the flow stops | `how`: `done`, `failed`, or `stopped` |

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
hmz collect                                    # this workspace, all of its history
hmz collect ~/code/other                       # another workspace
hmz collect --session 0a1b2c3d,5f6e            # two sessions, wherever they ran
hmz collect ~/code/other --session 0a1b2c3d    # that session, only if it ran there
hmz collect --start "3 days ago"               # recent history only
hmz collect --end "yesterday 18:00" --output /tmp/before.json
```

- Naming **sessions alone** collects them wherever they were recorded.
- Adding a **workspace** keeps only the named sessions recorded there.
- Naming **neither** collects the current working directory.

A session is named by its whole id, by the key the trace shows it under, or by a leading part of
either — and the sub-agents it started come with it. `--start` and `--end` take anything
[dateparser](https://dateparser.readthedocs.io/) understands.

The default output is named after the UTC moment it was collected, so collecting twice keeps both.

## Where it reads from

The backends' own home directories, which humanize only ever reads:

| Backend | Variable | Default |
| --- | --- | --- |
| Claude Code | `CLAUDE_CONFIG_DIR` | `~/.claude` |
| Codex | `CODEX_HOME` | `~/.codex` |
| Kimi Code | `KIMI_CODE_HOME` | `~/.kimi-code` |

Those three, and no others. **opencode and mimocode keep a session in a database rather than in
a log file, and nothing here reads pi's own log yet**, so there is nothing to gather for any of
the three: a run of theirs is watched as it happens rather than collected after.

A home that does not exist is skipped rather than being an error.

::: warning A pi home stops `hmz collect` altogether
`hmz collect` looks for a reader for **every** backend whose home exists, and there is none for
pi — so with `~/.pi/agent` (or `$PI_CODING_AGENT_DIR`) present it exits with
`KeyError: 'pi'` rather than collecting the backends it can read. Collect with the variable
pointed somewhere empty until that is fixed:

```sh
PI_CODING_AGENT_DIR=/nonexistent hmz collect
```
:::

A flow that ran on a [machine of its own](/features/containers) worked in a mirror rather than in
this directory, so find its trajectories with `--session` rather than by workspace.

## Watching instead

A trace is for after. While a run is going, [`/status`](/features/status) shows the same shape
live — and it is read off the turns going past, never by asking the flow.

## See also

- [Tutorial: read the run back](/guide/tutorial-trace)
- [Tracing reference](/reference/tracing)
- [CLI › `hmz collect`](/reference/cli#hmz-collect)

# Tracing

`amflows collect` reads the trajectories a coding agent recorded, whether or not a
[flow](flows.md) drove it.

```sh
amflows collect [<workspace>] [--session <session>[,<session>]...] [--output <output>] [--start <start>] [--end <end>]
```

Collects the trajectories recorded for a workspace and writes `.amflows/<datetime>.trace.json`.
Load it in [ui.perfetto.dev](https://ui.perfetto.dev) or `chrome://tracing`: sessions and
sub-agents become tracks, one slice per action, with prompt, reasoning, tool input and tool
output attached.

```sh
amflows collect                                   # current workspace, all history
amflows collect ~/myproject --start "3 days ago"  # another workspace, recent history only
amflows collect --session 0a1b2c3d,5f6e           # two sessions, wherever they ran
```

An [isolated](isolation.md) flow worked in a mirror rather than in this directory, so its
trajectories are found by `--session` rather than by workspace.

Each **agent** is one process. An agent is a configuration — a backend at a model at an effort —
together with every sub-agent it started, so a loop of one-shot sessions reads as one agent
rather than a hundred. A flow that drove the sessions itself knows better, and says so by passing
[`agents=`](agents.md#names), which is what tells two agents run at the same configuration apart.

`amflows collect` takes that from the last run in the workspace rather than being told it. Every
run of a flow is one **cycle**, written to `~/.amflows/cycles/<workspace>/<datetime>-<id>.jsonl`
as it happens — one line for the run, one for each session an agent opened, one for how it ended
— so the sessions of a run can be told apart afterwards by whose they were rather than by what
they were run at. A cycle covers one run: it closes when the flow finishes, fails or is
interrupted, and running the flow again is another cycle.

Trajectories are read from the backends' own home directories, named by `CLAUDE_CONFIG_DIR`,
`CODEX_HOME` and `KIMI_CODE_HOME` and falling back to `~/.claude`, `~/.codex` and `~/.kimi-code`;
a missing one is skipped. `amflows.oronyx.collect` takes the same arguments plus `agents`,
returns the trace document, and writes a file only when `output` is given.

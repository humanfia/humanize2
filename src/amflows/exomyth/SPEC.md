# Exomyth

## Commands

```shell
amflows collect [<workspace>] [--session <session>[,<session>]...] [--output <output>] [--start <start>] [--end <end>]
```

Collects and aggregates agent trajectories and generates Chrome JSON trace files for visualization.

Args:

- `<workspace>`: The path to the workspace directory to generate traces for. If not provided, the current working directory is used, unless sessions are named.
- `--session <session>[,<session>]...`: The sessions to generate traces for, comma separated and repeatable. A session is named by its whole id, by the key the trace shows it under, or by a leading part of either, and the sub-agents it started are collected with it. If not provided, every session of the workspace is included. Named sessions are collected wherever they were recorded, and are cut down to the workspace when one is provided.
- `--output <output>`: The path to the output file where the aggregated trace will be saved. Its directory is created if it does not exist. If not provided, the trace is saved as `.amflows/<datetime>.trace.json` in the current working directory, where `<datetime>` is the UTC moment it was collected, so that collecting twice keeps both traces.
- `--start <start>`: The start time for filtering the session logs, in any wording dateparser understands. If not provided, up to earliest logs are included.
- `--end <end>`: The end time for filtering the session logs, in any wording dateparser understands. If not provided, up to latest logs are included.

Prints the output path with the number of sessions and slices it holds.

Environment Variables:

- `CLAUDE_CONFIG_DIR`, `CODEX_HOME`, and `KIMI_CODE_HOME`: The path to agent home directories for discovering session logs. If not set, use the default paths of each agent. A home directory that does not exist is skipped.

## API

```python
exomyth.collect(workspace=None, *, sessions=None, agents=None, output=None, start=None, end=None)
```

Carries out `amflows collect` and returns the trace as a document. The command line is a shell around it.

Args:

- `workspace`: Same as `<workspace>`.
- `sessions`: Same as `--session`, as a comma separated string or as an iterable of ids.
- `agents`: What each agent of a flow opened, as a mapping of the agent's name to the ids the backends gave the sessions it opened, which is what a janus agent reports as its `id` and its `opened`. The command line has no agents to name, so it never passes any.
- `output`: Same as `--output`, except that no file is written if it is not provided.
- `start`: Same as `--start`.
- `end`: Same as `--end`.

Returns the trace document, whose `otherData` reports what was asked for and what was collected.

Raises `ValueError` if a time cannot be read or a named session is empty. The command line reports these as usage errors.

Workflow:

```
For backend in [claude, codex, kimi]:
    Find the session logs asked for in the backend's home directory, including subagents' logs:
      - Of the workspace, if one is given or implied.
      - Of the named sessions, if any are given.
    Cut off records outside the specified time range (if provided).
Name the agent every collected session ran on:
  - The agent that says it opened the session, if any was given.
  - Otherwise the backend it ran on, so that one coding agent configuration is one agent
    however many sessions were driven through it.
  - Either way, followed by the model and the effort the session itself reports.
  - A sub-agent belongs to the agent of the session that started it, whatever it ran at itself.
Aggregate the logs into a single trace file:
  - Sessions of one agent share a process; those of an agent that never run at the same time share a track; root sessions and sub-agents stay apart.
  - Each slice represents a single action taken by the agent or waiting for reasoning; it should include information as detailed as possible.
```

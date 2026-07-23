# Exomyth

## Commands

```shell
exomyth collect [<workspace>] [--session <session>[,<session>]...] [--output <output>] [--start <start>] [--end <end>]
```

Collects and aggregates agent trajectories and generates Chrome JSON trace files for visualization.

Args:

- `<workspace>`: The path to the workspace directory to generate traces for. If not provided, the current working directory is used, unless sessions are named.
- `--session <session>[,<session>]...`: The sessions to generate traces for, comma separated and repeatable. A session is named by its whole id, by the key the trace shows it under, or by a leading part of either, and the sub-agents it started are collected with it. If not provided, every session of the workspace is included. Named sessions are collected wherever they were recorded, and are cut down to the workspace when one is provided.
- `--output <output>`: The path to the output file where the aggregated trace will be saved. If not provided, the default output file is `exomyth.trace.json` in the current working directory.
- `--start <start>`: The start time for filtering the session logs, in any wording dateparser understands. If not provided, up to earliest logs are included.
- `--end <end>`: The end time for filtering the session logs, in any wording dateparser understands. If not provided, up to latest logs are included.

Prints the output path with the number of sessions and slices it holds.

Environment Variables:

- `CLAUDE_CONFIG_DIR`, `CODEX_HOME`, and `KIMI_CODE_HOME`: The path to agent home directories for discovering session logs. If not set, use the default paths of each agent. A home directory that does not exist is skipped.

## API

```python
exomyth.collect(workspace=None, *, sessions=None, output=None, start=None, end=None)
```

Carries out `exomyth collect` and returns the trace as a document. The command line is a shell around it.

Args:

- `workspace`: Same as `<workspace>`.
- `sessions`: Same as `--session`, as a comma separated string or as an iterable of ids.
- `output`: Same as `--output`, except that no file is written if it is not provided.
- `start`: Same as `--start`.
- `end`: Same as `--end`.

Returns the trace document, whose `otherData` reports what was asked for and what was collected.

Raises `ValueError` if a time cannot be read or a named session is empty. The command line reports these as usage errors.

Workflow:

```
For agent in [claude, codex, kimi]:
    Find the session logs asked for in the agent's home directory, including subagents' logs:
      - Of the workspace, if one is given or implied.
      - Of the named sessions, if any are given.
    Cut off records outside the specified time range (if provided).
    Aggregate the logs into a single trace file:
      - Sessions of an agent that never run at the same time share a track; root sessions and sub-agents stay apart.
      - Each slice represents a single action taken by the agent or waiting for reasoning; it should include information as detailed as possible.
```

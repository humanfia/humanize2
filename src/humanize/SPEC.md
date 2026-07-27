# humanize

## File Structure

```
.
├── __init__.py
├── __main__.py
├── cli.py
├── coganchor
├── janus
├── jetflow
├── oronyx
├── talanton
└── tui
```

Each subdirectory is a library and has a SPEC of its own. None of them MUST have a command
line: `cli.py` is the whole of it, and MUST reach a subpackage only from inside the command
carried out in it, so that a command pays for no subpackage but its own -- and so that the
same file serves as the target half of a session, where it is the only one installed.

## `__init__.py`

Expose nothing. A caller names the subpackage it wants.

## Commands

```shell
hmz [<command> [<args>...]]
```

- A line naming no command at all MUST open the terminal interface, which is every command at
  one prompt. There MUST be no command that opens it too: one way in is one way in. A line
  naming something that is not a command MUST be a usage error listing the commands there
  are. Everything after the command name MUST reach that command untouched, `--help`
  included, so that each answers for its own arguments.
- `__main__.py` MUST run this same command line, so that `python -m humanize` is `hmz`.

## `hmz exec`

```shell
hmz exec -f|--flow <flow> -a|--agent <cli>/<model>:<effort> [-a ...] <task>
```

Runs a flow in the current directory, on the agents it is given.

Args:

- `-f`, `--flow <flow>`: The Python file the flow is written in. Required.
- `-a`, `--agent <cli>/<model>:<effort>`: One agent to drive the flow with. Required, and
  repeated once for each agent the flow drives, in the order it takes them. It MUST also be
  accepted written out as `cli=<cli>,model=<model>,effort=<effort>`, in any order, since a
  model or an effort that holds the punctuation the short form separates on has nowhere else
  to go. One `-a` MUST be one agent: a list in a single `-a` MUST NOT be split into several.
- `<task>`: What the flow is to have the agents do, as the text itself.

- `<cli>` MUST be one of `claude`, `codex` and `kimi`, each of which MUST also answer to the
  longer name it is installed under, and `<model>` and `<effort>` MUST be what that CLI is
  asked for. A model MAY hold slashes of its own -- Kimi Code's are `kimi-code/k3` -- so the
  CLI MUST be read from the front and the effort from after the last colon.
- Two agents of one spelling MUST be two agents, so that a flow of an actor and a reviewer at
  one configuration is what it says it is.
- A flow that is not there, has no entry point, does not say how many agents it drives, or
  drives a different number than were given MUST be reported as a usage error, before any
  agent has run. Whatever else a flow does as it is imported is the flow's own, and MUST fail
  as it would anywhere.

## `hmz collect`

```shell
hmz collect [<workspace>] [--session <session>[,<session>]...] [--output <output>] [--start <start>] [--end <end>]
```

Collects and aggregates agent trajectories and generates Chrome JSON trace files for visualization.

Args:

- `<workspace>`: The path to the workspace directory to generate traces for. If not provided, the current working directory is used, unless sessions are named.
- `--session <session>[,<session>]...`: The sessions to generate traces for, comma separated and repeatable. A session is named by its whole id, by the key the trace shows it under, or by a leading part of either, and the sub-agents it started are collected with it. If not provided, every session of the workspace is included. Named sessions are collected wherever they were recorded, and are cut down to the workspace when one is provided.
- `--output <output>`: The path to the output file where the aggregated trace will be saved. Its directory is created if it does not exist. If not provided, the trace is saved as `.humanize/<datetime>.trace.json` in the current working directory, where `<datetime>` is the UTC moment it was collected, so that collecting twice keeps both traces.
- `--start <start>`: The start time for filtering the session logs, in any wording dateparser understands. If not provided, up to earliest logs are included.
- `--end <end>`: The end time for filtering the session logs, in any wording dateparser understands. If not provided, up to latest logs are included.

Prints the output path with the number of sessions and slices it holds.

Environment Variables:

- `CLAUDE_CONFIG_DIR`, `CODEX_HOME`, and `KIMI_CODE_HOME`: The path to agent home directories for discovering session logs. If not set, use the default paths of each agent. A home directory that does not exist is skipped.

# Tracing

## File Structure

```
.
├── __init__.py
├── chrome.py
├── collector.py
├── readers
└── session.py
```

`readers` holds one reader per backend, each turning that backend's own log format into the
shared session model. A backend is driven one way and logs another, so a reader MUST NOT need
anything of what drives it; where the logs are MUST be read from `humanize.backends` rather
than written down again here.

## API

```python
tracing.collect(workspace=None, *, sessions=None, agents=None, output=None, start=None, end=None)
```

Carries out `hmz collect` and returns the trace as a document. The command line is a shell around it.

Args:

- `workspace`: Same as `<workspace>`.
- `sessions`: Same as `--session`, as a comma separated string or as an iterable of ids.
- `agents`: What each agent of a flow opened, as a mapping of the agent's name to the ids the backends gave the sessions it opened, which is what an agent reports as its `id` and its `opened`. The command line has no agents to name, so it never passes any.
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

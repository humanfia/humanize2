# Tracing

## File Structure

```
.
├── __init__.py
├── chrome.py
├── collector.py
├── profile.py
├── readers
└── session.py
```

`readers` holds one reader per backend, each turning that backend's own log format into the
shared session model. A backend is driven one way and logs another, so a reader MUST NOT need
anything of what drives it; where the logs are MUST be read from `hmz.backends` rather
than written down again here.

`profile.py` samples the programs a run starts while it runs, so that what a turn spent its
minutes on is in that run's trace beside the turn. A turn is mostly other programs -- the
tests, the build, the greps -- and none of them appears in a backend's log, which records the
tool call rather than the process.

- It MUST sample rather than intercept: nothing here goes between an agent and what it runs.
- Nothing here MUST be able to stop a run. A machine whose processes cannot be read, a
  process that went while it was being read, a profile that cannot be written: each MUST
  leave the run as it was.
- What it saw MUST be appended as each program goes rather than held to the end, for the
  reason an epic's own record is appended: a run that died is a run whose profile has to say
  what it got to.
- A start MUST be timed against the clock the rest of a trace is timed by. What the operating
  system reports is worked out from an estimate of when the machine booted, which is half a
  second out on an ordinary one -- and half a second is a mile on a trace where a tool call
  is timed to the millisecond. The difference MUST be measured from the profile itself: a
  program is seen within one sample of starting, so the smallest gap anywhere between what
  was reported and when it was seen is as close to it as this can get.

## API

```python
tracing.collect(workspace=None, *, sessions=None, agents=None, output=None, start=None, end=None, profile=None)
```

Gathers the sessions asked for and returns the trace as a document. `hmz.sdk.Epics.trace` and `hmz.sdk.Epics.traced` are shells around it, and what the interface offers on a run is reached through them.

Args:

- `workspace`: The workspace whose sessions are to be read. Nothing at all where the sessions are asked for by id alone, since a workspace would narrow those to the ones recorded there.
- `sessions`: Which sessions to collect, as a comma separated string or as an iterable of ids. Nothing at all is every session of the workspace; an empty iterable is no session at all, which is what a trace of a run that opened none holds -- naming sessions is a filter, and naming none of them MUST NOT read as naming all of them.
- `agents`: What each agent of a flow opened, as a mapping of the agent's name to the ids the backends gave the sessions it opened, which is what an agent reports as its `id` and its `opened`. A trace of a run takes this from what that run wrote down; a trace of sessions no run drove has none to name.
- `output`: Where to write the trace. No file is written if it is not provided.
- `start`: The earliest moment to keep, in any wording dateparser understands.
- `end`: The latest.
- `profile`: The programs the run started while it ran, as the profile an epic holds or as the records themselves. Nothing for a run that was not profiled, which is every run until a workspace says otherwise.

Returns the trace document, whose `otherData` reports what was asked for and what was collected.

Raises `ValueError` if a time cannot be read or a named session is empty.

Workflow:

```
For backend in [claude, codex, kimi]:
    Find the session logs asked for in the backend's home directory, including subagents' logs:
      - Of the workspace, if one is given or implied.
      - Of the named sessions, if any are given -- and of none, where the names are empty.
    Cut off records outside the specified time range (if provided).
Name the agent every collected session ran on:
  - The agent that says it opened the session, if any was given.
  - Otherwise the backend it ran on, so that one coding agent configuration is one agent
    however many sessions were driven through it.
  - Either way, followed by the model and the effort the session itself reports.
  - A sub-agent belongs to the agent of the session that started it, whatever it ran at itself.
Aggregate the logs into a single trace file:
  - A process is an agent and everything it drove; a track is one of that agent's sub-agents.
    Those of an agent that never run at the same time share a track, and a track is named
    after the kind of sub-agent on it; root sessions and sub-agents stay apart.
  - Each slice represents a single action taken by the agent or waiting for reasoning; it should include information as detailed as possible.
  - A profiled run brings the programs its agents started, drawn the same way: a process is a
    program and a track is one of its threads. Which is the whole point of one document --
    an agent's turn is mostly other programs, so a timeline with the turns on it and not what
    they ran is a timeline that stops exactly where the time went.
```

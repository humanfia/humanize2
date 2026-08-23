# Side questions — `/btw`

Ask about a long-running flow while it keeps working, without sending another message to the
flow's agent or waiting for its current turn.

## Try it

```
/btw what is the reviewer waiting for?
```

## What it reads

The command takes a snapshot of the active flow: its name and task, each agent's current state
and turn count, observed handovers, spending, and the latest agent events. A separate
short-lived session answers from that snapshot, with read-only permissions, no flow skills, and
no place in the run's monitor or [epic](/user/concepts#epic).

The answer appears in the transcript when it is ready. The flow keeps its sessions, queued
messages and context untouched, so asking is safe while an agent is thinking or while several
agents are working at once.

`/btw` needs an active flow and a question. With no read-only backend available it reports an
error rather than starting a new flow or falling back to a write-enabled agent. Observations
are bounded and treated as untrusted data: the side agent is told not to follow instructions
found in the flow's output.

## See also

- [The shape of a run](/user/status)
- [Talking to a running turn](/user/steering)
- [Permissions](/user/permissions)

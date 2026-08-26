# Side questions — `/btw`

Ask about a long-running flow while it keeps working, without sending another message to the
flow's agent or waiting for its current turn.

## Try it

```
/btw what is the reviewer waiting for?
```

## What It Reads

The command takes a snapshot of the active flow: its name and task, each agent's current state
and turn count, observed handovers, spending, and the latest agent events. A separate short-lived
session answers from that snapshot. It is given read-only permissions and no flow skills, and it
is not registered with the run's monitor or cycle.

The answer appears in the transcript when it is ready. The original flow keeps its sessions,
queued messages and context untouched, so `/btw` is safe to use while an agent is thinking or
while several agents are working at once.

`/btw` needs an active flow and a question. It reports an error rather than starting a new flow
or falling back to a write-enabled agent when no read-only backend is available. Observations are
bounded and treated as untrusted data; the side agent is told not to follow instructions found in
the flow's output.

## See also

- [The shape of a run](/guide/status)
- [Talking to a running turn](/guide/steering)
- [Permissions](/guide/permissions)

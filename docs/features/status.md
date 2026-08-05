# The shape of a run — `/status`

`/status` answers three questions about the run in front of you:

1. **Who is working**, right now.
2. **Every handover between agents**, and how often each happened.
3. **What each model has cost.**

With, above them, what this run *is*: the **Flow** — every flow running, the one that was
started and whatever it called, innermost last — the **Agents**, one line apiece, and **Set**,
the flow's own settings where any were changed from what it declares.

That directed graph — who handed to whom, how many times — is the shape of the run. A
two-agent loop that was supposed to alternate and is in fact one agent doing everything looks
different here from the first glance.

## Where it comes from

Nothing asks the flow what it is doing. A flow is Python that may branch any way it
likes, so there is nothing to ask. What `/status` draws is kept from **the turns going past** —
the same `begins`/`ends` events any
[watcher](/reference/agents#watching-a-turn-as-it-happens) sees.

That is also why the person, driven as [an agent](/features/human-agent), is not in the graph:
their turns are not bracketed by those events, so counting them would put a human in the
handover graph and spin a clock at them while they thought.

## The same three readings, elsewhere

**Above the editor**, continuously: one line per agent — the name the flow calls it, what it
runs as `cli/model:effort`, the machine, [what it may do](/features/permissions) and the account
where those are not the ordinary ones, and how many conversations it holds. `●` is an agent with a turn open, `○` one that has stopped.

**On the status line, left**: whose turn it is and how long it has been going; between turns,
the flow and how long the run has been going. A flow that
[called another](/reference/flows#a-flow-that-calls-another-flow) names both, innermost last —
`chat ▸ official/rlar`.

**Under the agent lines**: what the run has cost and the rate it is costing it at, per model,
over a recent window — so a flow that has stopped reads as stopped. See
[Cost and rate](/features/tally).

## From Python

The cost half is on the agents themselves:

```python
agent.spent()            # Usage(input=…, output=…, cache_read=…)
agent.rate(over=60)      # tokens a second over the last minute
agent.juice()            # output tokens an average turn of the model came out with
```

The graph half is yours to keep, from a watcher:

```python
handovers: dict[tuple[str, str], int] = {}
last = None

def looking(agent, session, event):
    global last
    if event.kind == "begins":
        if last is not None and last != agent.id:
            handovers[(last, agent.id)] = handovers.get((last, agent.id), 0) + 1
        last = agent.id

for one in (actor, reviewer):
    one.watch(looking)
```

Which flows are running, innermost last:

```python
from hmz.runner import running

running()                       # one Running(flow, since) apiece, oldest first
[one.flow for one in running()] # ["chat", "official/rlar"]
```

## Afterwards

`/status` is the run in progress. Once it is over, the same shape — and far more of it — is
[`hmz trace collect`](/features/tracing): one process per agent, one track per row of its
sessions, one slice per thing the agent did.

## See also

- [Cost and rate](/features/tally)
- [Many conversations at once](/features/conversations)
- [Tracing](/features/tracing)

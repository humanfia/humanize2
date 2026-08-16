# The shape of a run — `/status`

`/status` answers three questions about the run in front of you: who is working right now,
every handover between agents and how often each happened, and what each model has cost. Above
those it shows the **Flow**, the **Agents**, and **Set**: every flow running, the one that was
started and whatever it called, innermost last; one line apiece; and the flow's own settings
where any were changed from what it declares. Use it to see the **shape** of a run — who handed
to whom and how many times — because a two-agent loop that was supposed to alternate and is in
fact one agent doing everything looks different here from the first glance.

## Try it

Type `/status`. Above the editor you get one line per agent, with `●` for an agent that has a
turn open and `○` for one that has stopped. On the status line, left, you see whose turn it is
and how long it has been going, or between turns the flow and how long the run has been going.
Under the agent lines you see what the run has cost and the rate it is costing it at, per
model, over a recent window.

## Where it comes from

Nothing asks the flow what it is doing. A **flow** is Python that may branch any way it likes,
so there is nothing to ask. What `/status` draws is kept from **the turns going past** — the
same `begins`/`ends` events any [watcher](/reference/agents#watching-a-turn-as-it-happens)
sees.

`/btw` uses this same live observation, together with the task, agent turn counts and handovers,
to answer a quick question. Its read-only side session receives a frozen snapshot, so asking it
does not add a message to, pause, or otherwise steer the flow.

That is also why the person, driven as [an agent](/guide/human-agent), is not in the graph.
Their turns are not bracketed by those events. Counting them would put a human in the handover
graph and spin a clock at them while they thought.

## The same three readings, elsewhere

**Above the editor**, continuously: one line per agent. Each line shows the name the flow calls
it, what it runs as `cli/model:effort`, the machine, [what it may do](/guide/permissions) and
the account where those are not the ordinary ones, and how many conversations it holds. `●` is
an agent with a turn open, `○` one that has stopped.

**On the status line, left**: whose turn it is and how long it has been going; between turns,
the flow and how long the run has been going. A flow that [called
another](/reference/flows#a-flow-that-calls-another-flow) names both, innermost last — `chat ▸
official/rlar`.

**Under the agent lines**: what the run has cost and the rate it is costing it at, per model,
over a recent window — so a flow that has stopped reads as stopped. See [Cost and
rate](/guide/tally).

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
from hmz.flows import running

running()                       # one Running(flow, since) apiece, oldest first
[one.flow for one in running()] # ["chat", "official/rlar"]
```

## Afterwards

`/status` is the run in progress. Once it is over, the same shape — and far more of it — is
[`hmz trace collect`](/guide/tracing): one process per agent, one track per row of its
sessions, one slice per thing the agent did.

## See also

- [Side questions](/guide/btw)
- [Cost and rate](/guide/tally)
- [Many conversations at once](/guide/conversations)
- [Tracing](/guide/tracing)

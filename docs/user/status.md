# The shape of a run — `/status`

`/status` answers three questions about the run in front of you: who is working right now,
every handover between agents and how often each happened, and what each model has cost. Reach
for it to see the **shape** of a run, because a two-agent loop that was supposed to alternate
and is in fact one agent doing everything looks different here from the first glance.

It is also where [the board](/user/board) is, for a flow that talks to you.

## Try it

Type `/status`, or press **esc** with nothing else on the screen. Above the diagram:

| | |
| --- | --- |
| **Flow** | every flow running — the one that was started and whatever it called, innermost last |
| **Agents** | one line apiece |
| **Set** | the flow's own settings, where any were changed from what it declares |

## What is drawn, and when

**A box appears as its agent takes its first turn.** Not before. A flow may declare ten agents
and reach three of them — it is Python, and it may never take the branch the other seven are on
— so the diagram is what the run *is doing* rather than a list of what was configured. Each box
stays for the rest of the run once it is there, and the agents of the last run are still drawn
after it ends: what they did is still worth reading.

**An agent one of them started of its own hangs under it.** Claude's `Task`, Codex's collab
agent, Cursor's task tool — a fleet under a turn is agents, so it is drawn as agents rather
than as another tool call:

```
  ┌──────────────────────────────────┐
  │ ● builder · claude#4f2a          │
  │ claude/claude-opus-5:max · 3 turns│
  └──────────────────────────────────┘
    ├╴◆ Task read the tests
    └╴◇ Task find the flaky one
```

`◆` is one still going and `◇` one that has come back; a flow's own agents wear `●` and `○`
instead, because they are a different kind of thing. A subagent is not a row to open: nobody
chose what it runs, nothing can be said to it, and it has no transcript of its own. A flow that
wants a word about one hangs a hook on
[`SUBAGENT_START`](/reference/agents#not-every-backend-runs-every-moment).

Enter on a **box** reads that agent, whether or not it is working — `tab` is held to the ones
working, so this is where the one that has stopped is reached.

## Where it comes from

Nothing asks the flow what it is doing. A **flow** is Python that may branch any way it likes,
so there is nothing to ask. What `/status` draws is kept from **the turns going past** — the
same `begins`/`ends` events any [watcher](/reference/agents#watching-a-turn-as-it-happens)
sees. [`/btw`](/user/btw) answers a question from that same live observation, frozen into a
snapshot, so asking it neither pauses nor steers the flow.

That is also why the person, driven as [an agent](/weaver/human-agent), is not in the graph.
Their turns are not bracketed by those events. Counting them would put a human in the handover
graph and spin a clock at them while they thought.

## The same three readings, elsewhere

Little of this waits for `/status`. Three parts of the screen carry it while the run goes on.

**Above the editor**, continuously: one line per agent. Each line shows the name the flow calls
it, what it runs as `cli/model:effort`, the machine, [what it may do](/user/permissions) and
the account where those are not the ordinary ones, and how many conversations it holds. `●` is
an agent with a turn open, `○` one that has stopped.

**On the status line, left**: whose turn it is and how long it has been going; between turns,
the flow and how long the run has been going. A flow that [called
another](/reference/flows#a-flow-that-calls-another-flow) names both, innermost last — `chat ▸
official/rlar`.

**Under the agent lines**: what the run has cost and the rate it is costing it at, per model,
over a recent window — so a flow that has stopped reads as stopped. See [Cost and
rate](/user/tally).

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
[`hmz trace collect`](/user/tracing): one process per agent, one track per row of its
sessions, one slice per thing the agent did.

## See also

- [Side questions](/user/btw)
- [Cost and rate](/user/tally)
- [Many conversations at once](/user/conversations)
- [Tracing](/user/tracing)

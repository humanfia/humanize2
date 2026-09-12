# Watching a run — `/monitor`

`/monitor` draws the run in front of you: a box per agent that has worked, marked as it works
and saying how long it has been at it, with the handovers between them as the arrows joining
them. Reach for it to see the **shape** of a run and where it has got to — a two-agent loop that
was supposed to alternate and is in fact one agent doing everything looks different here at the
first glance.

The diagram is the sheet, not a header on one. It takes the height your terminal has, and the
few lines under it are only what a picture cannot say.

It is also where [the board](/user/board) is, for a flow that talks to you.

## Try it

Type `/monitor`, or press **esc** with nothing else on the screen.

```
   ▣ every agent · 1 of 2 working · 17 turns · 7m11s

   ┌────────────────────────────────────────────────────────┐
   │ ● builder · claude#a1b2                            43s │
   │ claude/claude-opus-5:high · 12 turns                   │
   └────────────────────────────────────────────────────────┘
     ├╴◆ Task read the tests
     └╴◇ Task find the flaky one
   │   ↓ 6 · ↑ 5
   ┌────────────────────────────────────────────────────────┐
 ❯ │ ○ reviewer · codex#c3d4                     idle 1m04s │
   │ codex/gpt-5.6-sol:high · 5 turns                unread │
   └────────────────────────────────────────────────────────┘
```

The first row is the transcript every agent's work appears on — the way back to watching the
flow rather than one agent of it. Beside it: how many of the boxes are working, how many turns
they have taken between them, and how long the run has been going.

## What a box says

**On the left, what the agent is.** The name the flow calls it, what it runs as
`cli/model:effort`, and how many turns it has taken.

**On the right, what it is doing.** That column is the one that moves, and it is the one you
come back to:

| | |
| --- | --- |
| `●` and a clock | working, and how long this turn has been open |
| `○` and `idle 4m12s` | stopped, and how long since its last turn ended |
| `reading` | its transcript is the one on the screen behind the sheet |
| `unread` | it has said something since you last looked at it |

An agent thinking for eleven minutes and an agent that stopped eleven minutes ago look nothing
alike here, which is the point: the first is working and the second is where a flow has usually
gone wrong.

**The arrows carry the handovers** and how often each way went. The one the flow took most
recently is drawn lit, so where the run just went is the first thing you see. A handover between
two agents the boxes did not put next to each other is said under the diagram as `Also` rather
than drawn: a line crossing the page from the first box to the fourth is a line nothing in a
terminal draws readably.

**Enter on a box reads that agent**, whether or not it is working — `tab` is held to the ones
working, so this is where the one that has stopped is reached. The box under the cursor is drawn
in the marker colour, with `❯` beside its name.

## What is drawn, and when

**A box appears as its agent takes its first turn.** Not before. A flow may declare ten agents
and reach three of them — it is Python, and it may never take the branch the other seven are on
— so the diagram is what the run *is doing* rather than a list of what was configured. Each box
stays for the rest of the run once it is there, and the agents of the last run are still drawn
after it ends: what they did is still worth reading. Every clock stops where the run stopped.

Before anything has taken a turn the sheet says so, and lists the agents that are set up —
which is the one thing it says about them that there are no boxes yet to carry.

**An agent one of them started of its own hangs under it.** Claude's `Task`, Codex's collab
agent, Cursor's task tool — a fleet under a turn is agents, so it is drawn as agents rather
than as another tool call. `◆` is one still going and `◇` one that has come back; a flow's own
agents wear `●` and `○` instead, because they are a different kind of thing. A subagent is not
a row to open: nobody chose what it runs, nothing can be said to it, and it has no transcript of
its own. A flow that wants a word about one hangs a hook on
[`SUBAGENT_START`](/reference/agents#not-every-backend-runs-every-moment).

## Under the diagram

Only what the boxes cannot carry, so that the picture is what your eye lands on:

| | |
| --- | --- |
| **Flow** | every flow running — the one that was started and whatever it called, innermost last |
| **Set** | the flow's own settings, where any were changed from what it declares |
| **Also** | the handovers no arrow could be drawn for |
| **Tokens** | what each model has cost, and the rate it is costing it at |

Who is working, what each agent runs and how long it has been at it are on the boxes, and are
not said twice.

## Where it comes from

Nothing asks the flow what it is doing. A **flow** is Python that may branch any way it likes,
so there is nothing to ask. What `/monitor` draws is kept from **the turns going past** — the
same `begins`/`ends` events any [watcher](/reference/agents#watching-a-turn-as-it-happens)
sees. [`/btw`](/user/btw) answers a question from that same live observation, frozen into a
snapshot, so asking it neither pauses nor steers the flow.

That is also why the person, driven as [an agent](/weaver/human-agent), is not in the graph.
Their turns are not bracketed by those events. Counting them would put a human in the handover
graph and spin a clock at them while they thought.

## The same readings, elsewhere

Little of this waits for `/monitor`. Three parts of the screen carry it while the run goes on.

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

running()                       # one Running(flow, since, depth, under) apiece
[one.flow for one in running()] # ["chat", "official/rlar"]
```

Asked from inside a flow this is the branch that flow is on — the flow somebody started, then
each flow called to get there, and never a call gathered beside it. Asked from anywhere else it
is every flow of the run, oldest first, each saying how `deep` it is and what it is `under`.

## Afterwards

`/monitor` is the run in progress. Once it is over, the same shape — and far more of it — is
[a trace](/user/tracing), gathered from that run on `/epics`: one process per agent, one track
per row of its sessions, one slice per thing the agent did.

## See also

- [Side questions](/user/btw)
- [Cost and rate](/user/tally)
- [Many conversations at once](/user/conversations)
- [Tracing](/user/tracing)

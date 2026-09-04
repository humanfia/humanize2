# Stopping

A flow ends when its `run` returns. Most interesting flows never return, and a Ralph loop is a
`while True`, so you end them from outside. You reach for stopping when a flow is running and
you want it to end now.

## Try it

Press **ctrl+c** twice in the interface while a flow is running. Twice, because a day's work is
behind a key that is also pressed by mistake: the first press says `press ctrl+c again to stop
the flow`, and the second one does it.

## The three ways to stop

| | |
| --- | --- |
| **ctrl+c** twice, in the interface | Stops the flow — the whole flow, not just the turn. Clears what is half-typed first, if anything is. |
| **ctrl+c**, on a `hmz exec` command line | The same. |
| **`agent.stop()`**, from anywhere | The same, for that agent. |

**A third press does not wait for it.** A flow told to stop unwinds in its own time — a loop
sleeps off its round, a server is given its seconds — and the press after the one that stopped
it closes every conversation still open under whatever turn it is in. That is the backend's
process going, so the flow reads a turn that *failed* rather than an agent that was stopped,
and nothing is left reading as a run in progress. It is the last thing a key can do about a
run.

**esc does not stop anything.** It is pressed to dismiss whatever is on the screen everywhere
else in the interface, so it is not the key that ends a day's work: it opens
[`/status`](/reference/tui#how-the-run-is-going) instead. With nothing running at all, two
presses of **ctrl+c** leave the interface.

## What a stop does to the turn under way

The turn is **closed out**, and every later call into that agent raises `Stopped`.

A stop leaves the turn where it got to. It does not wait for the turn, because a stop that
waited would not read as a stop. A model can think for minutes, and a key that took four of
them to have an effect is a key nobody trusts.

A file the agent had half-written stays half-written. A command it had started keeps running
until it finishes. What ends is the agent's part in it.

## What stopping is not

**Not `/clear`.** That clears the screen and nothing else. It clears the conversation being
read, not the others, and nothing that is running.

**Not choosing another flow.** `/flow` is refused while one is running, with `no choosing a
flow while a flow is running: ctrl+c twice stops it first`. A flow drives the agents it was
handed, and it must not have them swapped underneath it. Stop it first, then choose. Looking at
`/flow` and leaving without choosing changes nothing.

**Not a question ending.** A question still up when the flow ends or is stopped ends with it.
Stopping is never blocked on one.

## Why `suppress=True` does not catch a stop

The other side of that key press is the loop a [weaver
wrote](/weaver/writing-a-flow#make-the-loop-survive-a-bad-turn), which has to let it out.
`suppress` turns a **failed turn** into an empty answer:

```python
agent(task, suppress=True)   # a turn that failed answers ""; the loop goes round again
```

The turn still says it failed — a [`failed`](/reference/agents#watching-a-turn-as-it-happens)
event, and the same sentence on stderr where nothing is watching the run. Suppressing a turn
keeps the loop going; it does not make the failure quiet.

It deliberately does not catch `Stopped`. A loop that carried on past a stop would never end:

```python
while True:
    agent(task, suppress=True)     # ← Stopped comes out of here, and the flow unwinds
```

`Stopped` is not a `subprocess.CalledProcessError`. Nothing that catches a failed turn catches
this by accident. Let it propagate. The [epic](/user/tracing#what-a-run-writes-down) then
records the run as **stopped by hand** rather than as one that finished — the difference
between "it decided it was done" and "somebody stopped it", and the only place that distinction
is written down.

There is one other thing `suppress` does not catch, for the same reason. An
[`Unrecoverable`](/reference/agents#when-an-account-goes-down) is a turn that failed for a
reason no other try could come out differently on — a conversation longer than the model's
context window, a session id the backend will not answer under. A `while True` that swallowed
one would go round on the same failure until somebody stopped it, so it comes out of the loop
and the run ends with it. Unlike a stop, it is a `CalledProcessError`, so a flow that really
does want to catch everything still can.

`agent.prompted()` raises `Stopped` too, so a run ended while it waited also reads as ended by
hand. `agent.stopped` is the quiet way to ask the same question — a bool, and never a raise:

```python
agent.prompted()      # waiting for the next thing to say; raises if the wait ended in a stop
agent.stopped         # whether it has been told to stop; answers True, and never raises
```

A hook that raises is normally the hook's own problem: a flow must not fail because something
hung off it did. `Stopped` is the one exception, and it is let out.

## See also

- [Talking to a running turn](/user/steering) — when a steer is enough
- [Being away](/user/afk)
- [Flows › Stopping](/reference/flows#stopping)

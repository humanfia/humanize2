# Stopping

A flow ends when its `run` returns. Most of the interesting ones never do — a Ralph loop is a
`while True` — so they are ended from outside.

## The three ways

| | |
| --- | --- |
| **esc**, in the interface | Stops the flow — the whole flow, not just the turn. Dismisses an open [offers list](/features/completion) first, if there is one. Silent when nothing is running. |
| **ctrl+c**, on a `hmz exec` command line | The same. |
| **`agent.stop()`**, from anywhere | The same, for that agent. |

In the interface, **ctrl+c** takes back the nearest thing there is to take back: what is
half-typed if anything is, the flow if not. Twice in a row leaves — and leaving is always two
presses, whatever was going on, with the second within two seconds of the first.

## What a stop does to the turn under way

The turn is **closed out**, and every later call into that agent raises `Stopped`.

What the turn was doing is left where it got to. A stop that waited for a turn would not read as a
stop — a model can think for minutes, and a key that took four of them to have an effect is a key
nobody trusts.

So: a file the agent had half-written stays half-written. A command it had started keeps running
until it finishes. What ends is the agent's part in it.

## Why `suppress=True` does not catch it

```python
agent(task, suppress=True)   # a turn that failed answers ""; the loop goes round again
```

`suppress` turns a **failed turn** into an empty answer. It deliberately does not catch
`Stopped`, because a loop that carried on past a stop would never end:

```python
while True:
    agent(task, suppress=True)     # ← Stopped comes out of here, and the flow unwinds
```

`Stopped` is not a `subprocess.CalledProcessError`, so nothing that catches a turn that failed
catches this by accident. Let it propagate. The [cycle](/features/tracing#what-a-run-writes-down)
then records the run as **stopped by hand** rather than as one that finished — which is the
difference between "it decided it was done" and "somebody pressed esc", and the only place that
distinction is written down.

`agent.prompted()` raises it too, so a run ended while it waited also reads as ended by hand.
`agent.stopped` is the quiet way to ask the same question — a bool, and never a raise:

```python
agent.prompted()      # waiting for the next thing to say; raises if the wait ended in a stop
agent.stopped         # whether it has been told to stop; answers True, and never raises
```

A hook that raises is normally the hook's own problem — a flow must not fail because something
hung off it did. `Stopped` is the one exception, and it is let out.

## What stopping is not

**Not `/clear`.** That clears the screen and nothing else: the conversation being read, not the
others, and nothing that is running.

**Not choosing another flow.** `/flow` is refused while one is running — `no choosing a flow
while a flow is running: esc stops it first` — since a flow drives the agents it was handed and
must not have them swapped underneath it. Esc first, then choose; `/agents` and `/config` are
the same, and looking and leaving without choosing changes nothing.

**Not a question ending.** A question still up when the flow ends or is stopped ends with it, so
stopping is never blocked on one.

## See also

- [Talking to a running turn](/features/steering) — when a steer is enough
- [Being away](/features/afk)
- [Flows › Stopping](/reference/flows#stopping)

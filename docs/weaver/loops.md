# Loops

A **Ralph loop** keeps one agent working until you stop it, starting fresh from the task and
the repository every turn. Reach for it when you want a task worked through with nothing
carrying over from one turn to the next.

## What a Ralph loop is

```python
while True:
    agent(task, suppress=True)
```

That is the whole of it. `agent(...)` opens a **session** (a conversation the agent holds) and
drops it, so nothing carries over. The agent starts from the task and the repository each time,
with nothing of the last turn in context.

The opposite is `stateful_ralph`, which holds one session for the whole run:

```python
session = agent.new()
while True:
    session(task, suppress=True)
```

The agent is the same, but the behaviour is opposite. **The flow decides, not the agent.** This
is the most important choice a flow makes. See [Concepts › Session](/user/concepts#session).

## Write a task the loop can finish

A Ralph loop wants a task with a finish line it can check for itself.

```sh
cat > TASK.md <<'EOF'
# Task

Make `calc.py` a real calculator:

- [ ] add, subtract, multiply, divide
- [ ] divide by zero raises ValueError
- [ ] a test file `test_calc.py` covering all four
- [ ] `python -m pytest -q` passes

Tick each box in this file as you finish it. Stop when all four are ticked.
EOF
git add -A && git commit -qm "the task"
```

## Choose the flow

In `hmz`:

```
/flow
```

The flows appear one place at a time, one list each. Press **←** and **→** to step between the
places. Press **s** to narrow by name. Take `ralph_loop` with enter.

Or say it outright:

```
/flow ralph_loop
```

`/flow` is **refused while a flow is running**. You get `no choosing a flow while a flow is
running: ctrl+c twice stops it first`. So stop the last one before you choose the next. Looking
and leaving without choosing changes nothing.

::: details What the three built-in flows are
| Flow | Agents | |
| --- | --- | --- |
| `chat` | 1 + you | one session; every line you type is a turn of it. What the interface opens on. |
| `ralph_loop` | 1 | a fresh session every turn |
| `stateful_ralph` | 1 | one session, re-sent the task every turn |

Both loops say they [can be picked up](/user/resuming). They keep which round they are on, so
starting one again in this directory says round 41 rather than round 1.
:::

## Start the loop

Say what you want done:

```
Work through TASK.md.
```

It keeps going until you stop it. That is what a Ralph loop is.

## Watch the run

```
/status
```

It shows three things: who is working, every handover between agents with how often it
happened, and what each model has cost. On a one-agent flow the graph is dull. On
[two agents taking turns](/user/tutorials/take-home) it is the shape of the run.

Above the editor, continuously:

```
   assistant · claude/claude-opus-4-8:high · ● 1
                       48.2k tokens · 91/s
```

`●` is an agent with a turn open, and `1` is how many conversations it has open **right now**.
A Ralph loop holds one at a time, and that conversation is the turn's own. It lets the
conversation go when the turn ends, so the number does not climb with the turns; between turns
it holds none and the line says nothing about conversations at all. All of them run down this
agent's one transcript either way — nothing is redrawn when the next one opens. **tab** steps
between the agents that are working, which matters on a flow that drives several, such as
[two agents taking turns](/user/tutorials/take-home).

The cost line is per model, over a recent window, so a flow that has stopped reads as stopped.
See [Cost and rate](/user/tally).

## Steer the loop without restarting

A Ralph loop re-reads the repository every turn, so **the fastest way to steer it is to edit
the task file**. In another terminal:

```sh
echo '- [ ] and a --help flag' >> TASK.md
```

The next turn starts from a file that says so. Nothing had to be told.

You can also type at it. That goes into the turn that is running, as before.

## Stop the loop

**ctrl+c**, twice.

The loop never ends by itself; it is a `while True`. A stop raises `Stopped` inside the flow's
code. `suppress=True` deliberately **does not** catch that — otherwise the loop would carry on
past a stop and never end. See [Stopping](/user/stopping).

Stopping is not losing your place. `ralph_loop` says it [can be picked up](/user/resuming),
and what it keeps is which round it is on. Start it here again and it goes on from the round it
reached. That run is a run of its own, with its own sessions and its own record. `/epics` is
where both of them are.

## Try this

**Hold the conversation instead of dropping it.** `/flow stateful_ralph`, same task. Compare
how often it re-reads files it has already read.

**Move the effort.** Open the Agents page of `/flow`, choose the agent, find the `effort` row,
and press **←/→**. A Ralph loop of `low` turns is a different animal from one of `max` turns.
See [Efforts](/user/efforts).

**Make it read-only.** `/flow` → Agents → the agent → `permission` → **→** to `read-only`. Now
it can look at the repository and change nothing, which is how you use a loop to *review*
rather than to build.

## See also

- [Concepts › Session](/user/concepts#session)
- [Stopping](/user/stopping)
- [Cost and rate](/user/tally)
- [Efforts](/user/efforts)
- [Beat a benchmark](/user/tutorials/take-home)

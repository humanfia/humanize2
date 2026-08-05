# 2 · Put a loop under it

**Ten minutes.** A flow that keeps going until you stop it, with the agent starting from the task
and the repository every single turn.

::: tip Before you start
[Your first run](/guide/tutorial-first-run). Stay in the same scratch project.
:::

## What a Ralph loop is

```python
while True:
    agent(task, suppress=True)
```

That is the whole of it. `agent(...)` opens a **session of its own and drops it**, so nothing
carries over: the agent starts from the task and the repository each time, with nothing of the
last turn in context.

The opposite — one session held for the whole run — is `stateful_ralph`:

```python
session = agent.new()
while True:
    session(task, suppress=True)
```

Same agent, opposite behaviour, and **the flow decides, not the agent**. This is the single most
important choice a flow makes; see [Concepts › Session](/guide/concepts#session).

## Step 1 — give it something a loop can finish

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

## Step 2 — pick the flow

In `hmz`:

```
/flow
```

The flows appear a place at a time, one list apiece — **←** and **→** step between the places.
Press **s** to narrow by name. Take `ralph_loop` with enter.

Or say it outright:

```
/flow ralph_loop
```

`/flow` is **refused while a flow is running** — `no choosing a flow while a flow is running:
esc stops it first` — so stop the last one with esc before you choose the next. Looking and
leaving without choosing changes nothing.

::: details What the three built-in flows are
| Flow | Agents | |
| --- | --- | --- |
| `chat` | 1 + you | one session; every line you type is a turn of it. What the interface opens on. |
| `ralph_loop` | 1 | a fresh session every turn |
| `stateful_ralph` | 1 | one session, re-sent the task every turn |

Both loops say they [can be picked up](/features/resuming), and what they keep is which round
they are on — so starting one again in this directory says round 41 rather than round 1.
:::

## Step 3 — start it

Say what you want done:

```
Work through TASK.md.
```

It will keep going until you stop it. That is what a Ralph loop *is*.

## Step 4 — watch it

```
/status
```

Three things: who is working, every handover between agents with how often it happened, and what
each model has cost. On a one-agent flow the graph is dull; on
[two](/guide/tutorial-two-agents) it is the shape of the run.

Above the editor, continuously:

```
   assistant · claude/claude-opus-4-8:high · ● 1 of 1
                       48.2k tokens · 91/s
```

`●` is an agent with a turn open. `1 of 1` is which conversation you are reading of the ones this
agent has open **right now** — a Ralph loop holds one at a time, the turn's own, and lets it go
when the turn ends, so the number after `of` does not climb with the turns. Between turns it
holds none and the line says nothing about conversations at all. **tab** steps between the ones
that are working, which is worth something on a flow that holds several at once —
[two agents](/guide/tutorial-two-agents), or a fan-out reading `1 of 200`.

The cost line is per model, over a recent window, so a flow that has stopped reads as stopped. See
[Cost and rate](/features/tally).

## Step 5 — steer it without restarting it

A Ralph loop re-reads the repository every turn, so **the fastest way to steer it is to edit the
task file**. In another terminal:

```sh
echo '- [ ] and a --help flag' >> TASK.md
```

The next turn starts from a file that says so. Nothing had to be told.

You can also just type at it — that goes into the turn that is running, as before.

## Step 6 — stop it

**esc.**

The loop never ends by itself; it is a `while True`. Note what that means for the flow's code: a
stop raises `Stopped` inside it, and `suppress=True` deliberately **does not** catch that —
otherwise the loop would carry on past a stop and never end. See [Stopping](/features/stopping).

Stopping is not losing your place. `ralph_loop` says it [can be picked up](/features/resuming),
and what it keeps is which round it is on: start it here again and it goes on from the round it
reached. That run is a run of its own, with its own sessions and its own record — `/cycles` is
where both of them are.

## Try this

**Hold the conversation instead of dropping it.** `/flow stateful_ralph`, same task. Compare how
often it re-reads files it has already read.

**Move the effort.** The Agents page of `/flow`, the agent, the `effort` row, **←/→**. A Ralph
loop of `low` turns is a different animal from one of `max` turns — see
[Efforts](/features/efforts).

**Make it read-only.** `/flow` → Agents → the agent → `permission` → **→** to `read-only`. Now it can look at the
repository and change nothing, which is how you use a loop to *review* rather than to build.

## What you now know

- `agent(...)` versus `agent.new()` is the whole difference between forgetting and remembering.
- `/flow` chooses, and is refused while a flow is running: esc first.
- `/status` is the shape of the run; the lines above the editor are the live version.
- A Ralph loop is steered by editing what it reads.

## Next

[Two agents at once](/guide/tutorial-two-agents) — one that builds and one that reads its work.

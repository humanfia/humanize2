# Showing the working — `/details`

How much of a turn to show: everything the agent did, or only what it said.

Tool calls and thinking are one question — how much of the working to show — so they are one
switch.

```
/details            flips it
/details on         tool calls and thinking are shown
/details off        only what the agent says
```

## What each setting looks like

**Off.** The transcript is the answer: what the agent said, turn after turn. This is the reading
view — a nine-hour Ralph loop is legible as a conversation.

**On.** Every tool the agent reached for and every line it thought aloud goes down as well. This
is the debugging view: it is where you find out that the agent read the wrong file, or spent four
minutes grepping.

Both are the same [events](/reference/agents#watching-a-turn-as-it-happens) — `text`,
`reasoning`, `tool` — and the switch is only about which of them are drawn. Nothing is discarded:
turning it back on does not recover what scrolled past, but the
[trace](/features/tracing) has all of it either way, always.

## It is a screen setting, not an agent setting

Nothing about the run changes. The agent is not told; it does not think less because you are not
looking. A flow that is running is not restarted, and nothing about the
[cycle](/guide/concepts#cycle) or the [trace](/features/tracing) is different.

## From Python

There is no `/details` outside the interface, because there is no screen. The same information
is the event stream:

```python
for event in session.stream("write the tests"):
    if event.kind in ("text", "result"):
        print(event.text)              # /details off
    elif event.kind in ("reasoning", "tool"):
        ...                            # /details on adds these
```

Or over a whole agent, whichever session it came from:

```python
def looking(agent, session, event):
    if event.kind == "tool":
        print(f"{agent.id} used {event.text}")

agent.watch(looking)
```

## When to reach for it

- **On**, the first time you run an unfamiliar flow — you find out what shape its turns are.
- **On**, when a turn is taking far longer than it should.
- **Off**, for a run you are reading rather than debugging, and for anything you are going to
  [`/export`](/features/export) and show somebody.

## See also

- [Cost and rate](/features/tally) — the other readout of a turn in progress
- [Tracing](/features/tracing) — the whole of it, afterwards
- [TUI › Commands](/reference/tui#commands)

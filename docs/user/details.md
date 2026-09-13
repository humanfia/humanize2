# Showing the working — `/details`

`/details` is a switch in the interface that decides how much of a **turn** you see. A turn is
one request to the agent and what it does in reply. It starts **off**: what you watch a flow
for is where it has got to, and what its agents said is that. Turn it on to see every tool
call and every line of thinking while you debug.

## Try it

```
/details            flips it
/details on         all of the working: tool calls, thinking, printed output
/details off        which agent is working, and what it said   ← the default
```

## What each setting looks like

**Off** shows the flow: which agent has started a turn, what it said, and how long it worked.
This is the reading view, and the one you get. A nine-hour Ralph loop reads as a conversation.

```
● claude#a1b2 is working

● Ready. The three failing tests pass now.

✻ Worked for 74s · claude#a1b2
```

**On** also shows every tool the agent reached for, every line it thought aloud, and whatever
its backend printed on the way past — all of it, not a sample. This is the debugging view. It
is where you find out that the agent read the wrong file, or spent four minutes grepping.

Both settings draw from the same [events](/reference/agents#watching-a-turn-as-it-happens):
`text`, `reasoning` and `tool`. The switch only decides which of them are drawn. Nothing is
discarded. Turning it back on does not recover what scrolled past, but the
[trace](/user/tracing) has all of it either way, always.

**You can see which way it is set.** While it is on, the status line under the editor says
`details`, in front of the flow and the directory:

```
details · ◉ chat · ~/work/api                     / commands · esc monitor · ctrl+c exit
```

## What it never hides

A `notice` is humanize saying what it is doing about the turn — waiting out a rate limit,
carrying on as another account, cutting the turn off, taking it away from a backend that had
stopped saying anything. That is not the working, and it is drawn whichever way the switch is
set:

```
● waiting 30s for a rate limit; carrying on as work
```

A turn told to wait half a minute and a turn that has hung look the same from the outside, and
that line is the only thing that tells them apart. It used to be drawn as a tool call, which
meant that asking not to see every file read was also asking not to be told why the run had
gone quiet.

## It is a screen setting, not an agent setting

`/details` changes nothing about the run. The agent is not told about the setting, and it does
not think less because you are not looking. A flow that is running is not restarted. Nothing
about the [epic](/user/concepts#epic) or the [trace](/user/tracing) is different.

## From Python

`/details` does not exist outside the interface, because there is no screen. The event stream
carries the same information:

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

- **On**, the first time you run an unfamiliar flow, to find out what shape its turns are.
- **On**, when a turn is taking far longer than it should.
- **Off**, which is where it starts: for a run you are reading rather than debugging, and for
  anything you will [export](/user/export) and show somebody.

## See also

- [`/monitor`](/reference/tui#watching-the-run) — the flow drawn, and who is working
- [Cost and rate](/user/tally) — the other readout of a turn in progress
- [Tracing](/user/tracing) — the whole of it, afterwards
- [TUI › Commands](/reference/tui#commands)

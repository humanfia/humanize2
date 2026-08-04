# Exporting a transcript — `/export`

`/export` writes what is on the screen to a file:

```
.humanize/<datetime>.session.md
```

Relative to the directory the interface is running in. The name is the moment it was written, so
exporting twice keeps both.

## What it writes

**What is on the screen**: everything drawn in the transcript since the last `/clear`. Stepping
between conversations with **tab** draws each into the same transcript, so what an export holds
is every conversation that has been read rather than only the one showing now. Which
that is, and how to move between them, is
[Many conversations at once](/features/conversations).

**As it was written, not as it was wrapped.** A line too long for your terminal is drawn over
four rows; what is exported is the line. No break where the terminal ran out of room, and none of
the spaces that padded each row out to the edge. A break in the file is a break that was really
there.

Whether tool calls and thinking are in it is whatever [`/details`](/features/details) is showing:
it is the screen that is written.

What is on the screen is not bounded — it is everything since the interface opened, or since the
last `/clear` — so an export of a nine-hour run is the whole of it rather than the tail of it.
The two-thousand-line bound is on what is kept to redraw a conversation you step back onto, not
on what has already been written down the screen. For the tool input and output that never
reached the screen, and for every agent's sessions rather than the ones that were read, use
[`hmz collect`](/features/tracing).

## Copying instead

For a few lines, the mouse is faster and there is no file:

| Gesture | What it takes |
| --- | --- |
| **drag** | Everything between where you pressed and where you let go. |
| **double click** | The word under it — so a path or an id comes whole. |
| **triple click** | The whole line, however many rows it was drawn over. |

The status line says `copied` for a moment, which is the only sign there is.

This copies what was written rather than what was drawn, exactly as `/export` does. The box the
interface opens with is a picture rather than a line, so dragging across it gives you its rows
as they are drawn, borders and all.

**It works over ssh.** The interface has the mouse, so your terminal never sees the drag; what is
selected goes out as OSC 52, the escape a terminal takes for its clipboard — which means it
reaches the clipboard of the machine you are sitting at rather than the one the flow is running
on. Some terminals want it turned on: `set-clipboard on` in tmux, `Allow reporting` in VTE-based
ones. Holding **shift** while dragging is your terminal's own selection instead, which copies the
screen as drawn, wrapping and all.

Changing the width of your terminal lets go of whatever was selected: the lines are wrapped again,
so a selection made against the old wrapping is dropped rather than left pointing a line or two
off.

## The three ways of keeping a run

| | What it holds | Where |
| --- | --- | --- |
| `/export` | the screen: everything since it opened or was last cleared | `.humanize/<datetime>.session.md` |
| the clipboard | whatever you dragged across | your machine's clipboard |
| [`hmz collect`](/features/tracing) | every session of every agent, in full, with tool input and output | `.humanize/<datetime>.trace.json` |

## See also

- [Tracing](/features/tracing)
- [Showing the working](/features/details)
- [TUI › Selecting and copying](/reference/tui#selecting-and-copying)

# Exporting a transcript — `/export`

`/export` writes what is on the screen to a file:

```
.humanize/<datetime>.session.md
```

The file lands in the directory the interface is running in. Its name is the moment it was
written, so exporting twice keeps both. Reach for it when you want to keep a whole run rather
than a few copied lines.

## Try it

Run `/export`. It writes the transcript to `.humanize/<datetime>.session.md`. Open that file to
see everything on the screen since the interface opened or since the last `/clear`.

## What it writes

**What is on the screen** is everything drawn in the transcript since the last `/clear`.
Pressing **tab** steps between conversations and draws each one into the same transcript. An
export therefore holds every conversation you have read, not only the one showing now. To see
which conversations are drawn and how to move between them, read [Many conversations at
once](/user/conversations).

**As it was written, not as it was wrapped.** A line too long for your terminal is drawn over
four rows, but what is exported is the line itself. There is no break where the terminal ran
out of room and none of the padding that stretched each row to the edge. A break in the file is
a break that was really there.

Whether the export includes tool calls and thinking depends on what
[`/details`](/user/details) is showing. It is the screen that is written.

What is on the screen is not bounded. It is everything since the interface opened or since the
last `/clear`. An export of a nine-hour run is therefore the whole of it, not the tail. The
two-thousand-line bound applies to what is kept to redraw a conversation you step back onto,
not to what has already been written down the screen. For tool input and output that never
reached the screen, and for every agent's sessions rather than the ones that were read, use
[`hmz trace collect`](/user/tracing).

## Copying instead

For a few lines, the mouse is faster and leaves no file:

| Gesture | What it takes |
| --- | --- |
| **drag** | Everything between where you pressed and where you let go. |
| **double click** | The word under it — so a path or an id comes whole. |
| **triple click** | The whole line, however many rows it was drawn over. |

The status line says `copied` for a moment. That is the only sign there is.

This copies what was written rather than what was drawn, exactly as `/export` does. The box the
interface opens with is a picture rather than a line. Dragging across it gives you its rows as
they are drawn, borders and all.

**It works over ssh.** The interface has the mouse, so your terminal never sees the drag. What
is selected goes out as OSC 52, the escape a terminal takes for its clipboard. It therefore
reaches the clipboard of the machine you are sitting at, not the one the flow is running on.
Some terminals want it turned on: `set-clipboard on` in tmux, `Allow reporting` in VTE-based
ones. Holding **shift** while dragging is your terminal's own selection instead. It copies the
screen as drawn, wrapping and all.

Changing the width of your terminal lets go of whatever was selected. The lines wrap again, so
a selection made against the old wrapping is dropped rather than left pointing a line or two
off.

## The three ways of keeping a run

| | What it holds | Where |
| --- | --- | --- |
| `/export` | the screen: everything since it opened or was last cleared | `.humanize/<datetime>.session.md` |
| the clipboard | whatever you dragged across | your machine's clipboard |
| [`hmz trace collect`](/user/tracing) | every session of every agent, in full, with tool input and output | `traces/<datetime>.trace.json`, in the run's own epic |

## See also

- [Tracing](/user/tracing)
- [Showing the working](/user/details)
- [TUI › Selecting and copying](/reference/tui#selecting-and-copying)

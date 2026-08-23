---
pageClass: hmz-feature
---

# The terminal can leave

A flow may work longer than an SSH connection or the shell that started it. For an interactive
run, humanize makes that terminal a reader rather than the owner: one process for the workspace
holds the interface on a pseudoterminal (PTY) of its own, and terminals come and go over a
local socket.

Close every reader and the run still has its terminal. Open the same workspace later and the
screen is drawn there again.

<HmzDaemon />

## The PTY belongs to the daemon

The holder is put in a session of its own and left with no controlling terminal. Its standard
input, output and errors are moved onto one PTY, and the interface draws there exactly as it
would have drawn on the shell that opened it — nothing in it has to know whether a person is
still at the other end. It is the machinery underneath a terminal multiplexer, built in rather
than delegated to one.

The socket carries framed terminal output, input, resize notices and control requests, and more
than one terminal may read the same PTY at once. The terminal type is fixed by the shell that
started the holder; the PTY's size changes when an attached terminal reports that its window
changed.

## One workspace, one holder

Two runs in one workspace would both claim the same current setup and the same run history.
When a holder binds it takes a kernel-held lock before an old socket can be replaced, and
however the process ends the kernel drops that lock. Another checkout has another full path and
therefore another holder.

A process number and a socket file are not proof that anything is alive — numbers are reused
and socket files outlive their listeners. A holder counts only when its process still exists
and its socket accepts a connection.

## Leaving is not stopping

Letting go closes readers. It does not signal the flow, close the interface or end the holder:
a disappearing terminal and a decision to stop the work are two different events.

| | |
| --- | --- |
| **A cooperative stop** | asks the interface to close the flow, and gives it time to unwind |
| **A forced stop** | ends the holder itself, leaving the work exactly where the process was — the last resort for a run that will not unwind |

This protects a run from terminal and SSH loss, not from the loss of its host or the daemon
process. After either of those, persistence makes the run inspectable and a resumable flow may
start another run from saved state; it does not bring the old process back. A non-interactive
invocation stays in its own process, because there is no terminal to proxy.

## Replay is a screen, not a transcript

A newly attached terminal begins empty and may have different modes and dimensions from the one
before it. The daemon sizes the PTY for it, then asks the interface to draw the whole current
screen from the top. The first terminal may also receive the bounded output drawn before
anybody had ever attached; after that, output drawn while nobody is reading is discarded.

So a later reconnect sees the current screen because the interface redraws it, not because the
daemon recorded every byte. The backend's own log and the run journal are the history; replay
is only a way back into the live view.

## A slow reader pays its own cost

PTY output is read once and offered to each attached terminal without waiting on any of them.
Each reader has its own pending buffer; if one stops taking bytes and that buffer grows past
one mebibyte, only that reader is released, and the run, the PTY and every other terminal keep
moving.

The same non-blocking rule applies in the other direction: a large paste is queued for the PTY
rather than allowed to make the only thread carrying screen output wait on the run it serves.

## What is written while it runs

The daemon writes a small, whole-file note saying which process and workspace it holds, when it
began and which terminal type it draws for. Failures that cannot be shown on a terminal are
appended to a log beside it.

The run's journal gains one complete line for each event as the event happens, so an abrupt end
still leaves everything written before it. If the flow is resumable, each change to its state
mapping writes a complete replacement file into place: a reader sees either the old state or
the new one, never a half-written state. What those records preserve is the shape and state of
the run — the coding-agent backend remains the owner of the conversation.

## Where the detail is

- [Run it unattended](/user/unattended) — running with no interactive reader at all
- [Picking a run up](/user/resuming) — what saved state can do after a process has ended
- [Stopping](/user/stopping) — how a flow unwinds, and what a harder stop leaves behind
- [Daemon reference](/reference/daemon) — lifecycle, terminal rules and the on-disk note
- [Tracing](/user/tracing) — the run journal, session links and traces made from them

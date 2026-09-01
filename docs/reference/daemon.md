# Daemon reference

A run of a flow outlives the terminal it was started from. A flow is a loop and a turn thinks
for minutes, so `hmz` holds the [interface](/reference/tui) in a process of its own — one per
directory — and the terminal you are sitting at reads it. Closing that terminal is not a thing
that happens to the run: it goes on taking its turns, and `hmz` in the same directory opens it
again from the top.

That is [`screen`](https://www.gnu.org/software/screen/) underneath, done rather than shelled
out to: a fork so the shell is not waiting, `setsid` so the terminal that started it is no
longer its own — which is what keeps a hangup from reaching it — a second fork so it can never
take another, and its own pseudoterminal so there is a screen to draw on when nobody is reading.

Nothing of the interface knows about any of it. It draws on a terminal, and whether that
terminal is your ssh session or one of these is not something it is told.

## From the prompt

| | |
| --- | --- |
| `hmz` | Reads whichever run is being held in this directory, and starts one where none is. |
| `/detach` | Lets go of this terminal and leaves the flow running. |
| `/exit` | Asks what is to become of a flow that is running: stop it and leave, or leave it running and let go of this terminal. With nothing running it is a window being closed. |
| `ctrl+c` twice | Stops the flow, as it always did. It is not what lets go of a terminal. |
| `ctrl+q` | The same question `/exit` puts, rather than leaving outright. |

## From outside the interface

[`hmz`](/reference/cli#hmz) in a directory is the whole of it at a terminal: it reads whichever
run is being held here, and starts one where none is. There is nothing else to type, because
there is nothing else a person sitting at one of these wants — reading it is what they came for,
and letting go of it is `/detach` once they are in.

Everything else there is to ask of a held run — what is being held on this machine, what one of
them is doing, letting go of every terminal on it, stopping it — is [asked in Python](#python).
Those are things a program does to a run it is looking after, and a program is not sitting at a
terminal to be shown a screen.

## What kind of terminal it draws for

A held run holds one pseudoterminal for its whole life, and takes its kind from the terminal it
was started on — the `TERM` of the shell that first ran `hmz` here. A terminal of another kind
that reads it later is drawn for in that first one's language. [`status()`](#python) says which,
under `term`; stopping the held run and opening `hmz` again on a terminal of the kind you
want is how it changes.

Its size is not like that: every terminal that arrives says how big it is, and the run is laid
out again for it.

## When a run is not held

The interface is opened in this process — exactly as it always was — where there is nowhere to
hand a run over to. Nothing on the line asks for it: what holding a run apart buys is being able
to close the terminal and still have the run, which is not something worth giving up one run at
a time.

- **Output going to a file, or input coming from a pipe.** A held run is read by a terminal
  proxying to it, so there has to be one on both ends — which is also why a suite driving the
  interface itself gets it in this process.
- **`HUMANIZE_DAEMON` set to `off`, `0` or `no`** in the environment, which is what this
  repository's own test suite sets: the machine saying once that runs here are not held, rather
  than every line saying it again. `hmz.daemon.start` asks for a run to be held outright, and
  holds one whatever the variable says.
- Anything at all that stops one being held — a machine that will not fork, a home directory
  that cannot be written, a socket that will not bind. It is said on stderr and then done
  without. What is lost is being able to walk away from the run, which is not a reason to
  refuse to open.

In that case `/detach` says so rather than doing nothing: closing the terminal is what closes
the run, so there is nothing to let go of.

## One per directory

Two runs of one project in one directory would be two flows writing over each other's
[epic](/reference/tracing#epics), so there is one daemon per workspace and `hmz` reads the one
that is there. The line says nothing about what to run — which flow, what drives it and what it
is set up with are [chosen at the prompt](/reference/tui#setting-a-flow-up) and remembered — so a
terminal arriving at a run already being held brings no second answer to how that run is set up,
and there is nothing for the one already running to lose to.

## What is on disk

| Path | |
| --- | --- |
| `~/.humanize/daemons/<project>-<digest>/daemon.sock` | The socket a terminal reaches the run through. `0600`. |
| `~/.humanize/daemons/<project>-<digest>/daemon.json` | The process holding it, the workspace, and when it started. |
| `~/.humanize/daemons/<project>-<digest>/daemon.log` | Whatever could not be said through a terminal about this run: what the daemon itself could not say, and what went wrong in a process reaching for its socket. |

The directory is named for the project and then for the whole path it is at, since two checkouts
of one repository are two workspaces. A note whose process has gone reads as nothing being held:
a socket file outlives the process that bound it, and a stale one would be a terminal that hangs
rather than one that says nothing is running.

## Python

```python
from hmz.daemon import Daemon, daemons, running, start
```

| | |
| --- | --- |
| `running(workspace=None)` | The daemon holding a run in one workspace, or `None`. |
| `daemons()` | Every run being held on this machine, oldest first. |
| `start(opens, workspace=None, *, columns=0, rows=0, seconds=10.0)` | Puts a run where a terminal closing cannot end it, and comes back once it is listening. `opens` is called in the detached process with the held run, and returns when the run is over. |

`Daemon` is `at`, `workspace`, `pid` and `started`, with:

| | |
| --- | --- |
| `alive` | Whether the process holding it is still there. |
| `attach()` | Reads it from this terminal, until it ends or lets go. |
| `status()` | What it says about itself: how many are reading, and what is running. |
| `detach()` | Lets go of every terminal reading it. |
| `stop(seconds=20.0)` | Asks the run to stop, as closing the interface does, and waits for it to go. |
| `kill(seconds=20.0)` | Ends the process holding it, whatever it was doing. |

`start` knows nothing about what a run is: it is handed something that opens one and returns
when it is over. That is what keeps the interface and this apart, and what makes the interface
running under a daemon identical to the interface running under none. What it hands back to the
opener is a `Held`, which is [`hmz.sdk.Session`](/reference/sdk#session) plus the three hooks the
process holding a run registers:

| | |
| --- | --- |
| `redrawn(hook)` | What to call when a terminal arrives, which is to draw the whole screen again. It is called on a thread of its own. |
| `stopping(hook)` | What to call when somebody asks the run to stop from outside it. |
| `says(hook)` | What to add to the answer when somebody asks what is running here. |

## What a terminal is put back to

A run that has let go says so and goes on running, so nothing on the other end is ever going to
write the sequences that leave the alternate screen and show the cursor again. The terminal
reading it writes them itself, whichever way the reading ended — out of the alternate screen,
cursor shown, mouse reporting off, bracketed paste off, keyboard protocol popped, wrapping back
on. A terminal left in a full-screen program's modes is a shell nobody can use.

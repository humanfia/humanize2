# Reporting

humanize is early, so a crash on somebody else's machine is a crash nobody here sees. An
interaction that reads as obvious to its author can read as nonsense to the person who meets
it, and that is not a crash either. humanize can report both, and it asks you once whether it
should.

## Try it

Start the interface. On its first run it asks:

```
   Report what goes wrong to humanize?

   humanize is early, and a crash nobody sees is a bug nobody fixes. Sent: the error
   and where in humanize it happened; which flow was running, and what each of its
   agents was set up to run; … Never sent: nothing you typed: no task, no prompt, no
   line at the prompt; nothing an agent said …

 ❯ 1. yes, report them     what broke, and what was running when it did
   2. no, send nothing     nothing about this machine leaves it
```

**The answer that helps is the one it opens on.** Esc leaves the question unanswered, and
humanize asks again next time: silence is neither a yes nor a no, and a machine that has not
answered sends nothing. `/settings` changes the answer afterwards.

Only the interface asks, because only the interface has somebody to ask. `hmz exec` reports if
the answer is already yes, and is silent otherwise. A headless run must not stop for a
question, and nothing on a CI box should start uploading because nobody was there to say no.

## What is sent

| | |
| --- | --- |
| the error | its type, its message, and where in humanize it happened |
| the run | which flow, how long it had been going, and one line per agent: the CLI, the model, the effort, the account **by name**, what it may do, where its work lands, which skills the flow mounted |
| the machine | which coding agents are installed, which accounts exist and how each was signed in, which skills each CLI would load and which flowverses are here — all by name |
| the friction | what humanize did that you then undid, refused or walked away from, as counts |
| the versions | humanize, Python, and the kind of machine |

## What is never sent

- **Nothing you typed.** No task, no prompt, no line at the prompt.
- **Nothing an agent said.** No transcript, no session log, no tool output.
- **No file, no path outside humanize itself, and no directory name.** A stack frame is named
  by where it sits under humanize, or under whatever humanize is installed beside —
  `hmz/agents/base.py`, `textual/app.py`. A frame in anything else, such as a flow of yours,
  keeps its line number and nothing else. No path, no file name, no module, no function. A home
  directory is replaced wherever it appears, even inside an exception's own message. The
  command line a failed turn ran as is also taken out of the one line Python writes for it. For
  several of these backends that command line holds the prompt.
- **No key, no token, no credential.** Not even the names of the variables an account sets.

The Sentry quickstart turns on three switches that are off here, and the module says why where
they are set. `send_default_pii` attaches the address, the machine's name and, in this SDK,
**the variables of every frame** — which is where the task, the prompt and the answer live.
`enable_logs` is off because what humanize logs is paths and commands. Stack-frame variables
have their own switch, and that is off too. The hostname is not sent either.

One default integration is switched off for the same reason. `ArgvIntegration` attaches
`sys.argv`, and the command `hmz exec -f ralph_loop -a claude/… "$(cat TASK.md)"` puts the
whole task there. It is disabled where the reporter starts. Everything the SDK collects under
`extra` is dropped again on the way out.

## The friction it notices

Not everything worth reporting is an error. humanize counts these cases, because each one is
somebody finding that it does not work the way they expected:

| | |
| --- | --- |
| `unknown-command` | a `/line` that is not one |
| `nothing-started` | a task typed, and nothing ran |
| `changes-dropped` | a menu answered and then thrown away |
| `save-refused` | a save asked for and refused |
| `key-does-nothing` | a key that is offered and does nothing where it was pressed |
| `line-refused`, `lines-never-sent` | something said to an agent that never arrived |

Each one carries counts and names — which sheet, which key, how many. It never records a word
of what was typed.

## From Python

This section is the weaver's, and any layer of humanize itself. A flow says what should go with
a report by handing over something that knows. That thing runs only when a report is actually
being made, so nothing is gathered on a machine that reports nothing:

```python
from hmz import telemetry

telemetry.about("worktrees", lambda: {"held": len(worktrees)})
telemetry.snag("gave-up", after=3)          # not an error, and not what anybody meant either
telemetry.crash(why, doing="my own tool")   # reported, and raised on as it was
```

`telemetry.enabled()` is the answer: `True`, `False`, or `None` for a machine nobody has asked.
`telemetry.SENT` and `telemetry.KEPT` are the two lists this page is written from.

## Turning it off

```sh
HUMANIZE_SENTRY=off hmz          # this run only, whatever is written down
```

`/settings` is the written-down answer, on its first page, beside the list of what a report
carries. The environment wins for one run, and the menu says so when it is set.

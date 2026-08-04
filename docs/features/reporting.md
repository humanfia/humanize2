# Reporting

humanize is early. A crash on somebody else's machine is a crash nobody here sees, and an
interaction that reads as obvious to whoever wrote it and as nonsense to whoever met it is not
a crash at all — so humanize can report both, and asks you once whether it should.

## The question

On the first start of the interface:

```
   Report what goes wrong to humanize?

   humanize is early, and a crash nobody sees is a bug nobody fixes. Sent: the error
   and where in humanize it happened; which flow was running, and what each of its
   agents was set up to run; … Never sent: nothing you typed: no task, no prompt, no
   line at the prompt; nothing an agent said …

 ❯ 1. yes, report them     what broke, and what was running when it did
   2. no, send nothing     nothing about this machine leaves it
```

**The answer that helps is the one it opens on.** Esc leaves it unanswered, which is asked
again next time — silence is neither a yes nor a no, and a machine that has not answered sends
nothing. `/settings` changes it afterwards.

Only the interface asks, because only the interface has somebody to ask. `hmz exec` reports if
the answer is already yes and is silent otherwise: a headless run must not stop for a question,
and nothing on a CI box should start uploading because nobody was there to say no.

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
- **No file, no path outside humanize itself, and no directory name.** A home directory is
  replaced wherever one appears, including inside an exception's own message.
- **No key, no token, no credential** — not even the names of the variables an account sets.

Three switches the Sentry quickstart turns on are off here, and the module says why where they
are set: `send_default_pii` (which attaches the address, the machine's name and, in this SDK,
**the variables of every frame** — where the task, the prompt and the answer live),
`enable_logs` (what humanize logs is paths and commands), and stack-frame variables again on
their own switch. The hostname is not sent either.

One default integration is switched off for the same reason: `ArgvIntegration`, which attaches
`sys.argv` — and `hmz exec -f ralph_loop -a claude/… "$(cat TASK.md)"` puts the whole task
there. It is disabled where the reporter starts, and everything the SDK collects under `extra`
is dropped again on the way out.

## The friction it notices

Not everything worth reporting is an error. These are the ones humanize counts, because each
is somebody finding out that it does not work the way they expected:

| | |
| --- | --- |
| `unknown-command` | a `/line` that is not one |
| `nothing-started` | a task typed, and nothing ran |
| `changes-dropped` | a menu answered and then thrown away |
| `save-refused` | a save asked for and refused |
| `key-does-nothing` | a key that is offered and does nothing where it was pressed |
| `line-refused`, `lines-never-sent` | something said to an agent that never arrived |

Each carries counts and names — which sheet, which key, how many — and never a word of what
was typed.

## From Python

A layer, or a flow, says what should go with a report by handing over something that knows —
run only when a report is actually being made, so nothing is gathered on a machine that reports
nothing:

```python
from hmz import telemetry

telemetry.about("worktrees", lambda: {"held": len(worktrees)})
telemetry.snag("gave-up", after=3)          # not an error, and not what anybody meant either
telemetry.crash(why, doing="my own tool")   # reported, and raised on as it was
```

`telemetry.enabled()` is the answer — `True`, `False`, or `None` for a machine nobody has asked
— and `telemetry.SENT` and `telemetry.KEPT` are the two lists this page is written from.

## Turning it off

```sh
HUMANIZE_SENTRY=off hmz          # this run only, whatever is written down
```

`/settings` is the written-down answer, on its first page, beside the list of what a report
carries. The environment wins for one run, and the menu says so when it is set.

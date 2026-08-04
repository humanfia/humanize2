# History

Everything said at the prompt goes down: the task that started a flow and the words
[put into one already running](/features/steering) alike. Both are things you wrote, and either
may be worth writing again.

## Walking it

**↑** and **↓** walk it — but only off the first and last line, so a prompt of several lines is
still moved around in with the same keys. Over an open [offers list](/features/completion), they
move within the list instead.

## What is walked

What was typed **in this directory**.

Where nothing has been typed here yet, everything ever typed anywhere — so a fresh project still
has something to walk back through.

Which of the two it is is settled when the interface starts, so a history cannot change under you
mid-session. Type one line in a new project, restart, and from then on it is that project's own.

**Commands go down too.** `/flow rlar` is a line you typed, and one you may want back; only a
line identical to the one before it is left out, so holding a key down does not fill the walk
with one thing.

## Where it lives

```
~/.humanize/history.jsonl
```

One line per thing typed, with where it was typed. It is `$HUMANIZE_HOME/history.jsonl` where
that variable is set. Deleting the file loses the history and nothing else.

It is a record of what **you** typed. Nothing an agent said is in it, and nothing a flow sent on
its own is either.

## What it is not

- **Not a session log.** For what actually happened, [`/export`](/features/export) writes the
  transcript and [`hmz collect`](/features/tracing) writes the whole run.
- **Not shared with the flow.** A flow gets the task it was started with; it cannot read the
  history.
- **Not on the command line.** `hmz exec` takes its task as an argument, and your shell's own
  history has it.

## See also

- [Completion](/features/completion)
- [What a project remembers](/features/settings) — the other thing kept between sessions
- [CLI › Files](/reference/cli#files)

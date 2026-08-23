# History

History records everything you type at the prompt. That covers the task that starts a flow, and
the words you [put into one already running](/user/steering). Both are things you wrote, so
you reach for history when you want to write either again.

## Try it

Press **↑** at an empty prompt and the last thing you typed appears. **↑** again walks further
back, **↓** comes forward. The keys act only off the first and last line, so a prompt of
several lines still moves with them; over an open [offers list](/user/completion) they move
within the list instead.

## What is walked

The history holds what you typed **in this directory**. If you have not typed anything here
yet, it holds everything you have ever typed anywhere, so a fresh project still has something
to walk back through.

The interface settles which of the two applies when it starts, and the history cannot change
under you mid-session. Type one line in a new project, restart, and from then on it is that
project's own.

**Commands go down too.** `/flow rlar` is a line you typed, and one you may want back. Only a
line identical to the one before it is left out. Holding a key down does not fill the walk with
one thing.

## Where it lives

```
~/.humanize/history.jsonl
```

The file holds one line per thing typed, with where it was typed. It is
`$HUMANIZE_HOME/history.jsonl` where that variable is set. Deleting the file loses the history
and nothing else.

It is a record of what **you** typed. Nothing an agent said is in it. Nothing a flow sent on
its own is in it either.

## What it is not

- **Not a session log.** For what actually happened, [`/export`](/user/export) writes the
  transcript and [`hmz trace collect`](/user/tracing) writes the whole run.
- **Not shared with the flow.** A flow gets the task it was started with. It cannot read the
  history.
- **Not on the command line.** `hmz exec` takes its task as an argument. Your shell's own
  history has it.

## See also

- [Completion](/user/completion)
- [What a project remembers](/user/settings), the other thing kept between sessions
- [CLI › Files](/reference/cli#files)

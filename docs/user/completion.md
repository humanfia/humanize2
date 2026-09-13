# Completion

Nothing is chosen from a dialog. Completion finishes a half-typed line: as you type a command
or a flow name, it offers what the line could become in a list under the editor. Use it
whenever you do not want to type the rest yourself.

## Try it

Type `/` and a list of commands appears under the editor. Type `/flow ` and the list becomes
the flows humanize knows. Type `$` and it becomes the same flows, under the sigil that
[starts one outright](/reference/tui#starting-a-flow-outright).

## What completion offers

| Typed | Offered |
| --- | --- |
| `/` | the commands, each with a line about what it does and what it takes after its name |
| `/flow ` | the flows there are: the ones humanize ships, the ones every [flowverse](/weaver/flowverses) fetched here holds, and your own `local/` and `user/` ones under `.humanize/flows` here or in your home directory |
| `$` | the same flows. `$ralph_loop fix the build` runs that flow on that line, so the name is finished where it is typed. Nothing is offered past the name: the rest is the prompt, which is prose |

## The keys

| | |
| --- | --- |
| **↑ ↓** | Move within the list. |
| **tab** or **enter** | Take the highlighted offer. |
| **esc** | Dismiss the list. Press it again with no list up and it opens [`/monitor`](/reference/tui#watching-the-run). |

A name that is already whole is offered nothing, whether it is a command or a flow. Enter over
an open list takes what is under the cursor rather than sending the line, so `/flow` — with
`/flowverses` beside it — and `$rlar` — with `$rlar2` beside it — would otherwise be lines
nobody could send. A command name that is whole shows a **hint** instead: type `/afk` and it
shows what the command takes after its name.

An offer is **the whole of what the word becomes**. Taking one replaces what you typed rather
than adding to it.

Completion is reconsidered when the cursor moves as well as when the text does. An offer made
at the end of a line does not stand once the cursor is back in the middle of it.

## What completion does not offer

**A flow anywhere else is a path, and a path is typed.** Finding one would mean reading every
Python file below here to see which declare a flow. That is a guess, and far too slow to make
between keystrokes.

```
/flow ./flows/mine
```

Nothing else completes either. Model ids are chosen where an agent is set up, which is inside
a flow in `/flow`, and you choose from the list the CLI itself said it runs. There is no
completion for a task, because a task is prose.

## Searching on a sheet

The lists a sheet puts up are flows, models and accounts. Narrow them with **s**
instead, since every other letter on a sheet is a key of its own:

- **Flows** narrow by name. What each says about itself sits beside its name and is *not*
  searched, because a subsequence of a sentence matches nearly everything.
- **Models** narrow on a few letters anywhere in the id, since nobody types a model id out.
  **esc** clears what was typed before it steps back.

## See also

- [Starting a flow outright](/reference/tui#starting-a-flow-outright) — what `$` does once the
  name is finished
- [History](/user/history) — the other way to not type something again
- [TUI › Completion](/reference/tui#completion)
- [TUI › Choosing a flow](/reference/tui#choosing-a-flow)

# Completion

Nothing is chosen from a dialog. Completion finishes a half-typed line: as you type a command
or a flow name, it offers what the line could become in a list under the editor. Use it
whenever you do not want to type the rest yourself.

## Try it

Type `/` and a list of commands appears under the editor. Type `/flow ` and the list becomes
the flows humanize knows. Press **↑ ↓** to move through the list, **tab** or **enter** to take
the highlighted offer, and **esc** to dismiss it.

## What completion offers

| Typed | Offered |
| --- | --- |
| `/` | the commands, each with a line about what it does and what it takes after its name |
| `/flow ` | the flows there are: the ones humanize ships, the ones every [flowverse](/guide/flowverses) fetched here holds, and the ones under `.humanize/flows` here or in your home directory |

## The keys

| | |
| --- | --- |
| **↑ ↓** | Move within the list. |
| **tab** or **enter** | Take the highlighted offer. |
| **esc** | Dismiss the list. Press it again with no list up and it stops the flow. |

A command name that is already whole shows a **hint** rather than offers. Type `/afk` and it
shows what the command takes after its name. There is nothing to take, because taking an offer
that is what you have already typed would do nothing.

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

Nothing else completes either. Model ids are chosen where an agent is set up: on the agents
page of `/flow`, or in a saved agent in `/agents`. You choose from the list the CLI itself said
it runs. There is no completion for a task, because a task is prose.

## Searching on a sheet

The lists a sheet puts up are flows, models, skills and accounts. Narrow them with **s**
instead, since every other letter on a sheet is a key of its own:

- **Flows** narrow by name. What each says about itself sits beside its name and is *not*
  searched, because a subsequence of a sentence matches nearly everything.
- **Models** narrow on a few letters anywhere in the id, since nobody types a model id out.
  **esc** clears what was typed before it steps back.

## See also

- [History](/guide/history) — the other way to not type something again
- [TUI › Completion](/reference/tui#completion)
- [TUI › Choosing a flow](/reference/tui#choosing-a-flow)

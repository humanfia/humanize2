# Completion

Nothing is chosen from a dialog. A half-typed line is offered what it could be finished with, in
a list under the editor.

## What is offered

| Typed | Offered |
| --- | --- |
| `/` | the commands, each with a line about what it does and what it takes after its name |
| `/flow ` | the flows there are — the ones humanize ships, the ones every [flowverse](/features/flowverses) fetched here holds, and the ones under `.humanize/flows` here or in your home directory |

## The keys

| | |
| --- | --- |
| **↑ ↓** | Move within the list. |
| **tab** or **enter** | Take the highlighted offer. |
| **esc** | Dismiss the list. Pressed again — with no list up — it stops the flow. |

An offer is **the whole of what the word becomes**, so taking one replaces what was typed rather
than being appended to it.

What is offered is reconsidered when the cursor moves as well as when the text does: an offer
made at the end of a line does not still stand once the cursor is back in the middle of it.

## What is not offered

**A flow anywhere else is a path, and a path is typed.** Looking for one would mean reading every
Python file below here to see which declare a flow — a guess, and far too slow to make between
keystrokes.

```
/flow ./flows/mine.py
```

Nothing else completes either. Model ids are chosen on the `/agents` sheet, where the list is
what the CLI itself said it runs; there is no completion for a task, because a task is prose.

## Searching, on a sheet

The lists a sheet puts up — flows, models, skills, accounts — narrow as you type instead:

- **Flows** narrow by name. What each says about itself is beside its name and is *not* searched:
  a subsequence of a sentence matches nearly everything.
- **Models** narrow on a few letters anywhere in the id, since nobody types a model id out.
  **esc** clears what was typed before it steps back.

## See also

- [History](/features/history) — the other way to not type something again
- [TUI › Completion](/reference/tui#completion)
- [TUI › Choosing a flow](/reference/tui#choosing-a-flow)

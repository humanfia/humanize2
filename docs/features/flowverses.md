# Flowverses

A flowverse is **a git repository of flows**: one `.py` per flow, and whatever they import beside
them under names starting with `_`.

It is cloned into `~/.humanize/flowverses/<name>/`, and every flow in it is then offered as
`<name>/<flow>`.

```sh
hmz exec -f official/rlar -a claude/claude-opus-5:max -a codex/gpt-5.6-sol:max "$(cat TASK.md)"
```

## The two that are always there

| | |
| --- | --- |
| `builtin` | the flows in the package: [`chat`, `ralph_loop`, `stateful_ralph`](/reference/flows#the-flows-humanize-ships) |
| `official` | [humanfia/flowverse](https://github.com/humanfia/flowverse) — everything else humanize offers |

`official` is **listed before it has been fetched**: what there is to run is not the same question
as what has been downloaded. Neither of the two can be taken away.

A flow from a flowverse that has not been fetched says so, rather than saying there is no such
file — the name is right, the download has not happened.

## Adding one

### From a command line

`hmz flowverses` is the same store, reached without opening anything:

```sh
hmz flowverses                       # what places flows come from
hmz flowverses add you/my-flowverse yours
hmz flowverses show yours            # what it holds, by the name -f takes
hmz flowverses fetch yours           # again, or for the first time
hmz flowverses remove yours          # flows and all
```

That is the way in for a machine being set up, a CI job that runs a flow somebody else wrote,
or anywhere the interface is not open. What it added is findable by `-f` at once:

```sh
hmz flowverses add you/my-flowverse yours
hmz exec -f yours/review -a claude/claude-opus-5:high "the payments module"
```

`add` names it after the repository when you do not, as `git clone` does. `list -q` prints just
the names, one a line, for a script to read.

`show` prints the name `-f` takes — so `official/humanize1:gen-plan` rather than the
`official/humanize1` its filename would suggest. Working that out means **importing** the files,
which is what `/flow` does for the same question; `list`, `add` and `fetch` read nothing, so a
repository you have just cloned is never run until you ask what is in it. See
[CLI reference](/reference/cli#hmz-flowverses).

### At the prompt

`/flow` is where they live:

| Key | |
| --- | --- |
| **←** **→** | Walk the places flows come from, a tab apiece — every flowverse, then `local` and `user` |
| **ctrl+n** | Add one: a URL or an `owner/repo`, and a name to keep it under |
| **ctrl+r** | Fetch the open one again, or for the first time |
| **ctrl+x** | Take an added one away, flows and all |

Those keys are there rather than in a menu of their own because that is the moment you find out
that the flow you want is in a flowverse you have not added, or that the one you have is out of
date. A fetch runs off the interface's own loop — it keeps drawing while it clones — and what
became of it is said under the list rather than thrown at you.

## Where a name is looked for

`-f` takes a name or a path. A name is looked for **nearest first**:

| | |
| --- | --- |
| `.humanize/flows/*.py` | this project's own |
| `~/.humanize/flows/*.py` | yours, in every project |
| — | the ones humanize ships, and every flowverse there is |

Nearest wins, so a flow of your own may stand in for one of humanize's by taking its name: a
`.humanize/flows/chat.py` is what `-f chat` runs *in that project*.

What a flow is **called** is a separate question:

| | |
| --- | --- |
| `chat` | one humanize ships |
| `official/rlar` | one a flowverse holds — the one spelling nothing can stand in for |
| `.humanize/flows/chat.py` | this project's own |
| `~/.humanize/flows/chat.py` | yours, in every project |

So yours is listed *beside* humanize's rather than instead of it, and what each was
[set up to run](/features/settings) is remembered apart.

Anything with a slash or an extension in it is a path, taken as given. A file whose name starts
with `_` is not a flow.

## A flowverse is a library too

`calls` takes exactly what `-f` takes, so a flow in a flowverse can be reached for from inside
another flow:

```python
from hmz.runner import calls

plan = calls("official/humanize1:gen-plan")
plan(agents, f"plan this first: {task}")
```

A name nothing answers to is refused where you ask for it rather than an hour into your loop.

## Making one

Any git repository will do. There is no manifest and nothing to register:

```
my-flowverse/
├── review.py        →  yours/review
├── nightly.py       →  yours/nightly
└── _shared.py       →  not a flow; imported by the two above
```

Add it with **ctrl+n** in `/flow`, or clone it into `~/.humanize/flowverses/<name>/` yourself.
There is a [tutorial](/guide/tutorial-flowverse).

::: danger Adding one is trusting that repository with this machine
A flow is a Python file, and reading one means **running** it. Listing what a flowverse holds
imports every file in it. Add the ones you would clone and run. See
[Security](/guide/security).
:::

## See also

- [Tutorial: publish a flowverse](/guide/tutorial-flowverse)
- [Flows › Flowverses](/reference/flows#flowverses)
- [The official flowverse](/reference/flows#the-official-flowverse)

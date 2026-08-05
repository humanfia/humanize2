# Flowverses

A flowverse is **a git repository with a `flows/` directory in it**: one directory per flow —
the `__init__.py` that is the flow, whatever it imports beside it and the `skills/` it brings —
or a single `.py` for a flow that needs neither. A name starting with `_` is not a flow but what
the flows beside it share.

It is cloned into `~/.humanize/flowverses/<name>/`, and every flow in its `flows/` is then
offered as `<name>/<flow>`. Nothing outside that directory is read, so the repository is free to
be a repository — a README, a pyproject, a test suite of its own.

```sh
hmz exec -f official/rlar -a claude/claude-opus-5:max -a codex/gpt-5.6-sol:max "$(cat TASK.md)"
```

## The two that are always there

| | |
| --- | --- |
| `builtin` | the flows in the package: [`chat`, `ralph_loop`, `stateful_ralph`](/reference/flows#the-flows-humanize-ships) |
| `official` | [humanfia/flowverse](https://github.com/humanfia/flowverse) — everything else humanize offers |

`official` is **listed before it has been fetched**: what there is to run is not the same question
as what has been downloaded. Opening `/flow` fetches whatever has never been fetched, so in
practice it is there by the time you look. Neither of the two can be taken away.

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

`/flowverses` is the places themselves:

![/flowverses: the places flows come from, and what one of them holds](/demo/flowverses.gif)

| Key | |
| --- | --- |
| **enter** | What that flowverse holds — which means importing its flows, so it is asked of the one you open rather than of the whole list |
| **a** | Add one: a URL or an `owner/repo`, and a name to keep it under — blank for the repository's own |
| **r** | Fetch the one under the cursor again, or for the first time |
| **d** **d** | Take an added one away, flows and all |

What one holds is a reading rather than a menu — each flow's name and the line it says about
itself. Which of them to run is `/flow`'s question, where every place's flows are:

![what builtin holds: chat, ralph_loop and stateful_ralph, each with the line its flow says about
itself](/demo/flowverse-holds.png)

One that has never been fetched has nothing to read yet, and says so — and that **r** fetches
it — rather than reading as a place with nothing in it.

`/flow` is where the flows are, and it steps between the same places:

| Key | |
| --- | --- |
| **←** **→** | Step between the places flows come from, a list apiece — every flowverse, then `local` and `user` where either holds anything |
| **f** | Copy the flow under the cursor into `.humanize/flows/`, to change |

A flow whose file will not import is still listed, under the name it would have had and with
nothing beside it: it is a flow somebody named, and saying so where it is chosen beats leaving
it off the list and letting you wonder where it went.

The two are apart because they are two questions. Which flow to run is the one `/flow` asks;
what places there are, and what is in them, is about the list rather than about the row under
the cursor. What stays on `/flow` is **f**, which is about the flow you are looking at: the
moment you find out that it is *nearly* what you want. A flow is a directory, so the copy is
the whole of it, skills and all, and it lands under the name it already had: yours are looked
in first, so from then on that name means your copy. Editing a flowverse's own copy would not
keep, since fetching it again takes what that repository says now. A fetch runs off the
interface's own loop — it keeps drawing while it clones — and what became of it is said under
the list rather than thrown at you. Opening `/flow` fetches whatever has never been fetched,
in the background and without moving what you are reading, so **r** is for fetching one
*again*.

Typing `/flow` and pressing enter still sends `/flow`. A command that has been written out
whole is offered nothing to finish it with, so `/flowverses` never sits under a cursor waiting
to be taken by the enter that meant to send the shorter one.

## Where a name is looked for

`-f` takes a name or a path. A name is looked for **nearest first**:

| | |
| --- | --- |
| `.humanize/flows/*/` | this project's own |
| `~/.humanize/flows/*/` | yours, in every project |
| — | the ones humanize ships, and every flowverse there is |

Nearest wins, so a flow of your own may stand in for one of humanize's by taking its name: a
`.humanize/flows/chat/__init__.py` is what `-f chat` runs *in that project*.

What a flow is **called** is a separate question:

| | |
| --- | --- |
| `chat` | one humanize ships |
| `official/rlar` | one a flowverse holds — the one spelling nothing can stand in for |
| `.humanize/flows/chat` | this project's own |
| `~/.humanize/flows/chat` | yours, in every project |

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
├── flows/
│   ├── review/           →  yours/review
│   │   ├── __init__.py       the flow
│   │   └── skills/           what it brings, mounted onto its agents' sessions
│   │       └── review-notes/SKILL.md
│   ├── nightly.py       →  yours/nightly, a flow that brings nothing
│   └── _shared.py       →  not a flow; imported by the two above
├── tests/               →  not read: only flows/ is
└── README.md
```

Add it with **a** in `/flowverses`, or clone it into `~/.humanize/flowverses/<name>/` yourself.
There is a [tutorial](/guide/tutorial-flowverse).

::: danger Adding one is trusting that repository with this machine
A flow is Python, and reading one means **running** it. Listing what a flowverse holds
imports every file in its `flows/`. Add the ones you would clone and run. See
[Security](/guide/security).
:::

## See also

- [Tutorial: publish a flowverse](/guide/tutorial-flowverse)
- [Flows › Flowverses](/reference/flows#flowverses)
- [The official flowverse](/reference/flows#the-official-flowverse)

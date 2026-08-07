# Flowverses

A [**flowverse**](/reference/flows#flowverses) is a git repository with a `flows/` directory in
it. Put your flows in one and they are offered by name, as `<flowverse>/<flow>`, on every
machine you add it to. Reach for a flowverse when you want to publish a flow somebody else can
run, or install one somebody else published.

## Try it

Publish two flows in a repository, add the repository, and run one by name. Four steps take you
from an empty directory to a running flow.

1. **Lay out the repository.** A flowverse is a git repository with a `flows/` directory in it.
   There is no manifest and nothing to register.

```
my-flowverse/
├── README.md
└── flows/
    ├── review/          →  yours/review
    │   ├── __init__.py      the flow
    │   └── skills/          what it brings, if it brings any
    ├── nightly.py       →  yours/nightly, a flow that brings nothing
    └── _shared.py       →  not a flow; imported by the two above
```

The `review` flow is a directory whose `__init__.py` holds the function marked `@flow`:

```python
# flows/review/__init__.py
"""Review the current diff and write the findings to REVIEW.md."""

from hmz.flows import Agent, flow


@flow
def run(agents: tuple[Agent], task: str) -> None:
    (agent,) = agents
    agent(f"Read the diff and write what is wrong to REVIEW.md.\n\n{task}", suppress=True)
```

The repository now has two flows: `review` and `nightly`.

2. **Push it.**

```sh
cd my-flowverse
git init -q && git add -A && git commit -qm "two flows"
git remote add origin git@github.com:you/my-flowverse.git
git push -u origin main
```

The repository is now at `you/my-flowverse`.

3. **Add it.**

```sh
hmz flowverses add you/my-flowverse yours
hmz flowverses show yours
```

`add` clones the repository into `~/.humanize/flowverses/yours/`. Every flow in it is then
offered as `yours/<flow>`, and `show` prints what it holds by the name `-f` takes.

4. **Run one.**

```sh
hmz exec -f yours/review -a claude/claude-opus-4-8:high "the payments module"
```

`yours/review` is the qualified spelling, `<flowverse>/<flow>`, the one spelling nothing can
stand in for.

That is the whole feature: flows in a repository are offered by name, on every machine you add
the repository to.

## The two that are always there

| | |
| --- | --- |
| `builtin` | the flows in the package: [`chat`, `ralph_loop`, `stateful_ralph`](/reference/flows#the-flows-humanize-ships) |
| `official` | [humanfia/flowverse](https://github.com/humanfia/flowverse) — everything else humanize offers |

Run a flow from `official` by giving `-f` the flowverse and the flow:

```sh
hmz exec -f official/rlar -a claude/claude-opus-5:max -a codex/gpt-5.6-sol:max "$(cat TASK.md)"
```

`official` is **listed before it has been fetched**. What there is to run is not the same
question as what has been downloaded. Opening `/flow` fetches whatever has never been fetched,
so in practice it is there by the time you look. Neither of the two can be taken away.

A flow from a flowverse that has not been fetched says so rather than saying there is no such
file. The name is right; the download has not happened.

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

Use this for a machine being set up, a CI job that runs a flow somebody else wrote, or anywhere
the interface is not open. What it added is findable by `-f` at once:

```sh
hmz flowverses add you/my-flowverse yours
hmz exec -f yours/review -a claude/claude-opus-5:high "the payments module"
```

`add` names it after the repository when you do not, as `git clone` does. `list -q` prints just
the names, one a line, for a script to read.

`show` prints the name `-f` takes. It prints `official/humanize1:gen-plan`, not the
`official/humanize1` its filename would suggest. Working that out means **importing** the
files, which is what `/flow` does for the same question. `list`, `add` and `fetch` read
nothing, so a repository you have just cloned is never run until you ask what is in it. See
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

What a flowverse holds is something you read rather than choose from. It shows each flow's name
and the line it says about itself. Which of them to run is `/flow`'s question, where every
place's flows are:

![what builtin holds: chat, ralph_loop and stateful_ralph, each with the line its flow says
about itself](/demo/flowverse-holds.png)

A flowverse that has never been fetched has nothing to read yet. It says so, and says that
**r** fetches it, rather than reading as a place with nothing in it.

`/flow` is where the flows are, and it steps between the same places:

| Key | |
| --- | --- |
| **←** **→** | Step between the places flows come from, a list apiece — every flowverse, then `local` and `user` where either holds anything |
| **f** | Copy the flow under the cursor into `.humanize/flows/`, to change |

A flow whose file will not import is still listed, under the name it would have had and with
nothing beside it. It is a flow somebody named. Saying so where it is chosen beats leaving it
off the list and letting you wonder where it went.

The two are apart because they are two questions. Which flow to run is the one `/flow` asks.
What places there are, and what is in them, is about the list rather than the row under the
cursor. What stays on `/flow` is **f**, which is about the flow you are looking at: the moment
you find out it is *nearly* what you want.

A flow is a directory, so the copy is the whole of it, skills and all, and it lands under the
name it already had. Yours are looked in first, so from then on that name means your copy.
Editing a flowverse's own copy would not keep, since fetching it again takes what that
repository says now.

A fetch runs off the interface's own loop. It keeps drawing while it clones, and what became of
it is said under the list rather than thrown at you. Opening `/flow` fetches whatever has never
been fetched, in the background and without moving what you are reading, so **r** is for
fetching one *again*.

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

Nearest wins. A flow of your own may stand in for one of humanize's by taking its name. A
`.humanize/flows/chat/__init__.py` is what `-f chat` runs *in that project*.

What a flow is **called** is a separate question:

| | |
| --- | --- |
| `chat` | one humanize ships |
| `official/rlar` | one a flowverse holds — the one spelling nothing can stand in for |
| `.humanize/flows/chat` | this project's own |
| `~/.humanize/flows/chat` | yours, in every project |

Yours is listed *beside* humanize's rather than instead of it, and what each was [set up to
run](/guide/settings) is remembered apart.

Anything with a slash or an extension in it is a path, taken as given. A file whose name starts
with `_` is not a flow.

## A flowverse is a library too

`calls` takes exactly what `-f` takes, so a flow in a flowverse can be called from inside
another flow:

```python
from hmz.flows import calls

plan = calls("official/humanize1:gen-plan")
plan(agents, f"plan this first: {task}")
```

A name nothing answers to is refused where you ask for it, rather than an hour into your loop.
Publish two small flows rather than one large one for exactly this reason.

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

| Rule | |
| --- | --- |
| the flows go in `flows/` | and nothing outside it is read, or run |
| one directory per flow | its `__init__.py` holds the function marked `@flow` |
| or a single `.py` | for a flow with nothing to bring and nothing to import |
| a name starting with `_` is not a flow | which is where shared code goes |
| the flow's docstring's first line | is what is shown beside its name |
| one file may hold several | `@flow(name="…")`, run as `<flow>:<name>` |

Add it with **a** in `/flowverses`, or clone it into `~/.humanize/flowverses/<name>/` yourself.

Whoever adds your flowverse is trusting it with their machine. Earn it. Say in the README:

- **What each flow drives**: how many agents, and what each is for.
- **Which backends it needs.** A flow that hangs a `PERMISSION_REQUEST` hook needs Claude Code
  or Codex; one built on `pursue` needs a backend with a goal feature.
- **What it writes.** Files, branches, commits, pushes.
- **The `hmz exec` line that starts it**, verbatim. Each flow humanize ships names its own in
  its docstring; do the same.

::: danger Adding one is trusting that repository with this machine
A flow is Python, and reading a flow means **running** it. Listing what a flowverse holds
imports every file in its `flows/`. Add the ones you would clone and run, exactly as you would
install a package.

So: no side effects at import time, nothing that reaches the network as the module loads, and
no `_shared.py` that does anything on import beyond defining things. Whatever a flow does as it
is imported is the flow's own business, and it fails for somebody who was only browsing the
list. See [Security](/guide/security).
:::

Check it in the repository's own CI before anybody else does:

```python
from hmz.flows import drives, wanted

drives("yours/review")     # loads it exactly as `-f` would
wanted("yours/review")     # what somebody choosing the agents will be asked
```

A flow that stopped loading is a red build.

## See also

- [Flows › Flowverses](/reference/flows#flowverses)
- [The official flowverse](/reference/flows#the-official-flowverse)
- [Testing a flow](/guide/testing-flows)

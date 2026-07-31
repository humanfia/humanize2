# TUI reference

`hmz` with no command opens the terminal interface. There is no command that opens it too: one
way in is one way in.

It is a coding agent's own terminal with a [flow](concepts.md#flow) underneath instead of one
agent — a transcript, a multi-line editor under it, and a status line under that.

## Table of Contents

- [The screen](#the-screen)
- [Keys](#keys)
- [Commands](#commands)
- [Talking to a running flow](#talking-to-a-running-flow)
- [Questions, and being away](#questions-and-being-away)
- [Completion](#completion)
- [History](#history)
- [What each agent runs](#what-each-agent-runs)
- [Where each agent works](#where-each-agent-works)
- [What each agent is loaded with](#what-each-agent-is-loaded-with)
- [Setting a flow up](#setting-a-flow-up)
- [What it remembers](#what-it-remembers)
- [Colours](#colours)
- [What it will not do](#what-it-will-not-do)

## The screen

```
┌──────────────────────────────────────────────────────────────────────┐
│  the transcript: what each agent said, one turn after another        │
│                                                                      │
├──────────────────────────────────────────────────────────────────────┤
│                       builder · claude/claude-opus-4-8:high          │  ← what each agent runs
│                       reviewer · codex/gpt-5.6-sol:high              │
│                       48.2k tokens · 91/s                            │
│ ❯ type here                                                          │  ← the editor
├──────────────────────────────────────────────────────────────────────┤
│ ⠋ builder… (73s · esc to interrupt)      enter say · / commands · …  │  ← the status line
└──────────────────────────────────────────────────────────────────────┘
```

**At the top**, the box it opens with: the name drawn large, the version, what humanize is, and
two lines on how to begin. Nothing about what is set up to run or where it would run — the
transcript is a record, so a copy of either up there could only ever be the copy that was true
when you opened it. Both are on the lines round the editor, which are redrawn.

**Above the editor**, one line per agent the flow drives: the name the flow calls it, then what
it runs as `cli/model:effort`, then the machine its turns land on where that is not this one.
Under them, what the run has cost so far and the rate it is
costing it at — per model, since two agents at one model are one bill, and over a recent window
only, so a flow that has stopped reads as stopped.

**The status line, left:** what is running, if anything is — whose turn it is and how long it
has been going. Between two turns it names the flow and how long the run has been going, since
a flow that sleeps off a round, commits, and reads what the last turn wrote has not stopped. A
flow that has run out of things to do until you say something says `waiting for you`. With
nothing running at all, it names the flow that is set up to run and the directory it would run
in, with your home written as `~`.

**The status line, right:** the keys that do something *right now*, and only those. A shortcut
listed in a state it does nothing in is worse than one that is not listed at all, and there is
nowhere else to look them up.

## Keys

| Key | What it does |
| --- | --- |
| **enter** | Sends what is typed. Over an open [offers list](#completion), takes what is highlighted instead. |
| **ctrl+j** | Breaks the line, which is what enter would do anywhere else. |
| **shift+tab** | Steps to the next flow, carrying over what each agent runs. Refused while a flow is running, and not the interface's while a sheet is open — there it turns the sheet's [tabs](#what-each-agent-runs) back. |
| **esc** | Stops the flow — the whole flow, not just the turn. Dismisses the offers list first, if one is open. Silent when nothing is running. |
| **ctrl+c** | Takes back the nearest thing there is to take back: what is half-typed if anything is, the flow if not. Twice in a row leaves. |
| **↑ / ↓** | Walks what was typed here before — but only off the first and last line, so a prompt of several lines is still moved around in. Over an open offers list, moves within the list. |
| **tab** | Takes the highlighted offer. The offers' alone; it does nothing when none are showing. |

Leaving is always two presses and never one, whatever was going on. The second ctrl+c has to
land within two seconds of the first to count as the same one.

Focus cannot leave the editor. There is nowhere else for it to go.

## Commands

A line beginning with `/` is a command; any other line is said to the agent. Type `/` and the
list appears under the editor with a line about each.

| Command | Takes | What it does |
| --- | --- | --- |
| `/flow` | `[path]` | Switches which flow runs, then [how it is set up](#setting-a-flow-up) if it takes any setting up, then what each of its agents runs. With a path, takes that file. Stops whatever was running — a flow is chosen in order to be run. Looking and leaving without choosing changes nothing. |
| `/config` | | Sets up the flow itself, for a flow that says it can be. See [below](#setting-a-flow-up). |
| `/agents` | | Sets what each agent of the current flow runs, one at a time, by the name the flow calls it — and, on **ctrl+a**, [where its turns land](#where-each-agent-works), and on **ctrl+s**, [which of its CLI's skills it is loaded with](#what-each-agent-is-loaded-with). It does not ask how the flow itself is set up; `/config` is that half. |
| `/status` | | How the run is going: who is working, every handover between agents with how often it happened, and what each model has cost. That directed graph is the shape of the run. |
| `/details` | `[on\|off]` | Shows or hides tool calls and thinking. They are one question — how much of the working to show — so they are one switch. |
| `/afk` | `[on\|off]` | Whether an agent may stop and ask you something. See [below](#questions-and-being-away). |
| `/clear` | | Clears the screen, and nothing else. What is running is left running. |
| `/export` | | Writes the transcript to `.humanize/<datetime>.session.md`. |
| `/exit` | | Leaves. |

`/details` and `/afk` flip when given nothing, and take `on` or `off` when you want to say
which.

**`hmz collect` and `hmz anchor` are deliberately not here.** Neither is a thing to do to a
flow that is running, and a command that only ever means one thing is a command line.

## Talking to a running flow

The editor means both things at once. A line typed while a turn is running is put *into* that
turn rather than starting another, so the agent takes it into account instead of being
restarted with it. If no turn is open, it is held for the next one — a line to a running flow
is never dropped.

A line that is being held is **pinned onto the editor** rather than written into the
transcript, dimmed, behind the same `❯`. It shares the block that sits on the prompt with
what the run is running as, and the two are read from the bottom up — the last line typed and
the running total end on the same row:

```
❯ and fix the tests too                    assistant · claude-opus-5:high
❯ then push                                     12.3k tokens · 84/s
────────────────────────────────────────────────────────────────────────
❯ █
```

It has not been said to anybody yet, and the transcript is what happened. The moment something
takes it — the next turn, or a flow waiting to be told what to do — it comes off the pin and
into the transcript, in front of the turn that took it.

**Handed to a backend is not the same as taken.** A line put into a turn that is already
running stays pinned too, now against the agent it went to:

```
❯ and fix the tests too · with claude#3a15
```

It comes off only when that agent's own turn says the words are in front of it — each backend
says so in its own way, and humanize waits for whichever it is. A turn that ends without ever
saying it had the line puts it back into the transcript as never sent, so a line typed at an
agent that was not listening is never quietly counted as said.

**Lines go one at a time, in the order you typed them.** Everything typed joins one queue and
leaves it a line at a time: the next one goes only once the turn has said it has the one before
it, and a turn takes one waiting line rather than the whole queue. Three `hi` in a row are three
things said and come back as three answers — handing a backend two at once has it run them
together and answer once.

The pin is held to a few rows: a line longer than the screen is cut with an ellipsis rather
than wrapped, and what will not fit is counted instead — `… 3 more waiting`, or `… 6 more
lines` for one message too long to show whole. Only what is drawn is cut; the whole of what
you typed is what goes. A flow that ends, however it ends, drops whatever is still pinned into
the transcript and says it was never sent.

A line reaches the agent that has a turn open, not whichever was named last: an agent between turns
may still be holding a session that would take it silently.

How far "into the turn" it gets depends on the backend:

| Backend | What a mid-turn line does |
| --- | --- |
| **Claude Code** | Answered within the same turn. The turn is over once the agent has answered everything it was told, not when it first stops. |
| **Codex** | A steer on the turn its app server is running. |
| **Kimi Code** | Queued, then steered into the turn already running. |
| **pi** | A steer on the run it is making, taken into it rather than answered after it. |
| **opencode**, **mimocode** | Nothing: a run per turn has ended by the time there is anything to say to it. |

An [anchored](remote-execution.md) Claude ends its process with each turn so that its work
reaches the target before the turn says it landed — so it hears you between turns rather than
during one. An anchored Codex keeps one app server for the life of the agent and can be steered
throughout, at the cost of that same guarantee.

## Questions, and being away

An agent may stop mid-turn to ask you something. The question and whatever it offered are
shown, and the next line you type is the answer rather than a word put into the turn — the
status line says `enter answer` while that is so.

`/afk` says you are not there. An agent that wants to ask is then told nobody answered and
carries on, rather than waiting on a reply that is not coming. Asking starts **allowed**: an
agent that really needs a person gets one unless it has been said that none is there.

A question still up when the flow ends or is stopped ends with it, so stopping a flow is never
blocked on one.

## Completion

Nothing is chosen from a dialog. A half-typed line is offered what it could be finished with,
in a list under the editor:

- `/` offers the commands, each with a line about what it does and what it takes after its
  name.
- `/flow ` offers the flows there are — the ones humanize came with, and the ones under
  `.humanize/flows` here or in your home directory.

An offer is the whole of what the word becomes, so taking one replaces what was typed rather
than being appended to it. What is offered is reconsidered when the cursor moves as well as
when the text does: an offer made at the end of a line does not still stand once the cursor is
back in the middle of it.

A flow anywhere else is a path, and a path is typed. Looking for one would mean reading every
Python file below here to see which declare a flow — a guess, and far too slow to make between
keystrokes.

## History

Everything said goes down: the task that started a flow and the words put into one already
running alike. Both are things you wrote, and either may be worth writing again.

↑ and ↓ walk it. What is walked is what was typed *in this directory* — and, where nothing has
been typed here yet, everything ever typed anywhere, so a fresh project still has something to
walk back through. Which of the two it is is settled when the interface starts, so a history
cannot change under you mid-session.

## What each agent runs

`/agents` asks it one agent at a time, by the name the flow calls each. A CLI and a model are
one choice — a model belongs to the CLI that runs it — so picking a row picks the pair. They
are read one CLI at a time all the same:

```
   claude · codex · kimi · mimo · opencode · pi   tab/shift+tab to switch

     1. claude-opus-5           claude
   ❯ 2. claude-sonnet-5         claude

   ◉ max effort  ←/→ to adjust · ◉ on this machine  ctrl+a to move · ◉ every skill  ctrl+s to choose
```

A tab per CLI **that is actually installed here**, and its models under it. **tab** turns to
the next, **shift+tab** to the one before, and they wrap. One CLI on its own is a heading
rather than a row of tabs: there is nowhere to switch to, so nothing says there is.

Every model of every CLI in one list is a list that grows each time any of them ships a model,
and one you scroll to the end of to find one thing is one you read rather than use.

Typing narrows the list you are looking at — `cop` finds `claude-opus-5`, since nobody types a
model id out — and belongs to the tab it was typed into: switching starts the next CLI's list
fresh rather than showing it through the last search.

Under the models, the things that are adjusted rather than chosen: **←/→** the effort,
**ctrl+w** [swarm mode](agents.md#efforts) for a model that has one, **ctrl+a**
[where it works](#where-each-agent-works), **ctrl+s**
[what it is loaded with](#what-each-agent-is-loaded-with). Enter takes the row under the
cursor and asks about the next agent the flow drives.

## Where each agent works

On the `/agents` sheet, **ctrl+a** asks where that agent's turns land. It is a second question
about the same agent rather than a way of running the model, which is why it is a key and not a
row: the tuning line under the models says `◉ on this machine · ctrl+a to move`.

The sheet lists what this machine can see — each container that is running, each host with an
entry in your `~/.ssh/config` — and anything else is a target you type:

| Typed | Where the work goes |
| --- | --- |
| *(nothing)* | this machine |
| `docker://<container>` | a container that is already running |
| `ssh://<host>` | a host you can reach |
| `tcp://<host>:<port>` | a coganchor target listening there |

The agent itself still runs here whatever you choose — its credentials, its state directory and
its link to its model provider stay put. What moves is the project it reads and the commands it
runs. See [Remote execution](remote-execution.md).

Two agents of one flow may work on two machines, since it is a setting of the agent. A target
that cannot be read is said so when the flow is started, before any turn has run.

## What each agent is loaded with

On the same sheet, **ctrl+s** asks which of that CLI's skills this agent is to have. Another
second question about the agent, so another key rather than a row: the tuning line says
`◉ every skill · ctrl+s to choose`.

```
   ❯ 1. [✔] code-review    Review the current diff… (yours)
     2. [ ] dataviz        Use this skill whenever you… (yours)
     3. [✔] housekeeping   Tidies the tree (this project)
```

The skills are found where the CLI itself looks — yours and this project's, read for the name
and the line each describes itself with — and nothing is asked of the CLI, which would mean
starting it. Every box starts ticked, which is how a CLI comes. **Space** switches the one
under the cursor, enter takes the lot, and esc leaves the agent loaded as it was.

What it answers with is the skills the agent **has**, so an agent that has been asked has
exactly those from then on. It is a setting of the agent, so the reviewer reading a change
need not be carrying what the builder writing it was. What each backend does with it, and what
a CLI with no way of being told anything does, is in
[Agents](agents.md#which-skills-an-agent-is-loaded-with).

## Setting a flow up

Some flows take settings of their own — `humanize1` takes twenty-three. A flow says so by
[declaring a model](flows.md#settings-of-the-flows-own), and the sheet is that model with a
cursor on it: one row per setting, its name, what it is set to, and the line the flow declared
it with.

```
   gen-idea  ·  open the idea into a draft
     1. gen_idea                     on           open the idea into a repo-grounded draft
     2. n                            6            --n: how many directions explore the idea
   ❯ 3. idea_output                  docs/d.md▏   --output: where the draft goes

   gen-plan  ·  turn the draft into a plan
     4. gen_plan                     on           turn the draft into a plan, against review
     5. gen_plan_mode                discussion   --discussion or --direct: converge, or write it once
```

A setting that is written carries a caret under the cursor, where the next letter would land;
one that is stepped does not, and the keys at the bottom say which it is. A blank one would
otherwise read as a setting nothing can be typed into.

A flow with many settings groups them: each field says which part of the sheet it belongs
under, and the sheet draws a heading above each group. The arrows walk the settings and step
over the headings.

| Key | What it does |
| --- | --- |
| **↑ ↓** | Move between settings |
| **← →** | Move the one under the cursor along: a switch flips, a choice steps, a number goes up or down by one |
| letters | Write the one under the cursor, for the ones that are written rather than stepped |
| **enter** | Take the lot, and go on to the agents |
| **esc** | Back to the flows, changing nothing |

It comes between choosing the flow and choosing its agents, which is the only place it can:
only the flow just chosen says what there is to set. `/config` opens it on its own, and
`/agents` never does — the two are halves of one question, and each asks only its own. So
does `hmz -f <flow> -c <setup.yaml>`, which opens the interface already set up. See
[CLI › hmz](cli.md#hmz).

Nothing in the interface knows what any of the settings mean. The types say how a value moves,
and the flow's own model says which combinations it will not take — so a flow that refuses
`gen_idea` without `gen_plan` refuses it here, in its own words, rather than an hour in.

## What it remembers

Opening the interface again in the same project finds it set up the way you left it: the flow
that was last run there, for each flow that workspace has run, what each of its agents was
running, where its turns landed and which skills it was loaded with — and how the flow
itself was set up.

Kept per flow — by the name humanize's own flows have, and by the path yours have, so a flow of
yours cannot inherit the agents or the settings of the one it shares a name with. Per flow
rather than per workspace alone, because what an agent runs is only meaningful
against the flow driving it — a flow's second agent is its reviewer, and the flow before it had
no second agent at all. Keyed by the name the flow calls each one, so a flow that grows an
agent in the middle does not silently hand the reviewer's model to the builder. What was set up
is read back through the flow's own model, so a setting the flow has since dropped or renamed
is one it starts over from rather than one that quietly comes back.

It lives in `~/.humanize/settings.yaml`. See [CLI reference](cli.md#files).

## Colours

Drawn in your terminal's own colours, and it never asks the terminal what they are. Every
surface is the terminal's background, and everything drawn is one of the sixteen colours your
terminal already has a setting for, or a reversal of what is already there. A colour of its own
would be a guess about the background it lands on.

`NO_COLOR` is honoured.

## What it will not do

- **Open twice.** `hmz` with no command is the only way in — with or without `-f`, `-c` and
  `-a`, which say how it opens rather than opening a second one.
- **Run two flows at once.** Choosing a flow stops whatever was running.
- **Guess at a bad line.** A line it cannot carry out is shown and the interface stays up. Only
  `/exit` and two ctrl+c close it.
- **Ask the flow anything.** What is drawn beside and under the transcript is kept from the
  turns going past. A flow is a Python file that may branch any way it likes, so that is the
  only place a run is ever visible.

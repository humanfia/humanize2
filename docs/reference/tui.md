# TUI reference

`hmz` with no command opens the terminal interface. There is no command that opens it too: one
way in is one way in.

It is a coding agent's own terminal with a [flow](/guide/concepts.md#flow) underneath instead of one
agent — a transcript, a multi-line editor under it, and a status line under that.

## The screen

```
┌──────────────────────────────────────────────────────────────────────┐
│  the transcript: one conversation, a turn after another              │
│                                                                      │
├──────────────────────────────────────────────────────────────────────┤
│              builder · claude/claude-opus-4-8:high · 2 of 5          │  ← what each agent runs
│              reviewer · codex/gpt-5.6-sol:high · 3 · unread          │
│                       48.2k tokens · 91/s                            │
│ ❯ type here                                                          │  ← the editor
├──────────────────────────────────────────────────────────────────────┤
│ ⠋ builder… (73s · esc to interrupt)      enter say · tab agent · …  │  ← the status line
└──────────────────────────────────────────────────────────────────────┘
```

**At the top**, the box it opens with: the name drawn large, the version, what humanize is, and
two lines on how to begin. Nothing about what is set up to run or where it would run — the
transcript is a record, so a copy of either up there could only ever be the copy that was true
when you opened it. Both are on the lines round the editor, which are redrawn.

**The transcript** is one conversation, not every agent's at once. Which one, and how to move
between them, is [below](#reading-one-conversation).

**Above the editor**, one line per agent the flow drives: the name the flow calls it, then what
it runs as `cli/model:effort`, then the machine its turns land on where that is not this one, the
[account](#which-cli-and-which-account) it runs as where that is not this machine's own, and
finally the conversations it has open — `2 of 5` on the agent holding the one you are reading,
the count alone on the others, and `unread` against one holding a conversation that has said
something since you last looked at it. Under them, what the run has cost so far and the rate it is
costing it at — per model, since two agents at one model are one bill, and over a recent window
only, so a flow that has stopped reads as stopped.

**The status line, left:** what is running, if anything is — whose turn it is and how long it
has been going. Between two turns it names the flow and how long the run has been going, since
a flow that sleeps off a round, commits, and reads what the last turn wrote has not stopped. A
flow that [called another flow](/reference/flows.md#a-flow-that-calls-another-flow) names both, innermost
last: `chat ▸ official/rlar`. A
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
| **shift+enter** | Breaks the line, which is what enter would do anywhere else. |
| **ctrl+j** | The same, for a terminal that cannot tell shift+enter from enter. |
| **esc** | Stops the flow — the whole flow, not just the turn. Dismisses the offers list first, if one is open. Silent when nothing is running. |
| **ctrl+c** | Takes back the nearest thing there is to take back: what is half-typed if anything is, the turn of the conversation being read if not. Silent when there is neither. |
| **↑ / ↓** | Walks what was typed here before — but only off the first and last line, so a prompt of several lines is still moved around in. Over an open offers list, moves within the list. |
| **tab** | [Steps to the next agent that is working](#reading-one-conversation) and reads its conversation. Over an open offers list, takes the highlighted offer instead. |
| **shift+tab** | Steps to the one before it. |

shift+enter reaches a program only from a terminal that speaks the keyboard protocol that has
a way to say so — Ghostty, kitty, WezTerm, Alacritty. Anywhere else it is a plain carriage
return, which is enter, and would send the line: ctrl+j is a line feed and arrives from every
terminal there is.

**iTerm2 is the one terminal humanize keeps that protocol off in.** It loses text composed at
an input method while the protocol is on, so a session sitting straight in iTerm2 is never
asked for it — and shift+enter does not break the line there. ctrl+j is what does. A tmux in
between handles the protocol properly, so iTerm2 under tmux breaks the line on shift+enter
like everywhere else.

ctrl+c never leaves. It is pressed while work is going on, and what it ends is that work: the
conversation on the screen is closed under its turn, so the flow reads the turn as one that
failed — the same thing it would have read had the agent fallen over by itself. A flow that
catches its own turns carries on from there; one that does not stops there. The rest of the
flow is left running, ten conversations being what a flow may have open and one of them being
what is on the screen. esc is what stops all of it, and `/exit` is what leaves.

Focus cannot leave the editor. There is nowhere else for it to go — which is why tab and
shift+tab are free to read the conversations. While a sheet is up over the interface they are
the sheet's, and while the offers list is open tab is its.

## Selecting and copying

Drag across the screen with the mouse, and what you dragged across is on your clipboard when you
let go. The status line says `copied` for a moment, which is the only sign there is: a clipboard
is written to silently.

| Gesture | What it takes |
| --- | --- |
| **drag** | Everything between where you pressed and where you let go, across as many lines as you like. |
| **double click** | The word under it — everything up to the spaces on either side, so a path or an id comes whole. |
| **triple click** | The whole line, however many rows of the screen it was drawn over. |

**What comes back is what was written, not what was drawn.** A line too long for your terminal is
drawn over four rows, and copying it gives you the line: no break where the terminal ran out of
room, and none of the spaces that padded each row out to the edge. A break in what you copy is a
break that was really there. The same goes for `/export`, which writes the same text to a file.

The box the interface opens with is a picture rather than a line, so dragging across it gives you
its rows as they are drawn, borders and all.

The editor selects for itself — dragging in it copies what you dragged across, the same as
anywhere else — and so do the lists a sheet offers you to choose from: a click on one of those
is still a choice, and only a drag is a selection.

Changing the width of your terminal lets go of whatever was selected. The lines are wrapped
again at the width you gave them, so a selection made against the old wrapping is dropped rather
than left pointing a line or two off what you dragged across.

**How it reaches the clipboard.** The interface has the mouse, so your terminal never sees the
drag and cannot copy anything itself. What is selected goes out as the escape a terminal takes
for its clipboard (OSC 52), which is why it works over ssh: it reaches the clipboard of the
machine you are sitting at rather than the one the flow is running on. Most terminals take it;
some ask you to turn it on — `set-clipboard on` in tmux, `Allow reporting`/`clipboard write` in
VTE-based ones. Holding **shift** while dragging is your terminal's own selection instead, which
every terminal keeps for itself and which copies the screen as drawn, wrapping and all.

## Commands

A line beginning with `/` is a command; any other line is said to the agent. Type `/` and the
list appears under the editor with a line about each.

| Command | Takes | What it does |
| --- | --- | --- |
| `/flow` | `[flow]` | The menu of two pages: [which flow runs](#choosing-a-flow) and [what each of its agents is](#what-each-agent-is). With a name or a path, opens already holding that one. The first page is shut while a flow is running; the second never is. Nothing lands until you save on the way out. |
| `/config` | | Sets up the flow itself, for a flow that says it can be. Choosing a flow asks the same thing. See [below](#setting-a-flow-up). |
| `/agents` | | [The agents saved under a name](#agents-kept-under-a-name), to be imported wherever a flow's agent is set up. Not the agents of the flow — those are the second page of `/flow`. |
| `/providers` | | [The accounts](#the-accounts-themselves) an agent may be run as: what there is, and what can happen to one — made, corrected, signed in again, marked as a fallback, taken away. |
| `/status` | | How the run is going: who is working, every handover between agents with how often it happened, and what each model has cost. That directed graph is the shape of the run. |
| `/details` | `[on\|off]` | Shows or hides tool calls and thinking. They are one question — how much of the working to show — so they are one switch. |
| `/afk` | `[on\|off]` | Whether an agent may stop and ask you something. See [below](#questions-and-being-away). |
| `/clear` | | Clears the screen, and nothing else: the conversation being read, not the others, and nothing that is running. |
| `/export` | | Writes what is on the screen — the conversation being read — to `.humanize/<datetime>.session.md`, as it was written rather than as it was wrapped. |
| `/exit` | | Leaves. |

`/details` and `/afk` flip when given nothing, and take `on` or `off` when you want to say
which.

**`hmz collect` and `hmz anchor` are deliberately not here.** Neither is a thing to do to a
flow that is running, and a command that only ever means one thing is a command line.

## Reading one conversation

A flow drives several agents, and each of them holds as many conversations as it likes — a
Ralph loop opens one a turn, a fan-out holds one per worktree. All of them written down the
same screen is none of them readable, so **the transcript is one conversation**, and **tab**
and **shift+tab** step to the next agent and the one before, wrapping at either end.

**They step between the ones that are working.** With ten agents going, what you are stepping
between is the ones thinking right now, not the ones that have stopped. A conversation between
its turns is still read once you are on it — what you are reading is left where it is until you
press one of these — but it is not stepped onto, and with nothing working at all both keys do
nothing.

The conversation you are reading is the one:

- the transcript shows — moving to another writes a line saying which one is being read from
  there down, and draws what it has said under that;
- a line you type goes into;
- the line above the prompt marks as `2 of 5`, against the agent holding it.

**Nothing you have read is taken off the screen.** Moving to another conversation carries on
under the line saying so, and so does a conversation ending under you — a Ralph loop drops one
a turn, and the line then says `that conversation has gone`. Only `/clear` clears.

That line also says **which agents are working**: `●` for one with a turn open, `○` for one
that has stopped. It is the first thing to look for with several going at once, and the only
thing on that line that changes by itself:

```
   builder · claude/claude-opus-5:max · ● 2 of 5
   reviewer · codex/gpt-5.6-sol:high · ○ 1 · unread
```

An agent holding a conversation that has said something since you last looked at it is marked
`unread` there, so a flow of ten conversations is not nine nobody knows to look at.

You start out reading the first conversation the flow opens, so a flow that only drives one
agent needs none of this. With no flow running there is nothing to read and both keys do
nothing. A flow that talks to you is talking to you here, so the conversation with the person
is not one of the ones these keys move between.

**What is being read is held by the conversation itself**, not by where it comes in the list.
The list churns — a Ralph loop drops one every turn — and when the one you were reading goes,
the newest of that agent's is read instead, since a loop that dropped one has already opened
the next. Where that agent has none left, whatever is nearest to where it was.

What is kept is bounded, a flow being a thing that runs for days: the last eight conversations,
and the last two thousand lines of each. Older lines and older conversations are gone from the
screen, not from the [trace](/reference/tracing.md) — that is what a trace is for.

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

A line reaches [the conversation you are reading](#reading-one-conversation), and only while a
turn of it is open. Not whichever agent happens to be working: an agent may be holding one
conversation you are reading and taking a turn in another, and a line said to the wrong one is
a line said to somebody else. A conversation between turns would answer it on its own, outside
the flow, so it waits for the turn that starts next instead.

How far "into the turn" it gets depends on the backend:

| Backend | What a mid-turn line does |
| --- | --- |
| **Claude Code** | Answered within the same turn. The turn is over once the agent has answered everything it was told, not when it first stops. |
| **Codex** | A steer on the turn its app server is running. |
| **Kimi Code** | Queued, then steered into the turn already running. |
| **pi** | A steer on the run it is making, taken into it rather than answered after it. |
| **opencode**, **mimocode** | Nothing: a run per turn has ended by the time there is anything to say to it. |

An [anchored](/reference/remote-execution.md) Claude ends its process with each turn so that its work
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
- `/flow ` offers the flows there are — the ones humanize ships, the ones every
  [flowverse](/reference/flows.md#flowverses) fetched here holds, and the ones under `.humanize/flows`
  here or in your home directory.

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

## The menus, and when what they hold lands

`/flow`, `/agents` and `/providers` are menus rather than walks. Three things are true of all
of them:

- **No key is a chord.** A menu asks one thing and its keys are its own, so nothing here needs
  a modifier held down.
- **Typing does not search.** Every letter is a key, so a search is asked for with **s** and
  left with **esc**, which clears what was typed. While one is running the letters go into it.
- **Nothing lands until you save on the way out.** Esc asks — a box in the middle of the
  screen, over the menu rather than instead of it, with the two answers there are: save and
  close, or discard and close. Esc on the box is the way back to the menu. A menu you only
  looked at asks nothing.

A menu of several pages shows their titles across the top, and **tab** / **shift+tab** turn
between them. A page that cannot be opened right now is still a title, struck through. A page
made of several lists names them under the titles, and `←` / `→` step between those.

## Choosing a flow

`/flow` opens on two pages — **Flow** and **Agents** — and the first of them puts up the flows
of one place at a time, with `←` and `→` stepping between the places: every
[flowverse](/reference/flows.md#flowverses) — `builtin`, which is the package's own, `official`, which is
where the rest come from, and whatever else has been added — and then `local`, this project's
flows under `.humanize/flows`, and `user`, yours under `~/.humanize/flows`, each where there
are any. The strip above the list is the places, with the one being read marked; the list is
that place's flows and nothing else.

```
  Flow

  Which flow the agents are driven through. The first thing you say once it is chosen is what
  it is to do. A flow anywhere else is a path you type.

  Flow · Agents   tab/shift+tab to switch
  builtin · official · local   ←/→ to switch

❯ 1. chat                    Chat — one agent, one session, and every line typed between…
  2. ralph_loop              Ralph loop (flowbench: ralph_loop) — a fresh session every…
  3. stateful_ralph          Stateful ralph (flowbench: stateful_ralph) — one session, re-…

  Enter to choose · a adds a flowverse · r fetches one · d twice takes one away · Esc to
  close · s to search
```

| Key | |
| --- | --- |
| `←` `→` | Read the place before or after this one, wrapping round. |
| `a` | Add a flowverse: a URL or an `owner/repo`, and a name to keep it under. |
| `r` | Fetch the place being read again, or for the first time. |
| `d` `d` | Take an added one away, flows and all. `builtin` and `official` are always here. |

The page opens on the place the flow in force came from, and a fetch leaves you reading what
it brought. **A flowverse that has never been fetched is fetched as the menu opens** — which
in practice is `official`, the one every flow that is not in the package is in — in the
background, without moving what you are reading, and once per opening however it goes. The
flowverse keys are here rather than in a menu of their own because this is the
moment you find out that the flow you want is in a flowverse you have not added, or that the
one you have is out of date. A fetch runs off the interface's own loop — it keeps drawing
while it clones — and what became of it is said under the list rather than thrown at you. A
flowverse with nothing in it says so where its flows would be, and `r` fetches it from there.

Choosing a flow reads back what that flow was last set up with here, asks
[what the flow itself takes](#setting-a-flow-up) where it takes anything, and lands on the
**Agents** page, which is the next thing to answer.

**The Flow page is shut while a flow is running** — a flow is chosen in order to be started,
and there is one going. The Agents page never is: an agent thinking too little, on the wrong
account or allowed too much is something you find out halfway through a run. What you save then
reaches the agents that are running, each of them from its next turn on. A CLI you changed is
the one thing that cannot be swapped under a flow already holding that agent, and says so.

The same places are on the command line as [`hmz flowverses`](/reference/cli.md#hmz-flowverses), for a
machine being set up or a script.

Typing narrows by name. What each flow says about itself is beside its name, and is not
searched: a subsequence of a sentence matches nearly everything. A search narrows the strip
to the places it found something in and steps to one of them, so what you type finds a flow
without your having to remember which flowverse it was in.

## What each agent is

The **Agents** page of `/flow` lists what the flow drives, by the name the flow calls each, and
enter opens one. Everything that agent is is a row of one sheet:

```
  Set up builder

  What this one agent is. Enter opens the row under the cursor, and the arrows step the ones
  that are a rung rather than a list. Nothing is applied until this sheet is left and saving is
  confirmed.

    1. import       ▸                          copy a saved agent into this one
  ❯ 2. cli          claude ▸                   which coding agent takes its turns
    3. provider     as local ▸                 the account those turns run as
    4. model        claude-opus-5 ▸            which of that CLI's models it runs
    5. effort       high                       how hard it thinks
    6. skills       every skill ▸              which of its CLI's skills it is loaded with
    7. permission   bypass                     what it may do without being asked
    8. goals        on                         whether the backend's own goals are available
    9. where        this machine ▸             the machine its work lands on
   10. save         ▸                          save this as an agent you can import

  Enter to open · Esc to close
```

One sheet rather than a walk of three, because an agent is one thing: a CLI, an account, a
model at an effort, a set of skills, a rung of what it may do and a machine its work lands on.
A walk meant that changing the effort of an agent already set up was four keypresses through two
sheets with nothing to say.

The rows are in the order of what depends on what. The CLI settles which accounts there are and
which models that CLI will name; the account settles which of them it may name. **Changing the
CLI lets go of the model**, which belonged to the CLI before it.

**The arrows step a row that is a rung in an order** — the effort, what it may do, swarm mode,
whether goals are available. Everything else opens a sheet of its own and comes back. `where` is
a row only for an agent [the flow says may be pointed at a machine](#where-each-agent-works);
for one the flow put in a container it is read rather than opened, and for one that works here
it is not there at all.

Esc off the sheet asks about anything you changed and hands it back to the menu, which is still
holding it: nothing is written down until the menu itself is saved.

## Which CLI, and which account

Two rows, in that order, because an [account](/reference/providers.md) is one backend's — what signs in
to Claude Code is not what signs in to codex. The CLIs are the ones **actually installed here**,
less any the flow ruled out by needing a moment or a goal feature that backend has not got:

```
   Select the account its turns run as

   ❯ 1. as local                  signed in as you signed it in
     2. deepseek                  gateway · ANTHROPIC_AUTH_TOKEN, ANTHROPIC_BASE_URL
     3. work                      login

   a to make one · Enter to choose · Esc to cancel · s to search
```

`as local` — always the first row — is what every agent ran as before there were any accounts:
the CLI signed in the way you signed it in, with nothing redirected.

**`a` makes one without leaving the question.** This is the moment you find out that the account
you want is not there, so it is the moment to be offered it: `a` asks how to sign in and what
that way needs — the same walk [`/providers`](#the-accounts-themselves) runs, minus the question
this row has already answered — hands the terminal to the CLI's own login where the way has one,
and comes back with the new account chosen. A CLI with no accounts yet says
`claude has no accounts here yet; a makes one` under the list.

An agent given an account that has since been taken away is a red line when the flow is started,
before any turn has run — never a traceback half an hour in.

## What each agent runs

The `model` row: which of that CLI's models, and under it the effort, stepped where it stands.

```
   Select what claude runs

   Which model of claude takes this one's turns, and how hard it may be asked to think. These
   are what it last said it runs as this account; r asks it again.

     1. claude-opus-5           max, high
   ❯ 2. claude-sonnet-5         max, high

   r to ask it again · Enter to choose · Esc to cancel · s to search
```

**The list is what that CLI said it runs as the account chosen above it**, not a list written
into humanize: a CLI ships a model without asking anybody, and which of them you may name
depends on the account. It is asked the first time the interface opens, and again whenever an
account is made. **r** asks it again from here, which is where you find out that the model you
came for is not in the list. A CLI that has never been asked says so where the list would be;
one that will not answer says why, under the list, and leaves the sheet up.

Choosing a model you were not already on starts the effort at the hardest that model takes —
the one to reach for. Choosing the one you are on leaves the effort where you had it.

## Agents kept under a name

`/agents` is not the flow's agents. It is the agents written down under a name, to be imported
wherever a flow's agent is set up: the reviewer you always use, the cheap one you fan out
across, the one on somebody's gateway. An agent is a CLI, an account, a model at an effort and
what it may do — none of which is a thing about the flow that happens to be driving it.

| Key | |
| --- | --- |
| `enter` | Set one up, on the same sheet a flow's agent is set up on. |
| `a` | Add one. It has a `name` row of its own, which a flow's agent has not. |
| `d` `d` | Take one away. |

They live in `~/.humanize/agents.yaml`, and land there when the menu is saved.

**A flow imports a copy.** The `import` row of a flow's agent copies everything the saved one
is; changing it afterwards changes that flow's agent alone. The `save` row is the other half:
what you tuned inside a flow, written down under a new name or over one already there.

## Where each agent works

The `where` row, and **only for an agent whose place the flow declared `Remote`**. Where an
agent works is the flow's to say rather than a setting anybody may reach for — a flow written to
read this project cannot have one of its agents reading somebody else's — so:

| What the flow declared | What you are asked |
| --- | --- |
| `Annotated[AgentBase, Remote]` | a `where` row: which machine its work lands on |
| `Annotated[AgentBase, Isolated("python:3.12")]` | nothing; the flow named the image, and the row reads `in a container of python:3.12` |
| `AgentBase` | nothing; it works here, and there is no row |

The sheet lists what this machine can see — each container that is running, each host with an
entry in your `~/.ssh/config` — and anything else is a target you type after **s**:

| Typed | Where the work goes |
| --- | --- |
| *(nothing)* | this machine |
| `docker://<container>` | a container that is already running |
| `ssh://<host>` | a host you can reach |
| `tcp://<host>:<port>` | a coganchor target listening there |

An agent the flow says may move but that nobody has pointed anywhere still works here: the row
is offered, not forced. The agent itself runs here whatever you choose — its credentials, its
state directory and its link to its model provider stay put. What moves is the project it reads
and the commands it runs. See [Remote execution](/reference/remote-execution.md).

Two agents of one flow may work on two machines, since it is a setting of the agent. A target
that cannot be read, and an agent pointed somewhere by a flow that does not say it may be, are
both red lines when the flow is started, before any turn has run.

## What each agent is loaded with

The `skills` row asks which of that CLI's skills this agent is to have. Until it is answered the
row reads `every skill`, which is how a CLI comes.

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
[Agents](/reference/agents.md#which-skills-an-agent-is-loaded-with).

## The accounts themselves

`/providers` is all of them, under a heading per CLI, with the way each was made by and the
variables it sets. Their names, never a value: this is drawn where somebody can read it.

```
   claude
   ❯ 1. deepseek                  gateway · ANTHROPIC_AUTH_TOKEN, ANTHROPIC_BASE_URL
     2. work                      login

   codex
     3. personal                  key
```

| Key | What it does |
| --- | --- |
| **enter** | Corrects what the one under the cursor holds, by the way it was made with |
| **a** | Makes one: which CLI, then how to sign in, then what that way asks |
| **l** | Signs the one under the cursor in again, by the way it was made with |
| **f** | Marks it as where a turn goes when the account it was running under fails |
| **d** **d** | Takes it away, credentials and all |
| **c** | Adds a CLI of your own that speaks ACP, for accounts to be made against |
| **esc** | Closes the menu, asking about anything it is holding |

Taking one away, marking one as a fallback and correcting what one holds are **held until the
menu is saved**. Making one and signing one in are not: both own the terminal while they run,
and something that has already happened is not a draft.

Making one is three questions rather than one form, because each is only answerable once the one
before it has been: a backend's [ways in](/reference/providers.md#the-ways-in) are its own, and what a way
asks is the way's. A secret is drawn as bullets and never shown back — it is on its way into a
credential store, which is also why correcting an account starts its secrets blank: you type one
again or you leave it as it was.

A way with a login command of its own is **handed the terminal**: its browser or its device code
owns the screen until it is done, and what it writes lands in that account's own directory rather
than in the CLI's. What came of it is a line in the transcript.

Nothing here is refused while a flow is running. An agent reads the account it was configured
with once, so one made or taken away now is one the next run sees.

The same accounts are on the command line as [`hmz providers`](/reference/providers.md#hmz-providers).

## Setting a flow up

Some flows take settings of their own — `humanize1` takes twenty-three. A flow says so by
[declaring a model](/reference/flows.md#settings-of-the-flow-s-own), and the sheet is that model with a
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
| **enter** | Take the lot, and hand it back to the menu holding it |
| **esc** | Back to the menu, changing nothing |

It opens as the flow is chosen — enter on a flow that takes settings puts it up, and answering
it lands on the Agents page — and what it answers is held with the rest of that menu until the
menu is saved: setting a flow up is a thing about the flow rather than about what runs it. A
flow that takes no settings is not asked, so the walk is the same either way. `/config` opens
it on its own, for a flow already chosen. So does `hmz -f <flow> -c <setup.yaml>`, which opens
the interface already set up. See [CLI › hmz](/reference/cli.md#hmz).

Nothing in the interface knows what any of the settings mean. The types say how a value moves,
and the flow's own model says which combinations it will not take — so a flow that refuses
`gen_idea` without `gen_plan` refuses it here, in its own words, rather than an hour in.

## What it remembers

Opening the interface again in the same project finds it set up the way you left it: the flow
that was last run there, for each flow that workspace has run, what each of its agents was
running, where its turns landed, which skills it was loaded with and which account it ran as —
and how the flow itself was set up.

Kept per flow — by the name humanize's own flows have, and by the path yours have, so a flow of
yours cannot inherit the agents or the settings of the one it shares a name with. Per flow
rather than per workspace alone, because what an agent runs is only meaningful
against the flow driving it — a flow's second agent is its reviewer, and the flow before it had
no second agent at all. Keyed by the name the flow calls each one, so a flow that grows an
agent in the middle does not silently hand the reviewer's model to the builder. What was set up
is read back through the flow's own model, so a setting the flow has since dropped or renamed
is one it starts over from rather than one that quietly comes back.

It lives in `~/.humanize/settings.yaml`. The agents you saved under a name live beside it in
`~/.humanize/agents.yaml`, which is neither a workspace's nor a flow's. See
[CLI reference](/reference/cli.md#files).

## Colours

Drawn in your terminal's own colours, and it never asks the terminal what they are. Every
surface is the terminal's background, and everything drawn is one of the sixteen colours your
terminal already has a setting for, or a reversal of what is already there. A colour of its own
would be a guess about the background it lands on.

`NO_COLOR` is honoured.

## What it will not do

- **Open twice.** `hmz` with no command is the only way in — with or without `-f`, `-c` and
  `-a`, which say how it opens rather than opening a second one.
- **Run two flows at once.** The Flow page of `/flow` is shut while one is running, and
  `/config` is refused. What each agent is stays open: that is the half worth changing mid-run.
- **Guess at a bad line.** A line it cannot carry out is shown and the interface stays up. Only
  `/exit` closes it.
- **Ask the flow anything.** What is drawn beside and under the transcript is kept from the
  turns going past. A flow is a Python file that may branch any way it likes, so that is the
  only place a run is ever visible.

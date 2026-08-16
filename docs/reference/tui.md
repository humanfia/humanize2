# TUI reference

`hmz` with no command opens the terminal interface. There is no command that opens it too: one
way in is one way in.

It is a coding agent's own terminal with a [flow](/guide/concepts#flow) underneath instead of one
agent — a transcript, a multi-line editor under it, and a status line under that.

## The screen

```
┌──────────────────────────────────────────────────────────────────────┐
│  the transcript: one agent, or all of them, a turn after another     │
│                                                                      │
├──────────────────────────────────────────────────────────────────────┤
│              builder · claude/claude-opus-4-8:high · ● 2 · reading   │  ← what each agent runs
│              reviewer · codex/gpt-5.6-sol:high · ○ 3 · unread        │
│                       48.2k tokens · 91/s                            │
│ ❯ type here                                                          │  ← the editor
├──────────────────────────────────────────────────────────────────────┤
│ ·|· builder… (73s · ctrl+c twice to stop)   esc status · tab agent  │  ← the status line
└──────────────────────────────────────────────────────────────────────┘
```

**At the top**, the box it opens with: the name drawn large, the version, what humanize is, and
three lines on how to begin — what starts a flow, what `/flow` and `/agents` choose, and what
`/providers` holds. Nothing about what is set up to run or where it would run — the
transcript is a record, so a copy of either up there could only ever be the copy that was true
when you opened it. Both are on the lines round the editor, which are redrawn.

**The transcript** is one agent's, or the one where every agent's work appears together —
which is the one it opens on. Which, and how to move between them, is
[below](#reading-one-agent).

**Above the editor**, one line per agent the flow drives: the name the flow calls it, then what
it runs as `cli/model:effort`, then the machine its turns land on where that is not this one,
[what it may do](/guide/permissions) where that is not the ordinary rung, the
[account](#which-cli-and-which-account) it runs as where that is not this machine's own, and
finally what it is holding — `●` or `○` for whether it is working, how many conversations it
has open, `reading` on the agent whose transcript is on the screen, and `unread` on one that
has said something since you last looked at it. Under them, what the run has cost so far and the rate it is
costing it at — per model, since two agents at one model are one bill, and over a recent window
only, so a flow that has stopped reads as stopped.

**The status line, left:** what is running, if anything is — whose turn it is and how long it
has been going. Between two turns it names the flow and how long the run has been going, since
a flow that sleeps off a round, commits, and reads what the last turn wrote has not stopped. A
flow that [called another flow](/reference/flows#a-flow-that-calls-another-flow) names both, innermost
last: `chat ▸ official/rlar`. A
flow that has run out of things to do until you say something says `waiting for you`. With
nothing running at all, it names the flow that is set up to run and the directory it would run
in, with your home written as `~`.

**The status line, right:** the keys that do something *right now*, and only those. A shortcut
listed in a state it does nothing in is worse than one that is not listed at all, and there is
nowhere else to look them up. What **ctrl+c** would do next is what it is called by there,
since it is the one key that means something different for having just been pressed. In a
terminal too narrow for all of them, the ones at the front go first: those are the keys that
mean the same thing whenever they are pressed.

## Keys

| Key | What it does |
| --- | --- |
| **enter** | Sends what is typed. Over an open [offers list](#completion), takes what is highlighted instead. |
| **shift+enter** | Breaks the line, which is what enter would do anywhere else. |
| **ctrl+j** | The same, for a terminal that cannot tell shift+enter from enter. |
| **esc** | Opens [`/status`](#how-the-run-is-going), which is where the run is read and the flow is drawn. Dismisses the offers list first, if one is open. |
| **ctrl+c** | Takes back the nearest thing there is to take back: what is half-typed if anything is, the run if not. Twice stops the flow, a third press does not wait for it to unwind, and with nothing running twice leaves. |
| **↑ / ↓** | Walks what was typed here before — but only off the first and last line, so a prompt of several lines is still moved around in. Over an open offers list, moves within the list. |
| **tab** | [Steps to the next agent that is working](#reading-one-agent), and round to the one they all appear on. Over an open offers list, takes the highlighted offer instead. |
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

**ctrl+c is asked twice, and means three things.** With something half-typed it clears the
line, which is what it does in every terminal there is. With nothing typed and a flow
running, the first press says `press ctrl+c again to stop the flow` and the second one stops
it: a day's work is behind a key that is also pressed by mistake. A third press does not wait
for the flow to unwind — every conversation still open is closed under its turn, which is the
backend's process going, and what the flow reads as a turn that failed. With nothing running,
two presses leave; `/exit` is the other way out.

**esc does not stop anything.** It is pressed to dismiss whatever is on the screen everywhere
else in this interface, so it is not the key that ends a day's work: it opens
[`/status`](#how-the-run-is-going) instead, which is where the run is read and where the
flow is drawn.

Focus cannot leave the editor. There is nowhere else for it to go — which is why tab and
shift+tab are free to read the agents. While a sheet is up over the interface they are
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
| `/flow` | `[flow]` | The menu of two pages: [which flow runs](#choosing-a-flow) and [what each of its agents is](#what-each-agent-is). With a name or a path, opens already holding that one — and is refused outright while a flow is running, since that name would be choosing one. Without a name it opens on the agents page, which is never shut. Its Agents page saves the complete setup; esc remains the way to save or discard on the way out. |
| `/flowverses` | | [Where flows come from](/guide/flowverses): what places there are, what one of them holds, and one added, fetched again or taken away. Not which flow to run — that is `/flow`, where the arrows step between the same places. |
| `/agents` | | [The agents saved under a name](#agents-kept-under-a-name), to be imported wherever a flow's agent is set up. Not the agents of the flow — those are the second page of `/flow`. |
| `/cycles` | | The runs of this directory, newest first: what each was, how it went, and what there is to do with one — gather its [trace](/guide/tracing), say where it is written, and carry it on where its flow says it can be picked up. |
| `/providers` | | [The accounts](#the-accounts-themselves) an agent may be run as: what there is, and what can happen to one — made, taken away, and, on enter, corrected, signed in again, pointed at what it falls back to or told how it is tried again. |
| `/settings` | | [What humanize remembers](#what-humanize-remembers): two pages, one for what is true of this machine and one for what is remembered about this directory. |
| `/status` | | [How the run is going](#how-the-run-is-going), and the shape of it: a box per agent, marked as it works, with the handovers between them drawn as the arrows joining them. Enter reads an agent. **esc** opens it. |
| `/btw` | `<question>` | Asks a side question about the running flow from a read-only snapshot of its progress. It runs in a separate session and never steers the flow. |
| `/details` | `[on\|off]` | Shows or hides everything a turn did on the way to its answer: tool calls, thinking, and whatever a backend printed on its way past. One question — how much of the working to show — so one switch. **Off** to begin with. |
| `/afk` | `[on\|off]` | Whether an agent may stop and ask you something. See [below](#questions-and-being-away). |
| `/fallback` | | Where a turn goes when what was taking it cannot: an agent that has nowhere left to run, and an account that has gone down. See [below](#where-a-turn-goes-when-it-cannot-be-taken). |
| `/clear` | | Clears the screen, and nothing else: the transcript being read, not the others, and nothing that is running. |
| `/export` | | Writes what is on the screen to `.humanize/<datetime>.session.md`, as it was written rather than as it was wrapped: everything drawn there since the last `/clear`, which is every conversation that has been read rather than only the one showing now. |
| `/exit` | | Leaves. |

`/details` and `/afk` flip when given nothing, and take `on` or `off` when you want to say
which.

**`hmz anchor` is deliberately not here.** It is not a thing to do to a
flow that is running, and a command that only ever means one thing is a command line.

## Reading one agent

A flow drives several agents, and each of them holds as many conversations as it likes — a
Ralph loop opens one a turn, a fan-out holds one per worktree. All of them written down the
same screen with no way of reading any one back is none of them readable, so **there is a
transcript per agent, and one more where every agent's work appears together**. That last one
is what the interface opens on: before you have any reason to single an agent out, what you
are watching is the flow.

**tab** and **shift+tab** step round it and whichever agents are working, wrapping at either
end. With ten agents going, what you are stepping between is the ones thinking right now, not
the ones that have stopped. An agent between its turns is still read once you are on it — what
you are reading is left where it is until you press one of these — but it is not stepped onto.
Every agent there is can still be read from [`/status`](#how-the-run-is-going), which draws the
whole flow: that is where the one that has stopped, or has not started, is picked out by name.

**Every conversation of one agent is that agent's one transcript**, running on down it. A
Ralph loop opens one a turn, and nothing is redrawn when it does — the screen would otherwise
be wiped every turn, taking with it the turn you were reading, the line you typed and whatever
went wrong. Which conversation a turn is in is said where the turn begins, for an agent holding
more than one:

```
● claude#a1b2 is working · conversation 3 of 3
```

**Stepping onto another agent draws that agent's transcript from the top**, under a line
saying which is being read. What one agent has done is that agent's; a screen that only ever
appended would be every agent's lines shuffled into one another. Only `/clear` clears, and it
clears the one you are reading rather than reaching into ones you were not looking at.

On the transcript they all appear on, a line says which agent each part is from as that
changes — once, rather than a name against every line:

```
── claude#a1b2

● claude#a1b2 is working

● Ready. The tests pass.
```

The line above the prompt says **which agents are working**: `●` for one with a turn open, `○`
for one that has stopped. It is the first thing to look for with several going at once, and
the only thing on that line that changes by itself:

```
   builder · claude/claude-opus-5:max · ● 2 · reading
   reviewer · codex/gpt-5.6-sol:high · ○ 1 · unread
```

`reading` marks the agent whose transcript is on the screen, and `unread` one that has said
something since you last looked at it — so a flow of ten agents is not nine nobody knows to
look at. Nothing is marked unread while you are reading all of them at once: what an agent
said went onto that screen too, and you have just read it there.

A flow that talks to you is talking to you here, so the person is not one of the agents these
keys move between. With no flow running there is nothing working, and both keys leave you on
the transcript they all appear on.

**A typed line goes to the agent you are reading** — of its conversations, the one with a turn
open. Where you are reading all of them at once there is no one agent you can have meant, so it
goes to whichever has a turn open, which is the one the screen is showing anyway.

What is kept is bounded, a flow being a thing that runs for days: the last eight conversations,
and the last two thousand lines of each. Older lines and older conversations are gone from the
screen, not from the [trace](/reference/tracing) — that is what a trace is for.

## How the run is going

`/status` says how the run is going and draws the shape of it, and **esc** is what opens it. It
is read rather than answered, so it is not refused while a flow runs, and it is redrawn while
it is open — what it is about moves without anybody touching it.

The shape of a flow is not written down anywhere. A flow is a Python file that may branch any
way it likes, so what it did is read off the turns going past — and drawn as a box per agent,
in the order the flow takes them, with the handovers between neighbours as the arrows joining
them:

```
  ▣ every agent · 1 of 2 working · reading

  ┌──────────────────────────────────────────────┐
  │ ● builder · claude#a1b2                      │
  │ claude/claude-opus-5:high · 12 turns         │
  └──────────────────────────────────────────────┘
      ↓ 6   ↑ 5
  ┌──────────────────────────────────────────────┐
  │ ○ reviewer · codex#c3d4                      │
  │ codex/gpt-5.6-sol:high · 5 turns             │
  └──────────────────────────────────────────────┘

   Working:  builder
   Running:  431s
   Also:     builder → reporter · ×2
   Tokens:   claude-opus-5                48.2k    91/s
```

`●` is an agent with a turn open and `○` one that has stopped, and they move as the run does.
A handover between two agents the boxes did not put next to each other is said under the
diagram as `Also` rather than drawn: a line crossing the page from the first box to the fourth
is a line nothing in a terminal draws readably.

**Enter or a click on a box reads that agent** — whether or not it is working. tab is held to
the ones thinking, so this is the one place an agent that has stopped, or has not started, is
reached. The first row is the transcript every agent's work appears on, which is the way back
to watching the flow rather than one agent of it.

The agents of the last run are still drawn once it is over. Their transcripts are still on the
screen and still worth reading back, and a run that has just ended is usually the one you want
to look at.

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

A line reaches [the agent you are reading](#reading-one-agent) — of its conversations, the one
with a turn open. Not whichever agent happens to be working: a flow drives several, and a line
said to the one that is not on the screen is a line said to somebody else. Reading all of them
at once there is no one agent you can have meant, so it goes to whichever has a turn open. A
conversation between turns would answer it on its own, outside the flow, so it waits for the
turn that starts next instead.

How far "into the turn" it gets depends on the backend:

| Backend | What a mid-turn line does |
| --- | --- |
| **Claude Code** | Answered within the same turn. The turn is over once the agent has answered everything it was told, not when it first stops. |
| **Codex** | A steer on the turn its app server is running. |
| **Kimi Code** | Queued, then steered into the turn already running. |
| **pi** | A steer on the run it is making, taken into it rather than answered after it. |
| **opencode**, **mimocode** | Nothing: a run per turn has ended by the time there is anything to say to it. |

An [anchored](/reference/remote-execution) Claude ends its process with each turn so that its work
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
  [flowverse](/reference/flows#flowverses) fetched here holds, and your own `local/` and `user/`
  ones under `.humanize/flows` here or in your home directory.

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

`/flow`, `/agents`, `/providers` and `/settings` are menus rather than walks. Three things are
true of all of them:

- **No key is a chord.** A menu asks one thing and its keys are its own, so nothing here needs
  a modifier held down.
- **Typing does not search.** Every letter is a key, so a search is asked for with **s** and
  left with **esc**, which clears what was typed. While one is running the letters go into it.
- **Nothing lands until you save.** `/flow` has a `save` row on its Agents page for the
  complete flow setup. Esc remains available on every menu: it asks in a box in the middle of
  the screen, over the menu rather than instead of it, whether to save and close or discard
  and close. Esc on the box is the way back to the menu. A menu you only looked at asks
  nothing.

`/cycles` and `/flowverses` are lists of the same kind, and the first two are true of them as
well. The third is not: neither holds a draft of anything, so what is asked for there happens
as it is asked for and esc asks nothing on the way out.

A menu of several pages shows their titles across the top, and **tab** / **shift+tab** turn
between them. A page that cannot be opened right now is still a title, struck through. A page
made of several lists names them under the titles, and `←` / `→` step between those.

## Choosing a flow

`/flow` opens on two pages — **Flow** and **Agents** — and the first of them puts up the flows
of one place at a time, with `←` and `→` stepping between the places: every
[flowverse](/reference/flows#flowverses) — `builtin`, which is the package's own, `official`, which is
where the rest come from, whatever else has been added, and last `local`, this project's flows
under `.humanize/flows`, and `user`, yours under `~/.humanize/flows`, each where there are any.
The strip above the list is the places, with the one being read marked; the list is that
place's flows and nothing else.

```
  Flow

  Which flow the agents are driven through. The first thing you say once it is chosen is what
  it is to do. A flow anywhere else is a path you type.

  Flow · Agents   tab/shift+tab to switch
  builtin · official · local   ←/→ to switch

❯ 1. chat                    Chat — one agent, one session, and every line typed between…
  2. ralph_loop              Ralph loop (flowbench: ralph_loop) — a fresh session every…
  3. stateful_ralph          Stateful ralph (flowbench: stateful_ralph) — one session, re-…

  Enter to choose · f copies it here · Esc to close · s to search
```

| Key | |
| --- | --- |
| `←` `→` | Read the place before or after this one, wrapping round. |
| `f` | Copy the flow under the cursor into `.humanize/flows/`, whole — what it imports and the skills it brings — to change. Your own are looked in first, so from then on that name means your copy. |

The page opens on the place the flow in force came from. **A flowverse that has never been
fetched is fetched as the menu opens** — which in practice is `official`, the one every flow
that is not in the package is in — in the background, once per opening however it goes, and
without moving what you are reading: this is the place nobody fetched being fetched because
its flows are wanted, not somebody asking to be taken to it. It runs off the interface's own
loop — the menu keeps drawing while it clones — and what became of it is said under the list
rather than thrown at you. A place with nothing in it says so where its flows would be, and
one that has never been fetched says which menu fetches it: adding a place, fetching one again
and taking one away are [`/flowverses`](#where-flows-come-from).

Choosing a flow reads back what that flow was last set up with here, asks
[what the flow itself takes](#setting-a-flow-up) where it takes anything, and lands on the
**Agents** page, which is the next thing to answer. Its last row, `save`, validates every
agent and applies the flow and all its agents together.

**The Flow page is shut while a flow is running** — a flow is chosen in order to be started,
and there is one going. The Agents page never is: an agent thinking too little, on the wrong
account or allowed too much is something you find out halfway through a run. What you save then
reaches the agents that are running, each of them from its next turn on. A CLI you changed is
the one thing that cannot be swapped under a flow already holding that agent, and says so.

The same places are on the command line as [`hmz flowverses`](/reference/cli#hmz-flowverses), for a
machine being set up or a script.

**s** starts a search, and what is typed into it narrows by name. What each flow says about
itself is beside its name, and is not searched: a subsequence of a sentence matches nearly
everything. A search narrows the strip to the places it found something in and steps to one of
them, so what you type finds a flow without your having to remember which flowverse it was in.

## Where flows come from

`/flowverses` is the places themselves — a git repository with a `flows/` directory apiece,
cloned under humanize's home, and the flows of your own read where they lie. Each is offered
under the name it is listed under. A place that has never been fetched is listed all the same,
with its URL and `not fetched yet` beside it: what there is to run is not the same question as
what has been downloaded.

![The /flowverses list: builtin, which holds the flows humanize ships, and official, a GitHub
URL marked as not fetched yet](/demo/flowverses.png)

| Key | |
| --- | --- |
| **enter** | What that flowverse holds: one row per flow, with the line it says about itself. Reading them means importing them, so it is asked of the one you opened rather than of all of them at once. |
| **a** | Add one: a URL or an `owner/repo`, and a name to keep it under. |
| **r** | Fetch the one under the cursor again, or for the first time. `builtin` came with humanize, and `local` and `user` are directories of your own: all three say there is nothing to fetch. |
| **d** **d** | Take an added one away, flows and all. `builtin`, `official`, `local` and `user` are always here, and say so. |

Its own menu rather than three more keys on `/flow`, because they are about something else:
adding a repository, fetching one again and taking one away are done to the list of places,
while the page they were on is asking which flow to run — and a sheet that asks one question
with three keys about another is a sheet asking two.

**What happens here happens as it is asked for** rather than when the menu is saved: each of
these runs git, and something that has already been cloned is not a draft. A clone runs off
the interface's own loop, so the menu keeps drawing while it fetches, and what came of it is
said under the list and again in the transcript on the way out. Nothing here is refused while
a flow is running: a place fetched now is one the next run may reach for, and none of it
touches the flow that is going.

`/flow` kept the two keys that are about flows rather than about places: `←` and `→`, which
step between these same places because that is which list of flows is being read, and `f`,
which copies the flow under the cursor into this project.

Typing `/flow` and pressing enter still sends `/flow`. A command that has been written out
whole is [offered](#completion) nothing at all, so `/flowverses` is never left standing under
the cursor with enter meaning it.

## What each agent is

The **Agents** page of `/flow` lists what the flow drives, by the name the flow calls each, and
enter opens one. Everything that agent is is a row of one sheet:

```
  Set up builder

  What this one agent is. Enter opens the row under the cursor, and the arrows step the ones
  that are a rung rather than a list. Save accepts this setup; save as keeps a reusable copy.

    1. import       ▸                          copy a saved agent into this one
  ❯ 2. cli          claude ▸                   which coding agent takes its turns
    3. provider     as local ▸                 the account those turns run as
    4. model        claude-opus-5 ▸            which of that CLI's models it runs
    5. effort       high                       how hard it thinks
    6. skills       as its CLI finds them ▸    what it will be carrying, which its CLI keeps
    7. permission   bypass                     what it may do without being asked
    8. goals        on                         whether the backend's own goals are available
    9. web search   on                         whether it may search the web
   10. where        this machine ▸             the machine its work lands on
   11. save                                    accept this agent setup
   12. save as      ▸                          save a reusable agent you can import

  Enter to open · Esc to close
```

One sheet rather than a walk of three, because an agent is one thing: a CLI, an account, a
model at an effort, a rung of what it may do and a machine its work lands on.
A walk meant that changing the effort of an agent already set up was four keypresses through two
sheets with nothing to say.

The rows are in the order of what depends on what. The CLI settles which accounts there are and
which models that CLI will name; the account settles which of them it may name. **Changing the
CLI lets go of the model**, which belonged to the CLI before it.

**The arrows step a row that is a rung in an order** — the effort, what it may do, swarm mode,
whether goals are available, whether it may search the web. Everything else opens a sheet of its
own and comes back. `web search` is a row only for a CLI that can be told: claude, codex, grok,
qwen, opencode and mimo. A switch for something the backend would go on doing either way is a
switch that lies, so for every other CLI the question is not put. `where` is
a row only for an agent [the flow says may be pointed at a machine](#where-each-agent-works);
for one the flow put in a container it is read rather than opened, and for one that works here
it is not there at all.

`save` accepts this agent and returns straight to the flow's Agents page. It changes only the
flow draft; the complete setup is written down when `save` is chosen on that outer page.
`save as` instead asks for a name and immediately keeps a reusable copy without applying the
flow. Esc off the agent sheet remains a fallback: it asks whether to accept or discard changes.

## Which CLI, and which account

Two rows, in that order, because an [account](/reference/providers) is one backend's — what signs in
to Claude Code is not what signs in to codex. The CLIs are the ones **installed here**, less any
the flow ruled out by needing a moment or a goal feature that backend has not got — plus any
supported backend that is only a `pip install` away, which is listed so that it can be found
rather than looked for, and says so on its row:

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

The setup sheet for a named agent also ends with `save`, which accepts that agent and returns
to this list. The outer menu still holds all additions, edits and removals together until the
menu itself is saved.

They live in `~/.humanize/agents.yaml`, and land there when the menu is saved. The same store
is on the command line as [`hmz agents`](/reference/cli#hmz-agents), for a machine being set up or a
CI job.

**A flow imports a copy.** The `import` row of a flow's agent copies everything the saved one
is; changing it afterwards changes that flow's agent alone. The `save as` row is the other
half: what you tuned inside a flow, written down under a new name or over one already there.

## Where each agent works

The `where` row, and **only for an agent whose place the flow declared `Remote`**. Where an
agent works is the flow's to say rather than a setting anybody may reach for — a flow written to
read this project cannot have one of its agents reading somebody else's — so:

| What the flow declared | What you are asked |
| --- | --- |
| `Annotated[Agent, Remote]` | a `where` row: which machine its work lands on |
| `Annotated[Agent, Isolated("python:3.12")]` | nothing; the flow named the image, and the row reads `in a container of python:3.12` |
| `Agent` | nothing; it works here, and there is no row |

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
and the commands it runs. See [Remote execution](/reference/remote-execution).

Two agents of one flow may work on two machines, since it is a setting of the agent. A target
that cannot be read, and an agent pointed somewhere by a flow that does not say it may be, are
both red lines when the flow is started, before any turn has run.

## What each agent carries

The `skills` row reads `as its CLI finds them`, and opening it is a reading rather than a
choice:

```
     1. code-review    Review the current diff… (yours)
     2. dataviz        Use this skill whenever you… (yours)
     3. housekeeping   Tidies the tree (this project)

   These are claude's own: add one, or switch one off, where claude keeps them
```

The skills are found where the CLI itself looks — yours and this project's, read for the name
and the line each describes itself with — and nothing is asked of the CLI, which would mean
starting it. **Nothing here changes any of them.** A skill installed on this machine is that
CLI's own, and what a person installed is not something a flow is entitled to rewrite.

What a run adds to that is [the skills the flow brings](/reference/flows#the-skills-a-flow-brings),
mounted onto every session its agents open and taken away again after.

## The runs that have already happened

`/cycles` is every run of a flow in this directory, newest first. A run writes itself down as
it happens — which flow, on what, by which agents, and every session each of them opened —
and this is what reads it back:

![The /cycles list: two runs, each with when it began, the flow that ran, what it was asked to
do and how many sessions it opened, the newer one marked "can be picked up"](/demo/cycles.png)

A row is when the run began and the flow that ran; beside it, what that flow was asked to do,
how many sessions it opened, and `can be picked up` for a run whose flow said it was
resumable. How it went is there only where it went some way other than finishing — stopped,
failed, or left unfinished by a machine that went away under it — since a list of runs is
mostly runs that finished, and a column saying so of nearly all of them is a column taking the
room the others need. Newest first, because what somebody who opens this came to look at is
the run that has just happened. **s** searches the flow, what it was asked to do, and the name
the run is written under.

The list is read rather than chosen from, so **enter** opens what there is to do with the run
under the cursor:

![The menu under one run: carry on from here, collect a trace, and where it is, each with a
line saying what it does](/demo/cycle-does.png)

| Row | What it does |
| --- | --- |
| **carry on from here** | Runs that run's own flow again, on what that run left behind — which a flow that says it [can be picked up](/reference/flows#a-flow-that-can-be-picked-up) is handed. |
| **collect a trace** | Gathers **that run's** sessions — and the programs it ran, for a [profiled](/reference/tracing#profiling-a-run) run — into `traces/` inside the run itself, rather than into whatever directory you are standing in. That run's and no others: they are asked for by the ids it wrote down, so a directory run in fifty times has fifty traces and none of them holds another's work. Where it went and what is in it are said under the list, and again in the transcript. |
| **where it is** | The directory the run is written in, sessions and all, said under the list. |

**Carrying on is offered where the flow says so now**, rather than where the run said so then.
The mark on the row is what that run wrote down as it ran; opening the menu asks the flow
itself, since a flow is a file that may have been rewritten since — and one that will not load
at all is one there is nothing to carry on from. Where it is not offered the row is not there
and the reason is said under the two that are. Collecting a trace is offered for every run,
whatever its flow says: a run that cannot be continued is still a run to read.

What is carried on is the run rather than what the interface happens to be set up on — the
flow, its agents and what they were asked to do all come off the record of that run, an agent
swapped under it being a different run wearing its name. And it is a run of its own: a
[cycle](/reference/tracing#cycles) is never reopened, so carrying one on writes a new one
that says which run it came from.

**Reading is not refused while a flow is running. Carrying one on is.** What has already
happened does not change under you, so the list is worth having open mid-run — but a run
picked up is a flow started, and there is one going. It is said under the list rather than by
shutting the menu, since the question the menu is asking is still worth answering: `a flow is
running; ctrl+c twice stops it before another can be picked up`.

A directory nothing has ever been run in says so under the empty list. The same trace is
[`hmz trace collect`](/reference/cli#hmz-trace-collect) on a command line, with `--cycle` to
name which run. A trace of what a directory holds whoever opened it — a session no flow ever
drove — is `--all` or `--session` there, and is not offered here at all: this is a list of runs,
and a trace of none of them has nothing here to hang on.

## The accounts themselves

`/providers` is all of them, under a heading per CLI, with the way each was made by and the
variables it sets. Their names, never a value: this is drawn where somebody can read it.

```
   claude
   ❯ 1. deepseek                  gateway · ANTHROPIC_AUTH_TOKEN, ANTHROPIC_BASE_URL
     2. work                      login
     3. as local                  the CLI as this machine is already signed in · falls back to work

   codex
     4. personal                  key
     5. as local                  the CLI as this machine is already signed in
```

![/providers: the accounts under a heading per CLI, enter opening what there is to do with one,
and a asking which backend a new one is for](/demo/accounts.gif)

| Key | What it does |
| --- | --- |
| **enter** | Opens what there is to do with the one under the cursor: correct what it holds, sign it in again, say what it falls back to, say how a failed turn under it is tried again |
| **a** | Makes one: which CLI, then how to sign in, then what that way asks. The list of CLIs is also where a CLI of your own that speaks ACP is written down |
| **d** **d** | Takes it away, credentials and all |
| **esc** | Closes the menu, asking about anything it is holding |

![What enter opens on one account: correct what it holds, sign it in again, what it falls back
to, and how it is tried again](/demo/account-does.png)

Four questions about one account are a menu rather than four letters to read off the bottom of
the screen — while **enter**, which every list already means, was doing one of them.

The last row under each CLI is the account this machine is already signed into — the CLI as
you run it, which is what an agent nobody gave an account runs as, and where that agent's
chain begins. Where it falls back to and how it is tried again are what it takes; correcting
it and signing it in are not offered at all, and the menu says why under the two rows that are
left. **d** says the same thing: humanize did not make that account and keeps no credentials
for it.

Taking one away, saying where it falls back to, saying how it is tried again and correcting
what one holds are **held until the menu is saved**. Making one and signing one in are not: both own the terminal while they run,
and something that has already happened is not a draft.

Making one is three questions rather than one form, because each is only answerable once the one
before it has been: a backend's [ways in](/reference/providers#the-ways-in) are its own, and what a way
asks is the way's. A secret is drawn as bullets and never shown back — it is on its way into a
credential store, which is also why correcting an account starts its secrets blank: you type one
again or you leave it as it was.

A way with a login command of its own is **handed the terminal**: its browser or its device code
owns the screen until it is done, and what it writes lands in that account's own directory rather
than in the CLI's. What came of it is a line in the transcript.

Nothing here is refused while a flow is running. An agent reads the account it was configured
with once, so one made or taken away now is one the next run sees.

The retry sheet answers in rungs rather than in numbers: the tries step through 0, 1, 2, 3, 5,
8, 13 and 21, and the time the retrying is given through *as long as it takes*, 30s, 1m, 5m,
15m and 1h. A text box for an integer is a text box to validate.

The same accounts are on the command line as [`hmz providers`](/reference/providers#hmz-providers).

## Where a turn goes when it cannot be taken

`/fallback` is two pages of one menu, because two different things are called falling back.

**Agents.** An agent that has nowhere left to run — a model retired, a CLI that will not
start, a rate limit on the whole account rather than one request — falls back to a whole other
agent. `a` chooses the one that cannot run and then the one that takes its turns, each on
[the same sheet](#what-each-agent-is) a flow's agent is chosen on. `d` twice takes a step away.
Enter on a row says where that agent's turns go instead.

**Accounts.** **tab** turns to the account chains, which are the ones
[`/providers`](#the-accounts-themselves) also reaches: enter says which account of the same CLI
a turn under this one carries on under. Making an account and taking one away stay there, and
the keys here say so rather than doing nothing.

Both are held until the menu is saved on the way out, as everything on a menu is.

```
  Fallback

  Where a turn goes when what was taking it cannot. An agent falls back to a whole other
  agent -- another CLI, model, effort or account -- in a session of its own, and is what is
  left when a backend has nowhere to run. An account falls back to another account of the
  same CLI, inside the conversation that was running.

  Agents · Accounts   tab turns the page

  ❯ 1. claude@work/claude-opus-5:high     falls back to codex@key/gpt-5.6-sol:high
    2. codex@key/gpt-5.6-sol:high         falls back to dsh/deepseek-v4-flash:high

  Enter for where its turns go · a adds one · d twice takes one away · Esc to close
```

An agent cannot fall back to itself, and a chain that comes round on itself ends at the second
sight of an agent. The same steps are on the command line as
[`hmz fallback`](/reference/cli#hmz-fallback), and what they mean is
[Falling back](/guide/fallback).

## What humanize remembers

`/settings` is two pages over `~/.humanize/settings.yaml`, and they are two kinds of thing
rather than two halves of one:

```
   Settings

   Everywhere · This directory                       tab and shift+tab

   ❯ 1. reports         on   report what goes wrong to humanize
     2. sent                 what a report carries, and what it never does
```

**Everywhere** is what is true of this machine wherever humanize is run from: whether it
[reports what goes wrong](/guide/reporting), and — on enter — the list of what a report
carries and what it never does, said under the rows. The row shows what is **written down**: an
environment that is answering for this run says so under the list rather than being drawn as
the setting, since a menu cannot change it.

**This directory** is what is remembered here: the directory itself, the flow it opens on and
how many agents that flow was set up with, and a row that forgets the lot — leaving every other
directory, and every setting, as it was.

The arrows step the row under the cursor, and nothing lands until the menu is left and saving is
confirmed.

## Setting a flow up

Some flows take settings of their own — `humanize1` takes twenty-three. A flow says so by
[declaring a model](/reference/flows#settings-of-the-flow-s-own), and the sheet is that model with a
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
flow that takes no settings is not asked, so the walk is the same either way. There is no
command for it: choosing the flow again is how you answer it again. `hmz -f <flow> -c
<setup.yaml>` opens the interface already set up. See [CLI › hmz](/reference/cli#hmz).

Nothing in the interface knows what any of the settings mean. The types say how a value moves,
and the flow's own model says which combinations it will not take — so a flow that refuses
`gen_idea` without `gen_plan` refuses it here, in its own words, rather than an hour in.

## What it remembers

Opening the interface again in the same project finds it set up the way you left it: the flow
that was last run there, for each flow that workspace has run, what each of its agents was
running, where its turns landed and which account it ran as —
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
[CLI reference](/reference/cli#files).

## Colours

Drawn in your terminal's own colours, and it never asks the terminal what they are. Every
surface is the terminal's background, and everything drawn is one of the sixteen colours your
terminal already has a setting for, or a reversal of what is already there. A colour of its own
would be a guess about the background it lands on.

`NO_COLOR` is honoured. `TEXTUAL_THEME` names one of Textual's own themes to use instead of
the terminal's colours; a name no theme answers to is ignored rather than refused.

## What it will not do

- **Open twice.** `hmz` with no command is the only way in — with or without `-f`, `-c` and
  `-a`, which say how it opens rather than opening a second one.
- **Run two flows at once.** The Flow page of `/flow` is shut while one is running, and
  what the flow itself takes is not asked. What each agent is stays open: that is the half
  worth changing mid-run.
- **Guess at a bad line.** A line it cannot carry out is shown and the interface stays up. Only
  `/exit` closes it.
- **Ask the flow anything.** What is drawn beside and under the transcript is kept from the
  turns going past. A flow is Python that may branch any way it likes, so that is the
  only place a run is ever visible.

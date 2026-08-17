# TUI

## File Structure

```
.
├── __init__.py
├── app.py
├── complete.py
├── discover.py
├── history.py
├── monitor.py
├── pick.py
├── selecting.py
└── tally.py
```

## `__init__.py`

Expose `Humanize`.

## `app.py`

```python
class Humanize(App[None]):
    def __init__(self) -> None: ...
```

The terminal interface, which `hmz` with no command opens. It is a coding agent's own
terminal with a flow underneath: laid out as a transcript, a multi-line editor, and a status
line, with what the flow is doing beside the transcript.

- It MUST open on a flow that is only talking to one agent, at the first agent installed that
  has said what it runs, so that saying something is all it takes to start. A flow is what is
  reached for once talking to one agent is not the shape of the work, and that is not known
  before anything has been said. Which model MUST be the first that CLI named, which is that
  CLI's own idea of what it runs; naming one here would be naming one that was right on the
  day it was written. The agent it opens on MUST NOT be at the hardest effort the model
  takes: that is the one to reach for, not the one to spend before it has been asked for.
  DeepSeek Harness MUST participate in this implicit fallback only where its local account
  resolves a nonempty API key from the same layers a turn uses. An installed DeepSeek Harness
  with no such key MUST still be offered in the agent picker, where it can be selected and an
  account configured, but MUST NOT become the implicit fallback. An explicit or remembered
  choice of it MUST be left as chosen.
- Every backend installed here that has never said what it runs MUST be asked as the
  interface opens, in the background and one at a time: before that there is nothing to
  offer at any sheet and nothing to open talking to. It MUST NOT hold the prompt up, and a
  backend that will not answer MUST NOT be asked again on its own.
- Choosing a flow MUST stop whatever is running, since a flow is chosen in order to be run.
  Looking at the flows and leaving without choosing MUST change nothing at all.
- It MUST be drawn in the terminal's own colours, and MUST NOT ask the terminal what they
  are: every surface is the terminal's background and everything drawn is one of the sixteen
  colours the terminal already has a setting for, or a reversal of what is already there. A
  colour of its own would be a guess about the background it lands on.
- The editor MUST mean both things at once: a line beginning with `/` is a command, and any
  other line is said to the conversation being read, through `SessionBase.interject`, so that
  a turn already under way takes it into account rather than being restarted with it.
- Enter MUST send and `shift+enter` MUST break the line, so that a long prompt can be written.
  `ctrl+j` MUST break it too: a terminal reports shift+enter as itself only where it speaks a
  keyboard protocol that can say so, and sends a bare carriage return where it does not --
  which is enter, and would send the line. A line feed arrives from every terminal there is.
- A half-typed line MUST be offered what it could be finished with, in a list under the
  editor, and tab MUST take what is highlighted. What is offered MUST be reconsidered when the
  cursor moves as well as when the text does: an offer made at the end of a line MUST NOT
  still stand once the cursor is back in the middle of it.
- Keys the offers are using MUST be theirs only while there are offers: a prompt of more than
  one line needs its arrows back, and focus MUST NOT be able to leave the editor.
- The transcript MUST be one per agent, and one more where every agent's work appears
  together: a flow drives several agents and each of them holds as many conversations as it
  likes, and all of them interleaved with no way of reading any one back is none of them
  readable. What an agent says MUST be kept against that agent and against the one they are
  all on. What is kept MUST be bounded -- a machine runs one flow after another -- by keeping
  the last few and the last few lines of each, and neither the one being read nor the one
  they are all on MUST ever be among what is dropped.
- It MUST open on the one they all appear on, and a run starting MUST return to it. That is
  where a flow is watched rather than one agent of it, which is what somebody at this prompt
  is doing before they have any reason to single one out.
- Every conversation of one agent MUST be that agent's one transcript, running on down it,
  and opening another MUST NOT clear the screen or draw anything again. A Ralph loop opens
  one a turn, and a screen redrawn every turn is one nobody can read back through. Which of
  them a turn is being taken in MUST be said where the turn begins, for an agent holding more
  than one.
- Stepping onto another agent MUST draw that agent's transcript from the top, under a line
  saying which is being read. What one agent has done is that agent's, and a screen that only
  ever appended would be every agent's lines shuffled into one another. Only `/clear` clears,
  and it MUST clear the one being read rather than reaching into ones nobody was looking at.
- tab and shift+tab MUST step round the transcript they are all on and whichever agents are
  *working*, wrapping. The ones working rather than every agent the flow drives: with ten
  agents going, what somebody is stepping between is the ones thinking. An agent read already
  MUST be left where it is when its turn ends -- it is being read -- but MUST NOT be stepped
  onto again until it is working. Every agent there is MUST still be readable, from the
  diagram `/status` draws: an agent that has stopped is picked out by name there rather than
  stepped past.
- Which agent is being read MUST be visible, beside how many conversations it holds, and one
  that is not being read and has said something since it was last looked at MUST be marked as
  having something unread. Otherwise a flow of ten agents is nine nobody knows to look at.
  Nothing MUST be marked unread while the one they all appear on is being read: what an agent
  said went onto that one too and was read there, so marking it would be marking every agent
  of the flow for what is on the screen.
- Whether each agent is working MUST be visible on that same line. It is the first thing
  looked for with several going at once -- who is thinking and who has stopped -- and the one
  thing there that changes without anybody touching it.
- A word put into a turn MUST be kept against the agent that took it, rather than against
  whichever transcript was on the screen when it went. It is part of that conversation, and a
  conversation read back with half of what was said to it missing is not that conversation.
- A typed line MUST reach the agent being read, not whichever happens to have a turn open: a
  flow drives several, and a line said to the one that is not on the screen is a line said to
  the wrong agent. Of that agent's conversations it MUST reach the one with a turn open --
  one between turns would answer it on its own, outside the flow -- and MUST wait for the turn
  that starts next otherwise. Where every agent is being read at once there is no one of them
  to have meant, so it MUST reach whichever has a turn open.
- What is running MUST be what is running: a flow may reach for another by name and run it, so
  the line that names one MUST name the flow that was started and whatever it called, innermost
  last, and the sheet that says how the run is going MUST say the same. A flow that called
  another and reads as the flow somebody chose is an interface that stopped being true the
  moment the call was made.
- The accounts an agent may be run as MUST be reachable from here as well as from a command
  line: an account outlives the flow that was set up with it, and the one place a person is
  asked anything is the one place a credential can be typed. It is the one thing said in both
  places, and the same store either way.
- `hmz anchor` MUST NOT be a command here: it is not a thing to do to a flow that is running,
  and a command that only ever means one thing is a command line. Gathering a trace MUST NOT
  be one either -- it is a thing done to a run that has already happened, so it is one of the
  things `/cycles` offers about the run under the cursor rather than a command of its own.
- Setting the flow up MUST NOT be a command here either: it is asked as the flow is chosen, so
  a command for it would be a second way in to one sheet of one menu -- and one that has to
  say `that flow takes no setting up` for most of the flows there are.
- A turn MUST be shown as it happens: that the agent has started one, which agent it is, and
  what it says. It MUST be shown once -- a backend teeing to stderr for the benefit of a plain
  terminal MUST NOT also be shown here. A turn thinks for minutes and says nothing for most of
  them, so the line saying one has started is the whole of what a flow looks like while it
  works.
- `/details` MUST toggle all of what a turn did on the way to its answer -- tool calls,
  thinking, and whatever a backend printed on its way past -- and MUST start off. They are one
  question, how much of the working to show, and were two switches for no reason. Off, because
  a flow is watched to see where it has got to: what the agents said is that, and a tool row
  per file read is a screen nobody is reading with the answer somewhere in it. On, all of it
  MUST be shown rather than a sample of it.
- An agent that stops to ask MUST be able to reach whoever is at the prompt: the question and
  what it offers MUST be shown, and the next line typed MUST be the answer rather than a word
  put into the turn. It MUST be shown against whichever of that agent's sessions is working,
  and against the one being read where none of them is: the server that puts a question speaks
  for every session of its agent and so names none, and a question shown nowhere is a turn
  waiting on an answer nobody was asked for. `/afk` MUST toggle whether it may ask at all, and
  asking MUST start allowed, so that an agent that really needs a person gets one unless it has
  been said that none is there. A question still up when the flow ends or is stopped MUST end
  with it, so that stopping a flow is never blocked on one.
- `ctrl+c` MUST take back the nearest thing there is to take back: what is half-typed if
  anything is, and the run if not. The run MUST be asked for twice -- the first press saying
  what the next one does, the second one stopping the flow -- because a day's work is behind a
  key that is also pressed by mistake. Stopping it MUST tell every agent to take no further
  turn, so that the turn running now is closed out and the loop ends rather than handing on.
- A third press MUST NOT wait for it. A flow told to stop unwinds in its own time, so the
  press after the one that stopped it MUST close every conversation still open under whatever
  turn it is in -- which is the backend's process going, and what the flow reads as a turn
  that failed -- and MUST leave nothing behind still reading as a run in progress. That is
  the last thing a key can do about a run.
- With nothing running, two presses MUST leave. Twice for the reason stopping is asked twice,
  and never on one press: it is pressed while work is going on, and leaving is not what was
  meant by it. A press long enough after the last MUST be the first of its own gesture.
- `esc` MUST NOT stop a flow. It is pressed to dismiss whatever is on the screen everywhere
  else in this interface, and a key pressed to dismiss things MUST NOT be the key that ends a
  day's work. It MUST be `/status` instead, which is where the run is read and where the flow
  is drawn.
- A line that cannot be carried out MUST be shown and MUST leave the interface up. Only
  `/exit` closes it.
- A key of the interface's own MUST NOT fire while a sheet is up over it: a sheet is open in
  order to be answered, and reading another conversation is not an answer to it. The key MUST
  reach the sheet instead, rather than being swallowed by the interface and doing nothing.
- Letting go of a selection MUST put what was selected on the clipboard, by the escape a
  terminal takes for one -- which is the only way to reach the clipboard of the machine
  somebody is sitting at while the interface runs on another. The interface has the mouse, so
  the terminal never sees the drag and a selection nobody copied is one that goes nowhere. The
  editor MUST be copied from the same way, holding a selection of its own so that the screen's
  has nothing in it. That something was copied MUST be said for a moment, since a clipboard is
  written to silently and a gesture that says nothing is one nobody knows worked.
- What `/export` writes MUST be the text the transcript was written as rather than the rows it
  was drawn as, for the reason a selection gives back that text: a file of lines broken where
  the terminal ran out of room is one nothing reads back.

## `selecting.py`

```python
class Transcript(ScrollView): ...


class Choices(OptionList): ...
```

The two things on the screen that are read rather than answered: the transcript, and the list a
sheet offers. A terminal that is being sent the drags as well as the clicks is a terminal that
is no longer selecting anything itself, so the selection is the interface's to draw and the
interface's to hand over.

- What a selection gives back MUST be the text that was written rather than the screen it was
  drawn on: a line too long for the terminal is drawn over four rows and MUST come back as the
  one line it is, without the break the width put in it and without the spaces that padded each
  row out to the edge. A break in what comes back MUST be a break that was really there.
- Every row drawn MUST therefore say which line of the text it is a piece of and where in that
  line it begins, including a row with nothing on it and the room below the last line: a row
  that says nothing about itself is one Textual can only take to mean the whole widget, and a
  drag that began on a blank line would copy the lot.
- A thing Rich draws rather than says MUST be kept as the rows it drew, a line apiece. There is
  no text behind a box to go back to.
- A selection MUST be let go of rather than moved when what it was made against goes: the
  transcript being emptied, or drawn again at another width -- a box is as many lines as it has
  rows, and is a different number of rows in a narrower terminal. One that quietly comes to mean
  the lines below the ones somebody dragged across is worse than one that is gone.
- Two clicks MUST take the word under them and three MUST take the whole line, rather than
  Textual's own answer to both, which is every line there is -- and which, since a selection is
  copied as it is let go of, would put a day's transcript on the clipboard.
- The lists MUST be selectable as the rows they offer, and MUST stay lists that are picked from:
  a click is a choice and only a drag is a selection. Textual numbers the offsets it leaves on a
  drawn row against the option that row came out of, so they MUST be said again against the
  whole list, or every option in one reads as the first.
- The transcript MUST NOT take focus, and MUST NOT jump to the end while something further up is
  being read: the editor is the only thing on the screen that is typed at, and a transcript that
  scrolled out from under a drag could not be copied from while a flow was running.

## `pick.py`

The sheets: which flow, how it is set up, what each of its agents is, the agents kept under a
name, the accounts they run as, and how the run is going. Each MUST be drawn the way Claude
Code draws its own `/model` -- a rule across the top, the question and a line about it, the
choices numbered with a marker against the one under the cursor, and under them whatever is
adjusted rather than chosen.

### The keys

- No key here MUST be a chord. A sheet asks one thing and its keys are its own, so a key that
  needed a modifier held down would be a key somebody had to already know about; what is
  reached with one is either a letter or a key a terminal already has.
- Typing MUST NOT be what searches. Every letter on these sheets is a key of its own, so a
  search MUST be asked for -- on `s` -- and MUST be left on esc, which clears what was typed
  before it goes. While one is running the letters MUST reach it rather than the keys they
  otherwise are, and esc MUST come out of the search before it leaves the sheet.
- A menu of several pages MUST show their titles, and tab and shift+tab MUST turn between
  them: that is the one pair of keys a terminal has for exactly this. A page that may not be
  opened MUST still be a title, struck through, and MUST be stepped over rather than opened.
- A page made of several lists MUST show what they are called, and the left and right arrows
  MUST step between them: the list itself is walked up and down, so across is what is left,
  and the titles are read the same way the pages' are.
- Taking anything away MUST be asked for twice on the same key, the first press saying what
  the second one does. Moving the cursor MUST put it down again, so that a stray press is
  harmless.
- The keys MUST be inside the terminal, whatever the sheet is holding: the list is what MUST
  be shortened until they are, since everything else on a sheet is a line or two and the rows
  are what there are a hundred of. The keys are the last row, so they are what falls off the
  bottom of a short terminal, and a key nobody can see is a key nobody has. A line of them too
  long for the width MUST wrap rather than run off the side, for the same reason.

### What lands, and when

- A menu MUST hold everything changed in it until it is left and saving is confirmed. Turning
  a page MUST apply nothing: what is read on the second page is what the first is holding, and
  a menu that applied each page as it was left would be one where walking out changed things
  nobody confirmed.
- Esc on a menu holding changes MUST ask whether to save them, and esc on that question MUST
  be the way back to the menu. Esc on a menu holding none MUST just leave: a walk in to look
  and out again is not a question anybody wants asked of them.
- That question MUST be drawn as a box in the middle of the screen, over the menu it is about
  rather than instead of it: a sheet is a question somebody walked to, and this is one that
  arrived. It MUST be the two answers there are -- save, or throw away -- and MUST NOT make a
  row of going back, that being what esc already is on every sheet there is.
- What runs an external command MUST NOT be held: making an account and signing one in own the
  terminal while they run, and something that has already happened is not a draft.

### Which flow, and what drives it

- The flow menu MUST be two pages: which flow to run, and what each of its agents is. Two
  because they are two questions about one thing and are not open at the same moments.
- The page that chooses a flow MUST be shut while a flow is running: a flow is chosen in order
  to be started, and there is one going. The page its agents are set up on MUST never be shut
  -- an agent thinking too little, on the wrong account or allowed too much is found out
  halfway through a run.
- What is saved while a flow runs MUST reach the agents that are running, as far as it can:
  each of them MUST be set up as it now stands from its next turn on. A CLI that has changed
  MUST NOT be swapped under the flow holding that agent -- a backend is the class the agent is
  -- and MUST be said to take effect from the next run rather than silently doing nothing.
- A flow MUST be copyable into this project's own flows from the page it is chosen on, on a
  key. A flow is a directory, so the copy MUST be the whole of it -- what it imports and the
  skills it brings -- and MUST land under the name it already had, which from then on means
  the copy. It is the only way to change a flow that keeps: a flowverse is somebody else's
  repository and is fetched again over whatever was written into it.
- The flows MUST be read a place at a time, the arrows stepping between the places: every
  flowverse there is, fetched or not, and then this project's flows and yours where there are
  any. All of them in one list under headings was a list nobody could see the end of, and one
  where walking to a flow meant walking past every flow that came before it. A flowverse MUST
  be one of the places whether or not it has been fetched -- fetching it is what having it
  here is for -- and one with nothing in it MUST say so where its flows would be. A directory
  of your own with nothing in it MUST NOT be one of them, there being nothing to add to it.
- Which place is being read MUST be visible, and MUST be visible as one of however many there
  are: a flowverse nobody can see is a flowverse nobody steps to. The place read when the page
  opens MUST be the one the flow in force came from, that being the flow the page is about.
- A search MUST narrow the places to the ones it found something in, and MUST step to one of
  them: a search is for finding a flow whose flowverse is the thing nobody remembers, so one
  that left somebody stepping through empty lists to reach the row it found would be a search
  that answered a question nobody asked.
- A flowverse that has never been fetched MUST be fetched as the menu opens, in the
  background: it is here because its flows are wanted, and a list with nothing in it and a
  key to press about it is a step nobody would choose to take. It MUST NOT hold the menu up,
  MUST NOT move what is being read, and MUST be tried once per opening however it goes -- a
  machine with no network says so once rather than on every keystroke.
- Adding a flowverse, fetching one again and taking one away MUST NOT be keys of this page.
  They are things done to the list of places rather than to the flow under the cursor, and a
  sheet that asks `which flow` with three keys on it about something else is a sheet asking
  two questions. `/flowverses` is where they are, and stepping between the places stays here:
  that is about which list of flows is being read.
- Setting the flow itself up MUST be asked as the flow is chosen, between the flow and its
  agents, rather than being a key or a page of its own: a flow that takes settings is chosen
  in order to be run with settings, and that is the one moment somebody is thinking about the
  flow rather than about what drives it. A flow that takes none MUST NOT be asked, the walk
  being the same either way, and what is answered MUST be held with the rest until the menu is
  saved.
- Each flow MUST say what it does beside its name, which is the line the flow itself says. What
  is typed MUST narrow the list by name and not by that line: a subsequence of a sentence is a
  match nobody typed.
- Choosing a flow MUST read back what that flow was last set up with here, and MUST end on the
  page its agents are on: that is the next thing to answer.
- A menu MUST NOT be saved holding an agent that names no model: a flow driven by one is a flow
  that stops on its first turn, and the page it would be answered on is the page to be looking
  at when that is said.

### What one agent is

- Everything one agent is MUST be one sheet of rows rather than a walk of a sheet per question:
  an agent is one thing with a CLI, an account, a model at an effort, a rung of what it may do
  and a machine its work lands on. A walk meant that changing the effort of
  an agent already set up was four keypresses through two sheets with nothing to say.
- The rows MUST be in the order of what depends on what: the CLI settles which accounts there
  are and which models that CLI will name, and the account settles which of them it may name.
  Changing the CLI MUST therefore let go of the model, which belonged to the CLI before it.
- The account MUST always offer the machine's own first, as `as local`: an agent nobody has
  been asked about runs as whoever signed the CLI in, and that is a row rather than a blank.
- A row that is a rung in an order -- the effort, what it may do, whether it runs as a fleet,
  whether goals are available, whether it may search the web -- MUST be stepped where it
  stands on the arrows. Everything else MUST open a sheet of its own and come back.
- Whether it may search the web MUST be a row only for a CLI that can be told: a switch for
  something the backend would go on doing whichever way it was set is a switch that lies, and
  a CLI with no way of being told is one this question is not put about.
- Where an agent works MUST be a row only where the flow said that agent may be pointed at a
  machine, and MUST be read rather than opened where the flow settled it: an agent that works
  here, and one the flow isolates in a container of its own, are each a question nobody is
  being asked. A saved agent belongs to no flow, so it MUST be asked every question there is.
- Nothing MUST be typed in that could be found: the CLIs offered MUST be the ones installed
  here less any the flow ruled out, the models offered MUST be the ones that CLI said it runs
  as the account chosen for it, the efforts offered MUST be the ones that model takes, and the
  skills shown MUST be the ones that CLI would load. Nothing MUST be asked of a CLI while a
  sheet is being drawn -- starting one costs seconds a prompt has not got -- so what was kept
  is what is read.
- The models MUST be askable again from the sheet they are chosen on, on `r`, which is the key
  a flowverse is fetched again on. This is where somebody finds out that the model they came
  for is not in the list, and sending them elsewhere to fix it would lose the question they
  came to answer. Asking MUST NOT stop the interface redrawing, and what came of it MUST be
  said under the list rather than raised at whoever opened the sheet.
- A CLI that has never said what it runs as the chosen account MUST say so where the list
  would be, and MUST say which key asks it: an empty list that explains nothing reads as a
  CLI with no models.
- An account MUST be makeable from the row that asks for one. That row is where somebody finds
  out they have none for that CLI, and sending them to another command to make one loses the
  question they were answering.
- The skills sheet MUST be a reading and MUST NOT be a checklist: the skills a CLI finds are
  that CLI's own, installed and switched off where that CLI keeps them, and the sheet MUST say
  so under the list rather than offer a switch. A CLI that keeps none anywhere MUST say that,
  rather than that none are installed.

### Where flows come from

- `/flowverses` MUST list every place there is, saying where each came from and which have
  not been fetched, and MUST be the four things there are to do with one: what it holds, one
  added, one fetched again, one taken away. It MUST be the same store `/flow` reads the flows
  out of and the same one `hmz flowverses` walks -- one place a thing is kept is one place it
  is kept, whichever way somebody reached it.
- Enter MUST say what one holds, which MUST be read only of the flowverse it was asked of: a
  flow is read by running it, so what a place holds is the one question about it with no cheap
  answer. `a` MUST add one; `r` MUST fetch one again; `d` twice MUST take one away.
- Nothing here MUST be held until the menu is saved: each of these runs git, and something
  that has already been cloned is not a draft. What became of one MUST be said under the list
  rather than raised at whoever opened it, and MUST NOT stop the interface redrawing while it
  runs.
- Where a flowverse came from MUST be shown with whatever was signed into the URL taken out,
  for the reason `hmz flowverses` shows it that way: a private one is added as
  `https://x-access-token:$TOKEN@...`, git keeps that verbatim, and a token on a screen is a
  token in a photograph. It MUST be taken out in one place, which both ways of showing it ask.

### The agents kept under a name

- The agents menu MUST list the agents written down under a name, and MUST NOT be the agents of
  a flow: an agent is a CLI, an account, a model at an effort and what it may do, and none of
  that is a thing about the flow that happens to be driving it. Enter MUST set one up, on the
  same sheet a flow's agent is set up on; `a` MUST add one; `d` twice MUST take one away.
- A flow MUST be able to import one where its agents are set up, and MUST take a copy: an agent
  tuned inside a flow is that flow's, and writing the change back into the thing it was copied
  from would change every other flow that had imported it.
- A flow's agent MUST be saveable as one, under a new name or over one already there. Which is
  the other half of importing: what was tuned in a flow is worth keeping.

### The accounts

- The accounts menu MUST list every account there is under a heading per CLI, and MUST be read
  rather than chosen from: which account an agent runs as is asked where that agent is set up.
  `a` MUST make one and `d` twice MUST take one away.
- What else can be done to one account -- correcting what it holds, signing it in again,
  saying which account it falls back to, saying how a failed turn under it is tried again --
  MUST be a menu opened with enter on the account it is about, rather than a letter apiece on
  the list. Four questions about one row is a menu; four letters that have to be read off the
  bottom of the screen are four keys nobody presses, while enter -- which every list already
  means -- did one of them.
- Writing down a CLI of your own MUST be a row of the list of backends a new account is for,
  rather than a key of the accounts menu: it answers `which CLI`, which is the question that
  sheet is asking, and it is reached at the moment somebody finds out that the agent they
  want is not one humanize drives.
- The account this machine is already signed into MUST be a row too, under each CLI that has
  an account of its own and after the ones somebody made: it is what an agent nobody gave an
  account runs as, and where that agent's chain begins. Correcting it and signing it in MUST
  NOT be offered for it, with the reason said where they would have been, and taking it away
  MUST say why there is nothing to do rather than doing nothing: humanize did not make that
  account and keeps no credentials for it.
- An account several backends could be run as MUST be asked, at the moment it is made and at
  the moment it is corrected, which of them to write it down for as well. It is one question
  about one account rather than a walk of its own, so it MUST be one sheet of switches, and
  the ones installed here MUST start on -- those are the ones an agent could be run on
  tomorrow. An account that could run nothing else MUST NOT be asked about at all: a sheet
  with nothing on it is not a question.
- What is copied while an account is being corrected MUST be held until the menu is saved, as
  the correction itself is: correcting one is usually a key being rotated, and the copies are
  the other places that key is.
- Where an account falls back to MUST be chosen from that CLI's own other accounts, and MUST
  offer the end of the line first: each account naming the next is what makes a chain, and an
  account cannot fall back to itself.
- How an account is tried again MUST be three rungs stepped where they stand -- how many
  tries, which wait, and how long the whole may go on for -- rather than three numbers to
  type: a text box for an integer is a text box to validate.
- A row MUST say the name, the way it was made by and the variables it sets. Their names and
  never a value: this is drawn where somebody can read it, and a key on a screen is a key in a
  photograph. A secret MUST NOT be read back onto the screen to be corrected -- it is typed
  again or it is left as it was.
- The row that takes variables of your own MUST take several, a line apiece, and MUST break
  the line on the same keys the editor does: enter is what takes the form, so a list typed
  into one row needs a key of its own to be a list at all.

### Where a turn goes when it cannot be taken

- Falling back MUST be a menu of its own rather than a row of the accounts. Two things are
  called that and they answer two different failures: an account that goes down, which
  another account of the same backend answers inside the conversation that was running, and
  an agent that has nowhere left to run -- a model retired, a CLI that will not start, a rate
  limit on the whole account -- which only another agent answers. Half of it is not about
  accounts at all, and the question somebody has when they come here is not "what does this
  account do when it fails" but "what happens when this stops working".
- It MUST be two pages of one menu rather than two menus, since it is one question at two
  scales: the steps between agents, and the chains between accounts. Both MUST be held until
  the menu is saved, as everything held on a menu is.
- A step MUST be two agents chosen, and each MUST be chosen on the same sheet a flow's agent
  and a saved agent are chosen on: an agent is one thing to choose -- a CLI, an account, a
  model at an effort -- and a second way of choosing one would be a second thing to keep
  right. An agent that would fall back to itself MUST be refused where it is said.
- The accounts page MUST be the same store `/providers` walks, and its keys MUST say so: an
  account is made and taken away there, and this page is where it is said what one falls back
  to. A key that did nothing MUST say why rather than do nothing.
- An empty page MUST say which key writes one down. A list with nothing in it and nothing
  under it reads as a feature that does not work.

### The runs that have already happened

- `/cycles` MUST list every run of a flow in this directory, newest first, saying what each
  was -- when it began, which flow, what it was asked to do, how it went and how many sessions
  it opened -- and marking the ones whose flow says they can be picked up again. A run is
  written down as it happens and nothing showed them, which made the record something only a
  command line could reach.
- It MUST be read rather than chosen from: enter MUST open what there is to do with the run
  under the cursor rather than doing any of it, since what there is depends on that run. A
  flow that says it can be picked up MUST offer carrying on from where it stopped; every run,
  whatever its flow says, MUST offer the things that can be done to a run that is over.
- Whether a run can be picked up MUST be asked of its flow rather than read off the run,
  wherever it is said -- the mark on the row and the row in the menu alike: a flow is a
  directory on disk, and one marked since that run is one whose older runs can be picked up
  now, while one that no longer says so MUST say why there is nothing to carry on from rather
  than offering it. What the run recorded is what it was, not what can be done with it.
- A trace gathered here MUST be a trace of that run: the sessions it opened and no others,
  asked for by the ids it wrote down rather than by the directory it ran in. A trace of what
  a directory holds whoever opened it MUST NOT be offered here at all -- this is a list of
  runs, and a trace that is of none of them has nothing here to hang on; `hmz trace collect
  --all` is where it is asked for.
- Carrying a run on MUST run that run's own flow, on that run's own agents, with what it was
  asked to do -- what is being picked up is what ran, and an agent swapped under it would be
  a different run wearing its name. It MUST be a run of its own, saying which run it came
  from, since a closed cycle is never reopened. While a flow is running it MUST be refused
  where it was asked for, `ctrl+c` twice being what stops one.
- It MUST be readable while a flow runs: what has already happened does not change under one.

### How the run is going

- `/status` MUST say how the run is going and MUST draw the shape of it, and MUST be what
  `esc` opens. It is read rather than answered in every other respect, so it MUST NOT be
  refused while a flow runs and MUST be redrawn while it is open: what it is about moves
  without anybody touching it.
- The shape MUST be drawn as a box per agent rather than listed. It is a graph, and a graph
  read as an adjacency list is one nobody reads. The boxes MUST be in the order the flow takes
  its agents, and the handovers between neighbours MUST be the arrows joining them, with how
  often each went. That is the shape of nearly every flow there is, since a flow is written as
  one agent after another. A handover the boxes have no arrow for MUST be said under the
  diagram rather than drawn: a line crossing the page from the first box to the fourth is a
  line nothing in a terminal draws readably.
- An agent that has not taken a turn MUST NOT be drawn, and one MUST appear as its first turn
  starts. A flow may declare ten agents and reach three of them -- it is a Python file, and it
  may never take the branch the other seven are on -- so what is drawn MUST be what the run is
  *doing* rather than a list of what was configured. Which agents there are MUST therefore be
  asked again as the sheet is redrawn rather than settled when it opened, or a box would appear
  only to whoever closed the sheet and opened it again.
- An agent one of them started of its own MUST be drawn under the box of the agent that
  started it, without a box of its own, marked as still going or as come back. It is not an
  agent of the flow -- nobody chose what it runs, nothing can be said to it and it has no
  transcript -- so it MUST NOT be a row anything attaches to, and its mark MUST differ from
  the one a flow's own agents wear: a box round it would say it was another agent to read. A
  fleet too long to draw MUST be cut, with a line saying how many were left off.
- Which agents are working MUST be marked on the boxes, and MUST move as they do. It is the
  one thing on this sheet that changes by itself, and the reason somebody opened it.
- Enter or a click on a box MUST read that agent, whether or not it is working. `tab` is held
  to the ones working, so this is the one place an agent that has stopped is reached. The first
  row MUST be the transcript every agent's work appears on, which is the way back to watching
  the flow rather than one agent of it.
- The agents of the last run MUST still be drawn once it is over. Their transcripts are still
  on the screen and still worth reading back, and a run that has just ended is the one
  somebody wants to look at.

### The board

- The board a flow and the person both write on MUST be drawn on this sheet, under the
  diagram, for a run whose flow talks to the person. It is about the run -- what there is left
  to do belongs beside how far through the run is -- and a board somebody has to go and open is
  a board nobody reads.
- It MUST be changed here without anything waiting: a line typed onto it MUST be there the
  moment it is typed, and the flow MUST go on running throughout. That is what tells it from a
  question, which stops the turn it was asked in until it is answered.
- Each line MUST say what it is called and what it says, and one that is the flow's own MUST
  say so and MUST NOT be opened for editing: a flow writing down how far through it is must not
  have that edited underneath it. Refusing MUST be said where the key was pressed rather than
  by doing nothing.
- Putting a line up, changing one and taking one away MUST be the keys the rest of the
  interface uses for those: a letter to add, enter to change what is under the cursor, and the
  taking-away key pressed twice.
- Nothing here MUST be held until the sheet is left. This is not a menu: the flow may be
  reading the board on the next line it runs, and a line held back would be one the flow was
  never told about.

### What humanize remembers

- `/settings` MUST be two pages: what is true of this machine wherever humanize is run from,
  and what is remembered about this directory. Two pages because they are two kinds of thing
  rather than two halves of one, and both MUST always be turnable.
- Whether humanize reports its own failures MUST be a row of the first, and what a report
  carries -- and what it never carries -- MUST be readable from beside it: the question is
  asked once on a first start, and this is where somebody who wants to read it again, or
  answer differently, goes.
- The row MUST say what is written down rather than what is happening where an environment
  variable is answering for the run, and MUST say that it is doing so: a menu that showed the
  override would be a menu offering to change something it cannot.
- Forgetting what is remembered about this directory MUST be a row of the second page, and
  MUST leave every other directory and every setting alone.
- Nothing MUST land until the menu is left and saving is confirmed, as on every other menu.

### The question on a first start

- Whether humanize reports its own failures MUST be asked once, by the interface, on a start
  where nobody has answered it -- and MUST NOT be asked by anything without somebody at it.
- It MUST say why it is being asked and MUST list what would be sent and what never would,
  where it is asked rather than somewhere to go and read.
- The answer that helps MUST be the one it opens on. Walking away MUST leave it unanswered and
  MUST be asked again next time: silence is neither a yes nor a no.

## `monitor.py`

```python
@dataclass(frozen=True, slots=True)
class Shape:
    turns: Mapping[str, int]
    working: frozenset[str]
    handovers: Mapping[tuple[str, str], int]


@dataclass(frozen=True, slots=True)
class Spend:
    model: str
    tokens: int
    rate: float


@dataclass
class Monitor:
    def begins(self, agent: str, model: str) -> None: ...
    def ends(self, agent: str) -> None: ...
    def spend(
        self,
        agent: str,
        tokens: int,
        model: str | None = None,
        now: float | None = None,
    ) -> None: ...
    def spending(self, now: float | None = None) -> list[Spend]: ...
    def now_working(self) -> list[str]: ...
    def shape(self) -> Shape: ...
```

What a flow is doing, kept from the turns going past -- which is the only place it is visible,
a flow being a Python file that may branch any way it likes.

- MUST be written from `AgentBase.watch`, and MUST NOT ask anything of the flow.
- Every read and every write MUST hold the lock: the turns are on threads of their own and
  the interface reads while they run.
- `shape` MUST report every agent the flow has run and how many turns each took, whichever
  are working, and every handover between them with how often it happened: that directed graph
  is the shape of the run. It MUST be taken whole under the lock, so that what is drawn from
  it is one moment of the run rather than three moments of three counters.
- `spending` MUST be per model rather than per agent, since two agents at one model are one
  bill, and MUST report a rate over a recent window only -- a flow that has stopped reads as
  stopped rather than as whatever it once averaged.
- A backend that says what a turn cost MUST be believed over what its agent was configured
  with: a turn that reached for a sub-agent spent it on that model.

## `complete.py`

```python
def offered(typed: str, commands: tuple[str, ...]) -> list[str]: ...
def flows(where: str | None = None) -> list[str]: ...
```

What the editor offers to finish, which is the only way anything is chosen.

- Nothing MUST be chosen from a dialog. A `/` MUST offer the commands, and a flag MUST offer
  whatever it is for -- the flows below this directory, the backends an agent runs on -- so
  that there is one way to say a thing and it is the way it is written down.
- An offer MUST be the whole of what the word becomes, so that taking one replaces what was
  typed rather than being appended to it.
- A command that has been written out MUST be offered nothing: enter over an open list takes
  what is under the cursor rather than sending the line, so a command that is the start of a
  longer one -- `/flow`, beside `/flowverses` -- would otherwise be one nobody could send.
- Finding the flows MUST NOT cost the interface its responsiveness: it reads every Python
  file below this directory, which is far too slow to repeat between keystrokes.

## `discover.py`

Which agents are installed here, what each one runs, and where their turns could land.

- Nothing MUST be asked of a backend here: starting one costs what it costs, and this is read
  at a prompt. What each runs MUST be what `hmz.models` last kept for it, and what only this
  machine knows -- which containers are up, which hosts are in an ssh config -- MUST be read
  off the disk it is written on.
- A backend that is not installed here MUST NOT be offered, and neither MUST an effort a model
  does not take.

## `history.py`

What has been typed here before, so that it can be had back by walking to it.

- Everything said MUST go down: the task that starts a flow and the words put into one already
  running alike. One file MUST hold them all, under humanize' own home, each line saying which
  directory it was typed in.
- What is walked MUST be what was typed in this directory, and everything ever typed anywhere
  where nothing has been typed here yet. Which of the two it is MUST be settled when the
  interface starts: a history that changed under you mid-session would be one nobody could find
  their way back through.

## `tally.py`

What a run has cost, read from the logs the agents keep for themselves.

- A backend says what a turn cost only once the turn has ended, and a turn is minutes long, so
  what is shown MUST be read from the CLIs' own usage logs as they are written instead.
- What is read MUST be reported as a total rather than as an addition, so that a log read twice
  cannot count a token twice -- and so that the backends' own reports may stand beside it,
  whichever has seen more being what has been spent.

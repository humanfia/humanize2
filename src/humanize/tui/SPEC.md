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
├── settings.py
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

- It MUST open on a flow that is only talking to one agent, at the first agent installed, so
  that saying something is all it takes to start. A flow is what is reached for once talking
  to one agent is not the shape of the work, and that is not known before anything has been
  said. The agent it opens on MUST NOT be at the hardest effort the model takes: that is the
  one to reach for, not the one to spend before it has been asked for.
- Choosing a flow MUST stop whatever is running, since a flow is chosen in order to be run.
  Looking at the flows and leaving without choosing MUST change nothing at all.
- It MUST be drawn in the terminal's own colours, and MUST NOT ask the terminal what they
  are: every surface is the terminal's background and everything drawn is one of the sixteen
  colours the terminal already has a setting for, or a reversal of what is already there. A
  colour of its own would be a guess about the background it lands on.
- The editor MUST mean both things at once: a line beginning with `/` is a command, and any
  other line is said to the conversation being read, through `SessionBase.interject`, so that
  a turn already under way takes it into account rather than being restarted with it.
- Enter MUST send and `ctrl+j` MUST break the line, so that a long prompt can be written.
- A half-typed line MUST be offered what it could be finished with, in a list under the
  editor, and tab MUST take what is highlighted. What is offered MUST be reconsidered when the
  cursor moves as well as when the text does: an offer made at the end of a line MUST NOT
  still stand once the cursor is back in the middle of it.
- Keys the offers are using MUST be theirs only while there are offers: a prompt of more than
  one line needs its arrows back, and focus MUST NOT be able to leave the editor.
- The transcript MUST be one conversation rather than every agent's at once: a flow drives
  several agents and an agent holds several sessions, and all of them interleaved is none of
  them readable. What each session says MUST be kept against that session, the transcript
  MUST show the one being read, and attaching to another MUST draw it again from what was
  kept. What is kept MUST be bounded -- a flow runs for days and a Ralph loop opens a session
  a turn -- by keeping the last few sessions and the last few lines of each.
- tab and shift+tab MUST step to the next and the previous session that is *working*,
  wrapping, and MUST do nothing at all where none is. The ones working rather than every one
  the flow holds: with ten agents going, what somebody is stepping between is the ones
  thinking. A session read already MUST be left where it is when its turn ends -- it is being
  read -- but MUST NOT be stepped onto again until it is working. What is read MUST be held by
  identity rather than by where it comes among them, since a flow opens and drops them as it
  runs: when the one being read goes, the newest of that agent's MUST be read instead, and
  the nearest that is still there where that agent has none.
- Which session is being read MUST be visible, beside how many that agent holds, and a
  session that is not being read and has said something since it was last looked at MUST be
  marked as having something unread. Otherwise a flow of ten conversations is nine nobody
  knows to look at.
- Whether each agent is working MUST be visible on that same line. It is the first thing
  looked for with several going at once -- who is thinking and who has stopped -- and the one
  thing there that changes without anybody touching it.
- A typed line MUST reach the session being read, not whichever agent has a turn open: an
  agent holding two sessions is working in one of them, and a line said to the other is a
  line said to the wrong conversation. It MUST reach it only while a turn of that session is
  open -- one between turns would answer it on its own, outside the flow -- and MUST wait for
  the turn that starts next otherwise.
- The accounts an agent may be run as MUST be reachable from here as well as from a command
  line: an account outlives the flow that was set up with it, and the one place a person is
  asked anything is the one place a credential can be typed. It is the one thing said in both
  places, and the same store either way.
- `hmz collect` and `hmz anchor` MUST NOT be commands here. Neither is a thing to do to a flow
  that is running, and a command that only ever means one thing is a command line.
- A turn MUST be shown as it happens: which agent is taking it, each tool it uses as one
  compact row, and what it says. It MUST be shown once -- a backend teeing to stderr for the
  benefit of a plain terminal MUST NOT also be shown here. `/details` MUST toggle all of what
  a turn did on the way to its answer, tool calls and thinking together: they are one question
  -- how much of the working to show -- and were two switches for no reason.
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
  anything is, and the flow if not. Two of them in a row MUST leave, so that leaving is always
  two presses and never one.
- A line that cannot be carried out MUST be shown and MUST leave the interface up. Only
  `/exit` and two `ctrl+c` close it.
- A key of the interface's own MUST NOT fire while a sheet is up over it: a sheet is open in
  order to be answered, and reading another conversation is not an answer to it. The key MUST
  reach the sheet instead, rather than being swallowed by the interface and doing nothing.

## `pick.py`

The sheets: which flow, how it is set up, what each of its agents runs and where, and how the
run is going. Each MUST be drawn the way Claude Code draws its own `/model` -- a rule across the
top, the question and a line about it, the choices numbered with a marker against the one under
the cursor, and under them whatever is adjusted rather than chosen.

- Nothing MUST be typed in that could be found: the CLIs offered MUST be the ones installed
  here, the efforts offered MUST be the ones that model takes, and the skills offered MUST be
  the ones that CLI would load. Nothing MUST be asked of a CLI to find out -- starting one
  costs seconds a prompt has not got.
- Which flow to run MUST be asked out of the places flows come from, a tab apiece: every
  flowverse there is, fetched or not, and then this project's flows and yours where there are
  any. The arrows the list itself is not using MUST turn between them, as they do between the
  CLIs. A flowverse MUST be a tab whether or not it has been fetched -- fetching it is what the
  tab is for -- and a directory of your own with nothing in it MUST NOT be one, there being
  nothing to add to it.
- Adding a flowverse, fetching one again and taking one away MUST be keys of this same sheet:
  this is the moment somebody finds out that the flow they want is in one they have not added,
  or that the one they have is out of date, and sending them elsewhere to fix it would lose the
  question they came here to answer. What became of a fetch MUST be said under the list rather
  than raised at whoever opened the sheet, and a fetch MUST NOT stop the interface redrawing
  while it runs.
- Each flow MUST say what it does beside its name, which is the line the flow itself says. What
  is typed MUST narrow the list by name and not by that line: a subsequence of a sentence is a
  match nobody typed.
- What each agent is MUST be asked in three steps, one agent at a time and in this order: which
  CLI and which of its accounts, then which of that CLI's models at what effort, then -- only
  for an agent the flow said may be pointed at a machine -- where it works. The order is what
  depends on what: an account is one backend's and a model belongs to the CLI that runs it, so
  neither is answerable before the CLI has been chosen. Esc MUST be the step before, out of the
  first step of the first agent entirely, and a step stepped back into MUST be as it was left.
- The last of those steps MUST NOT be put up for an agent the flow did not say may be pointed
  at a machine: an agent that works here, and one the flow isolates in a container of its own,
  are each a question nobody is being asked.
- What an agent runs MUST be one choice rather than two, a model belonging to the CLI that runs
  it; and the CLIs MUST be read one at a time, a tab apiece, since every model of every CLI in
  one list is a list that grows each time any of them ships a model. The arrows the list itself
  is not using MUST turn between them, and MUST wrap: a sheet that asks one thing has its keys
  free, and a chord for what a row of tabs is for would be a key to already know. One CLI MUST
  be a heading rather than a row of tabs: there is nowhere to switch to, so nothing MUST say
  there is.
- A step MUST NOT read back what another step settles. What cannot be changed where it is shown
  is a setting somebody tries to change there; what the walk has settled is on the line above
  the prompt when it is over.
- Typing MUST narrow the list being read and MUST belong to the tab it was typed into: a search
  that narrowed one CLI to one model would narrow the next to none, which reads as a CLI with
  nothing in it. Esc MUST clear what was typed before it leaves, on every sheet that is
  searched.
- Which of its CLI's skills an agent is loaded with, what it may do, and whether it runs as a
  fleet are each a second question about that agent rather than a way of running the model, so
  each MUST be a key on the sheet that asks what it runs rather than a row in it, and each MUST
  open a sheet of its own. Walking out of one of those without answering MUST leave that agent
  as it was. Where an agent works MUST NOT be one of them: a flow that says an agent may be
  pointed at a machine is a flow expecting to be told which, and a question somebody has to
  already know a key for is one that does not get asked.
- An account MUST be makeable from the step that asks for one. That step is where somebody
  finds out they have none for that CLI, and sending them to another command to make one loses
  the question they were answering.
- The skills sheet MUST be a checklist: every skill starts on, which is how a CLI comes, and
  space MUST switch the one under the cursor. What it answers with MUST be the skills the agent
  is to have. A CLI that offers no way of being told which to load MUST say that, rather than
  that none are installed.

## `settings.py`

What one workspace was last set up to run, kept under humanize's own home as `settings.yaml`
so that opening the interface again in the same project finds it that way.

- MUST be kept per flow as well as per workspace, by the name humanize's own flows have and by
  the path yours have: what an agent runs is only meaningful against the flow driving it, and a
  flow of yours MUST NOT inherit the agents of the one it shares a name with. Each agent MUST
  be keyed by the name the flow calls it, so that a flow which grows an agent in the middle does
  not silently hand the reviewer's model to the builder.
- A setting that was never chosen MUST be left out rather than written down as a default: a
  file written before there was such a setting and a workspace nobody has been asked MUST read
  the same way. What is read back MUST be checked before it is used -- a flow's own model
  refuses a config it no longer takes -- and a file that is missing, unreadable or not what
  this writes MUST be a workspace with nothing remembered rather than a reason not to open.

## `monitor.py`

```python
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
    def graph(self) -> list[str]: ...
```

What a flow is doing, kept from the turns going past -- which is the only place it is visible,
a flow being a Python file that may branch any way it likes.

- MUST be written from `AgentBase.watch`, and MUST NOT ask anything of the flow.
- Every read and every write MUST hold the lock: the turns are on threads of their own and
  the interface reads while they run.
- `graph` MUST report every agent the flow has run, marking whichever are working, and every
  handover between them with how often it happened: that directed graph is the shape of the
  run.
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
- Finding the flows MUST NOT cost the interface its responsiveness: it reads every Python
  file below this directory, which is far too slow to repeat between keystrokes.

## `discover.py`

Which agents are installed here, what each one runs, and where their turns could land.

- Nothing MUST be asked of a backend: starting one costs what it costs, and this is read at a
  prompt. What each runs MUST be read out of `humanize.backends`, and what only this machine
  knows -- which models an account may run, which containers are up, which hosts are in an ssh
  config -- MUST be read off the disk it is written on.
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

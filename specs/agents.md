# Agents

## File Structure

```
.
├── __init__.py
├── base.py
├── board.py
├── claude.py
├── codenames.py
├── codex.py
├── config.py
├── event.py
├── hooks.py
├── human.py
├── kimi.py
├── mimo.py
├── opencode.py
├── pi.py
├── skills.py
├── tools.py
└── watchdog.py
```

## `__init__.py`

Expose `AgentConfig`, `AgentBase`, `Event`, `Question`, `Saying`, `Stopped`, `Failed`,
`Unrecoverable`, `Usage`, `SessionBase`, `CommandSessionBase`, `StreamSessionBase`, `Tool`,
`Toolbox`, `Board`, `Item`, and all agent and session classes.

## `event.py`

`Event`, `Question`, `Stopped`, `Usage`, `Failed`, `Unrecoverable`, `Saying` and `say`: what a
turn says while it runs, what it asks, what it cost, how it failed, and how the fragments it
arrives in are put back together -- with no behaviour on the values themselves.

```python
class Failed(subprocess.CalledProcessError):
    def __init__(
        self,
        returncode: int,
        cmd: Sequence[str],
        output: str | bytes | None = None,
        stderr: str | bytes | None = None,
        *,
        fault: str = "",
        fix: str = "",
    ) -> None: ...

    def reads(self) -> str: ...


class Saying:
    def delta(self, kind: str, text: str, whose: str = "") -> None:
        """Takes one fragment of an answer, which is nothing to show on its own."""

    def whole(self, kind: str, text: str, whose: str = "") -> None:
        """Takes one kind of an answer entire, as the backend has it."""

    def upto(self, whose: str = "") -> list[Event]:
        """Says one answer as far as it has got, and remembers how far that was."""

    def ended(self, whose: str = "") -> list[Event]:
        """The same, and then lets the answer go: it has now been said in full."""

    def rest(self) -> list[Event]:
        """Everything gathered and not yet said, whichever answer it belongs to."""
```

- `Saying` MUST gather the fragments a streaming backend sends into the utterances they are
  pieces of, and every backend that streams MUST read its deltas through it rather than saying
  one as it arrives. A fragment is not a thing to show: an `Event` per token is a line per
  token on a terminal and a bulleted, blank-line-spaced block per token in a transcript --
  one paragraph broken into fifty rows of one word, which is not what the agent said and
  cannot be read as it. One coalescer, not one per backend: the same fragments arrive from all
  of them and the same mistake was made twice already.
- An utterance MUST be said the moment the agent reaches for a tool, because what it said
  before reaching is what says why it reached, and again as its message ends. It MUST NOT be
  held for the end of the turn: a turn is minutes of tool calls, and one that showed nothing
  until it was over is a flow that reads as hung for all of them.
- What has been said MUST NOT be said twice, so that a backend repeating the whole message once
  it is finished adds only the part nobody has seen -- and one that streamed nothing says the
  whole of it, both arriving the same way.
- Nothing MUST be left gathered once a turn's stream stops: a backend whose turn ends without
  closing its last message MUST say what it was holding, or the turn swallows its own answer.
- Several answers MAY be in flight at once, so each is gathered under whatever the backend
  numbers it by -- a message id, the step of the turn. A backend with one at a time MUST be
  able to name none, and so MUST the event that closes a message on a backend that names the
  rest: what has just come back is what the fragments before it were fragments of.
- What was thought MUST be said before what was said, whichever of them arrived first: the
  thinking is what says why the words followed, and an order that moved with the stream would
  put the two round the other way as often as not.

- `Failed` MUST be a `subprocess.CalledProcessError` that says what went wrong where whoever it
  happened to can read it: a flow catches turns rather than transports, and the sentence a CLI
  failed with is the whole of what a person needs.
- `Failed` MUST also carry which *kind* of failure it was and what a person does about it, as
  `hmz.backends.FAULTS` names the kinds, and MUST say both in its message. A kind rather than a
  sentence, because the answer to each kind is a different answer -- a rate limit is waited out
  and then taken to another account, a refused credential is not waited out at all, a retired
  model is answered by another place and by nothing else -- and one that said only a sentence
  is one every caller would have to read a message to act on. "" MUST mean nobody classified
  it, which MUST be the failure a turn has always had: tried again exactly as the place says.
- Which kind it was MUST NOT be worked out here. This is what a turn says and what it cost,
  with no behaviour on it; deciding takes the backend, the exit status and, for a CLI that
  keeps its reason in a log of its own, that log -- none of which a value has. A backend that
  knows MUST be able to say it on the failure it raises, and MUST be believed over any reading
  of a message.
- `Unrecoverable` MUST be a `Failed` a turn is not taken again for anywhere: not at this place,
  not under another account, and not at another place. It is what a backend says of a failure
  no other try could come out differently on, and nothing outside the backend MUST read a
  message to guess at one. A kind that is answered by another place -- a model that has been
  retired, a CLI that is not installed -- MUST NOT be one of these: it is a turn with somewhere
  left to go.

- An agent that starts an agent of its own MUST say so on the stream a turn is read from, as a
  `subagent` and then a `subagent-ends`, each naming that agent by the backend's own id for it
  so that the one that started and the one that ended read as one agent. A fleet under a turn
  is agents, and whatever is watching MUST be able to show it as agents rather than as another
  tool call. A backend that says only one of the two halves would be one whose subagents never
  finish, so it MUST say both or neither.

- These MUST NOT name the base classes. Every backend needs them and none of them needs the
  base classes to say one, so a reader of somebody else's stream format imports this alone.

## `config.py`

```python
CUTOFFS = ("next-response", "immediately")
OUTCOMES = ("end", "fail")


@dataclass(frozen=True, slots=True, kw_only=True)
class Budget:
    output: float = 0.0
    seconds: float = 0.0
    when: str = "next-response"
    then: str = "end"

    @property
    def bounded(self) -> bool: ...

    def over(self, *, output: float = 0.0, seconds: float = 0.0) -> str: ...


class Goal: ...


@dataclass(frozen=True, slots=True, kw_only=True)
class AgentDefaults:
    permission: str = "bypass"
    goals: bool = True
    web_search: bool = True


class Remote: ...


@dataclass(frozen=True, slots=True)
class Isolated:
    image: str = "python:3.12"


@dataclass(frozen=True, kw_only=True)
class AgentConfig:
    model: str
    effort: str
    machine: MachineConfig | None = None
    permission: str = "bypass"
    provider: str = ""
    goals: bool = True
    web_search: bool = True
    budget: Budget | None = None
```

- `Budget` MUST be what one turn may spend before it is cut off, and MUST be over a turn
  rather than over a session: a conversation is many turns, and a cap across all of them
  would cut a tenth round off for what the first round wrote. Every turn MUST start with the
  whole of it, and what is measured MUST be the rise across that turn.
- It MUST be a value rather than a handful of arguments. A budget is already four answers --
  how many tokens, how long, when it takes hold and what it leaves behind -- and the ones
  after it are more of the same question, so a dimension added MUST be a field on this and a
  line in `over` and MUST NOT be a signature change wherever a turn can be asked for. `over`
  MUST therefore be the one place a reading is compared with a cap, and MUST answer with why
  the turn is over budget in words a person reads, or "" while it is inside every cap.
- Nothing MUST be capped unless it is named, so a `Budget()` is a turn under no budget at
  all -- which is how one conversation says it is not to run under the budget its agent
  carries. `bounded` MUST say which of the two a budget is, so that a turn under none starts
  no clock and measures nothing.
- `when` MUST be one of `CUTOFFS` and MUST say when a spent budget takes hold.
  `next-response` MUST let the answer the model is in the middle of land and stop on it: what
  the flow gets is a whole thought, and the tokens already paid for are worth reading. Which
  means it MUST be paid out by a response landing rather than by the turn ending -- a budget
  that waited for the turn would never bite, the turn being the thing it is there to shorten.
  It MUST NOT wait for one indefinitely either: a backend that states a turn's whole cost only
  once the turn is over lands nothing mid-turn to stop on, and a turn that has gone quiet is
  the very one a clock was set for -- so the wait MUST have an end, and the end of it MUST be
  the cut-off. `immediately` MUST end the turn where it stands: an agent six minutes into an
  answer nobody wants goes on spending for as long as it is left alone.
- `then` MUST be one of `OUTCOMES` and MUST say what the turn comes to. `end` MUST answer
  with what has been said, so that a loop reads a short turn rather than an exception, and
  MUST be what a budget nobody has said otherwise about does: a turn cut off has still done
  what it did -- its edits are on disk and its conversation is open to the next turn -- so it
  is a round that ended early and not a round that failed. Read as a failure it would be
  taken again, on a budget refilled for the retry, and a cap a loop refills every time it is
  reached is not a cap. `fail` MUST raise, and MUST raise `Unrecoverable`: the same budget is
  spent again on the next try, so a turn taken over on a schedule would be cut off at the
  same word every round and never get anywhere.
- A turn ended by `end` MUST open the session wherever the backend has already said what to
  call the conversation, because that turn landed. The round after a short round MUST carry
  the same conversation on rather than start another, or a cap would cost the work it was
  meant to bound. The cut-off MUST NOT open one for a turn `fail` raised on, that being a
  turn that failed.
- What a budget is MUST be humanize's own and MUST NOT be a per-backend native setting. Two
  of these CLIs can be handed a cap of their own -- Claude Code takes dollars per process --
  and neither is a cap a flow could rely on: one that only some backends have is one a flow
  would have to ask about before it could be written, and one counted per process is not
  counted per turn. So it is held to here, off the meter every backend feeds, and MUST be
  said the same way whichever CLI is behind it.
- A word neither answers to MUST be refused where the budget is written rather than where it
  would have taken hold: a cut-off nothing recognises is a budget that quietly never bites,
  which is the one failure a budget must not have.
- `budget` MUST be what every turn of every session of this agent runs under, and MUST be
  `None` for an agent nobody has been asked about: a cap nobody chose is a cap that would
  truncate the one turn that needed the room. A conversation MUST be able to be given one of
  its own, which is where a loop watching what a round costs is when it decides the next one
  is to be shorter.
- What an agent may do, whether it has goals and whether it may search the web MUST be the
  flow's to say and nobody else's. They are three things about the work rather than three
  things about the agent -- a reviewer that may not write is a reviewer whichever CLI fills
  the place, and a run whose answers have to be reproducible tomorrow is one nobody may
  quietly switch searching back on for -- so whoever chooses an agent chooses a CLI, a model,
  an effort and an account, and MUST NOT be asked or able to say any of these three.
- `AgentDefaults` MUST be what a flow writes beside a place to say them, the way `Goal`,
  `Remote` and `Isolated` are written. What it declares by default -- `bypass`, goals on, the
  web readable -- MUST be the loosest of each, so that a place writing none of them settles
  nothing: what an agent already carries is never loosened to reach a declaration, which is
  what makes a flow that declares nothing run its agents at exactly what they came with. It
  MUST refuse a rung no backend has a word for where it is written, so that a flow declaring
  one is refused as the flow is read rather than reached down in a driver as a key that is
  not there.
- What it says MUST reach the agent before that agent's first turn, over whatever the agent
  was constructed with: a flow is handed agents somebody else made, and one that declared a
  reviewer which may not write cannot be given a reviewer that may. A flow that calls another
  MUST have the called flow's declaration hold for the length of the call and MUST hand the
  agents back as it found them, exactly as it does with the skills it brought.
- A backend with no way of being run at a rung MUST refuse it wherever the config arrives --
  where the agent is made, and where a flow settles what it declared onto one it was handed --
  rather than on the first turn: a rung it would have to ignore is a run to refuse before it
  starts, the way web search it cannot switch off is.
- `goals` MUST be the explicit on/off availability of backend goals for this agent. It has
  no inherited or automatic state, and a place run under a `Goal` MUST have them: the two
  written against each other on one place is a flow saying two things about one agent, and
  `hmz.flows.checking` MUST report it.

- `machine` MUST be the `hmz.machines.MachineConfig` the agent's turns land on, or `None`
  to run them on this machine. It is one setting because it is one question: a machine that is
  already running and a machine started for the agent are both answers to it.
- Which agents may be given one at all MUST be the flow's to say rather than a setting anybody
  may reach for: a flow is written for one shape of work, and one whose agents read this
  project cannot have one of them reading somebody else's. `Remote` and `Isolated` MUST be what
  a flow writes beside a place to say it -- the first that the place may be pointed at a
  machine, the second that it works in a container of an image the flow itself names. An
  `Isolated` place's machine MUST be settled where the flow is read and MUST NOT be
  configurable anywhere: nothing was asked, so there is nothing to answer differently.
- `provider` MUST be the account this agent's turns run as, by the name a
  `hmz.providers` provider of its CLI was made under, or "" for the CLI as whoever is at
  this machine already runs it -- which is an account like any other where a chain is
  concerned, and none at all where the environment, the credentials and the command line are:
  `AgentBase.provider` MUST answer `None` for it, so that a turn under it is the turn an agent
  with no account has always taken. It is a setting of the agent because it is the agent that
  signs in: two agents of one CLI on two accounts are two accounts running at once.
- `web_search` MUST be whether this agent may search the web, and MUST be on where the flow
  said nothing: that is what a coding agent has always been able to do. It
  MUST mean the same thing on every backend that can express it, which means saying it in
  both directions rather than only one -- a CLI whose own web search is off until it is asked
  for MUST be asked for it, or on would mean two things. A backend that cannot be told MUST
  refuse it off wherever the config arrives, the way one with no service tier to send refuses
  `fast`: an agent that went on searching would be a setting that lies. Which backends those
  are MUST be read off `hmz.backends`, so that the one place that says what a CLI is is the
  one place this is said too. A flow that declares it off MUST therefore be refused the
  backends that cannot be told, before the first turn and by name, the way a place declaring
  a `Goal` refuses a backend with no goal feature.
- What skills an agent carries MUST NOT be a setting of it, and MUST NOT be adjustable by
  whoever chose it: a skill installed on this machine is its CLI's own -- installed the way
  that CLI installs one, switched off the way that CLI switches one off -- and humanize MUST
  NOT rewrite, override or disable any of them. What a flow brings MUST be mounted onto the
  sessions it opens instead, which is `hmz.flows.skills`, and what a flow brings is the
  flow author's to change and nobody else's.
  Which of *those* one session carries MUST be that session's own answer -- which is the
  flow's own code speaking, since a session belongs to the flow driving it -- and is one of
  the two things about what an agent works by that MAY be said again while it is working. The
  other is which of the flow's own callbacks it is offering, which is `hmz.agents.tools`.
- An anchored turn MUST be run by spawning `AnchorConfig.command(argv)`, never by calling
  coganchor in this process: a turn is pumped from threads of its own, which a supervisor that
  forks the agent and takes the process's signal handling cannot be given.

## `hooks.py`

`Moment`, `Occasion`, `Verdict`, `Hook`, `Hooks` and `Unhooked`: the points of a turn something
may be hung on, what it is told when one arrives, and what it may say back.

- A hook MUST be a callable of the flow's own, hung on a live agent and taken down again while
  it runs -- the same table these CLIs take as shell commands, held here instead so that it is
  written in the language the flow is written in.
- `Hooks.on` MUST refuse a moment the agent does not run, saying so where the hook is hung
  rather than hours into a loop. Which moments those are MUST be `AgentBase.moments`.
- `SUBAGENT_START` and `SUBAGENT_STOP` MUST be moments a hook is told about rather than ones it
  may answer: no backend here waits to be told whether it may start an agent of its own, so a
  refusal would be a verdict that goes nowhere. They MUST be named only on the backends whose
  streams say when one starts and when it comes back, so that a hook hung where nothing would
  ever fire is refused where it is hung.
- A hook that raises MUST have said nothing, as a watcher that raises has: a flow MUST NOT fail
  because something hung off it did. `Stopped` is the one thing it MUST raise out of the turn,
  since a run ended by hand has to read as ended by hand.

## `skills.py`

```python
@dataclass(frozen=True, slots=True)
class Skill:
    name: str
    about: str
    whose: str


def skills(backend: str, where: Path | str | None = None) -> list[Skill]:
    """The skills one backend would load here, the way that backend finds them."""
```

- Nothing MUST be asked of the CLI: starting one costs seconds a prompt does not have, so the
  skills MUST be found where that CLI looks for them -- which is written down in
  `hmz.backends` and read from here. A skill MUST be named as the CLI names it: what its
  front matter says, or the directory it is in where it says nothing.
- This MUST be a reading and nothing else. Whatever shows the list -- an interface, a command
  line -- MUST show it as the CLI's own and MUST offer no way of switching one off: what a
  person installed is not something a flow is entitled to rewrite, and a list adjusted here
  while the CLI's own list said otherwise would be two answers to one question.

## `watchdog.py`

```python
WATCHDOG = "HUMANIZE_WATCHDOG"


def silence(backend: str) -> float: ...


@contextlib.contextmanager
def held(agent: AgentBase) -> Generator[None]: ...


class Watchdog:
    def __init__(
        self,
        session: SessionBase,
        *,
        riding: Callable[[], subprocess.Popen[str] | None] | None = None,
        window: float | None = None,
    ) -> None: ...

    def __enter__(self) -> Self: ...

    def __exit__(self, kind, value, traceback) -> None: ...

    def saw(self) -> None:
        """The backend said something, so the clock starts again."""

    @contextlib.contextmanager
    def held(self) -> Generator[None]:
        """Stops the clock while the turn waits on something that is not its backend."""

    def wedged(self) -> Failed | None:
        """What the watchdog decided, or None while nothing has gone wrong."""
```

A turn that has stopped saying anything, noticed and dealt with rather than waited on.

- Every read a turn blocks on MUST be under one of these. A backend that answers ends the turn
  and a backend that exits fails it, and both are already handled; the third thing a backend
  can do is stay up, hold its stream open and never write to it again, and no read loop can
  see that for itself. Unwatched, that is a flow hung until a person notices -- which on a
  fleet of conversations is hours.
- The clock MUST be patted by anything the backend sends, a line that turned into no event
  included: this is liveness rather than progress, and a CLI writing protocol nobody shows is
  a CLI that has not wedged.
- A window MUST come from `hmz.backends` rather than being chosen here, and MUST be generous.
  A turn thinks for minutes and says nothing for most of them, so a window short enough to
  catch a wedge quickly is a window that kills healthy turns -- and a wedge noticed late costs
  the time it was wedged, where a healthy turn shot costs the work. `WATCHDOG` MUST override
  every backend's own, and a window of zero or less MUST mean no watchdog at all.
- The clock MUST NOT run while the turn is waiting on something that is not its backend. A
  turn stopped to ask a person is a turn its backend owes nothing -- the CLI is sitting there
  with nothing being asked of it -- and so is one whose event is in the hands of a watcher or
  a hook. Counted as silence, somebody taking a quarter of an hour over a permission prompt
  would have the healthy CLI behind it killed for the delay they caused. Every clock of an
  agent MUST stop while that agent has a question outstanding, rather than only the one whose
  session asked: a backend driven through an app server asks from a reader of its own, on
  behalf of whichever of its threads is running.
- What is done about a wedge MUST be a ladder, gentlest first: look at the process, ask the
  turn to stop, put the transport down, kill what is left. Each rung MUST be given a window
  of its own -- a turn that ends because it was interrupted MUST NOT also be shot for taking a
  moment over it -- and the ladder MUST end rather than go round again, a read still blocked
  past a killed process tree being blocked on something the watchdog cannot reach.
- Looking MUST come before intervening. Thinking and spinning both say nothing, and the one
  thing that tells them apart from outside is the machine: a process burning processor time,
  itself or under something it started, MUST be given more windows rather than stopped. The
  benefit of the doubt MUST run out after a bounded number of them, since one that never does
  is the same hang wearing patience as a disguise.
- A process MUST be ended by a signal rather than by shutting the session it belongs to: the
  turn's own thread is sitting in that process's pipe, and closing a stream out from under a
  blocked reader is how one hang becomes two. Everything the process started MUST go with it,
  and MUST be taken down by name before the parent is signalled -- a child reparented as its
  parent goes is no longer under anything that could be looked up afterwards. What is killed
  MUST also be waited on, for the reason a dropped session's process is.
- A turn whose transport is shared -- an app server every conversation with the agent is on --
  MUST be freed through the session's own `_lets_go` rather than by signalling that process:
  ending one turn by shooting its siblings' server out from under them is not the watchdog's
  to do behind the session's back. The same for a turn whose transport is a runtime inside
  this interpreter, there being no process to signal. Such a transport MUST still be looked at
  where it is a process, since the look is what tells a long build from a wedge.
- Every rung MUST say so on the stream the turn is read from, as the retries and the fallbacks
  do. An intervention nobody can see reads exactly like the stall it was fixing, and an agent
  quietly restarted under a watcher is a watcher reading a lie.
- A wedged turn MUST fail as a `Failed` and MUST NOT fail as a `Stopped` or an `Unrecoverable`.
  It is not a run ended by hand, and the same prompt against a fresh transport is exactly what
  should be tried -- which is what the retry and fallback ladder above it does with a `Failed`
  and does with nothing else.
- That failure MUST say what happened, and MUST replace whatever the freed read raised,
  whatever kind that is: `exit status -9` and an SDK's own transport error both describe the
  killing rather than the wedge. It MUST NOT replace a run ended by hand, an answer a turn
  managed to give after being asked to stop, or a failure the watchdog had no part in -- so
  only a rung that actually did something MUST arm one. A backend already gone when the clock
  ran out has a diagnostic of its own, and taking the credit for that would lose it.
- What the turn had already said MUST survive where the read it replaces carried it: a caller
  reading a failed turn's output to salvage partial work MUST NOT get less after a wedge than
  after any other failure.
- The watchdog MUST NOT act on a turn that has already ended: whatever it reached for then
  would be the next turn's.

## `base.py`

### `AgentBase`

```python
class AgentBase(ABC):
    def __init__(self, config: AgentConfig, *, name: str | None = None): ...

    @property
    @abstractmethod
    def id(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def config(self) -> AgentConfig:
        raise NotImplementedError

    @property
    @abstractmethod
    def sessions(self) -> list[SessionBase]:
        raise NotImplementedError

    @property
    @abstractmethod
    def opened(self) -> list[str]:
        raise NotImplementedError

    @property
    @abstractmethod
    def anchor(self) -> AnchorConfig | None:
        raise NotImplementedError

    @abstractmethod
    def new(self, cwd: str | os.PathLike[str] | None = None) -> SessionBase:
        """Opens a new session, in the directory it is given or in this one.

        Returns:
            A new session object.
        """
        raise NotImplementedError

    def __call__[T: BaseModel](
        self, prompt: str, *, suppress: bool = False, schema: type[T] | None = None
    ) -> str | T | None:
        """Runs one turn in a session of its own, and keeps nothing."""

    def pursue(self, objective: str, *, suppress: bool = False) -> str:
        """Runs a goal in a session of its own, and keeps nothing."""

    def rename(self, name: str) -> None:
        """Takes the name the flow driving this agent calls it, if it has none of its own."""

    def reconfigure(self, config: AgentConfig) -> None:
        """Sets this agent up as something else, from its next turn on."""

    def asked(self, question: Question) -> str | None:
        """Puts something a turn stopped to ask to whoever is driving this agent."""

    def prompted(self) -> str | None:
        """Waits for the next thing to say to this agent, for a flow that is a conversation."""
```

- What a flow may ask of an agent MUST be written down in `hmz.flows.agent` rather than read
  off this class, and `AgentBase` and `SessionBase` MUST answer to it. Structurally, and this
  layer MUST NOT import it: a flow names what it drives, and a driver is written without ever
  naming a flow, so the arrow points one way and inheriting would turn it round. What is here
  and not there is how an agent is driven rather than what a flow drives, and a public name
  added here MUST be one or the other on purpose.
- `id` MUST be the given name, or a codename from `codenames.py` when no name is given, so that
  two agents of the same config are two agents. `rename` MUST take a name from a flow only for
  an agent that was not named where it was made: a name given is a name kept.
- `clone` MUST answer with another agent of this one's backend, differing in what the call
  names and in nothing else -- its config, its name, and the flow's skills it carries. It is
  the one way to have an agent that is not the one you were handed, and there MUST be nowhere
  to say any of it again afterwards: what an agent is, is settled where it is made.
- What a run puts on an agent rather than sets it up with MUST NOT come across: the clone MUST
  have opened no conversation, spent nothing, be watched by nobody, have nothing hung on its
  moments and be written down nowhere, and MUST NOT be stopped for the one it came from having
  been. Two agents, which is what they are. It MUST be named as any agent is -- the name given,
  else one nothing else answers to -- and MUST be refused a config its backend cannot express,
  where every other agent is refused one.
- A backend made from something other than a config MUST say how one of it is made rather than
  answer `clone` differently: the person at the prompt is made from nothing at all, and `clone`
  MUST be one thing wherever it is called.
- What a session does MUST NOT be called this. An agent is structure, so cloning one copies
  the structure and none of the history: the clone has held no conversation. A session is
  history, so branching one copies the history and none of the structure. Two things, so two
  words: `SessionBase.fork`, which is also what every CLI that has the operation calls it.
  Each MUST say, where it is written, that it is not the other.
- `reconfigure` MUST replace what every turn from then on runs at, and MUST leave the turn
  under way as it started: a model does not think harder halfway through an answer. It is the
  one thing that changes a frozen config, and it is for the one case that config was frozen
  against being read as -- somebody watching a run and saying that this agent is to go on as
  something else. What an agent *is* MUST NOT change this way: a backend is the class the
  agent is, and one becoming another is another object.
- `__call__` and `pursue` MUST be one turn in a session nothing keeps, which is what a Ralph
  loop is made of -- so that a flow says `agent(task)` rather than reaching through a session
  it is going to discard.
- Every one of them MUST take the directory the turn works in, and MUST hand it to the session
  it opens. It MUST be a session's setting rather than a turn's, because that is what it is to
  these backends: a conversation is rooted at a directory and every turn of it is there. Which
  is what makes one agent working in several places at once a session apiece, and a flow with a
  worktree per task able to drive all of them at once.
- Every call that runs a turn MUST also have a twin that is awaited, run on a thread of its
  own, so that a flow written as `async def run` can hold as many turns as it likes without any
  one of them stopping the rest. A batch MUST be the same call as many times over as it is
  given prompts, one session apiece and all of them going, answering in the order it was asked.
- `asked` MUST answer with what the user said, or `None` where there is nobody to ask -- a
  flow run from a command line, or an interface told its user is away. A backend MUST be told
  that nobody answered rather than left waiting: a turn waiting on an answer that is not
  coming is a flow that has stopped. It MUST also say what was asked to whatever is watching
  the agent, as an `asks` event, since the one place a run is visible is the turns going past.
- `prompted` MUST wait between turns for the next thing to say to the agent, so that a flow
  may be a conversation rather than a loop, and MUST answer `None` once there will be nothing
  more -- a flow run from a command line, where nobody is at a prompt, then does the one thing
  it was given and returns. It MUST raise `Stopped` for an agent stopped while it waited: a
  run ended by hand is written down as ended by hand, and answering with nothing would write
  it down as one that finished.
- Whatever is watching an agent MUST be told which of its conversations said a thing, and MUST
  be told None only for something the agent said rather than one of them -- a question put by a
  server that serves every session of it at once. An agent may be holding ten conversations, and
  a watcher that cannot tell them apart is one reading ten interleaved with nowhere to answer.
- `opened` MUST report the backend's id for every session this agent has opened, oldest first,
  including the sessions nobody holds any more. It is what a flow hands a trace to say which
  trajectories were this agent's.
- `anchor` MUST be where this agent's turns land, which is what `AgentConfig.machine` brings
  up, at most once and only when first asked, and which MUST be taken down when the agent is
  collected or the process exits. An agent given no machine MUST answer `None`.
- What an agent writes a session down to MUST be named as a protocol here rather than imported
  from `hmz.epic`: a run is written out of the agents it drove, so naming the run from
  here would be a circle.

### `SessionBase`

```python
class SessionBase(ABC):
    #: Whether the backend can be held to a shape rather than asked to keep to one.
    shapes: ClassVar[bool] = False

    def __init__(self, agent: AgentBase, cwd: str | os.PathLike[str] | None = None): ...

    @property
    @abstractmethod
    def id(self) -> str:
        raise NotImplementedError

    def __call__[T: BaseModel](
        self, prompt: str, *, suppress: bool = False, schema: type[T] | None = None
    ) -> str | T | None:
        """Runs one turn in the session.

        Args:
            prompt: The prompt to send to the agent.
            suppress: Whether a turn that fails answers with nothing rather than raising.
            schema: The shape to answer in, or None to take what the agent says.

        Returns:
            The agent's response, or the model it was asked for.
        """

    @abstractmethod
    def stream(
        self, prompt: str, *, schema: type[BaseModel] | None = None
    ) -> Iterator[Event]:
        """Runs one turn, saying what the agent says as it says it.

        Args:
            prompt: The prompt to send to the agent.
            schema: The shape to answer in, or None to take what the agent says.

        Yields:
            What the agent said, in the order it said it.
        """
        raise NotImplementedError

    def interject(self, text: str) -> None:
        """Says something to the agent while a turn is running.

        Args:
            text: What to say.
        """
        raise NotImplementedError

    @property
    def budget(self) -> Budget | None:
        """What each turn of this conversation may spend before it is cut off."""

    @budget.setter
    def budget(self, budget: Budget | None) -> None: ...

    def interrupt(self, *, why: str) -> None:
        """Cuts the turn now running off, wherever it has got to.

        Args:
            why: What it was cut off for.
        """

    def _lets_go(self) -> None:
        """Puts down the transport this turn is riding, from another thread than its own."""

    @property
    def forks(self) -> bool:
        """Whether this backend can carry this conversation into a second one."""

    def fork(self) -> SessionBase:
        """A second conversation carrying this one's history, and its own from there on.

        Returns:
            The new session, unopened with the backend until its first turn.
        """

    def pursue(self, objective: str, *, suppress: bool = False) -> str:
        """Runs the session under a goal the agent keeps itself going toward.

        Args:
            objective: What the agent is to have achieved before it stops.
            suppress: Whether a goal that fails answers with nothing rather than raising.

        Returns:
            The agent's response once it stops.
        """

    def _pursue(self, objective: str) -> str:
        """Runs the goal, which each backend reaches for its own way."""
        raise NotImplementedError
```

- `stream` MUST be the one primitive: it MUST end with exactly one `result` event, which is
  what `__call__` answers with, so that a turn read either way is the same turn. A backend
  that says nothing until it is done MUST still say that.
- `suppress` MUST catch a turn that failed and nothing else. A flow is a loop, and a loop that
  catches its own turns is `try` around every line of it -- so `|| true` is a word on the call
  rather than a block around it. It MUST NOT catch an agent that was stopped, which is not a
  failed turn, nor a backend that has no goal feature, which is a flow to correct. A turn asked
  for a shape that answered in some other one MUST be caught by it too, and MUST answer `None`
  rather than `""`: an answer that is not what was asked for is a turn that did not do what it
  was told, however cleanly the backend exited.
- It MUST NOT catch an `Unrecoverable` either, for the reason it does not catch a stop: a turn
  that failed for a reason no other try could come out differently on is one a loop would meet
  again on its next round, and a `while True` that swallowed it would go round on the same
  failure until somebody stopped it. Which failures those are is the backend's to say, and
  whatever tries a turn again MUST let one through rather than counting it as an attempt --
  the same failure on a schedule is a flow that makes no progress and never ends.
- A turn that failed MUST be classified before anything is done about it, and each kind MUST
  get the answer that kind takes. `hmz.backends.trouble` MUST be what reads it -- against
  signatures written down beside everything else that is true of a backend -- and
  `hmz.fallbacks.answers` MUST be what says what the kind is owed. A backend that named the
  kind itself MUST be believed without any of that: it knows something no signature does.
- The exit status MUST be read before the streams for the failures where the process never got
  as far as saying anything: a shell answers 127 for a command it could not find and 126 for
  one it could not run, and a process that died on a signal has no status but the signal. A
  spawn that came back as an error rather than as a process -- a CLI that is not installed --
  MUST become a failed turn of that kind rather than escaping as a transport: a flow catches
  turns, and a loop written against a failed turn could not carry on past anything else.
- A backend that keeps why a turn stopped somewhere other than the two streams MUST be read
  there, and only when the streams have said nothing this recognises. One of them does:
  Antigravity exits with a generic error and puts the HTTP status in a log of its own, which
  is how six rate-limited turns of the 2026-09-09 evaluation read as six turns that simply
  failed. Which files those are MUST be written down on the backend rather than found by the
  driver, and reading one MUST cost nothing for the backends that have none.
- Every step of a recovery MUST narrate itself as an event, saying what went wrong, what is
  being done about it and what a person does about it where there is anything to do. A
  recovery nobody can see is indistinguishable from a hang, and an account that needs signing
  in is worth saying so about while the turn is still going rather than only in what it
  finally failed with. Where nothing is watching the agent it MUST also go on stderr, beside
  the progress every backend puts there: a turn told to wait half a minute for a rate limit is
  the one somebody would otherwise watch do nothing at all.
- A transport reopened MUST resume the conversation by the id the backend gave it. What was
  lost was the socket and not the session: the conversation is the backend's own, so a turn
  that reopens starts a process and picks the same conversation up rather than starting a
  second one.
- A turn given a `schema` MUST answer with that model or not at all, and the model MUST be the
  whole of what the backend is asked: its fields, their types, which of them are required and
  the line each was declared with are already in it, so nothing about the shape MUST be said
  twice. A backend with a setting for this MUST be held to it there -- a flag of the command
  line, a setting of the turn -- and one with none MUST be asked in the prompt instead, with
  `shapes` saying which of the two a backend is. Either way the answer MUST be read back
  through the model, so that a flow reads a field rather than a marker in a paragraph.
- What is asked MUST be asked afresh for each turn of the model a call takes: a hook that
  sends the agent on says what to say next, and a shape that was only on the first prompt is
  one the last turn was never asked for. It MUST NOT be in what the hooks and the watchers are
  shown, which is the flow's own words -- a schema in the transcript is the plumbing showing
  through.
- `interrupt` MUST end the turn now running, and MUST be the primitive everything that cuts
  one off is written on -- a spent budget, a watchdog over a wedged CLI, a person who has seen
  enough. Stopping an agent is a different thing and MUST stay a different thing: that
  prevents its *next* turn, and until there was this, a turn gone wrong ran to the end
  whatever anybody did.
- What it ends MUST be whatever is actually holding the turn, whichever lifetime the backend
  is driven in: the process a command turn runs in, the process a session held open across
  its turns is spoken to. It MUST end what that process started as well as the process, or a
  turn cut off in the middle of a tool leaves the tool running and the turn is still
  spending. A backend whose turn is held somewhere shared -- an app server serving every
  session of an agent at once -- MUST NOT be taken down for one of them and MUST stop at the
  next answer instead: cutting one turn off must not end every other conversation on it.
- A turn cut off MUST still end the way every turn ends, on exactly one `result` or one
  failure. A stream that stopped mid-sentence would leave whatever is reading it waiting for
  an answer nobody is going to give. What that one `result` carries MUST be what the agent
  got as far as saying, since there is no answer to read it off once the thing saying it has
  been taken away.
- A turn cut off MUST NOT be taken again -- not on the retry that a failed turn gets, and not
  under the next account of the chain. The budget would be spent again on the same words, and
  a watchdog that ended a wedged turn did not ask for another one.
- A session with no turn running MUST be left alone by it: a reason left standing would end
  the next turn before it had said anything, and a turn that has not started is prevented by
  stopping the agent rather than by this.
- A budget MUST be held to off the live meter rather than checked when a turn ends, which is
  the whole of why it is worth having: the meter moves as each request to the model comes
  back, so a turn that has written what it was given is cut off in the middle of the turn
  rather than after it. A cap on the clock MUST bite whether or not anything is being spent,
  since a turn that has gone quiet is the one a clock is for -- so a backend that reports what
  it spent only at the end of a turn MUST still be held to one.
- A session MUST run its turns under the budget its agent was configured with unless it has
  been told otherwise, and MUST take being told while it is running -- which is where a loop
  watching what a round costs is. The turn already under way MUST keep the budget it opened
  with: what has been spent is measured against the cap the turn started on, and one swapped
  halfway through would cut a turn off for tokens it was allowed when it wrote them.
- A budget's cut-off MUST win over a hook that would have sent the agent on. A spent budget
  is not a question, and `Stop` refusing is what a turn goes round again on.
- A budget MUST be over a turn and not over a goal, and `interrupt` MUST NOT claim to reach
  one. A goal is the backend's own loop, started by the backend and followed rather than
  held, so there is no turn here to cut off and nothing that could honestly be measured
  against a cap: what ends a goal is stopping the agent.
- `interject` MUST reach the turn already under way rather than starting another, and MUST
  raise `NotImplementedError` on a backend that takes a turn's whole prompt up front. A
  backend that can be talked to MUST raise `RuntimeError` when nothing is running to hear it.
  A word that would be answered as a turn of its own once this one ended is a turn queued
  behind rather than a word put in, and MUST be moved into the running turn where the backend
  offers a way -- which every one driven through an app server does.
- `interrupt` MUST NOT end the conversation, and MUST say why: a turn that ended without a
  reason reads as a turn that crashed. The turn it stops fails; the session it stops it in
  MUST still be there, under the id it was opened with, for the next turn to resume. Every
  session MUST take being asked, since every turn is held by something reachable; a backend
  that nevertheless has nowhere to take the asking MUST raise `NotImplementedError` rather
  than pretending, and whatever asked MUST go on to what it does about a turn that cannot be
  asked rather than treating that as a failure of the turn.
- `_lets_go` MUST put down whatever transport a turn is riding, called from another thread
  than the turn's own, and MUST leave the conversation whole: the id has been adopted and the
  next turn resumes under it, which is what a session whose process restarted has always done.
  A backend whose turns run on something shared MUST say so here rather than shutting the
  session, which would put down nothing.
- Every read a turn blocks on MUST be under a `watchdog.Watchdog`, whichever shape that read
  has -- a line off a pipe, an event off a queue, a notification off somebody's SDK. A backend
  that stops answering without exiting is the one failure none of those loops can see, and a
  turn that cannot end is worse than one that fails.
- MUST NOT run a session in parallel; use a lock to ensure that only one turn is run at a time.
  The whole of a turn MUST be under it -- the moments it fires and what it says as well as what
  the backend is told -- so that two threads calling one session are two turns one after the
  other rather than two halves of a turn each.
- A session MUST say which of the flow's skills it carries and MUST take being told which,
  from its next turn on: what is put where the backend reads them MUST be settled as a turn
  opens rather than when the session was made, since a session is rooted at a directory it may
  not have yet and a turn already running MUST NOT have what it is working by moved underneath
  it. A session told nothing MUST carry every one the flow brought. A name the flow does not
  bring MUST be ignored rather than refused, and a session carrying what it was already
  carrying MUST do nothing at all -- which is every turn but the first and every turn after a
  change.
- A session MUST run its turns in the directory it was opened at, and MUST say which that is.
  For an agent whose turns land on another machine that directory MUST be named as that machine
  names it, MUST be inside the workspace the anchor names, and MUST be reached through this
  machine's mirror of it -- which the anchor MUST be told rather than left to guess, since two
  supervisors cannot be nested and only one of them holds the mirror. A directory that is not
  there, or one outside that workspace, MUST be refused before the turn rather than left to a
  backend that cannot start in it.
- MUST add a session to its agent's `opened` as it opens, and never for a turn that failed.
- `fork` MUST answer with a second conversation carrying this one's history: what the child
  knows MUST be what this session knew at the moment it was made, and what either of them is
  told afterwards MUST be its own. It MUST be made of the backend's own fork -- `claude
  --fork-session`, codex's `thread/fork`, `opencode run --fork`, `kimi fork`, ACP's
  `session/fork` -- and MUST NOT be a transcript replayed into a session opened from nothing:
  a conversation re-read is turns paid for twice, and what it re-reads is not what was there.
- It MUST raise `NotImplementedError` on a backend with no fork of its own, the way `pursue`
  refuses one with no goal feature, and MUST NOT hand back a second handle on the one
  conversation instead -- two flows each continuing what they take to be their own is a run
  nothing downstream could explain. `forks` MUST say beforehand which backends can, so that a
  flow may ask rather than catch, and MUST be read off `hmz.backends`: the one place a fact
  about a CLI is written down is the one place this is said.
- It MUST raise `RuntimeError` while no turn has landed here. A session that has got nowhere
  has no history to carry, and is one to open rather than one to fork.
- The fork MAY be the child's first turn rather than a call of its own, since most of these
  CLIs have no prompt-free fork. Where it is, the boundary MUST still be where `fork` was
  called: a child whose parent has been given a turn since MUST be refused rather than cut
  from where those turns left it. A branch from somewhere nobody chose that reads as the
  branch that was asked for is the failure this exists to prevent.
- A child whose first turn comes back naming the conversation it was cut from MUST raise
  rather than take that id. A CLI that took the fork flag and did not fork is the one way this
  fails with nothing looking wrong, and a session that adopted it would be the second handle
  the whole of this refuses to hand out.
- The child MUST be a conversation of its own in every way a run counts one: its own id, its
  own meter, its own place in its agent's `opened`, its own line in the run's record. Nothing
  spent on the one it came from MUST count twice. What this conversation is running by MUST
  come across rather than what its agent was set up with -- the effort it has got to, the
  skills it is carrying now, the callbacks it is offering -- since that is what the child is a
  continuation of.
- It MUST be unopened with the backend until its first turn: a fork nobody uses MUST cost
  nothing at all.
- The run MUST be told which conversation a child was cut from, where it is told the child was
  opened: the backend's own log says only that a session began knowing things.
- A turn that fails MUST raise `subprocess.CalledProcessError`, whatever it was run through, so
  that a flow catches turns rather than transports. What it says MUST include why: a
  `CalledProcessError` says only `returned non-zero exit status 1` and keeps the reason in a
  field nothing prints, and the reason is the whole of what is worth reading -- `that model is
  not available for your account`, `the free service has ended`, `no credential`. Both streams
  MUST be said where they say different things, a CLI that warns on one and fails on the other
  being otherwise reported by the half that does not matter, and each MUST be clipped: the
  sentence a turn failed with is worth having and the transcript it failed part way through is
  not.
- `pursue` MUST be the backend's own goal feature -- the one its `/goal` command reaches -- and
  MUST NOT fall back to asking for one in the prompt, which is a prompt and not a goal. It MUST
  raise `NotImplementedError` on a backend that has none, rather than running the objective as
  an ordinary turn.
- A goal is as many turns of the model as the objective takes, and the backend starts them
  itself. `pursue` MUST follow the goal across all of them and answer with the last of them: a
  session that has gone quiet is a goal that has stopped only once the goal itself says so.
- A backend that reports a turn finished before what it said can be read back MUST be read once
  more afterwards, and one that hands back a message still being written MUST be read again
  until it is not. Neither may leave a landed turn answering with nothing. A message still
  being written MUST NOT be said as it stands either: half a sentence shown as a thing of its
  own is a paragraph broken across as many parts as the backend was read, with whatever grew
  in place afterwards never shown at all.
- What a turn says MUST reach whoever is watching as the utterances the agent made, not as the
  fragments they crossed the wire in, and MUST be put on stderr the same way and once for a run
  nothing is watching. A backend teeing its own pieces as they arrive MUST NOT also tee the
  message they came to: the same paragraph twice over is not what the agent said either.

### `StreamSessionBase`

```python
class StreamSessionBase(SessionBase):
    @abstractmethod
    def _command(self) -> list[str]:
        """The command the session's one process is run as."""
        raise NotImplementedError

    @abstractmethod
    def _write(self, text: str) -> str:
        """Renders something to say to the agent as the line to write."""
        raise NotImplementedError

    @abstractmethod
    def _read(self, line: str) -> Iterable[Event]:
        """Reads one line the agent wrote."""
        raise NotImplementedError
```

- A session MUST be one process held open across its turns, spoken to a line at a time, which
  is what leaves the agent there for `interject` to reach.
- A backend answering each thing it is told with a turn of its own MUST be read until it has
  answered everything said in the turn, the words put in mid-turn included. Reading only as
  far as the first answer loses what was put in and leaves the rest for the next turn to
  take as its own.
- Nothing MUST be counted as said until it has landed, and a new process MUST owe nothing for
  what was said to the one before it: either mistake leaves a later turn waiting forever.
- A process MUST NOT outlive the session, and MUST NOT leave its descriptors or its exit
  status behind when a turn ends -- an anchored flow ends one per turn.
- `_restarted` MUST be told when a new process is up, for whatever a backend counts per
  process. Claude's own token totals restart with it, so a baseline kept across one would
  read every later turn as having spent nothing.
- An anchored session MUST end its process with each turn instead: coganchor pushes what the
  agent wrote when the session ends, so a process held open past the turn would leave that
  turn's work on this machine. Such a session therefore cannot be talked to between turns, and
  MUST resume rather than reopen on the turn after.
- Reading the process MUST be under a watchdog, and the process MUST be what the watchdog is
  told this turn is riding. A backend still holding stdout open and never writing to it again
  is neither an answer nor an exit, so the `for` over that stream waits for as long as anybody
  leaves the flow running; ending the process is what gives the read the EOF it is owed.

### `CommandSessionBase`

```python
class CommandSessionBase(SessionBase):
    @abstractmethod
    def _turn(self, prompt: str) -> tuple[list[str], str | None]:
        """Builds the command one turn is run as.

        Args:
            prompt: The prompt to send to the agent.

        Returns:
            The command to run, and what to write to its stdin, or None when the prompt is
            already inside the command.
        """
        raise NotImplementedError

    @abstractmethod
    def _read_session_id(self, transcript: str) -> str:
        """Reads back the id the backend gave this session.

        Args:
            transcript: Everything the turn printed, on stdout and stderr alike.

        Returns:
            The backend's session id.
        """
        raise NotImplementedError
```

- A turn MUST be one run of the command, with both of the agent's streams teed to ours as they
  arrive, so that a long turn stays watchable. A sink that has gone away MUST NOT take the turn
  down with it, and MUST NOT stop the reading either: a pipe nobody drains blocks the agent.
- The process a turn is running in MUST be reachable while it runs, and letting go of what
  holds the conversation open MUST end it. There is nothing to hold *between* turns, which is
  no reason to hold nothing during one: a session that held nothing at all would leave a stop
  and a cut-off with nowhere to reach, and `stop` says it ends the turn under way. What the
  turn's own reader finds out MUST be what it would find out about any process that has gone:
  the streams end and the status is nonzero, which is a failed turn, and whoever asked for it
  to be cut off is the one who answers for it.
- Its exit status MUST be taken through the handle that started it and MUST NOT be reaped any
  other way. A status taken by something that is not its parent is a status the turn's own
  reader never sees, and a turn killed mid-word would then read as one that exited cleanly.
- Reading MUST be under a watchdog too, told the command's own process. What this loop waits
  on is a queue the stream pumps fill, and a command that neither writes nor exits owes that
  queue a last entry it will never put there. A turn ended that way MUST fail with what the
  watchdog found rather than with the exit status of the killing.
- Every session that is not one command per turn MUST derive from `SessionBase` instead, so
  that a backend driven another way inherits none of this.

## `codenames.py`

```python
def codename() -> str: ...
```

- What an agent nobody named is called. It MUST be one rule and nothing else: a Greek word,
  capitalised at the front and wherever the word breaks, and three digits -- `NeiKos496`. The
  twelve the story spells out MUST be among what it answers with and MUST come up far oftener
  than their share of the pool, a name being only a joke to somebody who recognises it.
- A word MUST be buildable rather than only listed, since a list has a last word and there
  MUST NOT be one: morphemes join at the capital, so `Meta` and `Kratos` are `MetaKratos` by
  the same rule that spells `ApoRia`. There MUST be at least two morphemes a word may lead
  with, the count being spelled in them.
- A code MUST NOT be handed out twice in one process. Two agents left unnamed are two agents,
  and a name is what a trace groups an agent's sessions under.
- A process that has drawn every short code MUST be answered with a longer one built the same
  way -- the word grows a morpheme when the shorter ones run out -- and MUST NOT be answered
  with a hex tail or anything else off the rule. The point of the name is that a person can
  read it, and a name that degrades to hex under load degrades exactly where a run is hardest
  to read.

## `tools.py`

```python
@dataclass(frozen=True, slots=True)
class Tool:
    name: str
    about: str
    call: Callable[..., Any]
    takes: type[BaseModel] | None = None


class Toolbox:
    def offers(self, whose: int, tools: Iterable[Tool]) -> None: ...

    def offered(self) -> tuple[Tool, ...]: ...

    def empty(self) -> bool: ...

    def address(self) -> str: ...

    def command(self) -> list[str]: ...

    def close(self) -> None: ...


def serve(line: str, offered: Callable[[], tuple[Tool, ...]]) -> dict[str, Any] | None: ...
```

Callbacks of the flow's own, handed to a coding agent as tools it may reach for -- which is the
other direction from driving one, and the thing that lets an agent call a flow.

- The callback MUST run in the process the flow is in. That is the whole of what this is for: a
  tool server started as a program of its own would be a subprocess with none of the flow's
  variables in it, and a flow's own function is what a tool is meant to be. What a backend is
  handed MUST therefore be a command that relays its pipe back to this process rather than one
  that answers for itself.
- What a tool takes MUST be a model and nothing else, for the reason a turn held to a shape is
  asked with one: the fields, their types, which are required and the line each was declared
  with are already in it, so nothing about the arguments is said twice.
- The road MUST be the Model Context Protocol, that being the one way every one of these CLIs
  already takes a tool it was not shipped with. Only what a client actually calls MUST be
  answered -- saying hello, saying what there is, and calling one -- and a message with no id
  MUST NOT be answered at all, the protocol having nowhere to put the answer.
- Nothing MUST be started until something is offered. An agent whose flow hands it no callbacks
  MUST have no socket, no thread and no bridge, and its turns MUST be the turns they always
  were.
- The socket MUST be somewhere only this user may reach: it is a way into this process, and one
  anybody could connect to is a way in for anybody.
- A callback that raises MUST be answered to the agent as the tool having failed, in words it
  can act on, and MUST NOT be raised out of the turn: a flow must not end because a model called
  one of its tools wrongly, and a model that reads what went wrong is one that can call it
  again correctly.
- What is offered MUST be the agent's rather than one conversation's, since a CLI is told about
  its tools where it is started and some of these are started once per agent. Two conversations
  offering a tool of one name are offering one tool. Which conversation offered what MUST still
  be kept, so that one which stops offering takes only its own back.
- A session MUST say which callbacks it is offering and MUST take being told, from its next turn
  on -- the same shape a flow's skills have, and for the same reason. A backend with no way of
  being given a tool it was not shipped with MUST refuse one where it is offered rather than
  quietly never offering it, and MUST say beforehand which it is on the class.
- Nothing of the person at this machine's own configuration MUST be written to do it. Their own
  tool servers are theirs, and what this flow offers MUST go away with this flow.

## `board.py`

```python
ANYONE, USER, FLOW = "both", "user", "flow"


class Refused(PermissionError): ...


@dataclass(frozen=True, slots=True)
class Item:
    key: str
    value: str = ""
    about: str = ""
    whose: str = ANYONE
    at: float = ...
    by: str = FLOW


class Board:
    def items(self) -> tuple[Item, ...]: ...

    def get(self, key: str, otherwise: str = "") -> str: ...

    def held(self, key: str) -> Item | None: ...

    def put(self, key: str, value: str, *, about=None, whose=None, by=FLOW) -> Item: ...

    def drop(self, key: str, *, by: str = FLOW) -> bool: ...

    def moves(self, key: str, *, to: str, by: str = FLOW) -> Item: ...

    def watch(self, listener: Callable[[Board], None]) -> None: ...
```

What a flow and the person at the prompt both write on, and neither waits at.

- A question MUST go on stopping the turn it was asked in. This MUST NOT: it is for everything
  a run needs from a person that is not a question -- what there is to do next, how far through
  it is, what somebody thought of while it was running -- and a flow reading it MUST never be
  held up, nor a person changing it.
- It MUST be a handful of named lines and nothing more. What `todo`, `doing` and `done` mean is
  the flow's to decide, so no queue, no status and no ordering MUST be written down here: a
  board that knew what an issue was would be a board every flow had to agree with.
- A line MUST say whose it is, and the other side MUST be refused where it writes rather than
  quietly ignored: a flow writing down how far through it is must not have that edited
  underneath it, and a person's list of what they want next must not be rewritten by the thing
  meant to be reading it.
- Writing a value MUST keep what the line is for. What it is for is said once, where the line
  was made.
- It MUST be held by the person rather than by the flow. A flow is a function that returns, and
  the board outlives any one turn of it.
- It MUST say when a line moves, so that whatever is showing it draws again -- and a watcher
  that raises MUST have said nothing, in the way a watcher of an agent has.
- What is read out MUST be a copy taken whole: a flow reading the board while somebody types on
  it must read one moment of it rather than four moments of four lines.

## `human.py`

The person at the prompt, driven as an agent: `HumanAgent` and `HumanSession`.

- They MUST be made by whatever drives the flow rather than by the flow, and MUST NOT be among
  the agents a flow is configured with: nobody chooses what the person runs.
- They MUST carry the board, which is the other half of talking to them: a question stops the
  turn until it is answered and the board stops nothing at all. It MUST be theirs rather than
  the flow's, for the reason it is written down in `board.py`.
- A turn of theirs MUST NOT be bracketed by the `begins` and `ends` that say whose turn it is.
  The person takes no turn of a model, and counting it would put them in the graph of who
  handed to whom and spin a clock at them while they thought.
- Asked for a shape, they MUST be asked a question per field rather than shown the schema, and
  the model MUST be built out of what they typed: the description the flow wrote where it
  declared the field is the question, and a field that takes one of a fixed few MUST offer
  those, so that the question reads as one wherever it is shown. Each MUST go the road a coding
  agent's own question goes -- `AgentBase.asked` -- so that a flow gets the same thing from the
  person as from an agent.
- What the model refuses MUST be put back on the field it was refused for, in the model's own
  words: the flow that declared the field is the only thing that knows what it will take. It
  MUST be put back a bounded number of times, and a person who is not there or who walks away
  MUST answer with nothing rather than leave the flow waiting.

## `claude.py` / `codex.py` / ... - Concrete Agent and Session Classes

```python
@dataclass(frozen=True, kw_only=True)
class DummyAgentConfig(AgentConfig): ...


class DummyAgent(AgentBase): ...


class DummySession(CommandSessionBase): ...
```

- A backend MUST be driven through its command line where that can express what an agent is
  configured with, and through the app server the backend serves its own client from where it
  cannot -- a model, an effort, a mode or a goal that has no flag is a setting of a session
  there, and asking the model for it in the prompt is not the same feature. A turn that must
  stay open to be talked to is such a case: a command line run per turn has ended by the time
  there is anything to say to it.
- Such a server MUST be started only when a turn first needs one, so that a flow which needs
  none starts none; a driver that takes one turn at a time on one MUST start at most one per
  agent. It MUST be started under the agent's anchor, and stopped when the agent is collected
  or the process exits.
- One server is shared by more than one session of its agent, and what is written to it MUST be
  written whole. A driver whose backend takes one turn at a time MUST serialize its calls: two
  turns interleaved on one stream would each take the other's answers. A driver whose backend
  runs the turns of separate conversations at the same time MUST instead hand each message read
  back to whoever it belongs to -- the call that asked for it, or the turn of the thread it
  names -- and MUST NOT let a turn hold the stream for its duration, which would make sharing a
  server cost the whole of the turn ahead of it. What names no thread MUST reach the one turn
  reading where there is one, which is what a stream held alone would have handed it, and MUST
  reach none where more than one is: a message that does not say whose it is MUST NOT be what
  ends or fails somebody else's turn.
- Where such a backend will not hand a conversation it holds open to a second server, a session
  MUST take every turn of its life on the server it was opened on, and MUST be opened on one no
  turn is running on -- one more started only when every server the agent has is busy. So an
  agent runs one server for a flow that takes its turns in sequence, however many sessions it
  opens and drops, and one apiece for a fleet that works its sessions at once. A server per
  session starts one a turn for a loop that opens a session a turn; one per agent makes every
  session of a fleet wait out every turn ahead of it.
- A thread the server already holds, at the settings the turn asks for, MUST NOT be picked up
  again: picking one up reads the whole conversation back off the disk to tell that server what
  it has already been told.
- A backend told where to work MUST be told the directory the anchor puts it in, which is the
  workspace itself unless the mirror was put somewhere else, and this one when it is not
  anchored at all.
- A driver MUST NOT switch a skill of its CLI on or off, and MUST NOT write the CLI's own
  settings to do it: what the person who started the flow has installed is theirs. The skills
  a flow brings MUST reach a session by being mounted where that backend reads them, which is
  `hmz.flows.skills` and `Profile.mounts`.

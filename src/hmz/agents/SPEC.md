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
└── tools.py
```

## `__init__.py`

Expose `AgentConfig`, `AgentBase`, `Event`, `Question`, `Stopped`, `Failed`, `Unrecoverable`,
`Usage`, `SessionBase`, `CommandSessionBase`, `StreamSessionBase`, `Tool`, `Toolbox`, `Board`,
`Item`, and all agent and session classes.

## `event.py`

`Event`, `Question`, `Stopped`, `Usage`, `Failed`, `Unrecoverable` and `say`: what a turn says
while it runs, what it asks, what it cost, and how it failed -- with no behaviour on them.

- `Failed` MUST be a `subprocess.CalledProcessError` that says what went wrong where whoever it
  happened to can read it: a flow catches turns rather than transports, and the sentence a CLI
  failed with is the whole of what a person needs.
- `Unrecoverable` MUST be a `Failed` a turn is not taken again for. It is what a backend says
  of a failure no other try could come out differently on, and nothing outside the backend
  MUST read a message to guess at one.

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
class Goal: ...


@dataclass(frozen=True, slots=True, kw_only=True)
class AgentDefaults:
    goals: bool = True


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
```

- `goals` MUST be the explicit on/off availability of backend goals for this agent. It has
  no inherited or automatic state. `AgentDefaults` MAY be written beside a flow's agent type
  to suggest its initial picker value, but MUST be resolved into `AgentConfig.goals` before
  the agent is constructed and MUST NOT let the flow change it afterwards.

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
- `web_search` MUST be whether this agent may search the web, and MUST be on for an agent
  nobody has been asked about: that is what a coding agent has always been able to do. It
  MUST mean the same thing on every backend that can express it, which means saying it in
  both directions rather than only one -- a CLI whose own web search is off until it is asked
  for MUST be asked for it, or on would mean two things. A backend that cannot be told MUST
  refuse it off wherever the config arrives, the way one with no service tier to send refuses
  `fast`: an agent that went on searching would be a setting that lies. Which backends those
  are MUST be read off `hmz.backends`, so that the one place that says what a CLI is is the
  one place this is said too, and whatever is choosing an agent MUST put the question only
  where there is an answer.
- What skills an agent carries MUST NOT be a setting of it. A skill installed on this machine
  is its CLI's own -- installed the way that CLI installs one, switched off the way that CLI
  switches one off -- and humanize MUST NOT rewrite, override or disable any of them. What a
  flow brings MUST be mounted onto the sessions it opens instead, which is `hmz.flows.skills`.
  Which of *those* one session carries MUST be that session's own answer, and is one of the two
  things about what an agent works by that MAY be said again while it is working. The other is
  which of the flow's own callbacks it is offering, which is `hmz.agents.tools`.
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
  from `hmz.cycle`: a run is written out of the agents it drove, so naming the run from
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
- `interject` MUST reach the turn already under way rather than starting another, and MUST
  raise `NotImplementedError` on a backend that takes a turn's whole prompt up front. A
  backend that can be talked to MUST raise `RuntimeError` when nothing is running to hear it.
  A word that would be answered as a turn of its own once this one ended is a turn queued
  behind rather than a word put in, and MUST be moved into the running turn where the backend
  offers a way -- which every one driven through an app server does.
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
  until it is not. Neither may leave a landed turn answering with nothing.

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
- Such a server MUST be started at most once per agent, only when a turn first needs one, so
  that a flow which needs none starts none; it MUST be started under the agent's anchor, and
  stopped when the agent is collected or the process exits.
- One server is shared by every session of its agent, so a call on it MUST be serialized: two
  turns interleaved on one stream would each take the other's answers.
- A backend told where to work MUST be told the directory the anchor puts it in, which is the
  workspace itself unless the mirror was put somewhere else, and this one when it is not
  anchored at all.
- A driver MUST NOT switch a skill of its CLI on or off, and MUST NOT write the CLI's own
  settings to do it: what the person who started the flow has installed is theirs. The skills
  a flow brings MUST reach a session by being mounted where that backend reads them, which is
  `hmz.flows.skills` and `Profile.mounts`.

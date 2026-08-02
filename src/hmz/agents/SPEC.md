# Agents

## File Structure

```
.
├── __init__.py
├── base.py
├── claude.py
├── codex.py
├── config.py
├── event.py
├── hooks.py
├── human.py
├── kimi.py
├── mimo.py
├── opencode.py
├── pi.py
└── skills.py
```

## `__init__.py`

Expose `AgentConfig`, `AgentBase`, `Event`, `Question`, `Stopped`, `SessionBase`,
`CommandSessionBase`, `StreamSessionBase`, and all agent and session classes.

## `event.py`

`Event`, `Question`, `Stopped` and `say`: what a turn says while it runs and what it asks,
with no behaviour on them.

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
    skills: tuple[str, ...] | None = None
    permission: str = "bypass"
    provider: str = ""
    goals: bool = True
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
  this machine already runs it. It is a setting of the agent because it is the agent that
  signs in: two agents of one CLI on two accounts are two accounts running at once.
- `skills` MUST be the skills of its CLI the agent is to have, and MUST say what it has rather
  than what it has not: an agent told which skills to have has exactly those, whatever is
  installed afterwards. `None` MUST be the CLI as it comes, which is every skill it finds, and
  MUST be what an agent nobody has been asked about is left as -- an empty tuple is a choice
  and says none of them.
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


def leaving(
    backend: str, wanted: Iterable[str] | None, where: Path | str | None = None
) -> list[str]:
    """The skills to switch off, for an agent that is to have the ones it was given."""
```

- Nothing MUST be asked of the CLI: starting one costs seconds a prompt does not have, so the
  skills MUST be found where that CLI looks for them -- which is written down in
  `hmz.backends` and read from here. A skill MUST be named as the CLI names it: what its
  front matter says, or the directory it is in where it says nothing.
- Here rather than beside whatever offers them, because both halves need the same list: an
  interface asking which skills an agent is to have, and the driver that then has to tell the
  backend. `leaving` MUST be that second half -- an agent says what it has and every backend is
  told what it has not, and only looking says which those are.

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

    def asked(self, question: Question) -> str | None:
        """Puts something a turn stopped to ask to whoever is driving this agent."""

    def prompted(self) -> str | None:
        """Waits for the next thing to say to this agent, for a flow that is a conversation."""
```

- `id` MUST be the given name, or one no other agent answers to when no name is given, so that
  two agents of the same config are two agents. `rename` MUST take a name from a flow only for
  an agent that was not named where it was made: a name given is a name kept.
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
- A session MUST run its turns in the directory it was opened at, and MUST say which that is.
  For an agent whose turns land on another machine that directory MUST be named as that machine
  names it, MUST be inside the workspace the anchor names, and MUST be reached through this
  machine's mirror of it -- which the anchor MUST be told rather than left to guess, since two
  supervisors cannot be nested and only one of them holds the mirror. A directory that is not
  there, or one outside that workspace, MUST be refused before the turn rather than left to a
  backend that cannot start in it.
- MUST add a session to its agent's `opened` as it opens, and never for a turn that failed.
- A turn that fails MUST raise `subprocess.CalledProcessError`, whatever it was run through, so
  that a flow catches turns rather than transports.
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

## `human.py`

The person at the prompt, driven as an agent: `HumanAgent` and `HumanSession`.

- They MUST be made by whatever drives the flow rather than by the flow, and MUST NOT be among
  the agents a flow is configured with: nobody chooses what the person runs.
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
- An agent told which skills to have MUST have the rest of them switched off through whatever
  the backend takes for it -- a flag of the command line, an override of the server it is
  driven through -- and MUST NOT be given them by writing the CLI's own settings: two agents of
  one flow may be loaded differently, and neither is a reason to change what the person who
  started the flow has installed. A backend with no way of being told MUST offer none, rather
  than a list nothing acts on.

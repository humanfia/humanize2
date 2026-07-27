# Janus Agents

## File Structure

```
.
├── __init__.py
├── base.py
├── claude.py
├── codex.py
├── config.py
└── kimi.py
```

## `__init__.py`

Expose `AgentConfig`, `AgentBase`, `Event`, `Question`, `SessionBase`, `CommandSessionBase`,
`StreamSessionBase`, and all agent and session classes.

## `config.py`

```python
@dataclass(frozen=True, kw_only=True)
class AgentConfig:
    model: str
    effort: str
    anchor: AnchorConfig | None = None
    isolation: IsolationConfig | None = None
```

- `anchor` MUST be the `humanize.coganchor.AnchorConfig` the agent's turns are run under, or
  `None` to run them on this machine.
- `isolation` MUST be the machine to start for the agent and run its turns on, or `None` to use
  one that is already running.
- Both MUST NOT be given at once: each says where the work lands.
- An anchored turn MUST be run by spawning `AnchorConfig.command(argv)`, never by calling
  coganchor in this process: a turn is pumped from threads of its own, which a supervisor that
  forks the agent and takes the process's signal handling cannot be given.

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
    def new(self) -> SessionBase:
        """Opens a new session.

        Returns:
            A new session object.
        """
        raise NotImplementedError

    def __call__(self, prompt: str, *, suppress: bool = False) -> str:
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
- `opened` MUST report the backend's id for every session this agent has opened, oldest first,
  including the sessions nobody holds any more. It is what a flow hands a trace to say which
  trajectories were this agent's.
- `anchor` MUST be where this agent's turns land, which is `AgentConfig.anchor` unless the agent
  is isolated. An isolated agent MUST start its machine here, at most once and only when first
  asked, and MUST stop it when the agent is collected or the process exits.

### `SessionBase`

```python
class SessionBase(ABC):
    def __init__(self, agent: AgentBase): ...

    @property
    @abstractmethod
    def id(self) -> str:
        raise NotImplementedError

    def __call__(self, prompt: str, *, suppress: bool = False) -> str:
        """Runs one turn in the session.

        Args:
            prompt: The prompt to send to the agent.
            suppress: Whether a turn that fails answers with nothing rather than raising.

        Returns:
            The agent's response.
        """

    @abstractmethod
    def stream(self, prompt: str) -> Iterator[Event]:
        """Runs one turn, saying what the agent says as it says it.

        Args:
            prompt: The prompt to send to the agent.

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
  failed turn, nor a backend that has no goal feature, which is a flow to correct.
- `interject` MUST reach the turn already under way rather than starting another, and MUST
  raise `NotImplementedError` on a backend that takes a turn's whole prompt up front. A
  backend that can be talked to MUST raise `RuntimeError` when nothing is running to hear it.
  A word that would be answered as a turn of its own once this one ended is a turn queued
  behind rather than a word put in, and MUST be moved into the running turn where the backend
  offers a way -- which every one driven through an app server does.
- MUST NOT run a session in parallel; use a lock to ensure that only one turn is run at a time.
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

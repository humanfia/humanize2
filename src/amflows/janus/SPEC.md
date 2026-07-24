# Janus

## File Structure

```
.
├── __init__.py
├── base.py
├── claude.py
├── codex.py
├── config.py
├── isolation
│   ├── __init__.py
│   ├── base.py
│   └── docker.py
└── kimi.py
```

## `__init__.py`

Expose `AgentBase`, `SessionBase`, `CommandSessionBase`, and all agent and session classes.

## `config.py`

```python
@dataclass(frozen=True, kw_only=True)
class AgentConfig:
    model: str
    effort: str
    anchor: AnchorConfig | None = None
    isolation: IsolationConfig | None = None
```

- `anchor` MUST be the `amflows.coganchor.AnchorConfig` the agent's turns are run under, or
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
    def launch(self) -> SessionBase:
        """Creates a new session.

        Returns:
            A new session object.
        """
        raise NotImplementedError
```

- `id` MUST be the given name, or one no other agent answers to when no name is given, so that
  two agents of the same config are two agents.
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

    @abstractmethod
    def run(self, prompt: str) -> str:
        """Runs one turn in the session.

        Args:
            prompt: The prompt to send to the agent.

        Returns:
            The agent's response.
        """
        raise NotImplementedError

    def pursue(self, objective: str) -> str:
        """Runs the session under a goal the agent keeps itself going toward.

        Args:
            objective: What the agent is to have achieved before it stops.

        Returns:
            The agent's response once it stops.
        """
        raise NotImplementedError
```

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
  there, and asking the model for it in the prompt is not the same feature.
- Such a server MUST be started at most once per agent, only when a turn first needs one, so
  that a flow which needs none starts none; it MUST be started under the agent's anchor, and
  stopped when the agent is collected or the process exits.
- One server is shared by every session of its agent, so a call on it MUST be serialized: two
  turns interleaved on one stream would each take the other's answers.
- A backend told where to work MUST be told the directory the anchor puts it in, which is the
  workspace itself unless the mirror was put somewhere else, and this one when it is not
  anchored at all.

## `isolation/__init__.py`

Expose `IsolationBase`, `IsolationConfig`, and all backend and backend config classes.

## `isolation/base.py`

```python
@dataclass(frozen=True, kw_only=True)
class IsolationConfig(ABC):
    workspace: str | None = None

    @abstractmethod
    def create(self) -> IsolationBase:
        raise NotImplementedError


class IsolationBase(ABC):
    def __init__(self, config: IsolationConfig): ...

    @abstractmethod
    def start(self) -> AnchorConfig:
        """Brings the machine up.

        Returns:
            The anchor that reaches it.
        """
        raise NotImplementedError

    @abstractmethod
    def stop(self) -> None:
        """Takes the machine down."""
        raise NotImplementedError
```

- `workspace` MUST be the project directory to give the machine, defaulting to this one, and
  MUST be that directory itself rather than a copy of it, so the work outlives the machine.
- `start` MUST leave the machine ready for a turn to be run against it, and MUST take down
  whatever it created if it cannot.
- `stop` MUST leave the workspace behind.

## `isolation/docker.py` / ... - Concrete Isolation Backends

```python
@dataclass(frozen=True, kw_only=True)
class DummyIsolationConfig(IsolationConfig): ...


class DummyIsolation(IsolationBase): ...
```

- A container MUST run as the calling user, so the workspace stays that user's.

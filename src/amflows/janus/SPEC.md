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

Expose `AgentBase`, `SessionBase`, and all agent and session classes.

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
```

- MUST NOT run a session in parallel; use a lock to ensure that only one turn is run at a time.
- MUST add a session to its agent's `opened` as it opens, and never for a turn that failed.

## `claude.py` / `codex.py` / ... - Concrete Agent and Session Classes

```python
@dataclass(frozen=True, kw_only=True)
class DummyAgentConfig(AgentConfig): ...


class DummyAgent(AgentBase): ...


class DummySession(SessionBase): ...
```

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

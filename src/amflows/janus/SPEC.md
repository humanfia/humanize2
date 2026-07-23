# Janus

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

Expose `AgentBase`, `SessionBase`, and all agent and session classes.

## `config.py`

```python
@dataclass(frozen=True, kw_only=True)
class AgentConfig:
    model: str
    effort: str
    anchor: AnchorConfig | None = None
```

- `anchor` MUST be the `amflows.coganchor.AnchorConfig` the agent's turns are run under, or
  `None` to run them on this machine.
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

# Janus

## File Structure

```
.
├── __init__.py
├── base.py
├── claude.py
├── codex.py
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
```

## `base.py`

### `AgentBase`

```python
class AgentBase(ABC):
    def __init__(self, config: AgentConfig): ...

    @property
    @abstractmethod
    def config(self) -> AgentConfig:
        raise NotImplementedError

    @property
    @abstractmethod
    def sessions(self) -> list[SessionBase]:
        raise NotImplementedError

    @abstractmethod
    def launch(self) -> SessionBase:
        """Creates a new session.

        Returns:
            A new session object.
        """
        raise NotImplementedError
```

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

## `claude.py` / `codex.py` / ... - Concrete Agent and Session Classes

```python
@dataclass(frozen=True, kw_only=True)
class DummyAgentConfig(AgentConfig): ...


class DummyAgent(AgentBase): ...


class DummySession(SessionBase): ...
```

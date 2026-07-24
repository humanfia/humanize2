# Janus Isolation

## File Structure

```
.
├── __init__.py
├── base.py
└── docker.py
```

## `__init__.py`

Expose `IsolationBase`, `IsolationConfig`, and all backend and backend config classes.

## `base.py`

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

## `docker.py` / ... - Concrete Isolation Backends

```python
@dataclass(frozen=True, kw_only=True)
class DummyIsolationConfig(IsolationConfig): ...


class DummyIsolation(IsolationBase): ...
```

- A container MUST run as the calling user, so the workspace stays that user's.

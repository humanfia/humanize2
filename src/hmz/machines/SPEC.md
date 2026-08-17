# Machines

## File Structure

```
.
├── __init__.py
├── anchored.py
├── base.py
├── docker.py
└── mapped.py
```

## `__init__.py`

Expose `MachineBase`, `MachineConfig`, `Mapped`, `Ran`, and all machine and machine config
classes.

## `base.py`

```python
@dataclass(frozen=True, kw_only=True)
class MachineConfig(ABC):
    @abstractmethod
    def create(self) -> MachineBase:
        raise NotImplementedError


class MachineBase(ABC):
    def __init__(self, config: MachineConfig): ...

    @abstractmethod
    def start(self) -> AnchorConfig:
        """Brings the machine up.

        Returns:
            The anchor that reaches it.
        """
        raise NotImplementedError

    def stop(self) -> None:
        """Takes the machine down, for one that was brought up here."""
```

- Where an agent's turns land MUST be one setting, not two: a machine that is already running
  and a machine started for the agent are one answer to one question, and an agent given both
  would be a state nothing could act on.
- Which agents may be given one MUST be the flow's to say. A place a flow said nothing about
  MUST be refused a machine before its first turn, a place it declared `Remote` MUST be the
  only kind that may be pointed at one, and a place it declared `Isolated` MUST be given the
  container that flow named and MUST NOT be configurable -- by anybody, anywhere. A flow is
  written for one shape of work, and where its agents work is part of that shape rather than a
  preference somebody expresses afterwards.
- The setting and the machine MUST be two objects. One config drives as many agents as it is
  given to, and each of them MUST get a machine of its own.
- `start` MUST leave the machine ready for a turn to be run against it, and MUST take down
  whatever it created if it cannot.
- `stop` MUST leave the workspace behind, and MUST do nothing at all for a machine that was
  already running: one nobody here brought up is not one anybody here may take down.

## `anchored.py` / `docker.py` / ... - Concrete Machines

```python
@dataclass(frozen=True, kw_only=True)
class DummyConfig(MachineConfig): ...


class Dummy(MachineBase): ...
```

- A machine that is already running MUST be named by the anchor that reaches it, and MUST
  bring up nothing.
- A machine started for the agent MUST be given the project directory itself rather than a
  copy of it, so the work outlives the machine, and a container MUST run as the calling user,
  so the workspace stays that user's. What is isolated MUST be the tools a command finds and
  not the work: the agent goes on running here, with its own credentials and its own
  trajectory, and only what it does reaches the container.

## `mapped.py`

```python
@dataclass(frozen=True, slots=True)
class Ran:
    argv: tuple[str, ...]
    status: int
    output: str

    @property
    def ok(self) -> bool: ...


class Mapped:
    def __init__(self, anchor: AnchorConfig): ...

    @property
    def workspace(self) -> str: ...

    def read_text(self, path: str, encoding: str = "utf-8") -> str: ...

    def write_text(self, path: str, said: str, ...) -> None: ...

    def listdir(self, path: str = "") -> list[str]: ...

    def exists(self, path: str) -> bool: ...

    def mkdir(self, path: str, *, parents: bool = True) -> None: ...

    def remove(self, path: str) -> None: ...

    def run(self, argv: Sequence[str] | str, *, cwd: str = "", env=None) -> Ran: ...

    def close(self) -> None: ...
```

The workspace on the machine a run lands on, as the flow's own code reaches it.

- An agent under a machine is answered for without being told; the flow driving it is not, being
  this process running Python. So what the flow wants of that machine MUST be asked for rather
  than intercepted: a supervisor round the process a flow is running in would be a supervisor
  round the interface, the other agents and everything else in it.
- It MUST be the same road a turn takes, so that a file written here is a file the next turn
  reads.
- The connection MUST be opened when a flow first asks and held for the rest of the run: it is
  the handshake an anchored turn opens, and one per read would be a handshake per line of a
  file.
- A path MUST be taken as the machine names it or relative to the workspace, those being the
  same path for a container handed the project directory at the path it already had.

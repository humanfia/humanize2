# SDK

## File Structure

```
.
├── __init__.py
├── accounts.py
├── agents.py
├── core.py
├── cycles.py
├── fallbacks.py
├── flows.py
├── running.py
└── session.py
```

## `__init__.py`

Expose `Hmz` and every type it hands back: `Accounts`, `Agents`, `Cycles`, `Fallbacks`,
`Flows`, `Flowverses`, `Run`, `Session`, `Taken`.

## `core.py`

```python
class Hmz:
    def __init__(self, workspace: str | os.PathLike[str] | None = None): ...

    @property
    def workspace(self) -> Path: ...

    @property
    def home(self) -> Path: ...

    @property
    def settings(self) -> Settings: ...

    @property
    def flows(self) -> Flows: ...

    @property
    def verses(self) -> Flowverses: ...

    @property
    def agents(self) -> Agents: ...

    @property
    def accounts(self) -> Accounts: ...

    @property
    def fallbacks(self) -> Fallbacks: ...

    @property
    def cycles(self) -> Cycles: ...

    def backends(self) -> tuple[Profile, ...]: ...

    def reports(self) -> bool: ...

    def read(
        self, argv: list[str]
    ) -> tuple[str, list[AgentBase], str, dict[str, Any] | None, str]: ...

    def runner(
        self,
        flow: str | os.PathLike[str],
        agents: Sequence[AgentBase],
        config: BaseModel | dict[str, Any] | None = None,
        resume: str | os.PathLike[str] | None = None,
        container: str = "",
    ) -> Runner: ...

    def run(
        self,
        flow: str | os.PathLike[str],
        agents: Sequence[AgentBase],
        task: str,
        config: BaseModel | dict[str, Any] | None = None,
        resume: str | os.PathLike[str] | None = None,
        container: str = "",
    ) -> Run: ...

    def exec(self, argv: list[str]) -> None: ...
```

humanize as one object: a workspace, and everything humanize can be asked to do in it.

- There MUST be one of these and every way in MUST go through it. The command line calls it,
  the daemon calls it, and the terminal interface reaches it through the daemon holding the
  run -- so that what humanize can do is one list rather than four, and a thing that can be
  done from one of them can be done from all of them.
- It MUST NOT be a layer of its own doing. What a flow is, what an agent is, what is written
  down and what a run left behind are the layers under this, and each MUST go on being the one
  place its own rule is written: this composes them and MUST NOT restate any of it.
- What two ways in would otherwise each have written MUST be written here instead -- refusing
  a name already taken, where a flowverse came from, what an agent named on a command line is
  -- so that a command line and a menu answer the same way. What only one of them does MUST
  NOT be: asking somebody at a terminal is a command line's, and drawing is an interface's.
- Nothing MUST be loaded until it is asked for. A line that lists the agents kept under a name
  MUST NOT pay for the tracer, the sandbox and every coding agent driver there is, so every
  layer MUST be reached from inside the call that needs it and never at the top of a module.
  That MUST go for this package's own modules too: naming it is how every command begins, so
  `Hmz` MUST cost the one module it is written in rather than all of them.
- Running a line and building a run MUST be one thing. Whoever ran an `hmz exec` line through
  this and whoever built a run out of its parts MUST be holding the same run afterwards.
- It MUST name no way in. A DAG that pointed back at the command line, the daemon or the
  interface would be one of the four holding another up, and `tests/test_layering.py` refuses
  it.
- A workspace MUST be kept exactly as it was given. One nobody named is one that follows a
  flow which changes directory; one that was named is the directory it named, spelled the way
  it was named -- since naming sessions without a workspace collects them wherever they were
  recorded, and a workspace filled in here would narrow that.

## `flows.py`

```python
class Flowverses:
    def all(self) -> list[Flowverse]: ...
    def nearest(self) -> list[Flowverse]: ...
    def find(self, name: str) -> Flowverse | None: ...
    def add(self, url: str, name: str = "") -> Flowverse: ...
    def fetch(self, name: str) -> Flowverse: ...
    def remove(self, name: str) -> bool: ...
    def holds(self, one: Flowverse) -> list[Offer]: ...
    def where(self, name: str) -> Path: ...
    def plain(self, url: str) -> str: ...
    def whence(self, one: Flowverse, nowhere: str = "-") -> str: ...


class Flows:
    @property
    def verses(self) -> Flowverses: ...
    def all(self) -> list[Offer]: ...
    def find(self, named: str) -> str: ...
    def about(self, named: str) -> str: ...
    def places(self, named: str | os.PathLike[str]) -> tuple[Place, ...]: ...
    def configures(self, named: str | os.PathLike[str]) -> type[BaseModel] | None: ...
    def resumes(self, named: str | os.PathLike[str]) -> bool: ...
    def fork(self, named: str, into: str | os.PathLike[str] | None = None) -> str: ...
    def running(self) -> tuple[Running, ...]: ...
    def set_up_from(self, said: str | os.PathLike[str]) -> dict[str, Any]: ...
```

The flows there are, and the places they come from.

- Where a flowverse came from MUST be answered here, and MUST be answered from which
  flowverse it is rather than from whether its URL is empty. Whatever was signed into a URL
  MUST be taken out of it in one place, which every way of showing one asks.
- What to call a directory that is not a clone of anything is whoever is showing it to say:
  a listing has a column and a sheet has a sentence.

## `agents.py`

```python
class Taken(ValueError): ...


class Agents:
    def reads(
        self, spec: str
    ) -> tuple[
        Profile,
        str,
        str,
        str,
        str,
        str | None,
        bool | None,
        tuple[tuple[str, str], ...],
    ]: ...
    def all(self) -> list[Kept]: ...
    def find(self, name: str) -> Kept | None: ...
    def keep(self, agents: list[Kept]) -> None: ...
    def write(self, name: str, runs: Runs, *, force: bool = True) -> Kept: ...
    def add(
        self,
        name: str,
        spec: str,
        *,
        anchor: str = "",
        goals: bool = True,
        web_search: bool | None = None,
        force: bool = False,
    ) -> Kept: ...
    def remove(self, name: str) -> bool: ...
```

The agents written down under a name.

- One written over MUST keep its place in the list and one that is new MUST go on the end,
  which is the order they were written down in -- and MUST be so however it was written,
  since a menu and a command line write down the same thing.
- A name already written down MUST be its own refusal. What to say about it is whoever
  asked's: a command line says which flag writes over one, and a menu that has already asked
  which name to save over says nothing at all.

## `accounts.py`

```python
class Accounts:
    def all(self, cli: str = "") -> list[Provider]: ...
    def ways(self, cli: str) -> tuple[Way, ...]: ...
    def way(self, cli: str, name: str) -> Way | None: ...
    def find(self, cli: str, name: str) -> Provider | None: ...
    def where(self, cli: str, name: str) -> Path: ...
    def local(self, cli: str) -> Path: ...
    def write(
        self,
        cli: str,
        name: str,
        way: str = "",
        env: Mapping[str, str] | None = None,
        args: tuple[str, ...] = (),
    ) -> Provider: ...
    def make(
        self, cli: str, name: str, way: Way, answers: Mapping[str, str] | None = None
    ) -> Provider: ...
    def sign_in(
        self, provider: Provider, way: Way, answers: Mapping[str, str] | None = None
    ) -> int: ...
    def asks(self, way: Way, given: Mapping[str, str]) -> list[str]: ...
    def serves(self, one: Provider) -> tuple[str, ...]: ...
    def copies(self, one: Provider, cli: str, name: str = "") -> Provider: ...
    def chain(self, one: Provider) -> list[Provider]: ...
    def points(self, cli: str, name: str, at: str) -> bool: ...
    def remove(self, cli: str, name: str) -> bool: ...
    def env(self, said: str) -> dict[str, str]: ...
    def environ(self, provider: Provider | None) -> dict[str, str]: ...
    def models(self, cli: str, provider: str = "") -> tuple[Model, ...]: ...
    def asked(self, cli: str, provider: str = "") -> str: ...
    def ask(
        self, cli: str, provider: str = "", seconds: float | None = None
    ) -> tuple[Model, ...]: ...
```

The accounts an agent may be run as, and what each backend runs as one of them.

- The accounts and the catalogue MUST be one object. Which models an account may name is that
  account's rather than the CLI's, so whoever made an account is who asks.
- Asking MUST be the layer's own asking, reached through this rather than reimplemented: a
  suite that has taken the asking away MUST have taken it away here too.

## `fallbacks.py`

```python
class Fallbacks:
    @property
    def default(self) -> str: ...
    def policies(self) -> tuple[Policy, ...]: ...
    def named(self, policy: str) -> Policy | None: ...
    def all(self) -> list[Falls]: ...
    def reads(self, said: str) -> str: ...
    def spec(self, backend: str, model: str, provider: str = "") -> str: ...
    def tried(self, said: str) -> Falls: ...
    def chain(self, said: str) -> list[str]: ...
    def points(self, said: str, at: str) -> Falls: ...
    def retrying(self, said: str, tries: int, policy: str, timeout: float) -> Falls: ...
    def clear(self, said: str) -> bool: ...
```

Where a turn goes when the place taking it cannot take it at all.

## `cycles.py`

```python
class Cycles:
    def __init__(self, workspace: str | os.PathLike[str] | None = None): ...
    def under(self) -> Path: ...
    def all(self) -> list[Path]: ...
    def read(self, cycle: Path) -> Ran | None: ...
    def sessions(self, cycle: Path) -> list[Session]: ...
    def opened(self, cycle: Path) -> dict[str, list[str]]: ...
    def resumed(self, flow: str) -> Path | None: ...
    def state(self, cycle: Path, flow: str = "") -> dict[str, Any]: ...
    def traced(
        self,
        cycle: Path,
        *,
        output: str | os.PathLike[str] | None = None,
        start: str | None = None,
        end: str | None = None,
    ) -> tuple[Path, dict[str, Any]]: ...
    def trace(
        self,
        *,
        sessions: str | Iterable[str] | None = None,
        agents: Mapping[str, Iterable[str]] | None = None,
        output: str | os.PathLike[str] | None = None,
        start: str | None = None,
        end: str | None = None,
        profile: str | os.PathLike[str] | None = None,
    ) -> dict[str, Any]: ...
```

The runs of one workspace that have already happened, and the traces gathered of them.

- A trace of a run MUST be gathered here rather than by whoever asked for one. Two ways in ask
  for the same trace -- a command line and the sheet the runs are read on -- and every part of
  it is the same both times: the sessions asked for by the ids the run wrote down rather than
  by the directory it ran in, which agent opened each, the profile beside them, and where it
  goes, which is with the run.
- A workspace nobody named MUST stay nobody's. Naming sessions without one collects them
  wherever they were recorded, and a workspace filled in here would narrow that to whatever
  directory somebody was standing in -- which is why a trace of a run is gathered with none.

## `running.py`

```python
class Run:
    def __init__(self, runner: Runner, task: str): ...

    @property
    def agents(self) -> tuple[AgentBase, ...]: ...

    @property
    def running(self) -> bool: ...

    @property
    def raised(self) -> BaseException | None: ...

    def run(self) -> None: ...
    def start(self) -> None: ...
    def wait(self, timeout: float | None = None) -> bool: ...
    def stop(self) -> None: ...
    def close(self) -> None: ...
```

One run of one flow, and the handful of things there are to do to one.

- Making one MUST start nothing. `run` runs it here and returns when the flow does; `start`
  runs it on a thread, so that whoever made one chooses which of the two they are holding.
- A run in a container MUST be one at a time per process, and MUST say so: the container a
  run works in is the process's rather than the run's, a flow that called another being one
  run working in one place. Two started at once with an image between them would be two runs
  reaching for one container.
- `stop` MUST tell every agent to take no further turn, so that the turn running now is
  closed out and the loop ends rather than handing on. `close` MUST NOT wait for that: it
  closes every conversation still open, which is the backend's process going, and is the last
  thing there is to do about a run.
- What a run started on a thread raised MUST be kept rather than swallowed: a run that ended
  because the flow failed is not a run that finished.

## `session.py`

```python
@runtime_checkable
class Session(Protocol):
    @property
    def attached(self) -> int: ...

    def detach(self) -> int: ...
```

A run being read from a terminal, as whatever is holding the run sees it.

- It MUST be a protocol rather than the thing itself, so that the interface names no daemon:
  one run under a daemon is handed one of these and one run in the process somebody typed
  `hmz` in is handed none, and the interface says so where the question is asked.
- It MUST be the whole of what an interface has to know about being held somewhere: how many
  terminals are reading, and how to let go of them without stopping anything.

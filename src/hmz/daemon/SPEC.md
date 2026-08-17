# Daemon

## File Structure

```
.
├── __init__.py
├── attach.py
├── proto.py
├── serve.py
└── where.py
```

## `__init__.py`

```python
@dataclass(frozen=True, slots=True)
class Daemon:
    at: Path
    workspace: str
    pid: int
    started: str

    @property
    def alive(self) -> bool: ...

    def attach(self) -> int: ...
    def status(self) -> dict[str, Any]: ...
    def detach(self) -> int: ...
    def stop(self, *, seconds: float = 20.0) -> bool: ...
    def kill(self, *, seconds: float = 20.0) -> bool: ...
    def asked(self, said: dict[str, Any]) -> dict[str, Any]: ...


def running(workspace: str | os.PathLike[str] | None = None) -> Daemon | None: ...
def daemons() -> list[Daemon]: ...
def start(
    opens: Callable[[Held], object],
    workspace: str | os.PathLike[str] | None = None,
    *,
    columns: int = 0,
    rows: int = 0,
    seconds: float = 10.0,
) -> Daemon: ...
```

A run held where a terminal closing cannot end it, and the terminals that come and go from it.

- Nothing here MUST know what a run is. What it holds is a callable that opens one and
  returns when it is over, so that the interface and this stay apart: an interface draws on a
  terminal, and whether that terminal is somebody's ssh session or one of these is not a
  thing it has to be told. That is what makes it a leaf, and what makes the interface running
  under one identical to the interface running under none.
- It MUST be one daemon per workspace. Two runs of one project in one directory are two flows
  writing over each other's cycle, and a daemon somebody cannot find is a daemon nobody can
  stop. It MUST be held by a lock rather than by looking: looking is what leaves a window
  between the look and the socket, and two `hmz` started in the same second would both find
  nothing and both bind. The lock MUST be one the kernel drops however the process ends, so
  that there is no such thing as one left behind by a machine that was turned off.
- Holding a run MUST be done the way `nohup` and `screen` are done underneath, and MUST NOT
  be done by running either: a fork so that whatever asked for it is not waiting on it,
  `setsid` so that the terminal which started it is no longer its own -- which is what keeps a
  hangup from reaching it -- and a second fork so that it can never take a controlling
  terminal again. Its standard streams MUST be a pseudoterminal of its own, so that there is a
  screen to draw on when nobody is reading, and MUST be put back if the caller was not a
  forked child.
- The process holding a run MUST be adopted rather than waited on: the middle process forks
  it and exits, so that whatever asked for a daemon has nothing left to reap.
- Whoever asked for one MUST be told whether it came up, and MUST be told through a
  descriptor the held process closes rather than by looking for a socket that may take a
  moment: a failure to bind is a thing to report and not a thing to time out on.
- What is running MUST be told from what once was. A socket file outlives the process that
  bound it, so a directory MUST read as holding nothing unless the process is there *and*
  something answers on the socket -- process numbers come round, and a terminal that hangs is
  worse than one that says nothing is running.
- Letting go MUST NOT be stopping. Every terminal reading a run MUST be closable without the
  run noticing, and the run MUST be told only so that it can say so; stopping is a separate
  request and is what closing the interface means.

## `where.py`

```python
SOCKET: str
RECORD: str
LOG: str
LOCK: str


def under() -> Path: ...
def at(workspace: str | os.PathLike[str] | None = None) -> Path: ...
def reached(where: Path) -> Generator[str]: ...
def holds(where: Path) -> int: ...
def wrote(where: Path, said: dict[str, Any]) -> None: ...
def held(where: Path) -> dict[str, Any]: ...
def alive(pid: int) -> bool: ...
```

Where one workspace's daemon keeps its socket, and what is written down beside it.

- A directory MUST be named for the project and then for the whole path it is at: two
  checkouts of one repository are two workspaces, and a directory of these is read by people.
- What is written down MUST be written whole and moved into place, as every other file
  humanize writes is.
- A note whose process has gone MUST read as nothing written down: it is what tells a daemon
  that is running from one whose machine went down without it.
- What kind of terminal a run is drawing for MUST be written down and MUST be readable from
  outside it. A run holds one pseudoterminal for its whole life and takes its kind from the
  terminal it was started on, so a terminal of another kind that reads it later is read in the
  first one's language -- which is a thing to be able to see rather than one to discover.
- A socket MUST be reachable however deep the directory it is in. A Unix socket address holds
  about a hundred bytes whole, and a project under a deep home is longer than that, so a path
  that will not fit MUST be reached by standing in its directory and naming the socket alone.
  That MUST be done only where a process has one thread and never while a flow is running,
  which is a flow that may be standing somewhere of its own.

## `proto.py`

```python
HELLO: bytes
INPUT: bytes
OUTPUT: bytes
RESIZE: bytes
GONE: bytes
CONTROL: bytes


def frame(kind: bytes, payload: bytes = b"") -> bytes: ...
def spoken(kind: bytes, said: dict[str, Any]) -> bytes: ...
def asked(payload: bytes) -> dict[str, Any]: ...


class Frames:
    def feed(self, data: bytes) -> list[tuple[bytes, bytes]]: ...
```

What the socket between a run and the terminals reading it carries.

- It MUST be framed rather than a pipe both ways. The two directions are not only bytes: a
  terminal that has been resized has to say so, and a run letting go of one has to say that
  rather than closing a socket the terminal would read as the machine going down.
- A length no frame of this protocol has MUST be refused rather than allocated for: a socket
  carrying something else is a socket to close.
- What was read MUST be taken out of the buffer before any of it is handed over. A caller
  that stops reading partway -- a terminal that has just been told the run is over -- MUST
  NOT leave a frame it has already been handed sitting there to be handed out again.
- A question about the run rather than a terminal reading it MUST be one of these too, and
  MUST be answered on the same connection and closed: one socket is one protocol.

## `serve.py`

```python
class Held:
    def __init__(self, master: int, listening: socket.socket, at: Path): ...

    @property
    def attached(self) -> int: ...

    def detach(self) -> int: ...
    def redrawn(self, hook: Callable[[], None]) -> None: ...
    def stopping(self, hook: Callable[[], None]) -> None: ...
    def says(self, hook: Callable[[], dict[str, Any]]) -> None: ...
    def start(self) -> None: ...
    def close(self, why: str = "the run is over") -> None: ...


def sized(fd: int, columns: int, rows: int) -> None: ...
def logged(at: Path, about: str) -> None: ...
def hosts(
    opens: Callable[[Held], object],
    at: Path,
    *,
    columns: int = 80,
    rows: int = 24,
    telling: int | None = None,
) -> None: ...
```

The run on its pseudoterminal, and the terminals that come and go from it.

- `Held` MUST be what `hmz.sdk.Session` asks for and no less, since it is what the interface
  is handed.
- A terminal that has just arrived MUST be drawn for from the top. It has none of what was
  drawn before it: it is in whatever modes the shell left it in, at whatever size it happens
  to be. Asking for that MUST NOT be done on the thread carrying what the run draws -- a
  screen's worth of bytes has to be being carried out while it happens, and waiting for it
  there would be waiting on a buffer this is the only reader of.
- What a run drew before anybody was reading MUST be kept for the first terminal to arrive,
  and MUST be dropped whole rather than in part once it is more than is worth keeping: half
  an escape sequence is worse than none, and the terminal that arrives is drawn for again
  anyway. Once one has read it, output with nobody reading MUST be dropped rather than kept.
- A terminal that has stopped reading MUST NOT be able to stop the run: one that will not take
  what it is sent within a bounded time MUST be let go of.
- A size of nothing or less MUST be refused rather than believed. What is drawing on the other
  side lays a screen out against it, and a terminal that has never been told its own size
  reports zero -- which is not a terminal one column wide.
- The run MUST be told a terminal has resized by a signal to this process. The pseudoterminal
  has no foreground process group to signal, this process having no controlling terminal at
  all, so that is the one way left.
- Nothing this does MUST be able to end the run. A thread that raised, a hook that raised, a
  socket that will not accept: each MUST be written down where it can be read afterwards and
  left there.

## `attach.py`

```python
def attaches(at: os.PathLike[str] | str) -> socket.socket: ...
def reads(one: socket.socket) -> int: ...
def size() -> tuple[int, int]: ...
```

This terminal, reading a run somebody else is holding.

- Nothing of the interface MUST be here. This puts the terminal into the mode a full-screen
  program needs and gets out of the way: every byte typed goes to the run, every byte the run
  draws comes back, and a terminal that changes size says so.
- Putting the terminal back MUST be this side's and this side's alone, whichever way the
  reading ended. A run that has let go says so and goes on running, so nothing on the other
  end is ever going to write the sequences that leave the alternate screen and show the cursor
  -- and a terminal left in a full-screen program's modes is a shell nobody can use.
- Raw MUST be what the terminal is put in, which is what every terminal multiplexer does: the
  run on the other end does its own echoing, its own line editing and its own interrupts, and
  a terminal doing any of them too would be doing them twice.
- Why the reading ended MUST be said after the terminal has been put back and not before: a
  line drawn on the alternate screen is a line thrown away with it, and why a terminal was
  let go of is the one thing somebody is looking at when it happens.
- How big this terminal is MUST be answered here and asked of here. A terminal that has never
  been told its own size reports zero of both, which is not a terminal one column wide -- it
  is one that has not said, and what a full-screen program does about that is assume the
  ordinary eighty by twenty-four.

"""The run held where a terminal closing cannot end it, and the terminals that come and go.

A flow is a loop and a turn thinks for minutes, so a day's work must not end because somebody
closed a laptop. What holds it is a process of its own: a session leader's child, with no
controlling terminal of its own and its standard streams on a pseudoterminal instead of on
whatever terminal started it. Nothing about the interface it holds changes -- it is the same
interface, drawing on a terminal like any other, and what is on the other end of that terminal
is a socket rather than somebody's ssh session.

That is what `nohup` and `screen` are underneath, done here rather than by shelling out to
either: a fork so the shell is not waiting, `setsid` so the terminal that started it is no
longer its own, a second fork so it can never take another, and its own pseudoterminal so
there is a screen to draw on when nobody is reading.
"""

from __future__ import annotations

import contextlib
import dataclasses
import fcntl
import os
import selectors
import signal
import socket
import struct
import sys
import termios
import threading
import traceback
from pathlib import Path
from typing import TYPE_CHECKING, Any

from hmz.daemon import where
from hmz.daemon.proto import (
    CONTROL,
    GONE,
    HELLO,
    INPUT,
    OUTPUT,
    RESIZE,
    Frames,
    asked,
    frame,
    spoken,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Generator

__all__ = ["Held", "hosts", "logged", "sized"]

#: How much is read off the pseudoterminal at a time. A screen is kilobytes.
_READ = 1 << 16

#: How much of what a run drew before anybody was reading is kept, so that the first terminal
#: to arrive sees the screen it drew rather than a blank one. Dropped whole if it grows past
#: this: half an escape sequence is worse than none, and the terminal that arrives is drawn
#: for again anyway.
_KEPT = 1 << 17

#: How long the loop waits on nothing at all before looking again at whether the run is over.
_PATIENCE = 5.0

#: How much a terminal may let pile up before it is let go of. Nothing here waits on one --
#: every write is one that would not block -- so what a terminal that has stopped reading
#: costs is memory, and this is the ceiling on it. A screen is kilobytes, so a megabyte is a
#: terminal that has taken nothing for a long while.
_BACKLOG = 1 << 20

#: How many rounds may go wrong before the thread carrying them gives up. A handful, so that
#: a terminal that went away mid-write is one bad round rather than a run nobody can read.
_WRONG = 8

#: How big the pseudoterminal is before any terminal has said, which is what a run drawn for
#: nobody is drawn at.
_COLUMNS, _ROWS = 80, 24

#: The smallest terminal a run is drawn for. Anything under this is not a window somebody is
#: reading -- it is a terminal that has not been told its own size, or one being taken down --
#: and laying a screen out against it is what a full-screen program crashes on.
_NARROW, _SHORT = 8, 2


@dataclasses.dataclass(slots=True)
class _Reading:
    """One socket on the other end of this run, and what has arrived off it so far.

    A socket is on the list from the moment it connects, before it has said what it is for: a
    terminal says so with `HELLO` and is drawn for from then on, and a question about the run
    says so with `CONTROL` and is answered and closed. One record rather than a dict apiece,
    so that there is one list to take a socket off rather than three to keep in step.

    Attributes:
      one: The socket.
      frames: What has been read off it that is not yet a whole frame.
      joined: Whether it is a terminal reading this run, rather than one that has not said.
      sending: What the run has drawn that this socket has not taken yet.
    """

    one: socket.socket
    frames: Frames
    joined: bool = False
    sending: bytearray = dataclasses.field(default_factory=bytearray)


def sized(fd: int, columns: int, rows: int) -> None:
    """Says how big the terminal on this descriptor is.

    Args:
      fd: The pseudoterminal, either end.
      columns: How wide.
      rows: How tall.
    """
    with contextlib.suppress(OSError):
        fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, columns, 0, 0))


class Held:
    """One run, the terminals reading it, and the pseudoterminal between them.

    The run draws on the pseudoterminal exactly as it would on anybody's terminal. This
    carries what it drew out to whichever terminals are reading, carries what they type back
    in, and is what tells the run how big the terminal it is drawing for is.
    """

    def __init__(self, master: int, listening: socket.socket, at: Path) -> None:
        """Holds the two ends and the directory they are reached through.

        Args:
          master: The pseudoterminal the run is drawing on, this side of it.
          listening: The socket terminals arrive on, already bound and listening.
          at: The daemon's own directory, which is where its note is written.
        """
        self._master = master
        self._listening = listening
        self._at = at
        self._lock = threading.Lock()
        self._reading: dict[int, _Reading] = {}
        self._letting: list[tuple[socket.socket, str]] = []
        #: What was typed at a terminal and is not in the run's own terminal yet. Held here
        #: rather than written where it arrives: the descriptor it goes to is the one this
        #: thread is the only reader of, so a write that waited would be a screen nobody is
        #: carrying out while it waited.
        self._typing = bytearray()
        self._woken_r, self._woken_w = os.pipe()
        self._buffer = bytearray()
        self._spilled = False
        self._ever = False
        self._going = True
        self._thread: threading.Thread | None = None
        self._redraws: Callable[[], None] | None = None
        self._stops: Callable[[], None] | None = None
        self._saying: Callable[[], dict[str, Any]] | None = None

    # -- what the interface being held is told about, which is the whole of `hmz.sdk.Session`

    @property
    def attached(self) -> int:
        """How many terminals are reading this run right now."""
        with self._lock:
            return sum(1 for held in self._reading.values() if held.joined)

    def detach(self) -> int:
        """Lets go of every terminal reading this, leaving the run itself running.

        Returns:
          How many were let go of, which is zero where nobody was reading.
        """
        return self._lets_go("detached")

    # -- what the process holding it registers

    def redrawn(self, hook: Callable[[], None]) -> None:
        """Says what to do when a terminal arrives, which is to draw the screen again.

        The terminal that has just arrived has none of what was drawn before it: it is a
        fresh terminal, in its own modes, showing whatever the shell left on it. So the run
        is asked to draw itself again from the top.

        Args:
          hook: What to call. It is called on a thread of its own, since drawing a screen
            again is a screen's worth of bytes that this has to be carrying while it happens.
        """
        self._redraws = hook

    def stopping(self, hook: Callable[[], None]) -> None:
        """Says what to do when somebody asks the run to stop from outside it.

        Args:
          hook: What to call, which is whatever closing the interface means.
        """
        self._stops = hook

    def says(self, hook: Callable[[], dict[str, Any]]) -> None:
        """Says what to add to the answer when somebody asks what is running here.

        Args:
          hook: What to call for it.
        """
        self._saying = hook

    # -- the loop

    def start(self) -> None:
        """Starts carrying between the run and the terminals, on a thread of its own."""
        self._thread = threading.Thread(
            target=self._carries, name="humanize-daemon", daemon=True
        )
        self._thread.start()

    def close(self, why: str = "the run is over") -> None:
        """Lets go of every terminal, saying why, and stops listening.

        Args:
          why: What to tell them, which is what a terminal prints as it goes.
        """
        self._lets_go(why)
        self._going = False
        self._wake()
        if self._thread is not None:
            self._thread.join(timeout=_PATIENCE)
        self._unlisten()

    def _unlisten(self) -> None:
        """Stops anything being told there is a run here to read.

        The socket and the note beside it are what say one is being held, so both go the
        moment nothing is carrying it: a directory that still says yes is a terminal that
        connects and then waits forever.
        """
        with contextlib.suppress(OSError):
            self._listening.close()
        for name in (where.SOCKET, where.RECORD):
            with contextlib.suppress(OSError):
                (self._at / name).unlink()

    def _wake(self) -> None:
        """Wakes the loop, for something another thread has asked of it."""
        with contextlib.suppress(OSError):
            os.write(self._woken_w, b".")

    def _lets_go(self, why: str) -> int:
        """Takes every terminal off the list, for the loop to say goodbye to and close."""
        with self._lock:
            going = [held.one for held in self._reading.values() if held.joined]
            for one in going:
                self._letting.append((one, why))
                self._reading.pop(one.fileno(), None)
        if going:
            self._wake()
        return len(going)

    def _carries(self) -> None:
        """Carries the screen out and the keys in, until the run is over."""
        selector = selectors.DefaultSelector()
        selector.register(self._listening, selectors.EVENT_READ)
        selector.register(self._master, selectors.EVENT_READ)
        selector.register(self._woken_r, selectors.EVENT_READ)
        wrong = 0
        try:
            while self._going and wrong < _WRONG:
                try:
                    for key, events in selector.select(_PATIENCE):
                        if not self._going:
                            break
                        self._ready(selector, key.fd, events)
                    self._closes(selector)
                    self._watches(selector)
                    # Counted in a row rather than for the life of the run: a terminal that
                    # went away mid-write is one bad round, and a daemon holding a flow for a
                    # week must not spend its last go on the eighth of those.
                    wrong = 0
                except Exception:  # noqa: BLE001 -- a bad round is not the run over
                    # A descriptor that has gone, a terminal that went away mid-write: the
                    # run goes on, and the round after this one is tried. Only a thread that
                    # can do nothing at all stops, since a screen nobody carries out is a
                    # run that blocks writing one.
                    wrong += 1
                    self._logs(
                        "the daemon could not carry a round of what the run drew"
                    )
            if wrong >= _WRONG:
                # Nothing can be carried any more, so nothing may go on being told there is
                # something here to read: a socket that is still accepting and no longer
                # answering is a terminal that hangs rather than one that says so.
                self._going = False
                self._lets_go("this run can no longer be read")
                self._unlisten()
        finally:
            # Whichever terminals were let go of in the round the loop came out of: a
            # terminal told nothing reads a closed socket as the machine having gone down.
            with contextlib.suppress(Exception):
                self._closes(selector)
            selector.close()

    def _ready(self, selector: selectors.BaseSelector, fd: int, events: int) -> None:
        """Answers whichever of the four kinds of thing is ready, for whichever reason."""
        if fd == self._woken_r:
            with contextlib.suppress(OSError):
                os.read(self._woken_r, _READ)
            return
        if fd == self._master:
            if events & selectors.EVENT_WRITE:
                self._puts()
            if events & selectors.EVENT_READ:
                self._drew()
            return
        if fd == self._listening.fileno():
            self._arrived(selector)
            return
        if events & selectors.EVENT_WRITE:
            self._sends(fd)
        if events & selectors.EVENT_READ:
            self._typed(selector, fd)

    def _watches(self, selector: selectors.BaseSelector) -> None:
        """Says which descriptors are worth waking for, which is what has something waiting.

        Asked again each round rather than left standing: a descriptor watched for room it
        does not need is a loop that spins, and one not watched for room it does need is a
        screen that stops half-written.

        Args:
          selector: What the loop waits on.
        """
        _watching(selector, self._master, waiting=bool(self._typing))
        with self._lock:
            held = list(self._reading.values())
        for one in held:
            _watching(selector, one.one, waiting=bool(one.sending))

    def _drew(self) -> None:
        """Takes what the run has drawn out to whichever terminals are reading."""
        try:
            drawn = os.read(self._master, _READ)
        except (BlockingIOError, InterruptedError):
            return  # said it was readable and was not, which a pseudoterminal may
        except OSError:
            self._going = False
            return
        if not drawn:
            self._going = False
            return
        with self._lock:
            reading = [held for held in self._reading.values() if held.joined]
            if not reading and not self._ever:
                self._keeps(drawn)
        if not reading:
            return
        sent = frame(OUTPUT, drawn)
        for held in reading:
            self._writes(held, sent)

    def _keeps(self, drawn: bytes) -> None:
        """Keeps what was drawn for nobody, until it is more than is worth keeping."""
        if self._spilled:
            return
        self._buffer += drawn
        if len(self._buffer) > _KEPT:
            # Half an escape sequence is worse than none: the terminal that arrives is
            # drawn for again from the top, which is what makes this safe to throw away.
            self._spilled = True
            self._buffer.clear()

    def _writes(self, held: _Reading, sent: bytes) -> None:
        """Puts one frame on its way to one terminal, without waiting for it to take it.

        A terminal on a stalled link would otherwise hold up the one thread that is also the
        only reader of the run's own terminal -- so nothing here waits, and a terminal that
        has let more pile up than is worth keeping is let go of instead.

        Args:
          held: The terminal.
          sent: The frame.
        """
        held.sending += sent
        if len(held.sending) > _BACKLOG:
            self._drops(held.one)
            return
        self._sends(held.one.fileno())

    def _sends(self, fd: int) -> None:
        """Writes what one terminal has waiting, as much of it as it will take now."""
        with self._lock:
            held = self._reading.get(fd)
        if held is None:
            return
        while held.sending:
            try:
                written = held.one.send(held.sending)
            except (BlockingIOError, InterruptedError):
                return
            except OSError:
                self._drops(held.one)
                return
            del held.sending[:written]

    def _drops(self, one: socket.socket) -> None:
        """Lets go of one terminal that has gone, or will not read what it is sent.

        The closing itself is left to the round this is in: the selector it is registered
        with is the carrying thread's, and this is called from the middle of a write.
        """
        with self._lock:
            self._reading.pop(one.fileno(), None)
            self._letting.append((one, ""))
        self._wake()

    def _arrived(self, selector: selectors.BaseSelector) -> None:
        """Takes a socket that has just connected, whatever it turns out to be for."""
        try:
            one, _ = self._listening.accept()
        except OSError:
            return
        one.setblocking(False)  # noqa: FBT003 -- what a socket takes, not a flag of ours
        with self._lock:
            self._reading[one.fileno()] = _Reading(one, Frames())
        with contextlib.suppress(ValueError, KeyError, OSError):
            selector.register(one, selectors.EVENT_READ)

    def _typed(self, selector: selectors.BaseSelector, fd: int) -> None:
        """Takes what one socket said, which is keys, a resize, or a question."""
        with self._lock:
            held = self._reading.get(fd)
        if held is None:
            with contextlib.suppress(KeyError, ValueError, OSError):
                selector.unregister(fd)
            return
        one, frames = held.one, held.frames
        try:
            said = one.recv(_READ)
        except OSError:
            said = b""
        if not said:
            self._closing(selector, one)
            return
        try:
            for kind, payload in frames.feed(said):
                self._said(selector, one, kind, payload)
        except ValueError:
            self._closing(selector, one)

    def _said(
        self,
        selector: selectors.BaseSelector,
        one: socket.socket,
        kind: bytes,
        payload: bytes,
    ) -> None:
        """Does what one frame off a socket asked for."""
        if kind == HELLO:
            self._joins(one, asked(payload))
        elif kind == INPUT:
            self._into(payload)
        elif kind == RESIZE:
            self._sized(asked(payload))
        elif kind == CONTROL:
            self._answers(one, asked(payload))
            self._closing(selector, one)

    def _joins(self, one: socket.socket, said: dict[str, Any]) -> None:
        """Takes a terminal onto the list, and has the run draw itself for it."""
        self._sizes(said)
        with self._lock:
            held = self._reading.get(one.fileno())
            if held is not None:
                held.joined = True
            first = not self._ever
            self._ever = True
            kept = bytes(self._buffer) if first and not self._spilled else b""
            self._buffer.clear()
        if kept and held is not None:
            # What it drew before anybody was reading, so that a terminal arriving at a run
            # that has not moved since is not looking at a blank screen.
            self._writes(held, frame(OUTPUT, kept))
        # And then again from the top, in this terminal's own modes and at its own size: a
        # terminal that has just arrived is in whatever modes the shell left it in.
        os.kill(os.getpid(), signal.SIGWINCH)
        self._redraw()

    def _redraw(self) -> None:
        """Asks the run to draw itself again, on a thread of its own.

        On a thread of its own because drawing a screen again is a screen's worth of bytes
        into the pseudoterminal, and this thread is the one that has to be carrying them out
        while it happens: waiting for it here would be waiting for a buffer this thread is
        the only reader of.
        """
        hook = self._redraws
        if hook is None:
            return
        threading.Thread(target=_quietly, args=(hook,), daemon=True).start()

    def _into(self, typed: bytes) -> None:
        """Puts what was typed at a terminal on its way into the run's own."""
        self._typing += typed
        self._puts()

    def _puts(self) -> None:
        """Writes what is waiting into the run's own terminal, as much as it will take now.

        Without waiting, for the reason a terminal is not waited on: this thread is the only
        reader of what the run draws, so a paste bigger than the pseudoterminal's own buffer
        would be this thread waiting for a run that is waiting for this thread.
        """
        while self._typing:
            try:
                written = os.write(self._master, self._typing)
            except (BlockingIOError, InterruptedError):
                return
            except OSError:
                self._going = False
                return
            del self._typing[:written]

    def _sized(self, said: dict[str, Any]) -> None:
        """Says how big the terminal reading this is now, and tells the run."""
        if not self._sizes(said):
            return
        # The pseudoterminal has no foreground process group to signal, this process having
        # no controlling terminal at all, so the run is told the one way that is left.
        os.kill(os.getpid(), signal.SIGWINCH)

    def _sizes(self, said: dict[str, Any]) -> bool:
        """Says how big the terminal on the other end is, where it said anything sensible.

        Args:
          said: What the terminal sent.

        Returns:
          Whether the pseudoterminal was resized. A size of nothing or less is refused rather
          than believed: what is drawing on the other side of this lays a screen out against
          it, and a screen no columns wide is one nothing can be laid out on.
        """
        columns = said.get("columns")
        rows = said.get("rows")
        if not isinstance(columns, int) or not isinstance(rows, int):
            return False
        if columns < _NARROW or rows < _SHORT:
            return False
        sized(self._master, columns, rows)
        return True

    def _answers(self, one: socket.socket, said: dict[str, Any]) -> None:
        """Answers a question about the run rather than a terminal reading it."""
        doing = said.get("do")
        answer: dict[str, Any] = {"ok": True}
        if doing == "status":
            answer = {"ok": True, **self._status()}
        elif doing == "detach":
            answer = {"ok": True, "let go": self.detach()}
        elif doing == "stop":
            hook = self._stops
            if hook is None:
                answer = {
                    "ok": False,
                    "why": "this run cannot be stopped from outside it",
                }
            else:
                threading.Thread(target=_quietly, args=(hook,), daemon=True).start()
        else:
            answer = {"ok": False, "why": f"no such request: {doing!r}"}
        with contextlib.suppress(OSError):
            one.sendall(spoken(CONTROL, answer))

    def _status(self) -> dict[str, Any]:
        """What there is to say about this run, for somebody asking from outside it."""
        said: dict[str, Any] = dict(where.held(self._at))
        said["attached"] = self.attached
        hook = self._saying
        if hook is not None:
            with contextlib.suppress(Exception):
                said.update(hook())
        return said

    def _closing(self, selector: selectors.BaseSelector, one: socket.socket) -> None:
        """Takes one socket off the list and closes it."""
        with contextlib.suppress(KeyError, ValueError, OSError):
            selector.unregister(one)
        with self._lock:
            self._reading.pop(one.fileno(), None)
        with contextlib.suppress(OSError):
            one.close()

    def _closes(self, selector: selectors.BaseSelector) -> None:
        """Says goodbye to whichever terminals have been let go of, and closes them."""
        with self._lock:
            going, self._letting = self._letting, []
        for one, why in going:
            with contextlib.suppress(KeyError, ValueError, OSError):
                selector.unregister(one)
            if why:
                with contextlib.suppress(OSError):
                    one.sendall(frame(GONE, why.encode()))
            with contextlib.suppress(OSError):
                one.close()

    def _logs(self, about: str) -> None:
        """Writes down what went wrong where nobody was reading a terminal to see it."""
        logged(self._at, about)


def logged(at: Path, about: str) -> None:
    """Writes down what went wrong where nobody was reading a terminal to see it.

    Args:
      at: The daemon's own directory.
      about: What was being done, since whatever is being handled is what raised.
    """
    with (
        contextlib.suppress(OSError),
        (at / where.LOG).open("a", encoding="utf-8") as writing,
    ):
        writing.write(f"{about}\n{traceback.format_exc()}\n")


def _watching(
    selector: selectors.BaseSelector, one: socket.socket | int, *, waiting: bool
) -> None:
    """Says whether one descriptor is worth waking for room to write as well as to read.

    Args:
      selector: What the loop waits on.
      one: The descriptor, or the socket it belongs to.
      waiting: Whether anything is waiting to be written to it.

    Note:
      A descriptor that has gone since the round began is one there is nothing to say about,
      which is what the loop finds out when it closes it.
    """
    wanted = selectors.EVENT_READ | (selectors.EVENT_WRITE if waiting else 0)
    with contextlib.suppress(KeyError, ValueError, OSError):
        if selector.get_key(one).events != wanted:
            selector.modify(one, wanted)


def _quietly(hook: Callable[[], object]) -> None:
    """Runs one of the registered hooks, which must not be able to end the run."""
    with contextlib.suppress(Exception):
        hook()


def hosts(
    opens: Callable[[Held], object],
    at: Path,
    *,
    columns: int = _COLUMNS,
    rows: int = _ROWS,
    telling: int | None = None,
) -> None:
    """Holds one run on a pseudoterminal of its own, for terminals to come and go from.

    This is the whole of what the detached process does. It is called with the standard
    streams still on whatever terminal started it and returns with them back where they were,
    so that a caller which is not a forked child -- a test -- is left as it was found.

    Args:
      opens: What opens the run, called with the held run so that it can be let go of and
        drawn again. It returns when the run is over.
      at: The daemon's own directory, which is made here.
      columns: How wide the terminal it draws for is until one says otherwise.
      rows: How tall.
      telling: A descriptor to say on that it is listening, and then close, or None. What
        waits for a daemon to come up reads it: a line for a run that is up, and the reason
        for one that is not.

    Raises:
      OSError: If a daemon of this workspace is already running, or the socket cannot be
        bound -- which is the one failure whoever asked for a daemon has to hear about rather
        than read in a log.
    """
    import pty

    at.mkdir(parents=True, exist_ok=True)
    # Taken before anything is looked at: two `hmz` started in the same second would both
    # find no daemon here, and one of them would take the other's socket away as stale.
    holding = where.holds(at)
    listening = _listens(at)
    master, slave = pty.openpty()
    # Nothing carrying between the two ends may wait on either of them: the one thread that
    # reads what the run draws is the one that writes what was typed, so a write that waited
    # would be waiting for a run that is waiting for it.
    os.set_blocking(master, False)
    sized(master, columns, rows)
    where.wrote(
        at,
        {
            "pid": os.getpid(),
            # This process's own directory, which is the workspace: a daemon is forked in
            # the project it is holding, and the flow it runs runs there as it always did.
            "workspace": str(Path.cwd()),
            "started": _now(),
            "term": os.environ.get("TERM", ""),
        },
    )
    if telling is not None:
        with contextlib.suppress(OSError):
            os.write(telling, b"listening\n")
            os.close(telling)
    held = Held(master, listening, at)
    with _drawn_on(slave):
        held.start()
        try:
            opens(held)
        except BaseException:
            logged(at, "the run this daemon was holding stopped")
            raise
        finally:
            held.close()
            for fd in (master, slave, holding):
                with contextlib.suppress(OSError):
                    os.close(fd)


def _listens(at: Path) -> socket.socket:
    """Binds the socket terminals arrive on, taking away one a daemon that is gone left.

    Called with this workspace's daemon lock already held, so that taking a socket away as
    stale cannot be taking one from a daemon that is coming up beside this.

    Args:
      at: The daemon's own directory.

    Returns:
      The socket, listening.

    Raises:
      OSError: If it cannot be bound.
    """
    path = at / where.SOCKET
    if path.exists():
        # A socket file outlives the process that bound it, and one nothing is listening on
        # is a terminal that hangs rather than one that says nothing is running. Nothing else
        # can be listening on it: this workspace's daemon lock is held.
        with contextlib.suppress(OSError):
            path.unlink()
    listening = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        with where.reached(at) as reaching:
            listening.bind(reaching)
        path.chmod(0o600)
        listening.listen(8)
    except OSError:
        listening.close()
        raise
    return listening


@contextlib.contextmanager
def _drawn_on(slave: int) -> Generator[None]:
    """Puts the standard streams on the pseudoterminal, and puts them back afterwards.

    The run draws on whatever this process's standard streams are, which is the whole reason
    the interface needs to know nothing about any of this: it opens a terminal, and the
    terminal it opens is this one. What a flow prints goes the same way it always did.

    Args:
      slave: The pseudoterminal, the side the run draws on.

    Yields:
      Nothing.
    """
    for stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(Exception):
            stream.flush()
    kept = [os.dup(fd) for fd in (0, 1, 2)]
    # A size the terminal itself answers for, so that a run drawn for nobody is drawn at the
    # pseudoterminal's own size rather than at whatever the shell that started it was.
    said = {name: os.environ.pop(name, None) for name in ("COLUMNS", "LINES")}
    try:
        for fd in (0, 1, 2):
            os.dup2(slave, fd)
        yield
    finally:
        for fd, back in zip((0, 1, 2), kept, strict=True):
            with contextlib.suppress(OSError):
                os.dup2(back, fd)
            with contextlib.suppress(OSError):
                os.close(back)
        for name, was in said.items():
            if was is not None:
                os.environ[name] = was


def _now() -> str:
    """This moment, to the second, which is how long a daemon's own note has to be true."""
    import datetime

    return datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

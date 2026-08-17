"""The run a terminal closing cannot end, and the terminals that come and go from it.

    from hmz.daemon import running, start

    held = running() or start(opens)
    held.attach()

One daemon per workspace. It holds a run the way `screen` holds a shell -- a process of its
own, in a session of its own, drawing on a pseudoterminal nobody has to be looking at -- and a
terminal reads it by connecting to a socket beside it. Letting go of a terminal is not
stopping the run: the flow goes on taking its turns, and the next terminal to arrive is drawn
for from the top.

Nothing here knows what a run is. What it holds is a callable that opens one and returns when
it is over, which is what keeps the interface and this apart: the interface draws on a
terminal, and whether that terminal is somebody's ssh session or one of these is not a thing
it has to be told.
"""

from __future__ import annotations

import contextlib
import errno
import os
import socket
import sys
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from hmz.daemon import where
from hmz.daemon.attach import attaches, reads, size
from hmz.daemon.proto import CONTROL, Frames, asked, spoken
from hmz.daemon.serve import Held, hosts, logged

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

__all__ = ["Daemon", "Held", "daemons", "running", "start"]

#: How long a daemon is given to bind its socket before whoever asked for one gives up. It is
#: a fork and a bind; a second is already generous, and ten is a machine under load.
_PATIENCE = 10.0

#: How long a question about a run is given to be answered.
_ANSWERING = 5.0

#: How long a run told to stop is given to go before whoever asked is told it has not.
_UNWINDING = 20.0

#: How often a process being waited on is looked at.
_TICK = 0.1

#: How long the socket of a daemon that may not be listening is given to answer at all. It
#: is a connect to a file on this machine: either it is refused at once or it is taken, and a
#: wedged one must not be what a listing of every run on the machine waits on.
_ANSWERS_AT_ONCE = 1.0


@dataclass(frozen=True, slots=True)
class Daemon:
    """One workspace's run, held where a terminal closing cannot end it.

    Attributes:
      at: The daemon's own directory, which is where its socket is.
      workspace: The project it is holding a run in.
      pid: The process holding it.
      started: When it was started, in UTC.
    """

    at: Path
    workspace: str
    pid: int
    started: str

    @property
    def alive(self) -> bool:
        """Whether the process holding it is still there."""
        return where.alive(self.pid)

    def attach(self) -> int:
        """Reads this run from this terminal, until it ends or lets go.

        Returns:
          Zero once the terminal has been let go of, or one where there was nothing to read.
        """
        try:
            one = attaches(self.at)
        except OSError:
            return 1
        return reads(one)

    def status(self) -> dict[str, Any]:
        """What the run says about itself: how many are reading, and what is running.

        Returns:
          What it said, and what is written down beside its socket for a run that would not
          answer -- which is a daemon that is starting up, or one that is wedged.
        """
        said = self.asked({"do": "status"})
        return said if said.get("ok") else {**self._written(), "attached": 0}

    def detach(self) -> int:
        """Lets go of every terminal reading this run, leaving the run running.

        Returns:
          How many were let go of.
        """
        said = self.asked({"do": "detach"})
        held = said.get("let go")
        return held if isinstance(held, int) else 0

    def stop(self, *, seconds: float = _UNWINDING) -> bool:
        """Asks the run to stop, as closing the interface holding it does.

        Args:
          seconds: How long to wait for it to go.

        Returns:
          Whether it has gone.
        """
        if not self.asked({"do": "stop"}).get("ok"):
            return not self.alive
        return self._gone(seconds)

    def kill(self, *, seconds: float = _UNWINDING) -> bool:
        """Ends the process holding this run, whatever it was doing.

        The last thing there is to do about a daemon: whatever the run was in the middle of
        is what a killed process is in the middle of.

        Args:
          seconds: How long to wait for it to go before saying it has not.

        Returns:
          Whether it has gone.
        """
        import signal

        with contextlib.suppress(OSError):
            os.kill(self.pid, signal.SIGTERM)
        if not self._gone(seconds):
            with contextlib.suppress(OSError):
                os.kill(self.pid, signal.SIGKILL)
            self._gone(_UNWINDING)
        gone = not self.alive
        if gone:
            for name in (where.SOCKET, where.RECORD):
                with contextlib.suppress(OSError):
                    (self.at / name).unlink()
        return gone

    def _gone(self, seconds: float) -> bool:
        """Waits for the process holding this run to go.

        Args:
          seconds: How long to wait.

        Returns:
          Whether it has gone.
        """
        until = time.monotonic() + seconds
        while time.monotonic() < until:
            if not self.alive:
                return True
            time.sleep(_TICK)
        return not self.alive

    def asked(self, said: dict[str, Any]) -> dict[str, Any]:
        """Puts one question to the run, and reads the answer.

        Args:
          said: What to ask.

        Returns:
          What it answered, and nothing at all where it would not answer.
        """
        try:
            one = attaches(self.at)
        except OSError:
            return {}
        try:
            one.settimeout(_ANSWERING)
            one.sendall(spoken(CONTROL, said))
            frames = Frames()
            while True:
                read = one.recv(1 << 16)
                if not read:
                    return {}
                for kind, payload in frames.feed(read):
                    if kind == CONTROL:
                        return asked(payload)
        except (OSError, ValueError):
            return {}
        finally:
            with contextlib.suppress(OSError):
                one.close()

    def _written(self) -> dict[str, Any]:
        """What is written down beside its socket about it."""
        return dict(where.held(self.at))


def running(workspace: str | os.PathLike[str] | None = None) -> Daemon | None:
    """The daemon holding a run in one workspace, if one is.

    Args:
      workspace: The project directory, or None for wherever humanize is being run.

    Returns:
      It, or None where nothing is being held there. A directory left behind by a daemon
      whose process has gone reads as nothing being held: a socket file outlives the process
      that bound it.
    """
    return _read(where.at(workspace))


def daemons() -> list[Daemon]:
    """Every run being held on this machine, oldest first."""
    found: list[Daemon] = []
    with contextlib.suppress(OSError):
        for one in sorted(where.under().iterdir()):
            if not one.is_dir():
                continue
            held = _read(one)
            if held is not None:
                found.append(held)
    return sorted(found, key=lambda one: one.started)


def start(
    opens: Callable[[Held], object],
    workspace: str | os.PathLike[str] | None = None,
    *,
    columns: int = 0,
    rows: int = 0,
    seconds: float = _PATIENCE,
) -> Daemon:
    """Puts a run where a terminal closing cannot end it, and comes back once it is listening.

    A fork so that whatever asked for it is not waiting on it, `setsid` so that the terminal
    which started it is no longer its own -- which is what keeps a hangup from reaching it --
    and a second fork so that it can never take a controlling terminal again. That is what
    `nohup` and `screen` are underneath, and none of the three is run here to get it.

    Args:
      opens: What opens the run, called in the detached process with the held run, and
        returning when the run is over.
      workspace: The project directory, or None for wherever humanize is being run.
      columns: How wide the terminal it draws for is until one arrives, or 0 for this one's.
      rows: How tall, or 0 for this one's.
      seconds: How long to wait for it to bind its socket.

    Returns:
      The daemon, listening.

    Raises:
      OSError: If it could not be started, or did not come up in the time it was given --
        which is where a daemon of this workspace is already running.
    """
    at = where.at(workspace)
    already = _read(at)
    if already is not None:
        raise OSError(
            errno.EADDRINUSE, f"a run is already being held in {already.workspace}"
        )
    wide, tall = _terminal(columns, rows)
    reading, telling = os.pipe()
    # Before the fork: what this process has written and not yet flushed is buffered in it,
    # and a fork copies the buffer -- so anything left in one would be written twice, once
    # by each of them.
    for stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(Exception):
            stream.flush()
    middle = os.fork()
    if middle == 0:  # pragma: no cover -- the child never comes back to be covered
        os.close(reading)
        _detaches(opens, at, wide, tall, telling)
    os.close(telling)
    try:
        _waits(reading, seconds)
    finally:
        with contextlib.suppress(OSError):
            os.close(reading)
        # The middle process has already gone: it forked the one that holds the run and
        # exited, so that the run's own parent is whatever adopts it rather than this.
        with contextlib.suppress(ChildProcessError):
            os.waitpid(middle, 0)
    held = _read(at)
    if held is None:
        raise OSError(f"the run in {at} did not come up")
    return held


def _detaches(
    opens: Callable[[Held], object],
    at: Path,
    columns: int,
    rows: int,
    telling: int,
) -> None:  # pragma: no cover -- runs only in the forked child
    """The two forks and the session, and then the run, in the process that holds it."""
    status = 0
    try:
        with contextlib.suppress(OSError):
            os.setsid()
        if os.fork() != 0:
            os._exit(0)  # the middle process, which must unwind nothing at all
        # A hangup cannot reach a process with no controlling terminal, and this one has
        # none; refusing it as well costs nothing and says what is meant.
        import signal

        with contextlib.suppress(OSError, ValueError):
            signal.signal(signal.SIGHUP, signal.SIG_IGN)
        hosts(opens, at, columns=columns, rows=rows, telling=telling)
    except BaseException as why:  # noqa: BLE001 -- the last frame of a process nobody reads
        status = 1
        # Said back down the pipe as well as written down: whoever asked for a daemon is
        # still waiting, and `could not be held` on its own is a line nobody can act on.
        with contextlib.suppress(OSError):
            os.write(telling, f"the run could not be held: {why}\n".encode())
            os.close(telling)
        with contextlib.suppress(OSError):
            at.mkdir(parents=True, exist_ok=True)
            logged(at, "this run could not be held apart from the terminal")
    finally:
        with contextlib.suppress(Exception):
            sys.stdout.flush()
            sys.stderr.flush()
        os._exit(status)  # nothing of this process is anybody's to unwind


def _waits(reading: int, seconds: float) -> None:
    """Waits for the detached process to say it is listening, or for the time to run out."""
    import selectors

    selector = selectors.DefaultSelector()
    selector.register(reading, selectors.EVENT_READ)
    try:
        until = time.monotonic() + seconds
        while time.monotonic() < until:
            if not selector.select(0.1):
                continue
            said = os.read(reading, 1 << 12)
            if not said or said.startswith(b"listening"):
                return
            raise OSError(said.decode(errors="replace").strip())
    finally:
        selector.close()


def _terminal(columns: int, rows: int) -> tuple[int, int]:
    """How big to draw for, which is this terminal unless somebody said otherwise."""
    if columns and rows:
        return columns, rows
    wide, tall = size()
    return columns or wide, rows or tall


def _read(at: Path) -> Daemon | None:
    """The daemon whose directory this is, or None where nothing is being held there."""
    said = where.held(at)
    if not said:
        return None
    pid = said.get("pid")
    if not isinstance(pid, int):
        return None
    if not _listening(at):
        return None
    return Daemon(
        at=at,
        workspace=str(said.get("workspace") or ""),
        pid=pid,
        started=str(said.get("started") or ""),
    )


def _listening(at: Path) -> bool:
    """Whether something is actually listening on the socket there.

    A process of that number may be there and be something else entirely -- numbers come
    round -- so the note beside the socket is not the whole of the answer.
    """
    one = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        one.settimeout(_ANSWERS_AT_ONCE)
        with where.reached(at) as reaching:
            one.connect(reaching)
    except OSError:
        return False
    finally:
        one.close()
    return True

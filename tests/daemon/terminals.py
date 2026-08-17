"""A terminal of this suite's own, for reading a run that is being held.

A run is held on a pseudoterminal and read by a process that has one of its own, so a test
that reads one needs a terminal to be. This is that: a pseudoterminal, a child that reads the
run on it, and the two things a test does with the pair -- type at it, and see what came back.
"""

from __future__ import annotations

import contextlib
import os
import pty
import select
import signal
import time
from typing import TYPE_CHECKING

from hmz.daemon.serve import sized

if TYPE_CHECKING:
    from pathlib import Path

#: How big a terminal of this suite's own is. Wide enough that what is being read is not the
#: width somebody is running the suite at.
COLUMNS, ROWS = 100, 30

#: How long a read waits for nothing before deciding nothing is coming.
_QUIET = 0.2


class Terminal:
    """One terminal reading one held run, and the process reading it."""

    def __init__(self, at: Path, columns: int = COLUMNS, rows: int = ROWS) -> None:
        """Opens a pseudoterminal and starts a process reading the run on it.

        Args:
          at: The daemon's own directory.
          columns: How wide this terminal is.
          rows: How tall.
        """
        self.fd, slave = pty.openpty()
        sized(self.fd, columns, rows)
        self.pid = os.fork()
        if self.pid == 0:  # pragma: no cover -- the reading process never comes back
            os.close(self.fd)
            os.setsid()
            for one in (0, 1, 2):
                os.dup2(slave, one)
            if slave > 2:
                os.close(slave)
            from hmz.daemon.attach import attaches, reads

            status = 0
            try:
                reads(attaches(at))
            except BaseException:  # noqa: BLE001 -- a forked child reports by its status
                status = 3
            os._exit(status)
        os.close(slave)

    def types(self, what: str) -> None:
        """Types at this terminal, as somebody at it would."""
        os.write(self.fd, what.encode())

    def sized(self, columns: int, rows: int) -> None:
        """Says this terminal has been resized, as a window being dragged would."""
        sized(self.fd, columns, rows)
        os.kill(self.pid, signal.SIGWINCH)

    def drew(self, seconds: float = 3.0) -> bytes:
        """Everything the run has drawn on this terminal since it was last looked at."""
        got = b""
        until = time.monotonic() + seconds
        while time.monotonic() < until:
            ready, _, _ = select.select([self.fd], [], [], _QUIET)
            if not ready:
                if got:
                    break
                continue
            try:
                read = os.read(self.fd, 1 << 16)
            except OSError:
                break
            if not read:
                break
            got += read
        return got

    def until(self, said: bytes, seconds: float = 6.0) -> bytes:
        """Everything drawn up to and including the first sight of something."""
        got = b""
        until = time.monotonic() + seconds
        while time.monotonic() < until and said not in got:
            got += self.drew(0.4)
        return got

    @property
    def gone(self) -> bool:
        """Whether the process reading the run on this terminal has finished."""
        try:
            return os.waitpid(self.pid, os.WNOHANG)[0] == self.pid
        except ChildProcessError:
            return True

    def close(self) -> None:
        """Takes the terminal away, however far the test got."""
        with contextlib.suppress(OSError):
            os.kill(self.pid, signal.SIGKILL)
        with contextlib.suppress(OSError, ChildProcessError):
            os.waitpid(self.pid, 0)
        with contextlib.suppress(OSError):
            os.close(self.fd)

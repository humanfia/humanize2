"""A stand-in for the interface, for the tests that are about holding a run rather than one.

What a daemon holds is a callable that opens a run and returns when it is over. This is the
smallest thing of that shape: it draws a line, says back whatever is typed at it, lets go of
the terminals when it is told to, and returns when it is told to stop. Nothing here is the
terminal interface, which is the point -- what is being checked is the holding.
"""

from __future__ import annotations

import contextlib
import os
import select
import termios
import threading
import tty
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hmz.daemon import Held

#: How long the stand-in waits on its own terminal before looking at whether it is to stop.
_TICK = 0.05

#: How long it goes on for at the outside, so that a test which lost its daemon is a test
#: that fails rather than a process left behind.
_LONGEST = 120.0


def says(what: str) -> None:
    """Draws one line on whatever terminal this run is being drawn on.

    Onto the descriptor rather than through `sys.stdout`, which is what a terminal is: a
    suite that has taken the standard streams away from the process running it has not taken
    away the terminal a held run draws on.
    """
    os.write(1, f"{what}\r\n".encode())


def opens(session: Held) -> None:
    """Opens the stand-in, and returns when it is told to stop.

    Args:
      session: What is holding this run.
    """
    # The mode a full-screen program puts its terminal in, which is what the interface this
    # stands in for does: without it the line discipline is doing the reading, and a paste
    # longer than one canonical line never arrives whole.
    with contextlib.suppress(termios.error, OSError):
        tty.setraw(0)
    stop = threading.Event()
    session.redrawn(lambda: says("redrawn"))
    session.stopping(stop.set)
    session.says(lambda: {"kind": "a stand-in"})
    says("open")
    held = b""
    over = threading.Event()
    threading.Timer(_LONGEST, over.set).start()
    while not stop.is_set() and not over.is_set():
        ready, _, _ = select.select([0], [], [], _TICK)
        if not ready:
            continue
        try:
            read = os.read(0, 4096)
        except OSError:
            break
        if not read:
            break
        held += read
        while (cut := _cut(held)) is not None:
            line, held = cut
            if line == "quit":
                return
            if line == "detach":
                says(f"let go of {session.detach()}")
                continue
            if line == "reading":
                says(f"reading {session.attached}")
                continue
            says(f"said {line}")
    return


def _cut(held: bytes) -> tuple[str, bytes] | None:
    """The first whole line in what has been typed, and whatever came after it."""
    for end in (b"\r", b"\n"):
        if end in held:
            line, _, rest = held.partition(end)
            return line.decode(errors="replace").strip(), rest
    return None

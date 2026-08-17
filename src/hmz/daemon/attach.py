"""This terminal, reading a run somebody else is holding.

Nothing of the interface is here. What is here is a terminal put in the mode a full-screen
program needs and then got out of the way of: every byte typed goes to the run, every byte the
run draws comes back, and a terminal that changes size says so. The interface on the other end
is drawing on a terminal like any other and never finds out which one.

Putting the terminal back is this side's job and this side's alone. A run that has let go says
so and goes on running, so nothing on the other end is ever going to write the sequences that
leave the alternate screen and show the cursor again -- which is why they are written here,
whichever way the reading ended.
"""

from __future__ import annotations

import contextlib
import errno
import os
import selectors
import signal
import socket
import termios
import tty
from pathlib import Path
from typing import TYPE_CHECKING

from hmz.daemon import where
from hmz.daemon.proto import GONE, HELLO, INPUT, OUTPUT, RESIZE, Frames, frame, spoken

if TYPE_CHECKING:
    from collections.abc import Generator
    from types import FrameType

__all__ = ["attaches", "reads", "size"]

#: How much is read at a time, off the terminal and off the socket alike.
_READ = 1 << 16

#: What a terminal that has not been told its own size is drawn for.
_WIDE, _TALL = 80, 24

#: The terminal, which is the two descriptors a terminal is rather than the two streams
#: Python wraps them in: what is being carried is bytes, and something else may have put a
#: stream of its own where `sys.stdout` was without the terminal having moved.
_IN, _OUT = 0, 1

#: What a terminal is put back to, whichever way the reading ended: out of the alternate
#: screen, cursor shown, mouse reporting off, bracketed paste off, focus reporting off, the
#: keyboard protocol popped and line wrapping back on. The run writes these itself when it
#: closes; a run that has only let go of this terminal never will, and a terminal left in a
#: full-screen program's modes is a shell nobody can use.
_BACK = (
    b"\x1b[<u"  # pop whatever keyboard protocol was pushed
    b"\x1b[?2004l"  # bracketed paste off
    b"\x1b[?1004l"  # focus reporting off
    b"\x1b[?1000l\x1b[?1003l\x1b[?1015l\x1b[?1006l\x1b[?1016l"  # mouse reporting off
    b"\x1b[?2048l"  # in-band resize reports off
    b"\x1b[?7h"  # line wrapping back on
    b"\x1b[?25h"  # cursor shown
    b"\x1b[?1049l"  # and out of the alternate screen, last
)


def attaches(at: os.PathLike[str] | str) -> socket.socket:
    """Opens the socket a run is reached through.

    Args:
      at: The daemon's own directory.

    Returns:
      The socket, connected.

    Raises:
      OSError: If nothing is listening there.
    """
    one = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        with where.reached(Path(at)) as reaching:
            one.connect(reaching)
    except OSError:
        one.close()
        raise
    return one


def reads(one: socket.socket) -> int:
    """Reads a run from this terminal, until it ends or lets go.

    Args:
      one: The socket the run is reached through, already connected.

    Returns:
      Zero, once the run has ended or has let go of this terminal, or one where there was
      nothing to say hello to.
    """
    columns, rows = size()
    try:
        one.sendall(spoken(HELLO, {"columns": columns, "rows": rows}))
    except OSError:
        with contextlib.suppress(OSError):
            one.close()
        return 1
    with _raw():
        said = _pumps(one)
    # After the terminal has been put back, and not before: a line drawn on the alternate
    # screen is a line thrown away with it, and why this terminal was let go of is the one
    # thing somebody is looking at when it happens.
    if said:
        _says(said)
    return 0


def _pumps(one: socket.socket) -> str:
    """Carries the keys one way and the screen the other, until either end goes.

    Args:
      one: The socket the run is reached through.

    Returns:
      Why the reading ended, as the run said it, and "" where it did not say -- a socket that
      went, or a terminal that did.
    """
    woken_r, woken_w = os.pipe()
    os.set_blocking(woken_w, False)
    os.set_blocking(woken_r, False)
    was = signal.set_wakeup_fd(woken_w)
    resized = signal.signal(signal.SIGWINCH, _noticed)
    frames = Frames()
    reading = one.fileno()
    selector = selectors.DefaultSelector()
    selector.register(_IN, selectors.EVENT_READ)
    selector.register(one, selectors.EVENT_READ)
    selector.register(woken_r, selectors.EVENT_READ)
    said = ""
    try:
        while True:
            for key, _ in selector.select():
                if key.fd == woken_r:
                    # A signal arrived: the only one hooked is the terminal changing size.
                    with contextlib.suppress(OSError):
                        os.read(woken_r, _READ)
                    columns, rows = size()
                    one.sendall(spoken(RESIZE, {"columns": columns, "rows": rows}))
                elif key.fd == reading:
                    read = _taken(one)
                    if read is None:
                        continue  # nothing had arrived after all
                    if not read:
                        return said  # the run has gone
                    for kind, payload in frames.feed(read):
                        if kind == OUTPUT:
                            _draws(payload)
                        elif kind == GONE:
                            return payload.decode(errors="replace")
                else:
                    typed = _taken_from(_IN)
                    if not typed:
                        return said
                    one.sendall(frame(INPUT, typed))
    except (OSError, ValueError):
        # The run has gone, this terminal has, or what came off the socket is not this
        # protocol: either way there is nothing left to read.
        return said
    finally:
        signal.set_wakeup_fd(was)
        signal.signal(signal.SIGWINCH, resized)
        selector.close()
        for fd in (woken_r, woken_w):
            with contextlib.suppress(OSError):
                os.close(fd)
        with contextlib.suppress(OSError):
            one.close()


def _noticed(_signal: int, _frame: FrameType | None) -> None:
    """Notices that this terminal has changed size, which the wakeup descriptor carries."""


def _taken(one: socket.socket) -> bytes | None:
    """What has arrived off the socket.

    Args:
      one: The socket.

    Returns:
      What was read, or nothing at all for a run that has gone -- and None for a read that
      was interrupted or had nothing behind it, which is neither.
    """
    try:
        return one.recv(_READ)
    except OSError as why:
        if why.errno in (errno.EAGAIN, errno.EWOULDBLOCK, errno.EINTR):
            return None
        return b""


def _taken_from(fd: int) -> bytes:
    """What has been typed, and nothing at all for a terminal that has gone."""
    try:
        return os.read(fd, _READ)
    except OSError:
        return b""


def _draws(payload: bytes) -> None:
    """Puts what the run drew onto this terminal, whole."""
    while payload:
        try:
            written = os.write(_OUT, payload)
        except OSError as why:
            if why.errno in (errno.EAGAIN, errno.EWOULDBLOCK, errno.EINTR):
                continue
            return
        payload = payload[written:]


def _says(what: str) -> None:
    """Says why the reading ended, on the terminal that is now back to being a terminal."""
    with contextlib.suppress(OSError):
        os.write(_OUT, f"{what}\r\n".encode())


def size() -> tuple[int, int]:
    """How big this terminal is, as the run is to draw for it.

    Returns:
      The columns and the rows. A terminal that has not been told its own size reports zero
      of both, which is not a terminal one column wide: it is one that has not said, and what
      a full-screen program does about that is assume the ordinary eighty by twenty-four.
    """
    try:
        size = os.get_terminal_size(_OUT)
    except OSError:
        return _WIDE, _TALL
    return size.columns or _WIDE, size.lines or _TALL


@contextlib.contextmanager
def _raw() -> Generator[None]:
    """Puts this terminal into the mode a full-screen program needs, and puts it back.

    Raw, which is what every terminal multiplexer does: the run on the other end is doing its
    own echoing, its own line editing and its own interrupt handling, and a terminal that did
    any of them too would be doing them twice.

    Yields:
      Nothing.
    """
    kept = None
    with contextlib.suppress(termios.error, OSError):
        kept = termios.tcgetattr(_IN)
        tty.setraw(_IN)
    try:
        yield
    finally:
        if kept is not None:
            with contextlib.suppress(termios.error, OSError):
                termios.tcsetattr(_IN, termios.TCSADRAIN, kept)
        with contextlib.suppress(OSError):
            os.write(_OUT, _BACK)

"""The run being held, and the terminals reading it, driven in this process.

`tests/daemon/test_opening.py` and `terminals.py` drive the whole thing as it really works: a
double fork, a run in the detached process, a reader in a process of its own. Which is the
right way to check that a run outlives the terminal that started it, and the wrong way to
check what the holding itself does with each thing that can arrive -- every branch of it is
two processes away from the assertion, and the one that matters most is the one where a
terminal misbehaves.

So this drives `Held` directly. It is an ordinary object: a pseudoterminal the run draws on,
a socket terminals arrive at, and a thread carrying between them. The run here is the test
writing on the far side of the pseudoterminal, and the terminals are sockets the test opens.

The socket is bound by a bare name from inside its own directory: a Unix socket address holds
about a hundred bytes whole, 104 of them on macOS, and the directory pytest hands out is
longer than that.
"""

from __future__ import annotations

import contextlib
import json
import os
import pty
import socket
import time
import tty
from typing import TYPE_CHECKING, Any

import pytest

from hmz.daemon import where
from hmz.daemon.proto import (
    CONTROL,
    GONE,
    HELLO,
    INPUT,
    OUTPUT,
    RESIZE,
    Frames,
    frame,
    spoken,
)
from hmz.daemon.serve import Held

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from pathlib import Path

#: How long a test waits for something that should already be on its way.
PATIENCE = 10.0

#: A terminal of this suite's own, wide enough not to be the width the suite is being run at.
COLUMNS, ROWS = 100, 30


def until(what: Callable[[], bool], seconds: float = PATIENCE) -> bool:
    """Waits for something another thread is doing, rather than for a number of goes.

    The loop carrying a run is a thread, so everything a test asks of it lands a moment
    later. A count of iterations is a wait that is nothing at all on a fast machine, which
    is a test that passes here and fails on whatever CI is running today.

    Args:
      what: The question, asked again until it is yes.
      seconds: How long to go on asking.

    Returns:
      Whether it became true in the time it was given.
    """
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if what():
            return True
        time.sleep(0.01)
    return what()


class Terminal:
    """One socket on the other end of a held run, and the frames that came off it."""

    def __init__(self, one: socket.socket) -> None:
        self.one = one
        self._frames = Frames()
        self._held: list[tuple[bytes, bytes]] = []

    def says(self, kind: bytes, said: dict[str, Any] | None = None) -> None:
        """Sends one frame, as a terminal or as a question about the run."""
        self.one.sendall(spoken(kind, said) if said is not None else frame(kind))

    def types(self, typed: bytes) -> None:
        self.one.sendall(frame(INPUT, typed))

    def hears(self, kind: bytes) -> bytes:
        """Waits for the next frame of that kind, and gives back what it carried.

        Raises:
            AssertionError: If the run said nothing of that kind before it went quiet.
        """
        while True:
            for at, (said, payload) in enumerate(self._held):
                if said == kind:
                    del self._held[: at + 1]
                    return payload
            self.one.settimeout(PATIENCE)
            read = self.one.recv(1 << 16)
            if not read:
                raise AssertionError(f"the run went without ever saying {kind!r}")
            self._held.extend(self._frames.feed(read))

    def quiet(self, seconds: float = 0.3) -> bool:
        """Whether nothing more arrives, for a test about something not being sent.

        A socket that was closed is not a socket that stayed quiet, and reading one as the
        other is how a test about something not being sent passes for the wrong reason.

        Raises:
            AssertionError: If the run let go of this terminal instead of saying nothing.
        """
        self.one.settimeout(seconds)
        try:
            read = self.one.recv(1 << 16)
        except TimeoutError:
            return True
        if not read:
            raise AssertionError(
                "the run let go of this terminal rather than said nothing"
            )
        self._held.extend(self._frames.feed(read))
        return False

    def close(self) -> None:
        with contextlib.suppress(OSError):
            self.one.close()


class Holding:
    """A run being held here, with both sides of it reachable from the test."""

    def __init__(self, held: Held, run: int, at: Path) -> None:
        self.held = held
        self.run = run
        self.at = at
        self._opened: list[Terminal] = []
        self._joined = 0

    def draws(self, drawn: bytes) -> None:
        """What the run draws on its own terminal."""
        os.write(self.run, drawn)

    def read(self, how_many: int = 1 << 16) -> bytes:
        """What arrived in the run's own terminal, which is what somebody typed."""
        os.set_blocking(self.run, False)
        try:
            return os.read(self.run, how_many)
        except BlockingIOError:
            return b""
        finally:
            os.set_blocking(self.run, True)

    def terminal(self, *, joining: bool = True) -> Terminal:
        """A terminal arriving to read this run, closed however the test ends."""
        one = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        one.connect(where.SOCKET)
        held = Terminal(one)
        self._opened.append(held)
        if joining:
            self._joined += 1
            held.says(HELLO, {"columns": COLUMNS, "rows": ROWS})
            # Waited for here rather than in each test: everything a test does after this
            # is about a terminal that is reading, and a HELLO still in flight is not one.
            assert until(lambda: self.held.attached == self._joined), (
                "the terminal never joined the run"
            )
        return held

    def close(self) -> None:
        for one in self._opened:
            one.close()


@pytest.fixture
def holding(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Holding]:
    """A run held on a pseudoterminal, with the socket terminals arrive at already bound."""
    monkeypatch.chdir(tmp_path)
    controller, follower = pty.openpty()
    # The side the run draws on, in the modes a full-screen program puts it in -- without
    # which the terminal echoes what is typed straight back out as though the run drew it.
    tty.setraw(follower)
    listening = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listening.bind(where.SOCKET)
    listening.listen(8)
    where.wrote(tmp_path, {"pid": os.getpid(), "workspace": str(tmp_path)})
    held = Held(controller, listening, tmp_path)
    one = Holding(held, follower, tmp_path)
    held.start()
    try:
        yield one
    finally:
        one.close()
        held.close()
        for fd in (follower, controller):
            with contextlib.suppress(OSError):
                os.close(fd)


# ------------------------------------------------------ carrying it both ways


@pytest.mark.timeout(60)
def test_what_the_run_draws_reaches_the_terminal_reading_it(holding: Holding) -> None:
    terminal = holding.terminal()

    holding.draws(b"a screen")

    assert terminal.hears(OUTPUT) == b"a screen"


@pytest.mark.timeout(60)
def test_what_is_typed_at_a_terminal_reaches_the_run(holding: Holding) -> None:
    terminal = holding.terminal()
    reached = bytearray()

    terminal.types(b"typed")

    def arrived() -> bool:
        reached.extend(holding.read())
        return bytes(reached) == b"typed"

    assert until(arrived), f"what was typed reached the run as {bytes(reached)!r}"


@pytest.mark.timeout(60)
def test_every_terminal_reading_gets_what_the_run_drew(holding: Holding) -> None:
    """A run is read from more than one terminal at once, and both see the same screen."""
    first, second = holding.terminal(), holding.terminal()

    holding.draws(b"a screen")

    assert first.hears(OUTPUT) == b"a screen"
    assert second.hears(OUTPUT) == b"a screen"


# ------------------------------------------------- what was drawn before anybody read


@pytest.mark.timeout(60)
def test_a_terminal_arriving_at_a_run_that_has_not_moved_is_not_shown_a_blank_screen(
    holding: Holding,
) -> None:
    """What it drew before anybody was reading is kept for whoever arrives first."""
    holding.draws(b"drawn before anybody arrived")

    terminal = holding.terminal()

    assert terminal.hears(OUTPUT) == b"drawn before anybody arrived"


@pytest.mark.timeout(60)
def test_what_was_kept_is_given_to_the_first_terminal_alone(holding: Holding) -> None:
    """The second is a run already being read, so it is drawn again rather than replayed."""
    holding.draws(b"drawn before anybody arrived")
    first = holding.terminal()
    assert first.hears(OUTPUT) == b"drawn before anybody arrived"

    second = holding.terminal()

    assert second.quiet()


# ----------------------------------------------------------- how many are reading


@pytest.mark.timeout(60)
def test_a_run_nobody_has_arrived_at_is_read_by_nobody(holding: Holding) -> None:
    assert holding.held.attached == 0


@pytest.mark.timeout(60)
def test_a_terminal_that_has_said_hello_is_one_of_the_ones_reading(
    holding: Holding,
) -> None:
    holding.terminal()

    assert holding.held.attached == 1


@pytest.mark.timeout(60)
def test_a_socket_that_has_not_said_what_it_is_for_is_not_a_terminal_reading(
    holding: Holding,
) -> None:
    """One is on the list from the moment it connects, and says what it is for afterwards."""
    holding.terminal(joining=False)

    assert holding.held.attached == 0


# -------------------------------------------------------------- letting go


@pytest.mark.timeout(60)
def test_letting_go_says_why_and_leaves_the_run_running(holding: Holding) -> None:
    terminal = holding.terminal()
    holding.draws(b"a screen")
    terminal.hears(OUTPUT)

    assert holding.held.detach() == 1

    assert terminal.hears(GONE)
    assert holding.held.attached == 0


@pytest.mark.timeout(60)
def test_letting_go_of_a_run_nobody_is_reading_lets_go_of_none(
    holding: Holding,
) -> None:
    assert holding.held.detach() == 0


@pytest.mark.timeout(60)
def test_a_run_that_is_over_says_so_to_every_terminal(holding: Holding) -> None:
    terminal = holding.terminal()
    holding.draws(b"a screen")
    terminal.hears(OUTPUT)

    holding.held.close("the run is over")

    assert terminal.hears(GONE) == b"the run is over"


@pytest.mark.timeout(60)
def test_a_run_that_is_over_stops_saying_there_is_one_here_to_read(
    holding: Holding,
) -> None:
    """A directory that still says yes is a terminal that connects and then waits forever."""
    holding.held.close()

    assert not (holding.at / where.SOCKET).exists()
    assert not (holding.at / where.RECORD).exists()


# --------------------------------------------------------------- how big it is


@pytest.mark.timeout(60)
def test_the_run_is_drawn_for_the_terminal_that_is_reading_it(holding: Holding) -> None:
    terminal = holding.terminal()
    holding.draws(b"a screen")
    terminal.hears(OUTPUT)

    assert _size(holding.run) == (COLUMNS, ROWS)


@pytest.mark.timeout(60)
def test_a_terminal_dragged_wider_says_so_and_the_run_is_drawn_for_that(
    holding: Holding,
) -> None:
    terminal = holding.terminal()
    holding.draws(b"a screen")
    terminal.hears(OUTPUT)

    terminal.says(RESIZE, {"columns": 133, "rows": 44})
    holding.draws(b"again")
    terminal.hears(OUTPUT)

    assert _size(holding.run) == (133, 44)


@pytest.mark.timeout(60)
@pytest.mark.parametrize(
    "said",
    [
        {"columns": 0, "rows": 0},
        {"columns": 1, "rows": 1},
        {"columns": -5, "rows": 30},
        {"columns": "wide", "rows": 30},
        {},
    ],
)
def test_a_size_that_is_not_a_window_somebody_is_reading_is_refused(
    holding: Holding, said: dict[str, Any]
) -> None:
    """Laying a screen out against no columns is what a full-screen program crashes on."""
    terminal = holding.terminal()
    holding.draws(b"a screen")
    terminal.hears(OUTPUT)
    was = _size(holding.run)

    terminal.says(RESIZE, said)
    holding.draws(b"again")
    terminal.hears(OUTPUT)

    assert _size(holding.run) == was


# ------------------------------------------ a question about the run rather than a terminal


@pytest.mark.timeout(60)
def test_what_is_running_here_is_answered_off_what_was_written_down(
    holding: Holding,
) -> None:
    asking = holding.terminal(joining=False)

    asking.says(CONTROL, {"do": "status"})

    said = json.loads(asking.hears(CONTROL))
    assert said["ok"]
    assert said["workspace"] == str(holding.at)
    assert said["attached"] == 0


@pytest.mark.timeout(60)
def test_whatever_is_holding_the_run_may_add_to_what_is_said_about_it(
    holding: Holding,
) -> None:
    holding.held.says(lambda: {"flow": "rlar", "task": "go"})
    asking = holding.terminal(joining=False)

    asking.says(CONTROL, {"do": "status"})

    said = json.loads(asking.hears(CONTROL))
    assert said["flow"] == "rlar"
    assert said["task"] == "go"


@pytest.mark.timeout(60)
def test_something_that_cannot_say_what_it_is_doing_is_not_a_run_that_cannot_be_asked(
    holding: Holding,
) -> None:
    """A hook that raises is a hook that said nothing, rather than a status that failed."""

    def raising() -> dict[str, Any]:
        raise RuntimeError("not today")

    holding.held.says(raising)
    asking = holding.terminal(joining=False)

    asking.says(CONTROL, {"do": "status"})

    assert json.loads(asking.hears(CONTROL))["ok"]


@pytest.mark.timeout(60)
def test_a_run_may_be_let_go_of_from_outside_it(holding: Holding) -> None:
    reading = holding.terminal()
    holding.draws(b"a screen")
    reading.hears(OUTPUT)
    asking = holding.terminal(joining=False)

    asking.says(CONTROL, {"do": "detach"})

    assert json.loads(asking.hears(CONTROL))["let go"] == 1
    assert reading.hears(GONE)


@pytest.mark.timeout(60)
def test_a_run_nothing_can_stop_says_so_rather_than_saying_it_stopped(
    holding: Holding,
) -> None:
    asking = holding.terminal(joining=False)

    asking.says(CONTROL, {"do": "stop"})

    said = json.loads(asking.hears(CONTROL))
    assert not said["ok"]
    assert "cannot be stopped" in said["why"]


@pytest.mark.timeout(60)
def test_a_run_that_can_be_stopped_is_stopped(holding: Holding) -> None:
    stopped: list[bool] = []
    holding.held.stopping(lambda: stopped.append(True))
    asking = holding.terminal(joining=False)

    asking.says(CONTROL, {"do": "stop"})

    assert json.loads(asking.hears(CONTROL))["ok"]
    assert until(lambda: bool(stopped)), "the run was never asked to stop"


@pytest.mark.timeout(60)
def test_a_request_that_is_not_one_says_so(holding: Holding) -> None:
    asking = holding.terminal(joining=False)

    asking.says(CONTROL, {"do": "juggle"})

    said = json.loads(asking.hears(CONTROL))
    assert not said["ok"]
    assert "no such request" in said["why"]


# --------------------------------------------------------- drawing it again


@pytest.mark.timeout(60)
def test_a_terminal_arriving_has_the_run_draw_itself_again(holding: Holding) -> None:
    """A fresh terminal has none of what was drawn before it, in its own modes and size."""
    drawn: list[bool] = []
    holding.held.redrawn(lambda: drawn.append(True))

    holding.terminal()

    assert until(lambda: bool(drawn)), "the run was never asked to draw itself again"


def _size(fd: int) -> tuple[int, int]:
    """How big the pseudoterminal on this descriptor says it is."""
    import fcntl
    import struct
    import termios

    rows, columns, _, _ = struct.unpack(
        "HHHH", fcntl.ioctl(fd, termios.TIOCGWINSZ, struct.pack("HHHH", 0, 0, 0, 0))
    )
    return columns, rows

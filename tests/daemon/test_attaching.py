"""The pieces a terminal reads a held run with, each on its own.

The whole of `reads` is `test_opening.py`'s and `terminals.py`'s: it puts the terminal it is
called on into raw mode and sits on it until the run lets go, which is a thing to do in a
process built for it rather than to the one running the suite. What is here is everything
underneath that -- what is read off the socket, what is put on the terminal, how big the
terminal says it is, and what each of those does when the thing at the other end has gone.

Every descriptor below is a pipe or a pseudoterminal of the test's own. Nothing touches the
terminal the suite was started from.
"""

from __future__ import annotations

import contextlib
import errno
import json
import os
import pty
import signal
import socket
import struct
import termios
import threading
from typing import TYPE_CHECKING, cast

import pytest

from hmz.daemon import attach
from hmz.daemon.proto import GONE, HELLO, INPUT, OUTPUT, RESIZE, Frames, frame

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator


@pytest.fixture
def pipe() -> Iterator[tuple[int, int]]:
    """A pipe, closed however the test ends, standing in for a terminal."""
    reading, writing = os.pipe()
    try:
        yield reading, writing
    finally:
        for one in (reading, writing):
            with contextlib.suppress(OSError):
                os.close(one)


@pytest.fixture
def paired() -> Iterator[tuple[socket.socket, socket.socket]]:
    """Two ends of a socket, as a run reached through one and the terminal at the other."""
    here, there = socket.socketpair()
    try:
        yield here, there
    finally:
        here.close()
        there.close()


# ------------------------------------------------------ what comes off the socket


def test_what_the_run_drew_is_what_is_read_off_the_socket(
    paired: tuple[socket.socket, socket.socket],
) -> None:
    here, there = paired
    there.sendall(b"a screen")

    assert attach._taken(here) == b"a screen"


def test_a_run_that_has_gone_reads_as_nothing_at_all(
    paired: tuple[socket.socket, socket.socket],
) -> None:
    """Nothing at all and None are different answers: one is over, the other is not yet."""
    here, there = paired
    there.shutdown(socket.SHUT_WR)

    assert attach._taken(here) == b""


def test_a_read_with_nothing_behind_it_yet_is_neither_over_nor_anything(
    paired: tuple[socket.socket, socket.socket],
) -> None:
    here, _ = paired
    here.setblocking(False)

    assert attach._taken(here) is None


def test_a_socket_that_is_not_one_any_more_reads_as_a_run_that_has_gone() -> None:
    here, there = socket.socketpair()
    there.close()
    here.close()

    assert attach._taken(here) == b""


# ------------------------------------------------------- what comes off the terminal


def test_what_was_typed_is_what_is_read_from_the_terminal(
    pipe: tuple[int, int],
) -> None:
    reading, writing = pipe
    os.write(writing, b"typed")

    assert attach._taken_from(reading) == b"typed"


def test_a_terminal_that_has_gone_reads_as_nothing_at_all() -> None:
    reading, writing = os.pipe()
    os.close(reading)
    os.close(writing)

    assert attach._taken_from(reading) == b""


# --------------------------------------------------------- what goes to the terminal


def test_what_the_run_drew_is_put_on_the_terminal_whole(
    pipe: tuple[int, int], monkeypatch: pytest.MonkeyPatch
) -> None:
    reading, writing = pipe
    monkeypatch.setattr(attach, "_OUT", writing)

    attach._draws(b"a screen")

    assert os.read(reading, 64) == b"a screen"


def test_a_terminal_that_has_gone_is_not_something_to_crash_over(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Whoever was reading has closed their laptop; the run itself is still running."""
    reading, writing = os.pipe()
    os.close(reading)
    os.close(writing)
    monkeypatch.setattr(attach, "_OUT", writing)

    attach._draws(b"a screen")  # the absence of a raised error is the whole assertion


def test_why_the_reading_ended_is_said_on_a_line_a_raw_terminal_can_read(
    pipe: tuple[int, int], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A carriage return as well as a newline: the terminal has only just stopped being raw."""
    reading, writing = pipe
    monkeypatch.setattr(attach, "_OUT", writing)

    attach._says("the run is over")

    assert os.read(reading, 64) == b"the run is over\r\n"


def test_saying_why_to_a_terminal_that_has_gone_is_not_something_to_crash_over(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reading, writing = os.pipe()
    os.close(reading)
    os.close(writing)
    monkeypatch.setattr(attach, "_OUT", writing)

    attach._says("the run is over")


# ------------------------------------------------------------- how big it is


def test_the_size_is_the_terminal_s_own(monkeypatch: pytest.MonkeyPatch) -> None:
    controller, follower = pty.openpty()
    try:
        termios.tcgetattr(follower)
        attach.os.set_blocking(follower, True)
        from hmz.daemon.serve import sized

        sized(controller, 101, 37)
        monkeypatch.setattr(attach, "_OUT", follower)

        assert attach.size() == (101, 37)
    finally:
        os.close(follower)
        os.close(controller)


def test_something_that_is_not_a_terminal_is_the_ordinary_eighty_by_twenty_four(
    pipe: tuple[int, int], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A pipe has no size, and a full-screen program still has to draw something."""
    _, writing = pipe
    monkeypatch.setattr(attach, "_OUT", writing)

    assert attach.size() == (attach._WIDE, attach._TALL)


def test_a_terminal_that_has_not_been_told_its_own_size_is_the_ordinary_one_too(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Zero columns is not a terminal one column wide: it is one that has not said."""
    controller, follower = pty.openpty()
    try:
        from hmz.daemon.serve import sized

        sized(controller, 0, 0)
        monkeypatch.setattr(attach, "_OUT", follower)

        assert attach.size() == (attach._WIDE, attach._TALL)
    finally:
        os.close(follower)
        os.close(controller)


# ---------------------------------------------------------- the mode it is put into


def test_a_terminal_is_put_into_raw_and_put_back_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Raw is what every multiplexer does: the run does its own echoing and line editing."""
    controller, follower = pty.openpty()
    try:
        monkeypatch.setattr(attach, "_IN", follower)
        monkeypatch.setattr(attach, "_OUT", follower)
        before = termios.tcgetattr(follower)

        with attach._raw():
            inside = termios.tcgetattr(follower)

        assert inside != before, "the terminal was never put into raw mode"
        assert termios.tcgetattr(follower) == before
    finally:
        os.close(follower)
        os.close(controller)


def test_something_that_is_not_a_terminal_is_left_alone_rather_than_refused(
    pipe: tuple[int, int], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A run read by something other than a terminal is still a run being read."""
    reading, writing = pipe
    monkeypatch.setattr(attach, "_IN", writing)
    monkeypatch.setattr(attach, "_OUT", writing)

    with attach._raw():
        pass

    # And what is put back is the escape that leaves the alternate screen, whether or not
    # there was a mode to restore: the run drew there either way.
    assert os.read(reading, len(attach._BACK)) == attach._BACK


# ----------------------------------------------------------------- reaching one


def test_a_daemon_directory_nothing_is_listening_in_cannot_be_reached(
    tmp_path: object,
) -> None:
    with pytest.raises(OSError, match="No such file or directory"):
        attach.attaches(str(tmp_path))


def test_the_socket_a_run_is_reached_through_is_the_one_in_its_own_directory(
    tmp_path: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    from pathlib import Path

    from hmz.daemon import where

    at = Path(str(tmp_path))
    monkeypatch.chdir(at)
    listening = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listening.bind(where.SOCKET)
    listening.listen(1)
    try:
        reached = attach.attaches(at)
        try:
            held, _ = listening.accept()
            held.sendall(b"hello")
            assert reached.recv(16) == b"hello"
            held.close()
        finally:
            reached.close()
    finally:
        listening.close()


@pytest.mark.parametrize("why", [errno.EINTR, errno.EAGAIN, errno.EWOULDBLOCK])
def test_a_read_that_did_not_happen_is_not_a_run_that_has_gone(why: int) -> None:
    """`EINTR` is a signal arriving mid-read, which is every window resize there is."""

    class Interrupted:
        def recv(self, _size: int) -> bytes:
            raise OSError(why, os.strerror(why))

    assert attach._taken(cast("socket.socket", Interrupted())) is None


def test_a_read_that_failed_for_any_other_reason_is_a_run_that_has_gone() -> None:
    class Broken:
        def recv(self, _size: int) -> bytes:
            raise OSError(errno.ECONNRESET, "Connection reset by peer")

    assert attach._taken(cast("socket.socket", Broken())) == b""


# ------------------------------------------- carrying the keys one way and the screen the other


def _peer(
    there: socket.socket, answering: Callable[[Frames, bytes, bytes], bool]
) -> threading.Thread:
    """The run at the other end, reading frames and answering until it says to stop.

    Args:
      there: The run's end of the socket.
      answering: Called with the reader and each frame; True when it has said its last.

    Returns:
      The thread it is running on, already started.
    """

    def run() -> None:
        frames = Frames()
        while read := there.recv(1 << 16):
            if any(
                answering(frames, kind, payload) for kind, payload in frames.feed(read)
            ):
                break
        there.close()

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread


@pytest.mark.timeout(30)
def test_a_run_that_has_gone_ends_the_reading_without_saying_why(
    paired: tuple[socket.socket, socket.socket],
    pipe: tuple[int, int],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    here, there = paired
    reading, _ = pipe
    monkeypatch.setattr(attach, "_IN", reading)
    there.close()

    assert attach._pumps(here) == ""


@pytest.mark.timeout(30)
def test_a_run_that_lets_go_says_why_and_that_is_what_comes_back(
    paired: tuple[socket.socket, socket.socket],
    pipe: tuple[int, int],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Which is the one thing somebody is looking at when a terminal is let go of."""
    here, there = paired
    reading, _ = pipe
    monkeypatch.setattr(attach, "_IN", reading)
    there.sendall(frame(GONE, b"the run is over"))

    assert attach._pumps(here) == "the run is over"


@pytest.mark.timeout(30)
def test_what_the_run_draws_is_put_on_this_terminal(
    paired: tuple[socket.socket, socket.socket],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    here, there = paired
    typing, _ = os.pipe()
    drawn_r, drawn_w = os.pipe()
    try:
        monkeypatch.setattr(attach, "_IN", typing)
        monkeypatch.setattr(attach, "_OUT", drawn_w)
        there.sendall(frame(OUTPUT, b"a screen") + frame(GONE, b"over"))

        assert attach._pumps(here) == "over"
        assert os.read(drawn_r, 64) == b"a screen"
    finally:
        for one in (typing, drawn_r, drawn_w):
            with contextlib.suppress(OSError):
                os.close(one)


@pytest.mark.timeout(30)
def test_what_is_typed_here_reaches_the_run(
    paired: tuple[socket.socket, socket.socket],
    pipe: tuple[int, int],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    here, there = paired
    reading, writing = pipe
    monkeypatch.setattr(attach, "_IN", reading)
    heard: list[bytes] = []

    def answering(_frames: Frames, kind: bytes, payload: bytes) -> bool:
        if kind == INPUT:
            heard.append(payload)
            there.sendall(frame(GONE, b"over"))
            return True
        return False

    thread = _peer(there, answering)
    os.write(writing, b"typed")

    assert attach._pumps(here) == "over"

    thread.join(timeout=10)
    assert heard == [b"typed"]


@pytest.mark.timeout(30)
def test_a_terminal_that_goes_ends_the_reading(
    paired: tuple[socket.socket, socket.socket],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Whoever was reading has gone; the run itself is somebody else's to end."""
    here, _there = paired
    reading, writing = os.pipe()
    os.close(writing)
    try:
        monkeypatch.setattr(attach, "_IN", reading)

        assert attach._pumps(here) == ""
    finally:
        with contextlib.suppress(OSError):
            os.close(reading)


@pytest.mark.timeout(30)
def test_reading_a_run_says_hello_with_the_size_of_this_terminal(
    paired: tuple[socket.socket, socket.socket],
    pipe: tuple[int, int],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The run draws for the terminal reading it, so it is told how big that is first."""
    here, there = paired
    reading, _ = pipe
    drawn_r, drawn_w = os.pipe()
    try:
        monkeypatch.setattr(attach, "_IN", reading)
        monkeypatch.setattr(attach, "_OUT", drawn_w)
        said: list[tuple[bytes, bytes]] = []

        def answering(_frames: Frames, kind: bytes, payload: bytes) -> bool:
            said.append((kind, payload))
            there.sendall(frame(GONE, b"over"))
            return True

        thread = _peer(there, answering)

        assert attach.reads(here) == 0

        thread.join(timeout=10)
        assert said[0][0] == HELLO
        assert json.loads(said[0][1])["columns"] == attach._WIDE
    finally:
        for one in (drawn_r, drawn_w):
            with contextlib.suppress(OSError):
                os.close(one)


def test_a_run_there_was_nothing_to_say_hello_to_is_one_status_of_our_own() -> None:
    here, there = socket.socketpair()
    here.close()
    there.close()

    assert attach.reads(here) == 1


@pytest.mark.timeout(30)
def test_a_terminal_that_changes_size_tells_the_run_the_new_one(
    paired: tuple[socket.socket, socket.socket],
    pipe: tuple[int, int],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The run draws for the terminal reading it, so a window dragged wider is news."""
    here, there = paired
    reading, _ = pipe
    monkeypatch.setattr(attach, "_IN", reading)
    said: list[tuple[bytes, bytes]] = []

    def answering(_frames: Frames, kind: bytes, payload: bytes) -> bool:
        said.append((kind, payload))
        there.sendall(frame(GONE, b"over"))
        return True

    thread = _peer(there, answering)
    threading.Timer(0.1, os.kill, [os.getpid(), signal.SIGWINCH]).start()

    assert attach._pumps(here) == "over"

    thread.join(timeout=10)
    assert said[0][0] == RESIZE
    assert set(json.loads(said[0][1])) == {"columns", "rows"}


@pytest.mark.timeout(30)
def test_a_socket_carrying_something_else_ends_the_reading_rather_than_raising(
    paired: tuple[socket.socket, socket.socket],
    pipe: tuple[int, int],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Either way there is nothing left to read.

    And a stack trace over a terminal that is still in raw mode is a stack trace nobody
    can read.
    """
    here, there = paired
    reading, _ = pipe
    monkeypatch.setattr(attach, "_IN", reading)
    # A length no frame of this protocol has, which is what something else looks like.
    there.sendall(struct.pack(">cI", b"O", 1 << 30))

    assert attach._pumps(here) == ""

"""A run held where a terminal closing cannot end it, and the terminals that come and go.

Driven end to end, because there is no other way to check it: a daemon is a forked process
with a pseudoterminal, and a terminal reading one is another process with one of its own.
What stands in for the interface is `tests.daemon.runs`, which is the smallest thing of the
shape a daemon holds -- so that what is being checked is the holding rather than the drawing.
"""

from __future__ import annotations

import contextlib
import time
from typing import TYPE_CHECKING

import pytest

from hmz import daemon
from tests.daemon import runs
from tests.daemon.terminals import Terminal

if TYPE_CHECKING:
    from pathlib import Path

#: How long a test waits for something the two processes have to agree on.
_PATIENCE = 8.0


def _until(what: object, seconds: float = _PATIENCE) -> bool:
    """Waits for something to become true, since two processes agree in their own time."""
    assert callable(what)
    until = time.monotonic() + seconds
    while time.monotonic() < until:
        if what():
            return True
        time.sleep(0.05)
    return bool(what())


def test_a_run_is_held_and_found_again(held: daemon.Daemon, workspace: Path) -> None:
    """Which is what `hmz` in this directory does before it opens anything."""
    found = daemon.running()

    assert found is not None
    assert found.pid == held.pid
    assert found.workspace == str(workspace)
    assert [one.pid for one in daemon.daemons()] == [held.pid]


def test_a_directory_nothing_is_held_in_has_no_daemon(tmp_path: Path) -> None:
    assert daemon.running(tmp_path) is None


def test_two_runs_of_one_workspace_are_refused(held: daemon.Daemon) -> None:
    """One daemon per workspace: two flows writing over each other's epic is not two runs."""
    with pytest.raises(OSError, match="already being held"):
        daemon.start(runs.opens)


def test_a_terminal_reads_what_the_run_drew(held: daemon.Daemon) -> None:
    """Including what it drew before anybody was reading, which is the screen it is on."""
    terminal = Terminal(held.at)
    try:
        assert b"open" in terminal.until(b"open")
    finally:
        terminal.close()


def test_what_is_typed_at_a_terminal_reaches_the_run(held: daemon.Daemon) -> None:
    terminal = Terminal(held.at)
    try:
        terminal.until(b"open")
        terminal.types("hello\r")

        assert b"said hello" in terminal.until(b"said hello")
    finally:
        terminal.close()


def test_the_run_is_told_how_many_terminals_are_reading(held: daemon.Daemon) -> None:
    terminal = Terminal(held.at)
    try:
        terminal.until(b"open")
        terminal.types("reading\r")

        assert b"reading 1" in terminal.until(b"reading 1")
    finally:
        terminal.close()


def test_letting_go_of_a_terminal_leaves_the_run_running(held: daemon.Daemon) -> None:
    """Which is the whole point: closing a terminal is not a thing to do to a day's work."""
    terminal = Terminal(held.at)
    try:
        terminal.until(b"open")
        terminal.types("detach\r")

        assert _until(lambda: terminal.gone)
        assert held.alive
        assert held.status()["attached"] == 0
    finally:
        terminal.close()


def test_a_terminal_that_arrives_after_one_left_is_drawn_for_again(
    held: daemon.Daemon,
) -> None:
    """It has none of what was drawn before it: it is a fresh terminal in the shell's modes."""
    first = Terminal(held.at)
    try:
        first.until(b"open")
        first.types("detach\r")
        assert _until(lambda: first.gone)
    finally:
        first.close()
    second = Terminal(held.at)
    try:
        assert b"redrawn" in second.until(b"redrawn")
    finally:
        second.close()


def test_a_terminal_going_away_is_not_the_run_going_away(held: daemon.Daemon) -> None:
    """A laptop closing, an ssh session dropped: the run has not been told to stop."""
    terminal = Terminal(held.at)
    terminal.until(b"open")
    terminal.close()

    assert _until(lambda: held.status().get("attached") == 0)
    assert held.alive


def test_what_is_running_is_answered_without_attaching(held: daemon.Daemon) -> None:
    """A line asking is a line somebody typed instead of opening the interface."""
    said = held.status()

    assert said["pid"] == held.pid
    assert said["attached"] == 0
    # And whatever the run itself says about what it is, which the interface answers with
    # the flows it has running.
    assert said["kind"] == "a stand-in"


def test_letting_go_from_outside_lets_every_terminal_go(held: daemon.Daemon) -> None:
    one, other = Terminal(held.at), Terminal(held.at)
    try:
        one.until(b"open")
        other.until(b"redrawn")
        assert _until(lambda: held.status().get("attached") == 2)

        assert held.detach() == 2

        assert _until(lambda: one.gone and other.gone)
        assert held.alive
    finally:
        one.close()
        other.close()


def test_stopping_ends_the_run_and_takes_its_socket_away(held: daemon.Daemon) -> None:
    at = held.at

    assert held.stop()

    assert not held.alive
    assert daemon.running() is None
    assert not (at / "daemon.sock").exists()


def test_why_a_terminal_was_let_go_of_is_said_where_it_can_be_read(
    held: daemon.Daemon,
) -> None:
    """After the terminal is back: a line drawn on the alternate screen goes with it."""
    terminal = Terminal(held.at)
    try:
        terminal.until(b"open")
        held.detach()
        assert _until(lambda: terminal.gone)

        drawn = terminal.drew(1.0)
        # The sequence that leaves the alternate screen comes first, and the reason after it.
        assert b"\x1b[?1049l" in drawn
        assert drawn.index(b"\x1b[?1049l") < drawn.index(b"detached")
    finally:
        terminal.close()


def test_a_terminal_is_told_the_run_is_over(held: daemon.Daemon) -> None:
    """Rather than reading a closed socket as the machine having gone down."""
    terminal = Terminal(held.at)
    try:
        terminal.until(b"open")
        terminal.types("quit\r")

        assert _until(lambda: terminal.gone)
        assert _until(lambda: not held.alive)
    finally:
        terminal.close()


def test_a_run_that_will_not_go_is_ended_outright(held: daemon.Daemon) -> None:
    """The last thing there is to do about a daemon, which `--kill` asks for."""
    assert held.kill()
    assert not held.alive
    assert daemon.running() is None


def test_a_socket_left_by_a_daemon_that_has_gone_is_not_a_daemon(
    workspace: Path,
) -> None:
    """A socket file outlives the process that bound it, and one nothing answers on hangs."""
    from hmz.daemon import where

    at = where.at(workspace)
    at.mkdir(parents=True)
    (at / where.SOCKET).write_bytes(b"")
    where.wrote(at, {"pid": 2**30, "workspace": str(workspace)})

    assert daemon.running() is None
    assert daemon.daemons() == []


def test_more_than_a_terminal_can_take_at_once_still_reaches_the_run(
    held: daemon.Daemon,
) -> None:
    """A paste is bigger than the pseudoterminal's own buffer, and must not wedge either end.

    The one thread that reads what the run draws is the one that writes what was typed, so a
    write that waited for the run to read would be waiting for a run that is waiting for it.
    """
    terminal = Terminal(held.at)
    try:
        terminal.until(b"open")
        # Far more than a pseudoterminal will take in one go, as one line so that the
        # stand-in says it back whole.
        pasted = "x" * (1 << 16)
        terminal.types(f"{pasted}\r")

        assert b"said " + pasted.encode() in terminal.until(b"said xxx", seconds=20.0)
        # And the run is still being read afterwards, which is what says neither end stuck.
        terminal.types("hello\r")
        assert b"said hello" in terminal.until(b"said hello")
    finally:
        terminal.close()


def test_a_terminal_being_resized_reaches_the_run(held: daemon.Daemon) -> None:
    """A window dragged wider is a screen to lay out again, which only the run can do."""
    terminal = Terminal(held.at)
    try:
        terminal.until(b"open")
        with contextlib.suppress(OSError):
            terminal.sized(120, 40)

        # The stand-in draws nothing for a resize; what is checked is that neither end fell
        # over, which is what a run that is still reading what is typed says.
        terminal.types("hello\r")
        assert b"said hello" in terminal.until(b"said hello")
    finally:
        terminal.close()

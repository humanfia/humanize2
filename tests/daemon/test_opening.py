"""`hmz` with no command: which run it opens, and where that run is held.

A line naming no command reads whichever run is already being held in this directory and
starts one where none is, so that closing the terminal is not what ends a day's work. With no
terminal to hand over to -- output going to a file, this suite driving the interface itself --
it opens in this process exactly as it always did.
"""

from __future__ import annotations

import unittest.mock
from typing import TYPE_CHECKING

import pytest

from hmz import cli, daemon

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def terminal(_humanize_home: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """Says a run may be held here, which this suite otherwise says of nothing.

    Both halves of the question: the suite turns the holding off outright, and there is no
    terminal on either end of a process pytest is capturing. Named after the fixture that
    turned it off, so that this runs after rather than before it.
    """
    monkeypatch.delenv(cli.APART, raising=False)
    monkeypatch.setattr(cli, "_at_a_terminal", lambda: True)


def test_with_no_terminal_the_interface_opens_here(workspace: Path) -> None:
    """Which is what a suite driving it is, and what output going to a file is."""
    with unittest.mock.patch("hmz.tui.Humanize.run") as opened:
        assert cli.main([]) == 0

    assert opened.called
    assert daemon.running() is None


def test_a_line_that_says_not_to_hold_it_opens_here(
    workspace: Path, terminal: None
) -> None:
    """`--no-daemon`, for a machine that would rather the run went with the terminal."""
    with unittest.mock.patch("hmz.tui.Humanize.run") as opened:
        assert cli.main(["--no-daemon"]) == 0

    assert opened.called
    assert daemon.running() is None


def test_the_environment_says_the_same_thing(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """For a scripted install and for this suite, which is what sets it."""
    monkeypatch.setenv(cli.APART, "off")
    assert not cli._apart_is_wanted()

    monkeypatch.setenv(cli.APART, "")
    assert cli._apart_is_wanted()


def test_a_run_already_being_held_here_is_the_one_that_is_read(
    held: daemon.Daemon, terminal: None
) -> None:
    """Rather than a second run of the same directory, which is two flows over one cycle."""
    with unittest.mock.patch.object(daemon.Daemon, "attach", return_value=0) as reading:
        assert cli.main([]) == 0

    assert reading.called
    assert [one.pid for one in daemon.daemons()] == [held.pid]


def test_a_line_that_also_says_what_to_run_is_one_to_correct(
    held: daemon.Daemon, terminal: None, capsys: pytest.CaptureFixture[str]
) -> None:
    """A run that is set up is set up, and two answers is one of them silently losing."""
    with pytest.raises(SystemExit) as stopped:
        cli.main(["-f", "chat"])

    assert stopped.value.code == 2
    assert "already being held here" in capsys.readouterr().err


def test_a_run_that_cannot_be_held_is_opened_here_instead(
    workspace: Path, terminal: None, capsys: pytest.CaptureFixture[str]
) -> None:
    """What is lost is walking away from it, which is not a reason to refuse to open."""
    with (
        unittest.mock.patch.object(
            daemon, "start", side_effect=OSError("no forking here")
        ),
        unittest.mock.patch("hmz.tui.Humanize.run") as opened,
    ):
        assert cli.main([]) == 0

    assert opened.called
    said = capsys.readouterr().err
    assert "cannot be held apart from the terminal" in said
    assert "no forking here" in said


def test_the_interface_is_handed_what_is_holding_the_run(workspace: Path) -> None:
    """Which is the whole of what it is told: how many are reading, and how to let go."""
    made: dict[str, object] = {}

    class Stands:
        def __init__(self, **said: object) -> None:
            made.update(said)

        def run(self) -> None:
            return None

    with unittest.mock.patch("hmz.tui.Humanize", Stands):
        cli.apart("chat", (), None, unittest.mock.Mock(spec=daemon.Held))

    assert made["flow"] == "chat"
    assert made["session"] is not None

"""`hmz daemon` -- the runs being held apart from a terminal, said as arguments.

What is checked here is the line rather than the holding, which `test_held.py` drives end to
end: that a directory nothing is being held in says so, that what is running is answered
without attaching, and that stopping one means what closing the interface means.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hmz import cli, daemon

if TYPE_CHECKING:
    from pathlib import Path


def run(*argv: str) -> int:
    """Runs the command line with the given arguments."""
    return cli.main(["daemon", *argv])


def test_nothing_being_held_says_what_starts_one(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A list with nothing in it and nothing under it reads as a thing that does not work."""
    assert run("list") == 0

    said = capsys.readouterr().out
    assert "no runs are being held" in said
    assert "hmz" in said


def test_a_directory_nothing_is_held_in_is_said_and_not_started(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run("status") == 1
    assert "no run is being held" in capsys.readouterr().err
    assert daemon.running() is None

    assert run("stop") == 1
    assert "no run is being held" in capsys.readouterr().err


def test_what_is_held_is_listed_with_how_many_are_reading(
    held: daemon.Daemon, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run("list") == 0

    said = capsys.readouterr().out
    assert held.workspace in said
    assert f"pid {held.pid}" in said
    assert "0 terminals reading" in said


def test_the_directories_alone_are_what_a_script_reads(
    held: daemon.Daemon, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run("list", "-q") == 0

    assert capsys.readouterr().out.split() == [held.workspace]


def test_what_one_is_doing_is_answered_without_attaching(
    held: daemon.Daemon, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run("status") == 0

    said = capsys.readouterr().out
    assert held.workspace in said
    assert str(held.pid) in said
    assert "0 terminals" in said


def test_one_of_another_directory_is_asked_for_by_name(
    held: daemon.Daemon,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A run is held per directory, so which one is a thing a line may say outright."""
    monkeypatch.chdir(tmp_path)

    assert run("status", held.workspace) == 0
    assert str(held.pid) in capsys.readouterr().out


def test_stopping_means_what_closing_the_interface_means(
    held: daemon.Daemon, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run("stop") == 0

    assert "is over" in capsys.readouterr().out
    assert not held.alive
    assert daemon.running() is None


def test_ending_the_process_is_asked_for_outright(
    held: daemon.Daemon, capsys: pytest.CaptureFixture[str]
) -> None:
    """The last thing there is to do about a daemon, for one that will not go."""
    assert run("stop", "--kill") == 0

    assert "is over" in capsys.readouterr().out
    assert not held.alive


def test_two_runs_of_one_workspace_are_refused_where_it_was_asked_for(
    held: daemon.Daemon, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run("start") == 1
    assert "already being held" in capsys.readouterr().err


def test_a_line_naming_nothing_lists_them(
    held: daemon.Daemon, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run() == 0
    assert held.workspace in capsys.readouterr().out


def test_starting_one_holds_it_without_reading_it(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`hmz daemon start`, for a machine being set up rather than sat at."""
    assert run("start") == 0
    one = daemon.running()
    try:
        assert one is not None
        said = capsys.readouterr().out
        assert str(workspace) in said
        assert "`hmz` reads it" in said
    finally:
        if one is not None:
            one.kill()


def test_an_agent_with_no_flow_is_a_line_to_correct(workspace: Path) -> None:
    with pytest.raises(SystemExit) as stopped:
        run("start", "-a", "claude/model:high")

    assert stopped.value.code == 2
    assert daemon.running() is None

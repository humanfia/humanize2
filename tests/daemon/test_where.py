"""Where one workspace's daemon keeps its socket, and what is written down beside it."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from hmz.daemon import where

if TYPE_CHECKING:
    import pathlib


def test_two_checkouts_of_one_repository_are_two_daemons(
    tmp_path: pathlib.Path,
) -> None:
    """Named after the project and then after the whole path, so a name is not enough."""
    one = tmp_path / "a" / "humanize2"
    other = tmp_path / "b" / "humanize2"
    one.mkdir(parents=True)
    other.mkdir(parents=True)

    assert where.at(one) != where.at(other)
    # And still readable: which project it is is the front of the name.
    assert where.at(one).name.startswith("humanize2-")


def test_the_same_directory_is_the_same_daemon(tmp_path: pathlib.Path) -> None:
    """However it was spelled, since a run is looked for from wherever somebody stands."""
    (tmp_path / "ws").mkdir()

    assert where.at(tmp_path / "ws") == where.at(tmp_path / "ws" / ".")


def test_a_directory_with_nothing_in_it_holds_no_daemon(tmp_path: pathlib.Path) -> None:
    assert where.held(tmp_path) == {}


def test_what_is_written_down_is_read_back(tmp_path: pathlib.Path) -> None:
    where.wrote(tmp_path, {"pid": os.getpid(), "workspace": "/somewhere"})

    assert where.held(tmp_path)["workspace"] == "/somewhere"


def test_a_note_whose_process_has_gone_reads_as_nothing_held(
    tmp_path: pathlib.Path,
) -> None:
    """A socket file outlives the process that bound it, and so does the note beside it."""
    where.wrote(tmp_path, {"pid": 2**30, "workspace": "/somewhere"})

    assert where.held(tmp_path) == {}


def test_a_note_that_is_not_what_this_writes_reads_as_nothing_held(
    tmp_path: pathlib.Path,
) -> None:
    (tmp_path / where.RECORD).write_text("[]", encoding="utf-8")
    assert where.held(tmp_path) == {}

    (tmp_path / where.RECORD).write_text("{{{", encoding="utf-8")
    assert where.held(tmp_path) == {}

    (tmp_path / where.RECORD).write_text(json.dumps({"pid": "one"}), encoding="utf-8")
    assert where.held(tmp_path) == {}


def test_this_process_is_alive_and_a_number_nothing_answers_to_is_not() -> None:
    assert where.alive(os.getpid())
    assert not where.alive(2**30)
    assert not where.alive(0)


def test_only_one_process_holds_a_workspace_at_a_time(tmp_path: pathlib.Path) -> None:
    """Two `hmz` started in the same second must not both find nothing and both bind."""
    import os

    taken = where.holds(tmp_path)
    try:
        with pytest.raises(OSError, match=r"[Rr]esource|[Uu]navailable|locked"):
            where.holds(tmp_path)
    finally:
        os.close(taken)
    # And it is the kernel that drops it, so the next process has it the moment this one lets
    # go -- there is no such thing as one left behind by a machine that was turned off.
    again = where.holds(tmp_path)
    os.close(again)


def test_every_daemon_is_kept_under_humanize_s_own_home(
    tmp_path: pathlib.Path,
) -> None:
    """So that a machine holding more than one has them all in one place to list."""
    assert where.under() == where.at(tmp_path).parent


def _too_long_to_name_whole(tmp_path: pathlib.Path) -> pathlib.Path:
    """A daemon directory whose socket cannot be reached by its whole path.

    One long name rather than a deep tree, so that the address is over the limit whatever the
    temporary directory it is made under happens to be called. Well under NAME_MAX, which is
    255 bytes on every filesystem this runs on.
    """
    spot = tmp_path / ("d" * 128)
    spot.mkdir()
    assert len(str(spot / where.SOCKET).encode()) > where._LONGEST
    return spot


def test_a_socket_named_whole_is_reached_from_wherever_the_caller_stands(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The ordinary case: nothing moves, because the whole path is an address already.

    Which branch is taken is pinned rather than trusted to the directory pytest was given:
    under a long `--basetemp` this path is the long one, and the test would fail as though
    `reached` were wrong instead of covering the branch it is here for. The number it is
    pinned to is this path's own length, which also holds the inclusive edge of the test.
    """
    was = Path.cwd()
    monkeypatch.setattr(where, "_LONGEST", len(str(tmp_path / where.SOCKET).encode()))

    with where.reached(tmp_path) as reaching:
        assert reaching == str(tmp_path / where.SOCKET)
        assert Path.cwd() == was

    assert Path.cwd() == was


def test_a_socket_too_long_to_name_whole_is_reached_from_its_own_directory(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The name alone is short enough, and the process is put back once it has been used."""
    spot = _too_long_to_name_whole(tmp_path)
    standing = tmp_path / "standing"
    standing.mkdir()
    monkeypatch.chdir(standing)

    with where.reached(spot) as reaching:
        assert reaching == where.SOCKET
        assert Path.cwd() == spot

    assert Path.cwd() == standing


def test_a_directory_that_goes_while_the_socket_is_reached_is_written_down(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A process left standing where it was never asked to run must not be left silent.

    For a daemon that is a flow going on somewhere of its own choosing, which is the one thing
    worse than the move itself.
    """
    spot = _too_long_to_name_whole(tmp_path)
    standing = tmp_path / "standing"
    standing.mkdir()
    monkeypatch.chdir(standing)

    with where.reached(spot):
        standing.rmdir()

    said = (spot / where.LOG).read_text(encoding="utf-8")
    assert str(standing) in said
    assert "FileNotFoundError" in said


def test_an_interrupt_the_moment_the_move_is_made_still_puts_it_back(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The window is the breath between the move and the `try` that undoes it."""
    spot = _too_long_to_name_whole(tmp_path)
    standing = tmp_path / "standing"
    standing.mkdir()
    monkeypatch.chdir(standing)

    moves = os.chdir
    moved: list[object] = []

    def interrupted(path: os.PathLike[str] | str) -> None:
        moves(path)
        moved.append(path)
        if len(moved) == 1:
            raise KeyboardInterrupt

    monkeypatch.setattr(os, "chdir", interrupted)

    with pytest.raises(KeyboardInterrupt), where.reached(spot):
        pass

    assert Path.cwd() == standing

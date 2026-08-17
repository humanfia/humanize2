"""Where one workspace's daemon keeps its socket, and what is written down beside it."""

from __future__ import annotations

import json
import os
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

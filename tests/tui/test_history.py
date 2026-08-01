"""What was typed here before, and the walking back through it.

One file holds it all, under humanize' own home, and each line says where it was typed. What is
walked is what was typed here, or everything ever typed anywhere while nothing has been typed
here -- settled when the interface starts, so that the first thing typed here cannot move the
ground under whoever is walking.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from hmz import home
from hmz.tui.history import History

if TYPE_CHECKING:
    import pytest


def _texts(at: Path) -> list[str]:
    """What one history file says was typed, oldest first."""
    return [json.loads(line)["text"] for line in at.read_text().splitlines()]


def test_what_is_typed_is_written_down_with_where_it_was_typed(tmp_path: Path) -> None:
    """One file, under humanize' own home: a project is not a place to keep this.

    Which is why the directory goes on the line -- it is the only thing telling what was
    typed here from what was typed anywhere else.
    """
    history = History(tmp_path)

    history.add("run the tests")

    said = json.loads((home() / "history.jsonl").read_text().strip())
    assert said["text"] == "run the tests"
    assert said["workdir"] == str(tmp_path.resolve())
    assert not (tmp_path / ".humanize").exists()  # and nothing is left in the project


def test_the_arrows_walk_back_through_it_and_forward_again(tmp_path: Path) -> None:
    history = History(tmp_path)
    history.add("first")
    history.add("second")

    assert history.back("") == "second"  # newest first, which is where a walk starts
    assert history.back("") == "first"
    assert history.back("") is None  # and that is the far end of it
    assert history.forward() == "second"


def test_what_was_being_typed_is_given_back_rather_than_lost(tmp_path: Path) -> None:
    """The whole point of keeping it: an arrow pressed by mistake takes nothing with it."""
    history = History(tmp_path)
    history.add("something said before")

    assert history.back("a long prompt, half written") == "something said before"
    assert history.forward() == "a long prompt, half written"
    assert (
        history.forward() is None
    )  # there is nothing nearer than what you were typing


def test_one_thing_said_twice_running_is_one_thing_to_walk_back_to(
    tmp_path: Path,
) -> None:
    history = History(tmp_path)
    history.add("go on")
    history.add("go on")

    assert history.back("") == "go on"
    assert history.back("") is None
    assert _texts(home() / "history.jsonl") == ["go on"]


def test_a_project_with_nothing_typed_in_it_walks_what_was_typed_anywhere(
    tmp_path: Path,
) -> None:
    """A directory nothing has been run in still has a history to walk: everyone else's."""
    History(tmp_path / "elsewhere").add("said somewhere else")
    fresh = tmp_path / "fresh"
    fresh.mkdir()

    assert History(fresh).back("") == "said somewhere else"


def test_a_project_that_has_a_history_of_its_own_walks_that_one(tmp_path: Path) -> None:
    """Which is what it is for: what was said here is what is wanted back here."""
    History(tmp_path / "elsewhere").add("said somewhere else")
    here = tmp_path / "here"
    History(here).add("said here")

    walking = History(here)

    assert walking.back("") == "said here"
    assert walking.back("") is None  # and only what was said here


def test_which_history_is_walked_is_settled_when_it_starts(tmp_path: Path) -> None:
    """The first thing typed here makes this a directory with a history, mid-session.

    What is being walked must not change underneath that: this one goes on walking what it
    started on, and the next one walks what was typed here.
    """
    History(tmp_path / "elsewhere").add("said somewhere else")
    fresh = tmp_path / "fresh"
    fresh.mkdir()
    walking = History(fresh)

    walking.add("said here, first thing")

    assert walking.back("") == "said here, first thing"
    assert walking.back("") == "said somewhere else"  # still walking what it started on

    assert (
        History(fresh).back("") == "said here, first thing"
    )  # and the next one is not
    assert History(fresh).back("") != "said somewhere else"


def test_a_history_nobody_can_write_is_not_a_prompt_to_lose(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Writing it down is worth nothing at the price of what was typed."""
    monkeypatch.setenv("HUMANIZE_HOME", "/proc/nowhere/at/all")
    history = History(Path("/proc/nowhere"))  # nothing may be written under /proc

    history.add("still here")

    assert history.back("") == "still here"

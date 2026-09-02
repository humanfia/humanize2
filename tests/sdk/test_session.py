"""A run being read from a terminal, as whatever is holding the run sees it.

A protocol rather than the thing itself, so that a run held apart from a terminal and a run in
the process somebody typed `hmz` in are one interface: whatever is drawing asks how many
terminals are reading and lets go of them without knowing which of the two it is in. What is
worth checking about such a protocol is the two halves of that promise -- that the thing a
daemon really hands over satisfies it, and that something which only half does is not mistaken
for one.

The socket is bound by a bare name from inside its own directory: a Unix socket address holds
about a hundred bytes whole, 104 of them on macOS, and the directory pytest hands out is
longer than that.
"""

from __future__ import annotations

import os
import socket
from typing import TYPE_CHECKING

import pytest

from hmz.daemon.serve import Held
from hmz.sdk import Session

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


@pytest.fixture
def held(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Held]:
    """What a daemon holds a run in, with both its ends closed again afterwards."""
    monkeypatch.chdir(tmp_path)
    master, worker = os.openpty()
    listening = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listening.bind("daemon.sock")
    listening.listen(1)
    try:
        yield Held(master, listening, tmp_path)
    finally:
        listening.close()
        os.close(worker)
        os.close(master)


def test_what_a_daemon_holds_a_run_in_is_what_the_interface_was_promised(
    held: Held,
) -> None:
    """Which is the whole of the coupling: what is drawing names this and no `Held`."""
    assert isinstance(held, Session)


def test_a_run_nobody_is_reading_says_so_rather_than_saying_nothing(held: Held) -> None:
    assert held.attached == 0


def test_letting_go_of_terminals_nobody_was_reading_through_lets_go_of_none(
    held: Held,
) -> None:
    """Zero where nobody was reading, rather than a refusal: it is asked of every run."""
    assert held.detach() == 0


def test_something_offering_both_halves_is_one_of_these_whatever_it_is() -> None:
    """A protocol is a shape, so a run held some other way would satisfy it too."""

    class Otherwise:
        @property
        def attached(self) -> int:
            return 3

        def detach(self) -> int:
            return 3

    assert isinstance(Otherwise(), Session)


def test_something_offering_neither_half_is_not_one() -> None:
    """Which is what a run in the process somebody typed `hmz` in is handed instead: none."""
    assert not isinstance(object(), Session)


def test_something_offering_only_half_of_it_is_not_one() -> None:
    """Being able to count the terminals is no use where they cannot be let go of."""

    class Counting:
        @property
        def attached(self) -> int:
            return 1

    assert not isinstance(Counting(), Session)

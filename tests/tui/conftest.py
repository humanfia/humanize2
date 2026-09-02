"""What every test of the interface needs: somewhere of its own to be running in.

The interface writes down what is typed at it, in the project it is running in. A test types
things, and the project it would be writing them into is this one.

It also opens set up to run: a flow, and the first agent installed to run it on. What is
installed is whatever is on the developer's own PATH, so a test that did not say would pass
here and fail on a machine with nothing installed, or start a real coding agent on a line
typed as a no-op. Every test therefore starts with nothing installed until it says otherwise.

And two things here fetch from the network on a machine that only asked for the suite to pass:
the flow menu clones what has never been fetched as it opens, and the interface takes what
everything already fetched says now as it starts. Both are taken away here, and the first is
given back to the tests that are about it.
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

import pytest

import hmz.tui.app
import hmz.tui.pick
from hmz.tui.pick import Flows
from hmz.tui.selecting import Transcript

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from textual.pilot import Pilot

    from hmz.tui import Humanize

#: How long anything here waits for the interface to catch up before giving up on it.
PATIENCE = 30.0

#: Catching up on fetches, before the suite takes it away again.
_CATCHES = Flows._catches_up

#: And taking what the ones already here say now, likewise.
_FRESHENS = hmz.tui.app.Humanize._freshens_flows


@pytest.fixture(autouse=True)
def _elsewhere(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Runs the interface somewhere temporary, with no backend, unless the test says."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(hmz.tui.app, "installed", dict)
    monkeypatch.setattr(hmz.tui.app, "installable", dict)
    # The sheets ask too -- which of the backends an account could also be run as are worth
    # ticking is which of them are here -- and a suite that read the developer's own PATH
    # would pass on their machine and fail on the next one.
    monkeypatch.setattr(hmz.tui.pick, "installed", dict)


@pytest.fixture(autouse=True)
def _fetches_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stops anything here reaching a git remote: the menu's first fetch, and the interface's.

    Both, rather than the one the test being written is about: a suite that left either in
    would clone or fetch humanize's own flowverse on every interface it opens, which is a
    suite that is slow on a network and fails without one.
    """

    def nothing(_self: Flows) -> None:
        """What catching up on fetches comes to here, which is nothing at all."""

    def nor_again(_self: Humanize) -> None:
        """Nor does taking what the ones already here say now."""

    monkeypatch.setattr(Flows, "_catches_up", nothing)
    monkeypatch.setattr(hmz.tui.app.Humanize, "_freshens_flows", nor_again)


@pytest.fixture
def catching_up(_fetches_nothing: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """Gives it back, for a test that is about what the menu fetches as it opens.

    Named after the fixture that took it away, so that it is put back after rather than
    before: two fixtures setting one attribute is the order they run in.
    """
    monkeypatch.setattr(Flows, "_catches_up", _CATCHES)


@pytest.fixture
def freshening(_fetches_nothing: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """The same, for a test about what the interface fetches again as it starts."""
    monkeypatch.setattr(hmz.tui.app.Humanize, "_freshens_flows", _FRESHENS)


async def until(ready: Callable[[], bool], driver: Pilot[None]) -> None:
    """Pumps the interface until something is true, or gives up after a while.

    Waited on the clock rather than counted in pumps: a pump can pass in microseconds,
    so counting them is a spin that finishes before the worker thread has done anything.

    Args:
      ready: What is being waited for.
      driver: The interface to keep pumping while waiting.
    """
    deadline = time.monotonic() + PATIENCE
    while not ready() and time.monotonic() < deadline:
        await driver.pause()
        await asyncio.sleep(0.02)


def transcript(app: Humanize) -> str:
    """Everything the interface has shown, as one searchable string.

    Read while the interface is still up: its widgets go with it when it exits.
    """
    return app.query_one("#transcript", Transcript).text

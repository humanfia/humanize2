"""What every test of the interface needs: somewhere of its own to be running in.

The interface writes down what is typed at it, in the project it is running in. A test types
things, and the project it would be writing them into is this one.

It also opens set up to run: a flow, and the first agent installed to run it on. What is
installed is whatever is on the developer's own PATH, so a test that did not say would pass
here and fail on a machine with nothing installed, or start a real coding agent on a line
typed as a no-op. Every test therefore starts with nothing installed until it says otherwise.

And the flow menu fetches what has never been fetched as it opens, which is a clone from the
network on a machine that only asked for the suite to pass. It is taken away here, and given
back to the tests that are about it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

import hmz.tui.app
import hmz.tui.pick
from hmz.tui.pick import Flows

if TYPE_CHECKING:
    from pathlib import Path

#: Catching up on fetches, before the suite takes it away again.
_CATCHES = Flows._catches_up


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
    """Stops the flow menu cloning humanize's own flowverse every time one opens."""

    def nothing(_self: Flows) -> None:
        """What catching up on fetches comes to here, which is nothing at all."""

    monkeypatch.setattr(Flows, "_catches_up", nothing)


@pytest.fixture
def catching_up(_fetches_nothing: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """Gives it back, for a test that is about what the menu fetches as it opens.

    Named after the fixture that took it away, so that it is put back after rather than
    before: two fixtures setting one attribute is the order they run in.
    """
    monkeypatch.setattr(Flows, "_catches_up", _CATCHES)

"""What every test of a held run needs: a project of its own, and a run held in it.

A daemon is one per workspace, so a test that holds one has to be standing somewhere no other
test is -- and has to let go of it however it ended, or the next test finds a run it did not
start.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hmz import daemon
from tests.daemon import runs

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A project of its own to hold a run in, which is what a daemon is one of."""
    where = tmp_path / "project"
    where.mkdir()
    monkeypatch.chdir(where)
    return where


@pytest.fixture
def held(workspace: Path) -> Iterator[daemon.Daemon]:
    """One run, held, and gone again however the test ended."""
    one = daemon.start(runs.opens)
    try:
        yield one
    finally:
        if one.alive:
            one.kill()

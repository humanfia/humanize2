"""What every test of the interface needs: somewhere of its own to be running in.

The interface writes down what is typed at it, in the project it is running in. A test types
things, and the project it would be writing them into is this one.
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _elsewhere(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Runs the interface somewhere temporary, unless the test says where itself."""
    monkeypatch.chdir(tmp_path)

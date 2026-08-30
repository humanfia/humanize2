"""What a held-open CLI's own inputs are fingerprinted by, and what that costs.

The fingerprint is asked for once a turn, on every session that holds a process open, and it
walks the directories that CLI reads its settings and its skills out of. So what it reads has
to be bounded: a settings file is worth reading to tell it from the one before it, and a
bundle that happens to be under the same directory is not.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import IO, TYPE_CHECKING, Any, cast

from hmz.agents import _inputs

if TYPE_CHECKING:
    import pytest


def test_a_same_size_edit_with_its_time_put_back_is_still_a_change(
    tmp_path: Path,
) -> None:
    """Which is why a configuration file is read rather than taken on its stat alone."""
    settings = tmp_path / "settings.json"
    settings.write_text('{"verbosity":"low"}')
    was = settings.stat()
    before = _inputs.snapshot({tmp_path})

    settings.write_text('{"verbosity":"max"}')
    os.utime(settings, ns=(was.st_atime_ns, was.st_mtime_ns))

    assert _inputs.snapshot({tmp_path}) != before


def test_a_file_too_big_to_be_configuration_is_taken_on_its_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A skills directory that has grown a bundle is not a tree read whole, once a turn."""
    skill = tmp_path / "SKILL.md"
    skill.write_bytes(b"x" * 16)
    bundle = tmp_path / "bundle.js"
    bundle.write_bytes(b"y" * (_inputs._READ_TO + 1))
    opened: list[Path] = []
    original = Path.open

    def opening(self: Path, *args: Any, **kwargs: Any) -> IO[Any]:
        opened.append(self)
        return cast("IO[Any]", original(self, *args, **kwargs))

    monkeypatch.setattr(Path, "open", opening)
    before = _inputs.snapshot({tmp_path})

    assert skill in opened
    assert bundle not in opened
    # And it still counts for something: what such a file is is its identity, and an edit
    # that changes its size or its times changes that.
    bundle.write_bytes(b"z" * (_inputs._READ_TO + 2))
    assert _inputs.snapshot({tmp_path}) != before

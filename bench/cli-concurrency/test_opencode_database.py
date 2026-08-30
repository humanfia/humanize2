"""Offline contracts for the optional launcher; never execute the native CLI."""

# ruff: noqa: INP001, S101 -- standalone benchmark tests

from __future__ import annotations

import hashlib
import os
import runpy
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest
from setup_opencode_database import setup


def test_launcher_retains_workspace_database_and_forwards_native_arguments(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cold/warm share one DB; another workspace gets its own without altering argv/env."""
    official = tmp_path / "official"
    original = b"#!/bin/sh\nexit 99\n"
    official.write_bytes(original)
    official.chmod(0o700)
    environment = dict(os.environ)
    root = tmp_path / "optional"
    record = setup(root, official)
    assert dict(os.environ) == environment
    assert official.read_bytes() == original
    assert record["official_sha256"] == hashlib.sha256(original).hexdigest()
    assert record["default_shared_database_behavior_changed"] is False
    assert list((root / "databases").iterdir()) == []
    loaded = runpy.run_path(str(root / "bin/opencode"))
    choose = loaded["database_for"]
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    link = tmp_path / "alias"
    link.symlink_to(workspace, target_is_directory=True)
    cold = ["run", "--dir", str(workspace), "--format", "json"]
    warm = [*cold, "--session", "opaque-session"]
    expected = choose(cold, str(tmp_path))
    assert expected == choose(warm, str(tmp_path))
    assert expected == choose(["--dir=alias"], str(tmp_path))
    assert expected == choose([], str(workspace))
    assert expected != choose(["--dir", "different"], str(tmp_path))
    assert expected != choose(["--", "--dir", str(workspace)], str(tmp_path))
    assert Path(expected).parent == root / "databases"
    assert Path(expected).suffix == ".sqlite3"
    for malformed in (["--dir"], ["--dir="], ["--dir", ""]):
        with pytest.raises(ValueError, match="requires a task workspace"):
            choose(malformed, str(tmp_path))
    execute = Mock()
    monkeypatch.setattr(os, "execve", execute)
    monkeypatch.setattr(sys, "argv", ["opencode", *warm])
    loaded["main"]()
    execute.assert_called_once_with(
        str(official), [str(official), *warm], {**environment, "OPENCODE_DB": expected}
    )
    assert dict(os.environ) == environment


def test_setup_refuses_existing_directory_and_nonexecutable(tmp_path: Path) -> None:
    """Preparing a profile must not overwrite existing files or select a nonexecutable."""
    official = tmp_path / "official"
    official.write_text("retained", encoding="utf-8")
    with pytest.raises(ValueError, match="official OpenCode executable"):
        setup(tmp_path / "optional", official)
    assert not (tmp_path / "optional").exists()
    official.chmod(0o700)
    with pytest.raises(ValueError, match="new directory"):
        setup(tmp_path, official)
    assert official.read_text(encoding="utf-8") == "retained"

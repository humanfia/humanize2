from __future__ import annotations

import importlib.machinery
import importlib.util
import shutil
from typing import TYPE_CHECKING

from hmz.tui import discover

if TYPE_CHECKING:
    import pytest


def test_dsh_is_installed_when_its_python_sdk_is_importable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def missing_executable(_name: str) -> None:
        return None

    def found_module(name: str) -> importlib.machinery.ModuleSpec | None:
        return (
            importlib.machinery.ModuleSpec(name, loader=None)
            if name == "deepseek_harness"
            else None
        )

    monkeypatch.setattr(shutil, "which", missing_executable)
    monkeypatch.setattr(
        importlib.util,
        "find_spec",
        found_module,
    )

    found = discover.installed()

    assert list(found) == ["dsh"]
    assert [model.name for model in found["dsh"]] == [
        "deepseek-v4-flash",
        "deepseek-v4-pro",
    ]
    assert discover.installable() == {}


def test_a_missing_dsh_sdk_is_installable_but_not_installed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def missing_executable(_name: str) -> None:
        return None

    def missing_module(_name: str) -> None:
        return None

    monkeypatch.setattr(shutil, "which", missing_executable)
    monkeypatch.setattr(importlib.util, "find_spec", missing_module)

    assert discover.installed() == {}
    assert [model.name for model in discover.installable()["dsh"]] == [
        "deepseek-v4-flash",
        "deepseek-v4-pro",
    ]

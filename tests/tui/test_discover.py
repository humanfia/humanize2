from __future__ import annotations

import importlib.machinery
import importlib.util
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from hmz.coganchor import backends
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
    # And nothing where an installer would have left one either: what is installed here is
    # what this test says it is, rather than what the developer's own machine has.
    monkeypatch.setattr(backends, "_INSTALLED_AT", ())
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
    monkeypatch.setattr(backends, "_INSTALLED_AT", ())
    monkeypatch.setattr(importlib.util, "find_spec", missing_module)

    assert discover.installed() == {}
    assert [model.name for model in discover.installable()["dsh"]] == [
        "deepseek-v4-flash",
        "deepseek-v4-pro",
    ]


def test_a_backend_somebody_added_is_installed_if_the_command_they_gave_is_there(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One humanize drives is started by its own name; one somebody added, by their command."""

    def added() -> dict[str, tuple[str, ...]]:
        return {"theirs": ("a-cli-of-theirs",)}

    def looked_up(said: str) -> str | None:
        return "/usr/bin/it" if said == "a-cli-of-theirs" else None

    monkeypatch.setattr(backends, "_INSTALLED_AT", ())
    monkeypatch.setattr(discover, "speaking", added)
    monkeypatch.setattr(discover, "program", looked_up)

    assert discover._is_installed("theirs")


def test_a_backend_somebody_added_with_no_command_at_all_is_not_installed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def added() -> dict[str, tuple[str, ...]]:
        return {"theirs": ()}

    monkeypatch.setattr(discover, "speaking", added)

    assert not discover._is_installed("theirs")


def test_an_ordinary_cli_may_be_chosen_without_anybody_choosing_it() -> None:
    """A CLI on PATH is there because somebody installed it, which is the choosing."""
    assert discover.ready_to_open("claude", Path("/somewhere"))


def test_the_backend_that_arrives_with_humanize_is_asked_whether_it_is_set_up(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Its SDK arrives whatever happens, so being installed says nothing about being usable."""
    from hmz.coganchor.agents import dsh

    def set_up(where: Path) -> bool:
        return where == tmp_path

    monkeypatch.setattr(dsh, "native_ready", set_up)

    assert discover.ready_to_open("dsh", tmp_path)
    assert not discover.ready_to_open("dsh", tmp_path / "elsewhere")


# ----------------------------------------------- where a turn could land besides here


def test_the_containers_running_here_are_offered_before_the_hosts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".ssh").mkdir()
    (tmp_path / ".ssh" / "config").write_text("Host builder\n  HostName 10.0.0.2\n")
    _docker(monkeypatch, "one\ntwo\n")

    assert discover.machines() == [
        ("docker://one", "container"),
        ("docker://two", "container"),
        ("ssh://builder", "ssh config"),
    ]


def test_a_machine_with_no_docker_and_no_ssh_config_only_runs_its_own_turns(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    _refuses(monkeypatch, FileNotFoundError("no docker here"))

    assert discover.machines() == []


def test_a_docker_that_does_not_answer_is_not_a_reason_to_sit_at_a_sheet(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A daemon that has hung must not hold the picker open waiting on it."""
    monkeypatch.setenv("HOME", str(tmp_path))
    _refuses(
        monkeypatch, subprocess.TimeoutExpired(["docker"], discover._LOOKING_SECONDS)
    )

    assert discover.machines() == []


def test_the_hosts_are_the_ones_written_in_the_config_in_the_order_they_are_written(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".ssh").mkdir()
    (tmp_path / ".ssh" / "config").write_text(
        "# a note\n"
        "Host builder gpu\n"
        "  HostName 10.0.0.2\n"
        "\n"
        "Host *\n"
        "  ForwardAgent yes\n"
        "\n"
        "Host web-?\n"
        "Host !not-this\n"
        "Host builder\n"  # said twice, offered once
        "host lowercase\n"
    )
    _docker(monkeypatch, "")

    assert discover.machines() == [
        ("ssh://builder", "ssh config"),
        ("ssh://gpu", "ssh config"),
        ("ssh://lowercase", "ssh config"),
    ]


def _docker(monkeypatch: pytest.MonkeyPatch, said: str) -> None:
    """Answers `docker ps` with these names, without a docker daemon anywhere near it."""

    def listing(*_: object, **__: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(["docker"], 0, said, "")

    monkeypatch.setattr(subprocess, "run", listing)


def _refuses(monkeypatch: pytest.MonkeyPatch, why: Exception) -> None:
    """Makes `docker ps` fail the way a machine without one, or with a hung one, fails."""

    def refusing(*_: object, **__: object) -> subprocess.CompletedProcess[str]:
        raise why

    monkeypatch.setattr(subprocess, "run", refusing)

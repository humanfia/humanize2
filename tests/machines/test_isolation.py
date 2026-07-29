"""Machines: the one an agent starts for itself, and the anchor its turns then run under.

The wiring is checked against a machine that starts nothing, so what it proves is when one is
brought up and when it is taken down. The docker machine is then driven for real, which needs a
daemon and the image below.
"""

from __future__ import annotations

import gc
import os
import socket
import subprocess
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest

from humanize.agents import AgentConfig
from humanize.coganchor import check
from humanize.machines import AnchoredConfig, DockerConfig, MachineBase, MachineConfig
from tests.stubs import HereAnchor, ShellAgent

if TYPE_CHECKING:
    from pathlib import Path

    from humanize.coganchor import AnchorConfig

#: Small, and has the `python3` a target needs. Pulled by hand rather than by the test, so a
#: machine without it skips instead of spending a minute on a download.
IMAGE = "python:3.12-slim"


class _StubMachine(MachineBase):
    """A machine that is only ever said to be started, and records that it was."""

    def __init__(self, config: _StubMachineConfig) -> None:
        super().__init__(config)
        self.anchor = HereAnchor(target="tcp://stub:0")
        self.started = 0
        self.stopped = 0

    def start(self) -> AnchorConfig:
        self.started += 1
        return self.anchor

    def stop(self) -> None:
        self.stopped += 1


@dataclass(frozen=True, kw_only=True)
class _StubMachineConfig(MachineConfig):
    #: Every machine this config builds, so a test can ask what became of them.
    built: list[_StubMachine]

    def create(self) -> _StubMachine:
        machine = _StubMachine(self)
        self.built.append(machine)
        return machine


def test_a_machine_is_started_for_the_first_turn_and_shared_by_the_rest() -> None:
    setting = _StubMachineConfig(built=[])
    agent = ShellAgent(AgentConfig(model="m", effort="high", machine=setting))
    assert setting.built == []  # configuring an agent starts nothing

    agent.new()("echo one")
    agent.new()("echo two")  # a second session, and still one machine
    assert len(setting.built) == 1
    assert setting.built[0].started == 1
    assert agent.anchor is setting.built[0].anchor
    # Both turns ran under it, which is what a machine of the agent's own is for.
    assert setting.built[0].anchor.seen == [
        ["sh", "-c", "echo one"],
        ["sh", "-c", "echo two"],
    ]


def test_a_machine_is_taken_down_with_the_agent_that_started_it() -> None:
    setting = _StubMachineConfig(built=[])
    agent = ShellAgent(AgentConfig(model="m", effort="high", machine=setting))
    agent.new()("echo one")
    assert setting.built[0].stopped == 0  # while the agent may still run a turn

    del agent
    gc.collect()
    assert setting.built[0].stopped == 1


def test_a_machine_that_was_already_running_is_reached_and_left_running() -> None:
    """Which is the whole of what an anchor says, and the reason it is a machine like any."""
    anchor = HereAnchor(target="ssh://build-box")
    machine = AnchoredConfig(anchor=anchor).create()

    assert machine.start() is anchor
    machine.stop()  # and there is nothing to take down


def _inspect(container: str, field: str) -> str:
    """What docker says about one container, or "" when there is no such container."""
    found = subprocess.run(
        ["docker", "inspect", "--format", field, container],
        capture_output=True,
        text=True,
        check=False,
    )
    return found.stdout.strip() if found.returncode == 0 else ""


@pytest.fixture
def daemon() -> None:
    """A docker daemon holding the image, or a skip: this test runs a container for real."""
    try:
        ready = subprocess.run(
            ["docker", "image", "inspect", IMAGE], capture_output=True, check=False
        )
    except OSError as reason:
        pytest.skip(f"needs the docker command: {reason}")
    if ready.returncode != 0:
        pytest.skip(f"needs a docker daemon holding {IMAGE}")


def test_the_container_holds_the_workspace_as_this_user(
    daemon: None, tmp_path: Path
) -> None:
    (tmp_path / "hello.txt").write_text("only in the workspace\n")
    machine = DockerConfig(image=IMAGE, workspace=str(tmp_path)).create()

    anchor = machine.start()
    container = anchor.target.removeprefix("docker://")
    try:
        found = check(anchor)
        assert found["workspace"] == str(tmp_path)
        assert found["entries"] == 1  # the directory itself is there, not a copy of it
        assert anchor.shadow != str(tmp_path)  # the mirror is never what it mirrors

        assert _inspect(container, "{{.Config.User}}") == f"{os.getuid()}:{os.getgid()}"
        assert _inspect(container, "{{(index .Mounts 0).Source}}") == str(tmp_path)
    finally:
        machine.stop()

    assert _inspect(container, "{{.Id}}") == ""  # and it goes when it is stopped


def test_a_workspace_that_is_not_there_is_refused(tmp_path: Path) -> None:
    """Rather than mounted into being: docker would create it, owned by root, in this tree."""
    missing = tmp_path / "not-here"
    with pytest.raises(FileNotFoundError):
        DockerConfig(image=IMAGE, workspace=str(missing)).create().start()
    assert not missing.exists()


def test_a_turn_runs_in_the_container_and_leaves_its_work_in_the_workspace(
    daemon: None, tmp_path: Path
) -> None:
    agent = ShellAgent(
        AgentConfig(
            model="m",
            effort="high",
            machine=DockerConfig(image=IMAGE, workspace=str(tmp_path)),
        )
    )
    # `hostname` is spawned, so it runs on the target; the redirection is the shell's own, so
    # the file is written in the mirror and pushed from there.
    answer = agent.new()("hostname > stamp.txt; cat stamp.txt")

    assert answer
    assert answer != socket.gethostname()
    assert (tmp_path / "stamp.txt").read_text().strip() == answer

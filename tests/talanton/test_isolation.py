"""Isolation: the machine an agent starts for itself, and the anchor its turns then run under.

The wiring is checked against a backend that starts nothing, so what it proves is when a machine
is started and when it is taken down. The docker backend is then driven for real, which needs a
daemon and the image below.
"""

from __future__ import annotations

import gc
import os
import socket
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

from humanize.coganchor import AnchorConfig, check
from humanize.janus import AgentConfig
from humanize.talanton import (
    DockerIsolationConfig,
    IsolationBase,
    IsolationConfig,
)
from tests.janus.conftest import HereAnchor, ShellAgent

#: Small, and has the `python3` a target needs. Pulled by hand rather than by the test, so a
#: machine without it skips instead of spending a minute on a download.
IMAGE = "python:3.12-slim"


class _StubIsolation(IsolationBase):
    """A machine that is only ever said to be started, and records that it was."""

    def __init__(self, config: _StubIsolationConfig):
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
class _StubIsolationConfig(IsolationConfig):
    #: Every backend this config builds, so a test can ask what became of them.
    built: list[_StubIsolation]

    def create(self) -> _StubIsolation:
        backend = _StubIsolation(self)
        self.built.append(backend)
        return backend


def test_a_machine_is_started_for_the_first_turn_and_shared_by_the_rest() -> None:
    isolation = _StubIsolationConfig(built=[])
    agent = ShellAgent(AgentConfig(model="m", effort="high", isolation=isolation))
    assert isolation.built == []  # configuring an agent starts nothing

    agent.new()("echo one")
    agent.new()("echo two")  # a second session, and still one machine
    assert len(isolation.built) == 1
    assert isolation.built[0].started == 1
    assert agent.anchor is isolation.built[0].anchor
    # Both turns ran under it, which is what an isolated agent is for.
    assert isolation.built[0].anchor.seen == [
        ["sh", "-c", "echo one"],
        ["sh", "-c", "echo two"],
    ]


def test_a_machine_is_taken_down_with_the_agent_that_started_it() -> None:
    isolation = _StubIsolationConfig(built=[])
    agent = ShellAgent(AgentConfig(model="m", effort="high", isolation=isolation))
    agent.new()("echo one")
    assert isolation.built[0].stopped == 0  # while the agent may still run a turn

    del agent
    gc.collect()
    assert isolation.built[0].stopped == 1


def test_an_agent_is_anchored_or_isolated_but_not_both() -> None:
    with pytest.raises(ValueError, match="not both"):
        AgentConfig(
            model="m",
            effort="high",
            anchor=AnchorConfig(),
            isolation=_StubIsolationConfig(built=[]),
        )


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
    isolation = DockerIsolationConfig(image=IMAGE, workspace=str(tmp_path)).create()

    anchor = isolation.start()
    container = anchor.target.removeprefix("docker://")
    try:
        found = check(anchor)
        assert found["workspace"] == str(tmp_path)
        assert found["entries"] == 1  # the directory itself is there, not a copy of it
        assert anchor.shadow != str(tmp_path)  # the mirror is never what it mirrors

        assert _inspect(container, "{{.Config.User}}") == f"{os.getuid()}:{os.getgid()}"
        assert _inspect(container, "{{(index .Mounts 0).Source}}") == str(tmp_path)
    finally:
        isolation.stop()

    assert _inspect(container, "{{.Id}}") == ""  # and it goes when it is stopped


def test_a_workspace_that_is_not_there_is_refused(tmp_path: Path) -> None:
    """Rather than mounted into being: docker would create it, owned by root, in this tree."""
    missing = tmp_path / "not-here"
    with pytest.raises(FileNotFoundError):
        DockerIsolationConfig(image=IMAGE, workspace=str(missing)).create().start()
    assert not missing.exists()


def test_a_turn_runs_in_the_container_and_leaves_its_work_in_the_workspace(
    daemon: None, tmp_path: Path
) -> None:
    agent = ShellAgent(
        AgentConfig(
            model="m",
            effort="high",
            isolation=DockerIsolationConfig(image=IMAGE, workspace=str(tmp_path)),
        )
    )
    # `hostname` is spawned, so it runs on the target; the redirection is the shell's own, so
    # the file is written in the mirror and pushed from there.
    answer = agent.new()("hostname > stamp.txt; cat stamp.txt")

    assert (
        answer and answer != socket.gethostname()
    )  # the container's, not this machine's
    assert (tmp_path / "stamp.txt").read_text().strip() == answer

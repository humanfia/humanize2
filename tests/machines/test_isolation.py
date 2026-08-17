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

from hmz.agents import AgentConfig
from hmz.coganchor import check
from hmz.machines import AnchoredConfig, DockerConfig, MachineBase, MachineConfig
from hmz.runner import Runner
from tests.stubs import HereAnchor, ShellAgent

if TYPE_CHECKING:
    from pathlib import Path

    from hmz.coganchor import AnchorConfig

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


#: A flow that says one of its agents works in a container of an image it names, and has that
#: agent leave a mark where a person could find it afterwards.
ISOLATING = f'''
from typing import Annotated, NamedTuple

from hmz.agents import AgentBase, Isolated
from hmz.flows import flow


class Agents(NamedTuple):
    """The one this drives, in a container of its own."""

    tester: Annotated[AgentBase, Isolated("{IMAGE}")]


@flow
def run(agents: Agents, task: str) -> None:
    agents.tester("hostname > stamp.txt; cat /etc/os-release > which.txt")
'''


def test_a_flow_that_isolates_an_agent_runs_it_in_the_image_it_named(
    daemon: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Isolated mode, end to end: the flow names the image and nobody configures anything.

    The container is started for the agent, the project directory is mounted into it at the
    path it already has, and the turn runs there through coganchor -- so the work is this
    machine's file in this machine's directory, and the tools that did it were the image's.
    """
    monkeypatch.chdir(tmp_path)
    (tmp_path / "flow.py").write_text(ISOLATING)
    agent = ShellAgent(AgentConfig(model="m", effort="high"))

    Runner(tmp_path / "flow.py", [agent]).run("go")

    # Nobody said where it works, and it works in a container of the image the flow named.
    machine = agent.config.machine
    assert isinstance(machine, DockerConfig)
    assert machine.image == IMAGE
    # The work is here, and it was done there.
    assert (tmp_path / "stamp.txt").read_text().strip() != socket.gethostname()
    assert "Debian" in (tmp_path / "which.txt").read_text()


def test_a_session_may_be_opened_at_a_directory_on_the_machine_it_lands_on(
    daemon: None, tmp_path: Path
) -> None:
    """Which directory of the target, said as the target names it: the mirror follows."""
    (tmp_path / "packages" / "one").mkdir(parents=True)
    (tmp_path / "packages" / "one" / "which.txt").write_text("the package")
    agent = ShellAgent(
        AgentConfig(
            model="m",
            effort="high",
            machine=DockerConfig(image=IMAGE, workspace=str(tmp_path)),
        )
    )

    session = agent.new(tmp_path / "packages" / "one")

    # `pwd` is the shell's own, so it says where the agent was put: the mirror of that
    # directory. What it reads and writes there is that directory's, on the target.
    assert session("cat which.txt") == "the package"
    assert session("pwd > where.txt; cat where.txt").endswith("packages/one")
    assert (tmp_path / "packages" / "one" / "where.txt").exists()


#: A flow with two agents and nothing said about where either works, which is what a run put
#: in a container from outside is: the flow did not ask for one, and every agent lands there.
CONTAINED = """
from typing import NamedTuple

from hmz.flows import Agent, container, flow


class Agents(NamedTuple):
    builder: Agent
    reviewer: Agent


@flow
def run(agents: Agents, task: str) -> None:
    agents.builder("hostname > builder.txt")
    agents.reviewer("hostname > reviewer.txt")
    held = container()
    held.write_text("from-the-flow.txt", held.run(["hostname"]).output)
"""


def test_a_run_may_be_put_in_one_container_and_every_agent_lands_there(
    daemon: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Which is the convenience: said once from outside rather than agent by agent inside.

    One container for the run rather than one apiece, so that what one agent writes is what
    the next one reads -- and the flow's own code reaches the same place, which is the half a
    mounted workspace does not answer for.
    """
    monkeypatch.chdir(tmp_path)
    (tmp_path / "flow.py").write_text(CONTAINED)
    agents = [
        ShellAgent(AgentConfig(model="m", effort="high")),
        ShellAgent(AgentConfig(model="m", effort="high")),
    ]

    Runner(tmp_path / "flow.py", agents, container=IMAGE).run("go")

    # Both turns ran on the machine, and on the same one.
    said = [
        (tmp_path / one).read_text().strip()
        for one in ("builder.txt", "reviewer.txt", "from-the-flow.txt")
    ]
    assert said[0] == said[1] == said[2]
    assert said[0] != socket.gethostname()
    # And it is taken down when the run ends, whichever way it ends.
    assert _inspect(said[0], "{{.State.Running}}") == ""


def test_the_flow_reaches_the_container_only_while_the_run_is_in_one() -> None:
    """A run on this machine has none, and a flow does what it always did."""
    from hmz.flows import container

    assert container() is None


def test_the_flow_reads_writes_and_runs_on_the_machine_the_run_lands_on(
    daemon: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The half a mounted workspace does not answer for: the tools are the machine's.

    A file is the same file either way -- the project directory is mounted at the path it
    already has -- and a command is not, being run by this machine's shell against this
    machine's tools unless it is sent there.
    """
    from hmz.machines import Mapped

    monkeypatch.chdir(tmp_path)
    (tmp_path / "here.txt").write_text("written here\n")
    machine = DockerConfig(image=IMAGE, workspace=str(tmp_path)).create()
    anchor = machine.start()
    try:
        with Mapped(anchor) as held:
            assert held.workspace == str(tmp_path)
            assert held.read_text("here.txt") == "written here\n"
            held.write_text("there.txt", "written from the flow\n")
            assert "here.txt" in held.listdir()
            assert held.exists("here.txt")
            assert not held.exists("nothing.txt")

            said = held.run(
                ["python3", "-c", "import platform; print(platform.node())"]
            )
            assert said.ok
            assert said.status == 0
            assert said.output.strip() != socket.gethostname()
            # And a command that failed says so rather than reading as one that worked.
            assert not held.run(["python3", "-c", "raise SystemExit(3)"]).ok
    finally:
        machine.stop()

    # The work is here, because the directory the container was given is this one.
    assert (tmp_path / "there.txt").read_text() == "written from the flow\n"

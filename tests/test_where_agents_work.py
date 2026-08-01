"""Where a flow's agents may work, which is the flow's to say rather than a setting.

A flow is written for one shape of work. One whose agents read this project cannot have one of
them reading somebody else's, and one written to run its tests in a container of a particular
image is not one to be pointed at a colleague's laptop instead. So a place says what it is --
nothing, `Remote`, or an `Isolated` naming an image -- and everything else is refused before the
first turn rather than discovered by a turn that landed somewhere surprising.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hmz.agents import AgentConfig, Isolated, Remote, anchored
from hmz.machines import DockerConfig
from hmz.runner import NotAFlow, Runner, wanted
from tests.stubs import ShellAgent

if TYPE_CHECKING:
    from pathlib import Path

CONFIG = AgentConfig(model="m", effort="high")

#: A flow whose three agents say three different things about where they work.
DECLARED = '''
from typing import Annotated, NamedTuple

from hmz.agents import AgentBase, Isolated, Remote


class Agents(NamedTuple):
    """The three: one that may be sent away, one in a container, one that stays."""

    builder: Annotated[AgentBase, Remote]
    tester: Annotated[AgentBase, Isolated("python:3.12")]
    reviewer: AgentBase


def run(agents: Agents, task: str) -> None:
    pass
'''

#: A flow that says nothing about where its one agent works, which is most flows.
PLAIN = """
from hmz.agents import AgentBase


def run(agents: tuple[AgentBase], task: str) -> None:
    pass
"""


def _flow(tmp_path: Path, source: str) -> Path:
    """Writes a flow out and answers with its path."""
    where = tmp_path / "flow.py"
    where.write_text(source)
    return where


def test_a_flow_says_where_each_of_its_agents_may_work(tmp_path: Path) -> None:
    places = wanted(_flow(tmp_path, DECLARED))

    assert [place.name for place in places] == ["builder", "tester", "reviewer"]
    assert places[0].where is Remote
    assert places[1].where == Isolated("python:3.12")
    assert places[2].where is None  # which is this machine, and nothing to configure


def test_an_agent_the_flow_did_not_send_away_may_not_be_sent_away(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The change this makes: a machine used to be a setting anybody could reach for."""
    monkeypatch.chdir(tmp_path)
    flow = _flow(tmp_path, PLAIN)
    agent = ShellAgent(
        AgentConfig(model="m", effort="high", machine=anchored("ssh://elsewhere"))
    )

    with pytest.raises(NotAFlow, match="runs on this machine"):
        Runner(flow, [agent])


def test_an_agent_the_flow_says_is_remote_may_be_pointed_at_a_machine(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    flow = _flow(tmp_path, DECLARED)
    builder = ShellAgent(
        AgentConfig(model="m", effort="high", machine=anchored("ssh://elsewhere"))
    )
    agents = [builder, ShellAgent(CONFIG), ShellAgent(CONFIG)]

    Runner(flow, agents)  # which is the whole assertion: it is not refused

    assert builder.config.machine == anchored("ssh://elsewhere")


def test_an_isolated_agent_is_given_the_container_the_flow_named(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Nobody is asked which image: the flow said it, and that is the whole of the setting."""
    monkeypatch.chdir(tmp_path)
    flow = _flow(tmp_path, DECLARED)
    tester = ShellAgent(CONFIG)
    assert tester.config.machine is None

    Runner(flow, [ShellAgent(CONFIG), tester, ShellAgent(CONFIG)])

    machine = tester.config.machine
    assert isinstance(machine, DockerConfig)
    assert machine.image == "python:3.12"


def test_an_isolated_agent_may_not_be_pointed_anywhere(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    flow = _flow(tmp_path, DECLARED)
    tester = ShellAgent(
        AgentConfig(model="m", effort="high", machine=anchored("ssh://elsewhere"))
    )

    with pytest.raises(NotAFlow, match="container of this flow's own"):
        Runner(flow, [ShellAgent(CONFIG), tester, ShellAgent(CONFIG)])


def test_an_agent_that_has_already_worked_is_not_moved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A conversation resumes under the settings it opened with, so it cannot be relocated."""
    monkeypatch.chdir(tmp_path)
    flow = _flow(tmp_path, DECLARED)
    tester = ShellAgent(CONFIG)
    tester.new()("echo already")

    with pytest.raises(NotAFlow, match="has already opened a session"):
        Runner(flow, [ShellAgent(CONFIG), tester, ShellAgent(CONFIG)])


def test_what_a_flow_says_is_read_where_the_agents_are_chosen(tmp_path: Path) -> None:
    """So that whoever is choosing them can offer the machine only where it may be given."""
    places = wanted(_flow(tmp_path, PLAIN))

    assert [place.where for place in places] == [None]

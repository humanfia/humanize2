"""Where a flow's agents may work, which is the flow's to say rather than a setting.

A flow is written for one shape of work. One whose agents read this project cannot have one of
them reading somebody else's, and one written to run its tests in a container of a particular
image is not one to be pointed at a colleague's laptop instead. So a place says what it is --
nothing, `Remote`, or an `Isolated` naming an image -- and everything else is refused before the
first turn rather than discovered by a turn that landed somewhere surprising.

What a flow needs *of* that place is said the same way and checked here too: `Needs(where=...)`
names what the machine has to come to, and it is asked of the machine's settings rather than of
a machine, so that a place which will not do is refused before an image has been pulled. What
only a live handshake can answer is not asked here -- a machine that turns out not to be what
its settings promised fails as it starts, and this file does not bring one up.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hmz.coganchor.agents import AgentConfig, Isolated, Needs, Remote, anchored
from hmz.coganchor.machines import DockerConfig
from hmz.flows import NotAFlow, wanted
from hmz.runtime.runner import Runner
from tests.stubs import ShellAgent

if TYPE_CHECKING:
    from pathlib import Path

CONFIG = AgentConfig(model="m", effort="high")

#: A flow whose three agents say three different things about where they work.
DECLARED = '''
from typing import Annotated, NamedTuple

from hmz.coganchor.agents import AgentBase, Isolated, Remote
from hmz.flows import flow


class Agents(NamedTuple):
    """The three: one that may be sent away, one in a container, one that stays."""

    builder: Annotated[AgentBase, Remote]
    tester: Annotated[AgentBase, Isolated("python:3.12")]
    reviewer: AgentBase


@flow
def run(agents: Agents, task: str) -> None:
    pass
'''

#: A flow whose one agent may be sent away, and has to be: the work is not this machine's.
ELSEWHERE = '''
from typing import Annotated, NamedTuple

from hmz.coganchor.agents import AgentBase, Needs, Remote
from hmz.flows import flow


class Agents(NamedTuple):
    """The one it drives, and what where it works has to come to."""

    builder: Annotated[AgentBase, Remote, Needs(where=("remote",))]


@flow
def run(agents: Agents, task: str) -> None:
    pass
'''

#: One whose work has to happen on a Linux machine nobody here has to have configured.
CONTAINED = '''
from typing import Annotated, NamedTuple

from hmz.coganchor.agents import AgentBase, Isolated, Needs
from hmz.flows import flow


class Agents(NamedTuple):
    """The one it drives, in a container of the flow's own naming."""

    tester: Annotated[
        AgentBase, Isolated("python:3.12"), Needs(where=("isolated", "linux"))
    ]


@flow
def run(agents: Agents, task: str) -> None:
    pass
'''

#: One that needs a machine somebody here brought up, which an anchor onto one is not.
MANAGED = '''
from typing import Annotated, NamedTuple

from hmz.coganchor.agents import AgentBase, Needs, Remote
from hmz.flows import flow


class Agents(NamedTuple):
    """The one it drives, somewhere this run may take down again."""

    builder: Annotated[AgentBase, Remote, Needs(where=("managed",))]


@flow
def run(agents: Agents, task: str) -> None:
    pass
'''

#: One whose container could never come to what it asks of it, which is a flow to correct.
IMPOSSIBLE = '''
from typing import Annotated, NamedTuple

from hmz.coganchor.agents import AgentBase, Isolated, Needs
from hmz.flows import flow


class Agents(NamedTuple):
    """The one it drives, in a container that is asked to be a Mac."""

    tester: Annotated[AgentBase, Isolated("python:3.12"), Needs(where=("darwin",))]


@flow
def run(agents: Agents, task: str) -> None:
    pass
'''

#: One driven by an agent nobody points anywhere, whose work still has to land elsewhere.
ANYWHERE_ELSE = '''
from typing import Annotated, NamedTuple

from hmz.coganchor.agents import AgentBase, Needs, Remote
from hmz.flows import flow


class Agents(NamedTuple):
    """The one it drives, somewhere that is not this machine."""

    builder: Annotated[AgentBase, Remote, Needs(where=("remote",))]


@flow
def run(agents: Agents, task: str) -> None:
    pass
'''

#: A flow that says nothing about where its one agent works, which is most flows.
PLAIN = """
from hmz.coganchor.agents import AgentBase
from hmz.flows import flow


@flow
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


def test_a_place_that_needs_a_machine_is_refused_an_agent_pointed_nowhere(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """This machine comes to nothing at all, so anything asked of where the work lands fails."""
    monkeypatch.chdir(tmp_path)
    flow = _flow(tmp_path, ELSEWHERE)

    with pytest.raises(NotAFlow, match="comes to remote, which this machine does not"):
        Runner(flow, [ShellAgent(CONFIG)])


def test_a_place_that_needs_a_machine_takes_one_that_comes_to_what_it_asked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The other half: the settings already say `remote`, and nothing had to be reached."""
    monkeypatch.chdir(tmp_path)
    flow = _flow(tmp_path, ELSEWHERE)
    builder = ShellAgent(
        AgentConfig(model="m", effort="high", machine=anchored("ssh://elsewhere"))
    )

    Runner(flow, [builder])  # which is the whole assertion: it is not refused


def test_a_place_is_refused_a_machine_whose_settings_do_not_promise_what_it_needs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Nobody here started the machine an anchor names, so nobody here may take it down."""
    monkeypatch.chdir(tmp_path)
    flow = _flow(tmp_path, MANAGED)
    builder = ShellAgent(
        AgentConfig(model="m", effort="high", machine=anchored("ssh://elsewhere"))
    )

    with pytest.raises(
        NotAFlow, match="comes to managed, which the machine it works on does not"
    ):
        Runner(flow, [builder])


def test_the_container_a_flow_named_comes_to_what_that_flow_needs_of_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Settled and then checked, so a place the flow put in a container is checked in one."""
    monkeypatch.chdir(tmp_path)
    flow = _flow(tmp_path, CONTAINED)
    tester = ShellAgent(CONFIG)

    Runner(flow, [tester])

    assert isinstance(tester.config.machine, DockerConfig)


def test_what_a_place_needs_of_where_it_works_is_read_where_the_agents_are_chosen(
    tmp_path: Path,
) -> None:
    """So that whoever is choosing them can be asked for a machine that would do."""
    places = wanted(_flow(tmp_path, ELSEWHERE))

    assert places[0].needs == Needs(where=("remote",))


def test_a_place_refused_for_where_it_works_is_not_moved_there_first(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A refused call must hand its agents back as it found them, containers included."""
    monkeypatch.chdir(tmp_path)
    flow = _flow(tmp_path, IMPOSSIBLE)
    tester = ShellAgent(CONFIG)

    with pytest.raises(NotAFlow, match="comes to darwin"):
        Runner(flow, [tester])

    assert tester.config.machine is None


def test_a_run_put_in_a_container_from_outside_is_where_that_run_works(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Nothing is pointed at it until the run starts, so it is named rather than read."""
    monkeypatch.chdir(tmp_path)
    flow = _flow(tmp_path, ANYWHERE_ELSE)

    Runner(flow, [ShellAgent(CONFIG)], container="python:3.12")

    # And without one it is refused, which is the half that says the container did the work.
    with pytest.raises(NotAFlow, match="comes to remote, which this machine does not"):
        Runner(flow, [ShellAgent(CONFIG)])

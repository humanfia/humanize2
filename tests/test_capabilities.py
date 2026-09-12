"""What a flow says filling one of its places takes, and what happens when it does not.

Most of what a flow builds on, every backend here serves. Some of it only some of them do,
and a flow built on one of those is not a flow any agent can drive. So it writes `Needs`
beside the place, and an agent whose backend serves none of it is refused before the first
turn rather than found out from the call that reached for it, hours into a loop.

What is covered here is the agent half -- what the backend filling the place has to serve --
at the top of a run and again where one flow calls another, those being the two places an
agent is ever handed to a flow. The other half, what the machine an agent's turns land on has
to come to, is covered beside the rest of where agents work in `test_where_agents_work.py`.
Nothing here takes a turn: the whole point is that none of it needs one.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hmz.agents import (
    ClaudeCodeAgent,
    ClaudeCodeAgentConfig,
    DshAgent,
    DshAgentConfig,
    Needs,
)
from hmz.flows import NotAFlow, load, wanted
from hmz.runner import Runner
from tests.stubs import written

if TYPE_CHECKING:
    from pathlib import Path

    from hmz.backends import Model

#: A flow that steers the turn it is driving, which only some backends can be asked to do.
STEERS = '''"""One that talks to its agent mid-turn."""

from typing import Annotated, NamedTuple

from hmz.agents import AgentBase, Needs
from hmz.flows import flow


class Agents(NamedTuple):
    """The one it drives, and what filling that place takes."""

    builder: Annotated[AgentBase, Needs("steer")]


@flow
def run(agents: Agents, task: str) -> None:
    pass
'''

#: A flow that asks for three things at once, one of them a moment.
SEVERAL = '''"""One built on more than a flow usually is."""

from typing import Annotated, NamedTuple

from hmz.agents import AgentBase, Needs
from hmz.flows import flow


class Agents(NamedTuple):
    """Two places, only one of which asks for anything."""

    builder: Annotated[AgentBase, Needs("shape", "tools", "moment:SubagentStop")]
    reviewer: AgentBase


@flow
def run(agents: Agents, task: str) -> None:
    pass
'''

#: A flow built on a fact about the CLI rather than on one about the driver that speaks to it.
RESUMES = '''"""One that picks a conversation back up."""

from typing import Annotated, NamedTuple

from hmz.agents import AgentBase, Needs
from hmz.flows import flow


class Agents(NamedTuple):
    """The one it drives."""

    builder: Annotated[AgentBase, Needs("resume")]


@flow
def run(agents: Agents, task: str) -> None:
    pass
'''

#: One built on something every backend here serves, which is still a thing to be able to say.
EVERYONE = '''"""One built on what nobody has to shop for."""

from typing import Annotated, NamedTuple

from hmz.agents import AgentBase, Needs
from hmz.flows import flow


class Agents(NamedTuple):
    """The one it drives, which has only to do what all of them do."""

    builder: Annotated[AgentBase, Needs("schema", "hooks")]


@flow
def run(agents: Agents, task: str) -> None:
    pass
'''

#: A flow that asks for nothing in particular, which is most flows.
PLAIN = '''"""One that any agent can drive."""

from hmz.agents import AgentBase
from hmz.flows import flow


@flow
def run(agents: tuple[AgentBase], task: str) -> None:
    pass
'''

#: One that calls the one that steers, handing it the agent it was given.
CALLS = '''"""One that reaches for the flow that steers."""

from hmz.agents import AgentBase
from hmz.flows import flow, load


@flow
def run(agents: tuple[AgentBase], task: str) -> None:
    load("steers")(agents, task)
'''


def _claude() -> ClaudeCodeAgent:
    """An agent of the backend whose turns can be talked to while they run."""
    return ClaudeCodeAgent(ClaudeCodeAgentConfig(model="m", effort="low"))


def _dsh() -> DshAgent:
    """An agent of a backend whose turns cannot."""
    return DshAgent(DshAgentConfig(model="m", effort="high"))


@pytest.fixture(autouse=True)
def flows(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A project holding the flows these tests drive, and a home nothing wrote to."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    where = tmp_path / "project"
    kept = where / ".humanize/flows"
    kept.mkdir(parents=True)
    written(kept, "steers", STEERS)
    written(kept, "several", SEVERAL)
    written(kept, "resumes", RESUMES)
    written(kept, "everyone", EVERYONE)
    written(kept, "plain", PLAIN)
    written(kept, "calls", CALLS)
    monkeypatch.chdir(where)
    return where


def test_a_flow_says_what_filling_each_of_its_places_takes() -> None:
    """Read where the agents are chosen, so that only ones that would work are offered."""
    places = wanted("several")

    assert places[0].needs == Needs("shape", "tools", "moment:SubagentStop")
    assert places[1].needs is None  # which is a place any agent may fill


def test_a_place_that_asks_for_nothing_is_a_place_any_backend_may_fill() -> None:
    """Most places: what every backend serves is nothing a flow has to write down."""
    Runner("plain", [_dsh()])  # which is the whole assertion: it is not refused


def test_a_flow_built_on_steering_is_refused_a_backend_that_cannot_be_steered() -> None:
    """Before the first turn, which is the only time refusing it costs nothing."""
    with pytest.raises(
        NotAFlow, match="builder has to serve steer, which dsh does not"
    ):
        Runner("steers", [_dsh()])


def test_a_flow_built_on_steering_takes_a_backend_that_can_be_steered() -> None:
    """The other half of the same check: a fit agent is refused nothing."""
    runner = Runner("steers", [_claude()])

    assert len(runner.agents) == 1


def test_a_flow_is_refused_for_every_one_of_the_things_it_asks_for_at_once() -> None:
    """Named together rather than one at a time, so that one reading says what to choose."""
    with pytest.raises(NotAFlow) as refused:
        Runner("several", [_dsh(), _dsh()])

    assert "builder has to serve moment:SubagentStop, shape, tools" in str(
        refused.value
    )
    assert "which dsh does not" in str(refused.value)


def test_what_the_backend_itself_serves_is_read_where_it_is_written_down() -> None:
    """`resume` is a fact about the CLI rather than about the driver that speaks to it."""
    runner = Runner("resumes", [_dsh()])

    assert len(runner.agents) == 1


def test_a_flow_calling_another_is_refused_the_same_way_the_run_would_be() -> None:
    """The check is duplicated so that a flow cannot pass at the top and fail in the middle."""
    with pytest.raises(
        NotAFlow, match="builder has to serve steer, which dsh does not"
    ):
        load("calls")([_dsh()], "go")


def test_a_flow_calling_another_with_a_fit_agent_is_not_refused() -> None:
    """And the called flow runs, which is what being handed a fit agent comes to."""
    load("calls")([_claude()], "go")  # the whole assertion: nothing is raised


def test_what_every_backend_serves_is_served_by_every_backend() -> None:
    """The catalogue names nobody against those, which must not read as nobody serving them."""
    runner = Runner("everyone", [_dsh()])

    assert len(runner.agents) == 1


def test_a_place_takes_what_it_needs_as_names_rather_than_as_one_name() -> None:
    """`where="remote"` is five capabilities spelled a letter each, so it is refused outright."""
    with pytest.raises(TypeError, match="sequence of names rather than one name"):
        Needs(where="remote")


def test_whoever_is_choosing_an_agent_is_offered_only_the_ones_that_would_do() -> None:
    """Asked by backend before there is an agent, so a place cannot be filled wrong."""
    from hmz.flows.driving import Place
    from hmz.tui.pick import Clis

    offered: dict[str, tuple[Model, ...]] = {"claude": (), "dsh": ()}
    plain = Place(name="builder", person=False, moments=frozenset())

    assert [row[0] for row in Clis(offered, place=plain).rows()] == ["claude", "dsh"]

    steering = plain._replace(needs=Needs("steer"))

    assert [row[0] for row in Clis(offered, place=steering).rows()] == ["claude"]

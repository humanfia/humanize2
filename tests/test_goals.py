"""A flow built on the backends' own goal feature says so, and is refused an agent without one.

`pursue` is the agent keeping itself going toward an objective it decides for itself is met,
and three of the six backends have it. A flow written around that is not a flow any agent can
drive -- so it declares it where it declares the agent, exactly as it declares a moment it
hangs a hook on, and a run that could not work is refused before its first turn rather than
raising in the middle of one.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hmz.agents import (
    ClaudeCodeAgent,
    ClaudeCodeAgentConfig,
    CodexAgent,
    CodexAgentConfig,
    KimiCodeCLIAgent,
    KimiCodeCLIAgentConfig,
    OpencodeAgent,
    OpencodeAgentConfig,
    PiAgent,
    PiAgentConfig,
)
from hmz.runner import NotAFlow, Runner, wanted

if TYPE_CHECKING:
    from pathlib import Path

#: A flow that runs its one agent under a goal, and says so where it declares it.
PURSUING = '''"""A loop that hands the objective to the agent and lets it decide it is done."""

from typing import Annotated, NamedTuple

from hmz.agents import AgentBase, Goal
from hmz.flows import flow


class Agents(NamedTuple):
    """The one it drives, which has to have a goal feature of its own."""

    worker: Annotated[AgentBase, Goal]


@flow
def run(agents: Agents, task: str) -> None:
    agents.worker.pursue(task)
'''

#: The same loop, said the ordinary way: turns, and nothing asked of the backend.
PLAIN = '''"""A loop of plain turns, which any backend takes."""

from hmz.agents import AgentBase
from hmz.flows import flow


@flow
def run(agents: tuple[AgentBase], task: str) -> None:
    (agent,) = agents
    agent(task)
'''


def _written(tmp_path: Path, source: str, name: str = "pursuing") -> str:
    """Writes a flow out and answers with its path."""
    where = tmp_path / f"{name}.py"
    where.write_text(source)
    return str(where)


def test_a_place_run_under_a_goal_says_so(tmp_path: Path) -> None:
    """Which is what whoever is choosing the agents reads, before anything runs."""
    (place,) = wanted(_written(tmp_path, PURSUING))

    assert place.goal is True
    assert place.name == "worker"


def test_a_place_that_said_nothing_is_driven_by_turns(tmp_path: Path) -> None:
    (place,) = wanted(_written(tmp_path, PLAIN, "plain"))

    assert place.goal is False


def test_an_agent_whose_backend_has_no_goal_feature_is_refused(tmp_path: Path) -> None:
    """Before the first turn, which is where a loop would otherwise find out."""
    where = _written(tmp_path, PURSUING)

    with pytest.raises(
        NotAFlow, match="is run under a goal, which pi has no feature for"
    ):
        Runner(where, [PiAgent(PiAgentConfig(model="m", effort="low"))])

    with pytest.raises(NotAFlow, match="opencode has no feature for"):
        Runner(where, [OpencodeAgent(OpencodeAgentConfig(model="m", effort="low"))])


@pytest.mark.parametrize(
    "agent",
    [
        ClaudeCodeAgent(ClaudeCodeAgentConfig(model="m", effort="low")),
        CodexAgent(CodexAgentConfig(model="m", effort="low")),
        KimiCodeCLIAgent(KimiCodeCLIAgentConfig(model="m", effort="low")),
    ],
)
def test_an_agent_whose_backend_has_one_is_taken(agent: object, tmp_path: Path) -> None:
    """The three that answer `pursue`, each of which says so on the class."""
    runner = Runner(_written(tmp_path, PURSUING), [agent])  # pyright: ignore[reportArgumentType]

    assert len(runner.agents) == 1


def test_a_flow_that_asks_nothing_takes_any_of_them(tmp_path: Path) -> None:
    """A place that says nothing about a goal is one every backend can fill."""
    runner = Runner(
        _written(tmp_path, PLAIN, "plain"),
        [PiAgent(PiAgentConfig(model="m", effort="low"))],
    )

    assert len(runner.agents) == 1

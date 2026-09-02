"""A flow built on the backends' own goal feature says so, and is refused an agent without one.

`pursue` is the agent keeping itself going toward an objective it decides for itself is met,
and four of the seven backends have it. A flow written around that is not a flow any agent can
drive -- so it declares it where it declares the agent, exactly as it declares a moment it
hangs a hook on, and a run that could not work is refused before its first turn rather than
raising in the middle of one.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hmz.coganchor.agents import (
    ClaudeCodeAgent,
    ClaudeCodeAgentConfig,
    CodexAgent,
    CodexAgentConfig,
    DshAgent,
    DshAgentConfig,
    KimiCodeCLIAgent,
    KimiCodeCLIAgentConfig,
    OpencodeAgent,
    OpencodeAgentConfig,
    PiAgent,
    PiAgentConfig,
)
from hmz.flows import NotAFlow, wanted
from hmz.runtime.runner import Runner, flow_and_agents

if TYPE_CHECKING:
    from pathlib import Path

#: A flow that runs its one agent under a goal, and says so where it declares it.
PURSUING = '''"""A loop that hands the objective to the agent and lets it decide it is done."""

from typing import Annotated, NamedTuple

from hmz.coganchor.agents import AgentBase, Goal
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

from hmz.coganchor.agents import AgentBase
from hmz.flows import flow


@flow
def run(agents: tuple[AgentBase], task: str) -> None:
    (agent,) = agents
    agent(task)
'''

#: The same ordinary loop, declared without goals: this one owns its continuations, and
#: nobody outside it has any say in that.
GOALS_OFF = '''"""A loop that owns its continuations, and says so where it declares its agent."""

from typing import Annotated

from hmz.coganchor.agents import AgentBase, AgentDefaults
from hmz.flows import flow


@flow
def run(
    agents: tuple[Annotated[AgentBase, AgentDefaults(goals=False)]], task: str
) -> None:
    (agent,) = agents
    agent(task)
'''

#: A required goal is the more particular of the two things a flow can write, and wins.
#: Written both ways at once is a flow the checker has something to say about; read back, it
#: is a place run under a goal.
REQUIRED_WHILE_OFF = PURSUING.replace(
    "from hmz.coganchor.agents import AgentBase, Goal",
    "from hmz.coganchor.agents import AgentBase, AgentDefaults, Goal",
).replace(
    "Annotated[AgentBase, Goal]",
    "Annotated[AgentBase, Goal, AgentDefaults(goals=False)]",
)


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
    assert place.goals is True


def test_a_place_declares_whether_its_agent_has_goals(tmp_path: Path) -> None:
    """Which is the flow's to say: nobody else is asked, so nobody else can answer."""
    (place,) = wanted(_written(tmp_path, GOALS_OFF, "goals_off"))

    assert place.goal is False
    assert place.goals is False


def test_a_required_goal_is_a_goal(tmp_path: Path) -> None:
    (place,) = wanted(_written(tmp_path, REQUIRED_WHILE_OFF, "required"))

    assert place.goal is True
    assert place.goals is True


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
        DshAgent(DshAgentConfig(model="m", effort="high")),
        KimiCodeCLIAgent(KimiCodeCLIAgentConfig(model="m", effort="low")),
    ],
)
def test_an_agent_whose_backend_has_one_is_taken(agent: object, tmp_path: Path) -> None:
    """The four that answer `pursue`, each of which says so on the class."""
    runner = Runner(_written(tmp_path, PURSUING), [agent])  # pyright: ignore[reportArgumentType]

    assert len(runner.agents) == 1


def test_a_flow_that_asks_nothing_takes_any_of_them(tmp_path: Path) -> None:
    """A place that says nothing about a goal is one every backend can fill."""
    runner = Runner(
        _written(tmp_path, PLAIN, "plain"),
        [PiAgent(PiAgentConfig(model="m", effort="low"))],
    )

    assert len(runner.agents) == 1


def test_the_runner_settles_goals_from_what_the_flow_declared(tmp_path: Path) -> None:
    """Over whatever the agent was made with: the flow says, and it says for the run."""
    agent = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="m", effort="low"))

    Runner(_written(tmp_path, GOALS_OFF, "goals_off"), [agent])

    assert agent.config.goals is False
    assert not agent.goals_enabled


def test_a_flow_that_says_nothing_leaves_its_agent_as_it_came(tmp_path: Path) -> None:
    """Goals on is the loosest of the two, and a declaration only ever tightens.

    Which is what keeps a call from handing itself more than it was given: a flow that
    mentions nothing declares the loosest of each, and if that settled anything then calling
    one would switch goals back on for an agent somebody switched them off for.
    """
    agent = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="m", effort="low", goals=False))

    Runner(_written(tmp_path, PLAIN, "plain"), [agent])

    assert agent.config.goals is False
    assert not agent.goals_enabled


def test_an_exec_line_leaves_goals_to_the_flow(tmp_path: Path) -> None:
    """The line names a CLI, a model and an effort; the flow says what the work is."""
    where = _written(tmp_path, GOALS_OFF, "goals_off")

    _, agents, _, _, _ = flow_and_agents(
        ["-f", where, "-a", "claude/m:low", "the task"]
    )
    assert agents[0].config.goals is True

    Runner(where, agents)
    assert agents[0].config.goals is False


def test_a_required_goal_cannot_be_switched_off(tmp_path: Path) -> None:
    agent = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="m", effort="low", goals=False))

    with pytest.raises(NotAFlow, match="run under a goal, but goals were switched off"):
        Runner(_written(tmp_path, PURSUING), [agent])


def test_a_required_goal_refuses_an_agent_disabled_in_python(tmp_path: Path) -> None:
    agent = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="m", effort="low"))
    agent.disable_goals()

    assert agent.config.goals is False
    with pytest.raises(NotAFlow, match="run under a goal, but goals were switched off"):
        Runner(_written(tmp_path, PURSUING), [agent])

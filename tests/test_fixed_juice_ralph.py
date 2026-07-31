"""The fixed-juice ralph loop: a ralph loop with a governor on it.

Nothing here runs a coding agent. What is checked is the governing: that the effort moves one
rung a round towards the answer size the flow was set up to hold, that it settles rather than
swings once it is there, and that neither end of the ladder is stepped past.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from humanize.agents import AgentBase, AgentConfig, Event, SessionBase, Usage
from humanize.flows import fixed_juice_ralph

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from pydantic import BaseModel


class _Scripted(AgentBase):
    """An agent whose turns come out with what the test says, at whatever it is thinking at.

    What the flow reads is what the run has been doing lately, and a suite that had to wait
    for a real agent to do it would be a suite nobody runs.
    """

    def __init__(
        self,
        juices: list[float],
        model: str = "claude-opus-5",
    ) -> None:
        super().__init__(AgentConfig(model=model, effort="high"), name="worker")
        #: What `juice()` answers with, one round at a time, and the last of them thereafter.
        self.juices = juices
        #: What it was thinking at as each round's turn was taken.
        self.efforts: list[str] = []
        self.rounds = 0

    @property
    def backend(self) -> str:
        """Claude's, so that the ladder it is governed along is a real one."""
        return "claude"

    def new(self) -> _ScriptedSession:
        return _ScriptedSession(self)

    def juice(self, over: float = 300.0) -> float:
        del over
        at = min(self.rounds, len(self.juices)) - 1
        return self.juices[max(at, 0)] if self.juices else 0.0


class _ScriptedSession(SessionBase):
    def _stream(
        self, prompt: str, *, schema: type[BaseModel] | None = None
    ) -> Iterator[Event]:
        del prompt, schema
        agent = self._agent
        assert isinstance(agent, _Scripted)
        agent.efforts.append(self.effort)
        agent.rounds += 1
        self._adopt(f"session-{agent.rounds}")
        self._spends(Usage(input=10.0, output=100.0))
        yield Event(kind="result", text="done what I could")


class _Enough(Exception):  # noqa: N818  -- the way out of a loop that has no other
    """Raised out of the wait to end a loop that would otherwise run for days."""


#: How many rounds a test runs before the wait ends it.
_ROUNDS = 4


@pytest.fixture
def waits(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Stands in for the wait between rounds, keeping how long each one was to be."""
    rested: list[float] = []

    def slept(seconds: float) -> None:
        rested.append(seconds)
        if len(rested) >= _ROUNDS:
            raise _Enough

    monkeypatch.setattr(fixed_juice_ralph.time, "sleep", slept)
    return rested


def _run(agent: _Scripted, **setting: float) -> None:
    """Runs the loop until the wait says that is enough of it."""
    with pytest.raises(_Enough):
        fixed_juice_ralph.run((agent,), "add undo", fixed_juice_ralph.Config(**setting))


def test_the_ladder_is_the_one_the_agents_own_model_takes() -> None:
    """Read out of `humanize.backends`, which is where every other reader of it looks."""
    rungs = fixed_juice_ralph.ladder(_Scripted([]))

    assert rungs[0] == "ultracode"  # hardest first, as every effort list here is
    assert "low" in rungs
    assert rungs.index("high") < rungs.index("low")


def test_a_model_nobody_wrote_down_is_offered_its_backends_own_ladder() -> None:
    """An account has models this list does not, and they take the same efforts."""
    agent = _Scripted([], model="claude-something-new")

    assert fixed_juice_ralph.ladder(agent)[0] == "ultracode"


def test_thin_answers_have_it_asked_to_think_harder(waits: list[float]) -> None:
    """One rung a round, so that the loop settles rather than swings."""
    agent = _Scripted([50.0, 50.0, 50.0, 50.0])

    _run(agent, juice=2000.0, rest=0.0)

    # It starts where it was configured and climbs a rung after each round.
    assert agent.efforts == ["high", "xhigh", "max", "ultracode"]


def test_it_is_not_asked_to_think_harder_than_its_model_can(waits: list[float]) -> None:
    agent = _Scripted([50.0] * 8)

    _run(agent, juice=2000.0, rest=0.0)

    assert agent.efforts[-1] == "ultracode"
    # And staying there is not an error: the hardest effort is as much as it has to give.
    assert agent.rounds == _ROUNDS


def test_long_answers_have_it_asked_to_think_less(waits: list[float]) -> None:
    agent = _Scripted([9000.0, 9000.0, 9000.0, 9000.0])

    _run(agent, juice=2000.0, rest=0.0)

    assert agent.efforts == [
        "high",
        "medium",
        "low",
        "low",
    ]  # and no further down than that


def test_an_answer_size_inside_the_slack_leaves_the_effort_alone(
    waits: list[float],
) -> None:
    """Or the effort would swing round the target rather than settling on it."""
    agent = _Scripted([2100.0, 1900.0, 2000.0, 2050.0])

    _run(agent, juice=2000.0, slack=0.15, rest=0.0)

    assert set(agent.efforts) == {"high"}


def test_a_round_that_landed_no_turn_leaves_the_effort_where_it_was(
    waits: list[float],
) -> None:
    """Nothing to steer by is nothing to steer by, and not an agent answering with nothing."""
    agent = _Scripted([0.0, 0.0, 0.0, 0.0])

    _run(agent, juice=2000.0, rest=0.0)

    assert set(agent.efforts) == {"high"}


def test_the_wait_between_rounds_is_the_one_it_was_set_up_with(
    waits: list[float],
) -> None:
    """Nothing here is a clock: the wait is a pause, not a rate being held down."""
    agent = _Scripted([2000.0] * 4)

    _run(agent, juice=2000.0, rest=7.0)

    assert waits == [7.0] * _ROUNDS


def test_the_width_of_a_turn_rides_along_with_the_rung() -> None:
    """Kimi's effort says how wide to run as well as how hard, and moving it moves both."""
    agent = _Scripted([])
    agent.effort = "swarmhigh"

    assert fixed_juice_ralph._at(agent, ("max", "high", "low")) == 1


def test_a_flow_that_was_set_up_with_nothing_has_an_answer_size_of_its_own() -> None:
    """A flow with no defaults would be one nobody could run without a file."""
    held = fixed_juice_ralph.Config()

    assert held.juice > 0
    assert held.over >= 10
    assert held.rest >= 0


def test_an_answer_size_of_nothing_is_refused_where_it_is_set_up() -> None:
    """A target of no tokens at all is one no effort could ever be under."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        fixed_juice_ralph.Config(juice=0)


def test_the_flow_says_how_many_agents_it_drives_and_what_it_takes() -> None:
    """Which is what a command line reads before it starts one, and what `/config` asks."""
    from humanize.flows import find
    from humanize.runner import configures, drives

    where = find("fixed_juice_ralph")

    assert drives(where) == (
        "",
    )  # one agent, and the flow calls it nothing in particular
    model = configures(where)
    assert model is not None
    assert set(model.model_fields) == {"juice", "over", "slack", "rest"}


def test_it_is_one_of_the_flows_humanize_came_with() -> None:
    from humanize.flows import BUILTIN, found

    assert (BUILTIN, "fixed_juice_ralph") in found()


@pytest.mark.agent
@pytest.mark.timeout(900)
def test_the_governor_moves_a_real_agents_effort(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The whole chain against the real thing: an answer size read off it, and an effort taken.

    A target far above what any turn of this comes out with, so the loop asks for the next
    rung up each round -- which is the direction that has to reach a real CLI.
    """
    from humanize.agents import ClaudeCodeAgent, ClaudeCodeAgentConfig

    monkeypatch.chdir(
        tmp_path
    )  # an agent that decides to tidy up tidies up nothing of ours
    rounds: list[float] = []

    def slept(seconds: float) -> None:
        rounds.append(seconds)
        if len(rounds) >= 2:
            raise _Enough

    monkeypatch.setattr(fixed_juice_ralph.time, "sleep", slept)
    agent = ClaudeCodeAgent(
        ClaudeCodeAgentConfig(model="claude-haiku-4-5-20251001", effort="high")
    )

    with pytest.raises(_Enough):
        fixed_juice_ralph.run(
            (agent,),
            "Reply with exactly: OK",
            fixed_juice_ralph.Config(juice=100_000.0, rest=0.0, over=60.0),
        )

    assert agent.juice(over=60.0) > 0  # it read a real answer size off a real backend
    # Two rungs up from where it was configured, which the CLI took both times.
    assert agent.effort == "max"
    assert len(agent.opened) == 2  # a fresh session a round, which is what ralph is

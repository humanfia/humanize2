"""The fixed-TPS ralph loop: a ralph loop with a governor on it.

Nothing here runs a coding agent. What is checked is the governing: that the effort moves one
rung a round towards the rate the flow was set up to hold, that it settles rather than swings
once the rate is where it should be, that a turn which produced more than its share is rested
off, and that neither dial is turned past the end of what it has.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from humanize.agents import AgentBase, AgentConfig, Event, SessionBase, Usage
from humanize.flows import fixed_tps_ralph

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from pydantic import BaseModel


class _Scripted(AgentBase):
    """An agent that spends what the test says, at whatever it is being asked to think at.

    Its rate is the test's to say too: what the flow reads is what the run is doing, and a
    suite that had to wait for a real one to do it would be a suite nobody runs.
    """

    def __init__(
        self,
        rates: list[float],
        produces: float = 100.0,
        model: str = "claude-opus-5",
    ) -> None:
        super().__init__(AgentConfig(model=model, effort="high"), name="worker")
        #: What `rate()` answers with, one round at a time, and the last of them thereafter.
        self.rates = rates
        self.produces = produces
        #: What it was thinking at as each round's turn was taken.
        self.efforts: list[str] = []
        self.rounds = 0

    @property
    def backend(self) -> str:
        """Claude's, so that the ladder it is governed along is a real one."""
        return "claude"

    def new(self) -> _ScriptedSession:
        return _ScriptedSession(self)

    def rate(self, over: float = 300.0) -> Usage:
        del over
        at = min(self.rounds, len(self.rates)) - 1
        return Usage(output=self.rates[max(at, 0)] if self.rates else 0.0)


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
        # What the turn produced, which the flow reads off the agent rather than the event.
        self._spends(Usage(input=10.0, output=agent.produces))
        yield Event(kind="result", text="done what I could")


class _Enough(Exception):  # noqa: N818  -- the way out of a loop that has no other
    """Raised out of the wait to end a loop that would otherwise run for days."""


@pytest.fixture
def waits(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Stands in for the wait between rounds, keeping how long each one was to be."""
    rested: list[float] = []

    def slept(seconds: float) -> None:
        rested.append(seconds)
        if len(rested) >= _ROUNDS:
            raise _Enough

    monkeypatch.setattr(fixed_tps_ralph.time, "sleep", slept)
    return rested


#: How many rounds a test runs before the wait ends it.
_ROUNDS = 4


def _run(agent: _Scripted, **setting: float) -> None:
    """Runs the loop until the wait says that is enough of it."""
    with pytest.raises(_Enough):
        fixed_tps_ralph.run((agent,), "add undo", fixed_tps_ralph.Config(**setting))


def test_the_ladder_is_the_one_the_agents_own_model_takes() -> None:
    """Read out of `humanize.backends`, which is where every other reader of it looks."""
    rungs = fixed_tps_ralph.ladder(_Scripted([]))

    assert rungs[0] == "ultracode"  # hardest first, as every effort list here is
    assert "low" in rungs
    assert rungs.index("high") < rungs.index("low")


def test_a_model_nobody_wrote_down_is_offered_its_backends_own_ladder() -> None:
    """An account has models this list does not, and they take the same efforts."""
    agent = _Scripted([], model="claude-something-new")

    assert fixed_tps_ralph.ladder(agent)[0] == "ultracode"


def test_an_agent_under_the_rate_is_asked_to_think_harder(waits: list[float]) -> None:
    """One rung a round, so that the loop settles rather than swings."""
    agent = _Scripted([1.0, 1.0, 1.0, 1.0])

    _run(agent, tps=50.0, rest=0.0)

    # It starts where it was configured and climbs a rung after each round.
    assert agent.efforts == ["high", "xhigh", "max", "ultracode"]


def test_it_is_not_asked_to_think_harder_than_its_model_can(waits: list[float]) -> None:
    agent = _Scripted([1.0] * 8)

    _run(agent, tps=50.0, rest=0.0)

    assert agent.efforts[-1] == "ultracode"
    # And staying there is not an error: the hardest effort is the ceiling on how fast it goes.
    assert agent.rounds == _ROUNDS


def test_an_agent_over_the_rate_is_asked_to_think_less(waits: list[float]) -> None:
    agent = _Scripted([500.0, 500.0, 500.0, 500.0])

    _run(agent, tps=50.0, rest=0.0)

    assert agent.efforts == [
        "high",
        "medium",
        "low",
        "low",
    ]  # and no further down than that


def test_a_rate_inside_the_slack_leaves_the_effort_alone(waits: list[float]) -> None:
    """Or the effort would swing round the target rather than settling on it."""
    agent = _Scripted([52.0, 48.0, 50.0, 51.0])

    _run(agent, tps=50.0, slack=0.15, rest=0.0)

    assert set(agent.efforts) == {"high"}


def test_what_a_turn_produced_is_rested_off_over_the_seconds_it_is_worth(
    waits: list[float],
) -> None:
    """A hundred tokens at ten a second ought to have taken ten seconds, so it waits them."""
    agent = _Scripted([50.0] * 4, produces=100.0)

    _run(agent, tps=10.0, rest=0.0)

    # The turn itself takes no measurable time here, so the whole ten seconds are the wait.
    assert waits[0] == pytest.approx(10.0, abs=0.5)


def test_a_turn_that_produced_nothing_still_waits_the_shortest_wait(
    waits: list[float],
) -> None:
    """A loop that spun on a backend saying nothing would spin as fast as it could ask."""
    agent = _Scripted([0.0] * 4, produces=0.0)

    _run(agent, tps=50.0, rest=5.0)

    assert waits == [5.0] * _ROUNDS


def test_the_width_of_a_turn_rides_along_with_the_rung() -> None:
    """Kimi's effort says how wide to run as well as how hard, and moving it moves both."""
    agent = _Scripted([])
    agent.effort = "swarmhigh"

    assert fixed_tps_ralph._at(agent, ("max", "high", "low")) == 1


def test_a_flow_that_was_set_up_with_nothing_has_a_rate_of_its_own() -> None:
    """A flow with no defaults would be one nobody could run without a file."""
    held = fixed_tps_ralph.Config()

    assert held.tps > 0
    assert held.over >= 10
    assert held.rest >= 0


def test_a_rate_of_nothing_is_refused_where_it_is_set_up() -> None:
    """Dividing by it is what the wait is worked out with, hours before the first turn."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        fixed_tps_ralph.Config(tps=0)


def test_the_flow_says_how_many_agents_it_drives_and_what_it_takes() -> None:
    """Which is what a command line reads before it starts one, and what `/config` asks."""
    from humanize.flows import find
    from humanize.runner import configures, drives

    where = find("fixed_tps_ralph")

    assert drives(where) == (
        "",
    )  # one agent, and the flow calls it nothing in particular
    model = configures(where)
    assert model is not None
    assert set(model.model_fields) == {"tps", "over", "slack", "rest"}


def test_it_is_one_of_the_flows_humanize_came_with() -> None:
    from humanize.flows import BUILTIN, found

    assert (BUILTIN, "fixed_tps_ralph") in found()


@pytest.mark.agent
@pytest.mark.timeout(900)
def test_the_governor_moves_a_real_agents_effort(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The whole chain against the real thing: a rate read off it, and an effort it takes.

    A target far above what any turn of this does, so the loop asks for the next rung up each
    round -- which is the direction that has to reach a real CLI, since the other one is a
    wait this suite would only be sitting through.
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

    monkeypatch.setattr(fixed_tps_ralph.time, "sleep", slept)
    agent = ClaudeCodeAgent(
        ClaudeCodeAgentConfig(model="claude-haiku-4-5-20251001", effort="high")
    )

    with pytest.raises(_Enough):
        fixed_tps_ralph.run(
            (agent,),
            "Reply with exactly: OK",
            fixed_tps_ralph.Config(tps=100_000.0, rest=0.0, over=60.0),
        )

    assert agent.spent().output > 0  # it read a real rate off a real backend
    assert agent.rate(over=60.0).output > 0
    # Two rungs up from where it was configured, which the CLI took both times.
    assert agent.effort == "max"
    assert len(agent.opened) == 2  # a fresh session a round, which is what ralph is

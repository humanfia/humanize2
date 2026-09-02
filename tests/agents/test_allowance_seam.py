"""Where a run's allowance bites, which is every session of every backend and no driver's.

The check is on `SessionBase` itself rather than on a moment a flow hangs a hook on, so what
is proved here is that it reaches a turn whatever is driving it, that a turn which ran out
raises rather than answering with nothing a loop would read as a failed round, that the first
reading which comes up short stops every agent of the run at once rather than one at a time,
and that the person at the prompt is outside all of it -- a flow whose other side is a person
must still be able to say that it stopped.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

import pytest

from hmz.coganchor.agents import (
    Allowance,
    Event,
    HumanAgent,
    Ledger,
    SessionBase,
    Stopped,
    Usage,
)
from hmz.coganchor.agents.base import AgentBase
from hmz.coganchor.agents.config import AgentConfig

if TYPE_CHECKING:
    import os
    from collections.abc import Iterator

    from pydantic import BaseModel

#: What one turn of the stand-in below is said to have written. A thousandth of a million, so
#: that `Allowance(tokens=0.001)` is exactly one turn's worth and the second turn is over it.
EACH = 1000.0


class _Session(SessionBase):
    """A turn that says `ok` and spends :data:`EACH` output tokens saying it.

    A stand-in rather than a real CLI, because what is under test is the seam every driver
    inherits: the shortest turn that reaches it is one that spends a known amount.
    """

    def _stream(
        self, prompt: str, *, schema: type[BaseModel] | None = None
    ) -> Iterator[Event]:
        self._id = "stand-in"
        self._spends(Usage({"input": 1.0, "output": EACH}))
        yield Event(kind="result", text="ok")


class _Turn(AgentBase):
    """An agent of a backend that counts what it writes, on a model nobody prices."""

    counts: ClassVar[frozenset[str]] = frozenset({"input", "output"})

    def new(self, cwd: str | os.PathLike[str] | None = None) -> _Session:
        return _Session(self, cwd)


def _agent(name: str = "") -> _Turn:
    """One stand-in agent, made the way a run makes the agents it was given."""
    return _Turn(AgentConfig(model="stand-in", effort="high"), name=name or None)


def test_a_turn_under_a_spent_allowance_is_stopped() -> None:
    """Raised rather than answered empty: a loop cannot tell "" from a round that failed."""
    agent = _agent()
    ledger = Ledger(Allowance(tokens=EACH / 1_000_000), [agent])
    agent.allowance = ledger
    session = agent.new()

    assert session("first") == "ok"  # inside it, and the turn answers as any turn does

    with pytest.raises(Stopped, match="output tokens spent"):
        session("second")


def test_the_turn_that_spends_the_last_of_it_still_answers() -> None:
    """A turn cut off has still done what it did, and its work is worth reading.

    Read as a failure it would be taken again, on an allowance that is already spent, which
    is a loop taking every round it has left for nothing.
    """
    agent = _agent()
    ledger = Ledger(Allowance(tokens=EACH / 1_000_000), [agent])
    agent.allowance = ledger

    assert agent.new()("go") == "ok"
    assert ledger.spent


def test_the_first_reading_that_comes_up_short_stops_every_agent() -> None:
    """The allowance is the run's, so it is spent for every session of it at once.

    Which is why there is no set of blocked sessions to collect before the run can stop: a
    turn running elsewhere on the run's money is a turn to end, not one to wait for.
    """
    working = _agent("working")
    beside = _agent("beside")
    ledger = Ledger(Allowance(tokens=EACH / 1_000_000), [working, beside])
    working.allowance = beside.allowance = ledger
    held = beside.new()
    held("something")  # so that the other agent has an open conversation to lose

    assert ledger.spent
    assert working.stopped
    assert beside.stopped
    assert held._ended


def test_a_run_inside_every_dimension_takes_its_turns() -> None:
    """Nothing here may stop a run that is inside all of what it was given."""
    agent = _agent()
    agent.allowance = Ledger(Allowance(hours=1, tokens=1000, dollars=1000), [agent])
    session = agent.new()

    assert [session(str(at)) for at in range(3)] == ["ok", "ok", "ok"]


def test_a_run_out_of_clock_is_stopped_though_it_has_spent_nothing() -> None:
    """The one dimension that moves whether or not anything is being spent.

    Which is what stops a loop whose turns are all failing: a failed turn spends nothing, so
    a token cap would leave it going round for free forever.
    """
    agent = _agent()
    # A few microseconds, which making the ledger and reaching the turn have already taken.
    ledger = Ledger(Allowance(hours=1e-9), [agent])
    agent.allowance = ledger

    with pytest.raises(Stopped, match="h spent"):
        agent.new()("go")


def test_a_clone_spends_the_runs_allowance_and_is_stopped_with_it() -> None:
    """A flow that works only through clones is a flow the allowance must still reach."""
    agent = _agent()
    ledger = Ledger(Allowance(tokens=EACH / 1_000_000), [agent])
    agent.allowance = ledger
    made = agent.clone()

    assert made.allowance is ledger
    assert made.new()("first") == "ok"
    with pytest.raises(Stopped):
        made.new()("second")
    # The agent that spent nothing, stopped by the money its clone spent for the run.
    assert agent.stopped


def test_a_session_closing_on_the_end_of_it_is_read_as_spent() -> None:
    """So that a run whose last conversation closes on its allowance is filed as stopped.

    A session that takes its last turn and is dropped never reaches another turn edge, and a
    run nobody read again would be written down as having finished what it was doing.
    """
    agent = _agent()
    ledger = Ledger(Allowance(tokens=EACH / 2_000_000), [agent])
    agent.allowance = ledger
    session = agent.new()
    session._started = (
        True  # a conversation that was opened, as a turn would have opened it
    )
    agent._meter.spend(Usage({"output": EACH}))
    session.close()

    assert ledger.spent


def test_the_person_is_not_stopped_when_the_run_runs_out() -> None:
    """Because the run would then have nobody left to tell that it had stopped.

    A flow that is a conversation says so by speaking to the person, and a person who had
    been stopped raises on that line instead of hearing it -- so a flow that asks a question
    before giving up would never ask it. They spend nothing, being no model, so stopping them
    saves nothing either.
    """
    working = _agent()
    person = HumanAgent()
    ledger = Ledger(Allowance(tokens=EACH / 1_000_000), [working, person])
    working.allowance = person.allowance = ledger
    working.new()("go")

    assert ledger.spent  # the run is over its allowance, and every spender is stopped
    assert working.stopped
    assert not person.stopped
    assert person.new()("the run stopped -- anything else?") == ""


def test_what_the_person_spends_is_not_counted() -> None:
    """There is nothing of an allowance that is theirs: no token, no dollar, no minute.

    Counted, they would also mark every cap of a run of theirs unreadable, a person
    reporting no tokens and being on no price list -- which would put a line on a run's
    first turn saying a cap cannot bite when the cap is the only thing that can.
    """
    person = HumanAgent()
    ledger = Ledger(Allowance(tokens=0.001, dollars=5), [person])
    person._meter.spend(Usage({"output": 10_000.0}))  # as though they had spent it

    read = ledger.reads()

    assert read.output == 0.0
    assert read.blind == frozenset()
    assert ledger.over() == ""


def test_an_agent_nobody_gave_an_allowance_is_held_to_nothing() -> None:
    """An agent driven by hand is not a run of anything, and so is nobody's budget."""
    agent = _agent()

    assert agent.allowance is None
    assert agent.new()("go") == "ok"

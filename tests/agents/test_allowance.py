"""What a whole run may spend, and the reckoning that adds up what it has.

The value is three caps and one comparison; what is checked here is that each of the three
bites on its own, that nothing is capped unless it is named, that a negative one is refused
where it is written rather than an hour into the run it was meant to hold, and that the
reckoning over a run's agents answers the two questions a run's money is hard to answer:
what has been spent when some of the run is priced and some of it is not, and which caps
cannot be read at all for the agents this run happens to be driving.
"""

from __future__ import annotations

from typing import ClassVar

import pytest

from hmz.coganchor.agents import (
    Allowance,
    CodexAgent,
    CodexAgentConfig,
    Ledger,
    PiAgent,
    PiAgentConfig,
    Usage,
    unreadable,
    unwatched,
)

#: A model nobody lists, which is what leaves a run's bill unreadable. What is priced comes
#: from the `priced` fixture, so that no test here reaches the network for a unit price.
UNLISTED = "nobody-lists-this-model"


class _Priced(PiAgent):
    """An agent of a backend that counts what it writes, on a model somebody prices."""


class _Blind(CodexAgent):
    """An agent whose backend reports nothing at all, so nothing of it can be read."""

    counts: ClassVar[frozenset[str]] = frozenset()


def _spent(agent: _Priced | _Blind, **kinds: float) -> None:
    """Puts tokens on an agent's own meter, which is what a turn of it would have done."""
    agent._meter.spend(Usage(kinds))


def test_an_allowance_caps_nothing_it_was_not_given() -> None:
    """Which is what a run under no allowance is, and what every dimension's 0 means."""
    assert not Allowance().bounded
    assert not Allowance(hours=0, tokens=0, dollars=0).bounded
    assert Allowance().over(seconds=10**9, output=10**12, dollars=10**6) == ""

    assert Allowance(hours=1).bounded
    assert Allowance(tokens=1).bounded
    assert Allowance(dollars=1).bounded


@pytest.mark.parametrize(
    ("said", "reads", "why"),
    [
        (Allowance(hours=2), {"seconds": 7200.0}, "2h"),
        (Allowance(tokens=1.5), {"output": 1_500_000.0}, "1.5M output tokens"),
        (Allowance(dollars=50), {"dollars": 50.0}, "$50"),
    ],
)
def test_each_dimension_bites_on_its_own(
    said: Allowance, reads: dict[str, float], why: str
) -> None:
    """One cap named is one cap held to, and the others say nothing about the run."""
    assert said.over(**reads) == why
    # And a hair under it is a run still inside what it was given.
    short = {name: value * 0.99 for name, value in reads.items()}
    assert said.over(**short) == ""


def test_a_bill_nobody_can_read_never_reaches_the_cap() -> None:
    """A model nobody prices is a run whose money is unknown, not a run that was free.

    Stopping on `None` would stop every run of an unpriced model the moment it started, for a
    figure that was never measured.
    """
    assert Allowance(dollars=1).over(dollars=None) == ""


@pytest.mark.parametrize("said", [{"hours": -1}, {"tokens": -0.5}, {"dollars": -0.01}])
def test_an_allowance_below_nothing_is_refused(said: dict[str, float]) -> None:
    """Where it is written, rather than as a run that stops before it has started."""
    with pytest.raises(ValueError, match="less than nothing"):
        Allowance(**said)


def test_the_run_is_read_over_every_agent_in_it(priced: str) -> None:
    """Two agents under one allowance spend one allowance, which is what a run's money is."""
    first = _Priced(PiAgentConfig(model=priced, effort="high"))
    second = _Priced(PiAgentConfig(model=priced, effort="high"))
    ledger = Ledger(Allowance(tokens=1.0), [first, second])
    _spent(first, input=100, output=400_000)
    _spent(second, input=100, output=400_000)

    read = ledger.reads()

    assert read.output == 800_000
    assert read.dollars is not None
    assert not read.floor
    assert ledger.over() == ""

    _spent(second, output=200_000)

    assert ledger.over() == "1M output tokens"


def test_a_clones_spending_counts_toward_the_run(priced: str) -> None:
    """A flow that does all its work through clones would otherwise read as free.

    Two agents are two lines in a trace, because tracing is about identity; they are one
    allowance, because an allowance is about the run's money and a clone spends the run's.
    """
    agent = _Priced(PiAgentConfig(model=priced, effort="high"))
    ledger = Ledger(Allowance(tokens=1.0), [agent])
    agent.allowance = ledger
    made = agent.clone()
    _spent(made, output=1_000_000)

    assert made.allowance is ledger
    assert made in ledger.agents()
    assert ledger.reads().output == 1_000_000
    assert ledger.over() == "1M output tokens"


def test_an_unpriced_model_leaves_the_money_unknown_and_says_so(priced: str) -> None:
    """None rather than 0.00, and a dollars cap that cannot bite says so rather than not."""
    agent = _Priced(PiAgentConfig(model=UNLISTED, effort="high"))
    ledger = Ledger(Allowance(dollars=5), [agent])
    _spent(agent, input=1000, output=5_000_000)

    read = ledger.reads()

    assert read.dollars is None
    assert not read.floor  # nothing is priced, so there is no figure to be short of
    assert read.blind == frozenset({"dollars"})
    assert ledger.over() == ""


def test_a_run_half_of_which_is_priced_reads_its_bill_as_a_floor(priced: str) -> None:
    """A column quietly short of one agent's bill is worse than one marked as short of it."""
    listed = _Priced(PiAgentConfig(model=priced, effort="high"))
    beyond = _Priced(PiAgentConfig(model=UNLISTED, effort="high"))
    ledger = Ledger(Allowance(dollars=1000), [listed, beyond])
    _spent(listed, input=1000, output=1000)
    _spent(beyond, input=1000, output=1000)

    read = ledger.reads()

    assert read.dollars is not None
    assert read.floor
    assert read.blind == frozenset()  # something here is priced, so the cap can bite


def test_a_run_nothing_counts_says_the_token_cap_cannot_bite() -> None:
    """A backend that reports no tokens at all is a token cap that would never fire."""
    agent = _Blind(CodexAgentConfig(model=UNLISTED, effort="high"))
    ledger = Ledger(Allowance(tokens=1.0, dollars=5), [agent])

    assert ledger.reads().blind == frozenset({"tokens", "dollars"})


def test_a_dimension_nobody_asked_for_is_never_called_unreadable() -> None:
    """Blindness is about a cap that will not bite, and an unset cap was not going to."""
    agent = _Blind(CodexAgentConfig(model=UNLISTED, effort="high"))

    assert Ledger(Allowance(hours=1), [agent]).reads().blind == frozenset()


def test_what_ran_out_is_held_once_it_has(priced: str) -> None:
    """An allowance only ever runs out, so a second reading must not unstop the run."""
    agent = _Priced(PiAgentConfig(model=priced, effort="high"))
    ledger = Ledger(Allowance(tokens=0.001), [agent])
    _spent(agent, output=2000)

    assert ledger.over() == "0.001M output tokens"
    assert ledger.spent
    # The meter cannot go down, but the answer is held rather than reckoned again in any case:
    # a run that unstopped itself would take another turn on money it has not got.
    agent._meter._total.clear()

    assert ledger.over() == "0.001M output tokens"


@pytest.mark.parametrize(
    ("effective", "declared", "asked"),
    [
        # A flow with no opinion, left with no cap: nobody has said anything, so ask.
        (Allowance(), None, True),
        # A flow that wrote `Allowance()` in its own file: it has said so, so do not.
        (Allowance(), Allowance(), False),
        # A flow that declared a cap and had it overridden away. It said what a run of it is
        # worth; it did not say a run of it under nothing is what it is for -- so ask, or a
        # flow declaring six hours would be the one flow nobody is warned about zeroing.
        (Allowance(), Allowance(hours=6), True),
        # And anything that caps something is not the question at all.
        (Allowance(hours=1), None, False),
    ],
)
def test_who_is_asked_about_a_run_nothing_will_stop(
    effective: Allowance, declared: Allowance | None, asked: bool
) -> None:
    """The claim is read off the flow rather than off whether it said anything."""
    assert unwatched(effective, declared) is asked


def test_a_cap_nothing_can_read_is_said_however_it_was_handed_in() -> None:
    """Taken as it is given, a generator would be drained by the first field looked for.

    And the whole of what this is for is saying that a cap will never bite, so answering ""
    for a run whose caps nothing can read is the one wrong answer it has.
    """
    written = unreadable(name for name in ("tokens", "dollars"))

    assert "tokens" in written
    assert "dollars" in written


def test_an_unbounded_run_reads_no_meter_at_all() -> None:
    """Nothing is measured for a run that cannot reach the end of what it was given."""
    ledger = Ledger(Allowance())

    assert ledger.over() == ""
    assert not ledger.spent

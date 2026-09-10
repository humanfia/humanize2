"""What a flow is doing, kept from the turns going past.

The flow itself says nothing about its own shape -- it is a Python file that may branch any
way it likes -- so the order it ran its agents in is only ever recoverable from the turns.
"""

from __future__ import annotations

import pytest

from hmz.tui.monitor import Monitor, lasting


def test_who_is_working_is_whoever_has_a_turn_open() -> None:
    monitor = Monitor()

    monitor.begins("actor", "opus")
    assert monitor.now_working() == ["actor"]

    monitor.ends("actor")
    assert monitor.now_working() == []


def test_an_agent_holding_two_turns_at_once_stops_when_both_do() -> None:
    """One session ending is not the agent stopping: a flow may drive two of them at once."""
    monitor = Monitor()
    monitor.begins("actor", "opus")
    monitor.begins("actor", "opus")

    monitor.ends("actor")
    assert monitor.now_working() == ["actor"]  # the other turn is still open

    monitor.ends("actor")
    assert monitor.now_working() == []


def test_the_shape_is_who_handed_to_whom_and_how_often() -> None:
    """An actor and the reviewer reading its work, twice around: that is the shape of rlar."""
    monitor = Monitor()
    for _ in range(2):
        for agent in ("actor", "reviewer"):
            monitor.begins(agent, "opus")
            monitor.ends(agent)

    shape = monitor.shape()

    assert shape.turns == {"actor": 2, "reviewer": 2}
    assert shape.working == frozenset()
    assert shape.handovers[("actor", "reviewer")] == 2
    assert shape.handovers[("reviewer", "actor")] == 1  # the second round back round


def test_the_shape_is_taken_whole_rather_than_read_as_it_moves() -> None:
    """What is drawn is one moment of the run, not three moments of three counters."""
    monitor = Monitor()
    monitor.begins("actor", "opus")

    shape = monitor.shape()
    monitor.ends("actor")
    monitor.begins("reviewer", "opus")

    assert shape.working == frozenset({"actor"})
    assert shape.turns == {"actor": 1}


def test_an_agent_taking_two_turns_running_hands_to_nobody() -> None:
    monitor = Monitor()
    for _ in range(2):
        monitor.begins("actor", "opus")
        monitor.ends("actor")

    assert monitor.handovers == {}
    assert monitor.turns["actor"] == 2


def test_spending_is_counted_per_model_and_not_per_agent() -> None:
    """Two agents at one model are one line: what is being watched is the model's bill."""
    monitor = Monitor()
    monitor.begins("actor", "opus")
    monitor.begins("reviewer", "opus")
    monitor.begins("cheap", "haiku")

    monitor.spend("actor", 100)
    monitor.spend("reviewer", 300)
    monitor.spend("cheap", 50)

    spending = monitor.spending()
    assert [(spend.model, spend.tokens) for spend in spending] == [
        ("opus", 400),
        ("haiku", 50),
    ]


def test_the_rate_is_the_last_five_minutes_of_the_clock() -> None:
    """Of the clock, not of the turns: a flow is a program, and its own time counts too.

    It sleeps off a failed round, commits, reads what the last turn wrote -- all inside the
    window, all seconds the tokens were spent over. And while the run is younger than the
    window, the run is the window: a minute-old run is not divided by five minutes.
    """
    monitor = Monitor()
    monitor.began = 1000.0
    monitor.begins("actor", "opus")
    monitor.spend("actor", 3000, now=1030.0)

    (spending,) = monitor.spending(now=1060.0)

    assert spending.tokens == 3000
    assert spending.rate == 50.0  # over the minute the run has had, turn or no turn


def test_the_rate_is_worked_out_again_when_what_it_is_made_of_moves() -> None:
    """Adaptively rather than on a clock of its own.

    What moves it is tokens counted, or tokens ageing out of the window. A screen redrawn
    twice a second against numbers that have not changed is a number nobody can read.
    """
    monitor = Monitor()
    monitor.began = 1000.0
    monitor.spend("actor", 3000, now=1030.0)

    (first,) = monitor.spending(now=1060.0)

    assert first.rate == 50.0

    (again,) = monitor.spending(
        now=1070.0
    )  # nothing new counted, so nothing new worked out

    assert again.rate == 50.0

    monitor.spend(
        "actor", 3000, now=1071.0
    )  # and something new counted is worked out at once
    (moved,) = monitor.spending(now=1071.0)

    assert moved.tokens == 6000
    assert moved.rate == 6000 / 71.0


def test_two_sources_counting_the_same_tokens_are_not_two_lots_of_tokens() -> None:
    """The log a backend keeps and the backend's own report are one spend, seen twice.

    The log is ahead while the turn runs, being written as the turn goes; the backend catches
    up when the turn ends. What was spent is whatever the one that has seen furthest says.
    """
    monitor = Monitor()

    monitor.counted("read", "opus", 4000)  # mid-turn, out of the log
    assert monitor.spending()[0].tokens == 4000

    monitor.spend(
        "actor", 5000, model="opus"
    )  # the turn ends, and the backend says 5000
    assert monitor.spending()[0].tokens == 5000

    monitor.counted(
        "read", "opus", 5000
    )  # the log catches up, and nothing is counted twice
    assert monitor.spending()[0].tokens == 5000

    monitor.counted("read", "opus", 4000)  # a log read again from the top says no more
    assert monitor.spending()[0].tokens == 5000


def test_what_falls_out_of_the_window_stops_counting() -> None:
    """A flow that has gone quiet reads as quiet, which is what a window is for."""
    monitor = Monitor()
    monitor.began = 1000.0
    monitor.spend("actor", 6000, now=1030.0)
    monitor.spend("actor", 30000, now=4000.0)

    (windowed,) = monitor.spending(now=4090.0)

    assert windowed.tokens == 36000  # all told
    assert windowed.rate == 100.0  # but only the last five minutes, over five minutes

    monitor.until = 4100.0  # and the clock stops where the run did
    monitor.figured = None

    (over,) = monitor.spending(now=9999.0)

    assert (
        over.rate == 100.0
    )  # what it was doing at the end, not a rate decaying after it


def test_nothing_spent_is_nothing_shown() -> None:
    monitor = Monitor()
    monitor.begins("actor", "opus")
    monitor.spend("actor", 0)

    assert monitor.spending() == []


def test_a_box_says_how_long_its_agent_has_been_at_what_it_is_doing() -> None:
    """Which is two different lengths of time: a turn open, and a wait since the last one."""
    monitor = Monitor()
    monitor.begins("actor", "opus", now=1000.0)
    monitor.begins("reviewer", "opus", now=1010.0)
    monitor.ends("reviewer", now=1020.0)
    monitor.until = 1030.0  # a run that is over is read at its own end

    shape = monitor.shape()

    assert shape.since["actor"] == 30.0  # working, so since its turn began
    assert shape.since["reviewer"] == 10.0  # stopped, so since its last turn ended


def test_an_agent_holding_two_turns_has_been_working_since_the_first_of_them() -> None:
    """The second turn is not the agent starting: it never stopped between the two."""
    monitor = Monitor()
    monitor.begins("actor", "opus", now=1000.0)
    monitor.begins("actor", "opus", now=1015.0)
    monitor.until = 1020.0

    assert monitor.shape().since["actor"] == 20.0


def test_the_handover_taken_last_is_the_one_the_diagram_lights() -> None:
    """Where the run just went is the first thing a reader looks for, and only this says it."""
    monitor = Monitor()
    assert monitor.shape().latest is None  # nothing has been handed anywhere yet

    for agent in ("actor", "reviewer"):
        monitor.begins(agent, "opus")
        monitor.ends(agent)

    assert monitor.shape().latest == ("actor", "reviewer")

    monitor.begins("actor", "opus")
    assert monitor.shape().latest == ("reviewer", "actor")

    monitor.ends("actor")
    monitor.begins("actor", "opus")  # a second turn running hands to nobody
    assert monitor.shape().latest == ("reviewer", "actor")


def test_a_clock_is_read_in_whatever_units_it_is_worth_reading_in() -> None:
    """Seconds while a turn is young, minutes once it is not, and never a wider box."""
    assert lasting(0.4) == "0s"
    assert lasting(43.0) == "43s"
    assert lasting(75.0) == "1m15s"
    assert lasting(605.0) == "10m05s"
    assert lasting(3661.0) == "1h01m"


def test_a_model_nobody_prices_is_tokens_and_no_bill_at_all() -> None:
    """The whole honesty of the money: `$0.00` against an unlisted model is a lie."""
    monitor = Monitor()
    monitor.begins("actor", "a-model-nobody-lists")
    monitor.spend("actor", 4000, kinds={"input": 3000, "output": 1000})

    (spending,) = monitor.spending()

    assert spending.tokens == 4000
    assert spending.dollars is None


def test_the_bill_is_the_kinds_at_their_own_rates(priced: str) -> None:
    """Not the tokens at an average of them: an output token is five times an input one."""
    monitor = Monitor()
    monitor.begins("actor", priced)
    monitor.spend("actor", 1040, kinds={"input": 1000, "output": 40})

    (spending,) = monitor.spending()

    assert spending.tokens == 1040
    assert spending.dollars == pytest.approx(1000 / 1e6 * 1 + 40 / 1e6 * 5)


def test_a_source_that_says_no_kinds_says_no_bill(priced: str) -> None:
    """A lump of tokens is a lump nobody can put a figure on, listed model or not."""
    monitor = Monitor()
    monitor.begins("actor", priced)
    monitor.spend("actor", 1040)

    (spending,) = monitor.spending()

    assert spending.tokens == 1040
    assert spending.dollars is None


def test_the_bill_is_read_off_whichever_source_has_seen_the_most(priced: str) -> None:
    """The same rule the count follows: two sources counting one spend are one bill."""
    monitor = Monitor()
    monitor.counted("told", priced, 1040, kinds={"input": 1000, "output": 40})
    monitor.counted("read", priced, 2080, kinds={"input": 2000, "output": 80})

    (spending,) = monitor.spending()

    assert spending.tokens == 2080
    assert spending.dollars == pytest.approx(2 * (1000 / 1e6 * 1 + 40 / 1e6 * 5))


def test_a_source_that_says_the_kinds_is_believed_over_one_that_says_a_lump(
    priced: str,
) -> None:
    """A log catching up on a backend that said a total is a bill where there was none.

    The two are counting the same tokens, so the total does not move -- and the money still
    has to be worked out again, or the first `None` would stand for the rest of the run.
    """
    monitor = Monitor()
    monitor.spend(
        "actor", 1040, model=priced
    )  # the backend, saying only what it came to

    assert monitor.spending()[0].dollars is None

    monitor.counted("read", priced, 1040, kinds={"input": 1000, "output": 40})

    (spending,) = monitor.spending()

    assert spending.tokens == 1040  # the same tokens, seen twice
    assert spending.dollars == pytest.approx(1000 / 1e6 * 1 + 40 / 1e6 * 5)


def test_a_source_saying_the_kinds_of_fewer_tokens_is_still_the_one_priced(
    priced: str,
) -> None:
    """The log lags the backend by a second, and the backend may say only a total.

    Ranked on the total alone, the bigger lump would win and the bill would stay blank for
    the rest of the run with a full reckoning of most of it sitting right beside it.
    """
    monitor = Monitor()
    monitor.spend(
        "actor", 1050, model=priced
    )  # the backend: a lump, and the larger one
    monitor.counted("read", priced, 1000, kinds={"input": 900, "output": 100})

    (spending,) = monitor.spending()

    assert spending.tokens == 1050  # counted off whichever has seen the most
    assert spending.dollars == pytest.approx(900 / 1e6 * 1 + 100 / 1e6 * 5)


def test_a_source_reporting_nothing_at_all_does_not_stop_the_monitor(
    priced: str,
) -> None:
    """A breakdown of a total of nought is still a source, and still must not raise."""
    monitor = Monitor()

    monitor.counted("read", priced, 0, kinds={"input": 5})

    assert monitor.spending() == []  # nothing spent, so nothing to show


def test_a_breakdown_does_not_outlive_the_total_it_was_of(priced: str) -> None:
    """A source that stops saying which kinds is a source with no bill to give, again."""
    monitor = Monitor()
    monitor.counted("read", priced, 1040, kinds={"input": 1000, "output": 40})

    assert monitor.spending()[0].dollars is not None

    monitor.counted("read", priced, 9000)  # a bigger total, and nothing about its kinds

    (spending,) = monitor.spending()

    assert spending.tokens == 9000
    assert spending.dollars is None  # rather than nine thousand priced as one thousand

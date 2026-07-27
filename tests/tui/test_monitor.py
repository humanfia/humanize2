"""What a flow is doing, kept from the turns going past.

The flow itself says nothing about its own shape -- it is a Python file that may branch any
way it likes -- so the order it ran its agents in is only ever recoverable from the turns.
"""

from __future__ import annotations

from humanize.tui.monitor import Monitor


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


def test_the_graph_is_who_handed_to_whom_and_how_often() -> None:
    """An actor and the reviewer reading its work, twice around: that is the shape of rlar."""
    monitor = Monitor()
    for _ in range(2):
        for agent in ("actor", "reviewer"):
            monitor.begins(agent, "opus")
            monitor.ends(agent)

    graph = "\n".join(monitor.graph())

    assert "actor" in graph and "reviewer" in graph
    assert monitor.handovers[("actor", "reviewer")] == 2
    assert monitor.handovers[("reviewer", "actor")] == 1  # the second round back round
    assert monitor.turns["actor"] == 2


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

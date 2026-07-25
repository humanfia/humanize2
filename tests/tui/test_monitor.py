"""What a flow is doing, kept from the turns going past.

The flow itself says nothing about its own shape -- it is a Python file that may branch any
way it likes -- so the order it ran its agents in is only ever recoverable from the turns.
"""

from __future__ import annotations

from amflows.tui.monitor import Monitor


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


def test_the_rate_is_what_was_spent_lately_and_falls_back_to_nothing() -> None:
    """A flow that has stopped must read as stopped, not as whatever it once averaged."""
    monitor = Monitor()
    monitor.begins("actor", "opus")

    monitor.spend("actor", 3000, now=1000.0)

    (spending,) = monitor.spending(now=1000.0)
    assert spending.tokens == 3000
    assert spending.rate == 100.0  # 3000 over the thirty seconds behind us

    (later,) = monitor.spending(now=2000.0)
    assert later.tokens == 3000  # still spent
    assert later.rate == 0.0  # but not lately


def test_nothing_spent_is_nothing_shown() -> None:
    monitor = Monitor()
    monitor.begins("actor", "opus")
    monitor.spend("actor", 0)

    assert monitor.spending() == []

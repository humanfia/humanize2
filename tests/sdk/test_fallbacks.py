"""Where a turn goes when the place taking it cannot take it, reached through the SDK.

The store itself is `tests/test_fallback_command.py`'s and `hmz.fallbacks`'s. What is checked
here is the other half of the promise the SDK makes: that a step written from here is the step
a command line lists and the interface's own menu reads back, and that the three things which
can happen to one -- pointed somewhere, told how to try again, taken away -- are the same three
whichever way in wrote them.
"""

from __future__ import annotations

import pytest

from hmz.sdk import Hmz


def test_how_a_failed_turn_waits_unless_somebody_said_otherwise_is_one_of_the_policies() -> (
    None
):
    held = Hmz().fallbacks

    assert held.default in [one.name for one in held.policies()]


def test_the_waits_are_offered_hardest_last() -> None:
    """Which is the order a menu of them is drawn in, so it is the order they come in."""
    names = [one.name for one in Hmz().fallbacks.policies()]

    assert names[0] == "none"
    assert len(names) == len(set(names))


def test_a_wait_is_found_by_name_and_a_name_none_of_them_goes_by_is_nothing() -> None:
    held = Hmz().fallbacks

    found = held.named(held.default)

    assert found is not None
    assert found.name == held.default
    assert held.named("not-a-policy") is None


def test_a_place_is_read_back_as_it_is_written_down() -> None:
    assert Hmz().fallbacks.reads("claude/opus") == "claude/opus"


def test_a_spelling_no_place_answers_to_reads_as_nothing() -> None:
    assert Hmz().fallbacks.reads("definitely-not-a-backend/whatever") == ""


def test_a_place_is_spelled_out_of_the_three_things_a_place_is() -> None:
    held = Hmz().fallbacks

    assert held.spec("claude", "opus", "mine") == "claude@mine/opus"
    # And an account nobody named is the one this machine is already signed into.
    assert held.spec("claude", "opus") == "claude/opus"


def test_a_place_nothing_is_written_against_says_nothing_rather_than_missing() -> None:
    """A menu asks every place what it does, including the ones nobody has answered for."""
    written = Hmz().fallbacks.tried("claude/opus")

    assert written.spec == "claude/opus"
    assert written.to == ""
    assert written.tries == 0
    assert written.timeout == 0.0


def test_a_place_that_falls_back_nowhere_is_a_chain_of_itself_alone() -> None:
    assert Hmz().fallbacks.chain("claude/opus") == ["claude/opus"]


def test_a_step_written_from_here_is_the_chain_and_the_listing_a_line_walks() -> None:
    held = Hmz().fallbacks

    step = held.points("claude/opus", "codex/gpt")

    assert step.spec == "claude/opus"
    assert step.to == "codex/gpt"
    assert held.chain("claude/opus") == ["claude/opus", "codex/gpt"]
    assert [one.spec for one in held.all()] == ["claude/opus"]


def test_a_step_that_would_point_at_itself_is_refused() -> None:
    with pytest.raises(ValueError, match="cannot fall back to itself"):
        Hmz().fallbacks.points("claude/opus", "claude/opus")


def test_a_step_from_a_place_that_is_not_one_is_refused() -> None:
    with pytest.raises(ValueError, match="is not a place"):
        Hmz().fallbacks.points("definitely-not-a-backend/whatever", "codex/gpt")


def test_how_a_failed_turn_is_taken_again_is_written_on_the_same_row_as_the_step() -> (
    None
):
    """Both are answers to the one thing that happened, so one row holds them."""
    held = Hmz().fallbacks
    held.points("claude/opus", "codex/gpt")

    step = held.retrying("claude/opus", 3, "linear", 30.0)

    assert step.tries == 3
    assert step.policy == "linear"
    assert step.timeout == 30.0
    # And writing the one did not forget the other.
    assert step.to == "codex/gpt"
    assert [one.spec for one in held.all()] == ["claude/opus"]


def test_trying_again_by_a_wait_that_is_not_one_is_refused() -> None:
    with pytest.raises(ValueError, match="is not a retry policy"):
        Hmz().fallbacks.retrying("claude/opus", 3, "not-a-policy", 0.0)


def test_a_step_taken_away_is_a_place_that_falls_back_nowhere_again() -> None:
    held = Hmz().fallbacks
    held.points("claude/opus", "codex/gpt")

    assert held.clear("claude/opus")

    assert held.chain("claude/opus") == ["claude/opus"]
    assert held.all() == []
    # And there is nothing left to take away a second time.
    assert not held.clear("claude/opus")

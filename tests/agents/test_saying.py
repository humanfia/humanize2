"""The fragments every streaming backend answers in, gathered back into what was said."""

from __future__ import annotations

from hmz.coganchor.agents import Event, Saying


def _said(events: list[Event]) -> list[tuple[str, str]]:
    """The kind and the words of each event, which is the whole of what these carry."""
    return [(one.kind, one.text) for one in events]


def test_a_run_of_fragments_is_one_thing_said() -> None:
    saying = Saying()
    for piece in ("one ", "sentence, ", "in four ", "pieces."):
        saying.delta("text", piece)

    assert _said(saying.ended()) == [("text", "one sentence, in four pieces.")]


def test_a_fragment_is_not_said_until_something_asks_for_the_answer() -> None:
    saying = Saying()
    saying.delta("text", "half a ")
    saying.delta("text", "sentence")

    assert _said(saying.upto()) == [("text", "half a sentence")]
    assert saying.upto() == []  # and not again: it has been said


def test_what_led_up_to_a_tool_call_is_said_before_the_call() -> None:
    saying = Saying()
    saying.delta("reasoning", "I should look")
    saying.delta("text", "Reading the file")

    assert _said(saying.upto()) == [
        ("reasoning", "I should look"),
        ("text", "Reading the file"),
    ]

    saying.delta("text", " and then this one")

    assert _said(saying.ended()) == [("text", "and then this one")]


def test_the_whole_message_adds_only_what_nobody_has_seen() -> None:
    saying = Saying()
    saying.delta("text", "Hello")
    saying.upto()
    saying.whole("text", "Hello, world")

    assert _said(saying.ended()) == [("text", ", world")]


def test_a_whole_message_the_pieces_do_not_match_is_said_from_the_start() -> None:
    """A backend that trimmed or respaced its own deltas is not sliced at a stale offset."""
    saying = Saying()
    saying.delta("text", "  Let me check the file.")
    saying.upto()
    saying.whole("text", "Let me check the file. Done.")

    assert _said(saying.ended()) == [("text", "Let me check the file. Done.")]


def test_thinking_is_shown_before_talking_whichever_arrived_first() -> None:
    saying = Saying()
    saying.delta("text", "Looking now")
    saying.delta("reasoning", "the file first")

    assert _said(saying.ended()) == [
        ("reasoning", "the file first"),
        ("text", "Looking now"),
    ]


def test_a_backend_that_streamed_nothing_says_the_whole_of_it() -> None:
    saying = Saying()
    saying.whole("text", "all at once")

    assert _said(saying.ended()) == [("text", "all at once")]


def test_two_answers_in_flight_do_not_run_into_each_other() -> None:
    saying = Saying()
    saying.delta("text", "first", "a")
    saying.delta("text", "second", "b")

    assert _said(saying.ended("a")) == [("text", "first")]
    assert _said(saying.ended("b")) == [("text", "second")]


def test_the_event_that_names_no_answer_means_the_one_being_streamed() -> None:
    saying = Saying()
    saying.delta("text", "streamed", "a")
    saying.whole("text", "streamed and finished")

    assert _said(saying.ended()) == [("text", "streamed and finished")]


def test_a_stream_that_stops_says_everything_it_was_holding() -> None:
    saying = Saying()
    saying.delta("reasoning", "thought", "a")
    saying.delta("text", "said", "a")
    saying.delta("text", "and this", "b")

    assert _said(saying.rest()) == [
        ("reasoning", "thought"),
        ("text", "said"),
        ("text", "and this"),
    ]
    assert saying.rest() == []


def test_fragments_of_only_whitespace_are_not_a_thing_said() -> None:
    saying = Saying()
    saying.delta("text", "\n\n  ")

    assert saying.ended() == []

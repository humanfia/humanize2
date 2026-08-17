"""The frames the socket between a run and the terminals reading it carries.

A stream socket hands back whatever has arrived, which is half a frame as often as it is two,
so what is checked here is that what went in comes out whole however it was cut up -- and that
a length no frame of this protocol has is refused rather than waited for.
"""

from __future__ import annotations

import pytest

from hmz.daemon import proto


def test_a_frame_comes_back_as_it_went_in() -> None:
    frames = proto.Frames()

    said = list(frames.feed(proto.frame(proto.OUTPUT, b"hello")))

    assert said == [(proto.OUTPUT, b"hello")]


def test_two_frames_in_one_read_are_two_frames() -> None:
    frames = proto.Frames()
    both = proto.frame(proto.INPUT, b"a") + proto.frame(proto.INPUT, b"bc")

    assert list(frames.feed(both)) == [(proto.INPUT, b"a"), (proto.INPUT, b"bc")]


def test_a_frame_cut_in_half_is_held_until_the_rest_arrives() -> None:
    frames = proto.Frames()
    whole = proto.frame(proto.OUTPUT, b"a screen")

    for at in range(len(whole) - 1):
        assert list(frames.feed(whole[at : at + 1])) == []
    assert list(frames.feed(whole[-1:])) == [(proto.OUTPUT, b"a screen")]


def test_a_frame_handed_over_is_not_handed_over_again() -> None:
    """A terminal told the run is over stops reading, and must not be told twice."""
    frames = proto.Frames()
    both = proto.frame(proto.OUTPUT, b"one") + proto.frame(proto.GONE, b"over")

    for kind, _payload in frames.feed(both):
        if kind == proto.GONE:
            break  # as a terminal that has been let go of does

    assert list(frames.feed(b"")) == []
    assert list(frames.feed(proto.frame(proto.OUTPUT, b"two"))) == [
        (proto.OUTPUT, b"two")
    ]


def test_what_is_left_over_is_kept_and_what_was_whole_is_not() -> None:
    """Two frames and a piece of a third, which is what a read off a busy socket is."""
    frames = proto.Frames()
    said = (
        proto.frame(proto.OUTPUT, b"one")
        + proto.frame(proto.OUTPUT, b"two")
        + proto.frame(proto.OUTPUT, b"three")[:5]
    )

    assert list(frames.feed(said)) == [
        (proto.OUTPUT, b"one"),
        (proto.OUTPUT, b"two"),
    ]
    assert list(frames.feed(proto.frame(proto.OUTPUT, b"three")[5:])) == [
        (proto.OUTPUT, b"three")
    ]


def test_an_empty_payload_is_a_frame() -> None:
    """`GONE` carries a reason and `HELLO` carries a size; either may be nothing at all."""
    frames = proto.Frames()

    assert list(frames.feed(proto.frame(proto.GONE))) == [(proto.GONE, b"")]


def test_a_length_no_frame_of_this_has_is_refused() -> None:
    """A socket carrying something else is a socket to close, not one to allocate for."""
    frames = proto.Frames()

    with pytest.raises(ValueError, match="not one of these"):
        list(frames.feed(proto.OUTPUT + b"\xff\xff\xff\xff"))


def test_a_mapping_goes_and_comes_back() -> None:
    said = proto.spoken(proto.CONTROL, {"do": "status"})
    frames = proto.Frames()

    ((kind, payload),) = frames.feed(said)

    assert kind == proto.CONTROL
    assert proto.asked(payload) == {"do": "status"}


@pytest.mark.parametrize("payload", [b"", b"not json", b"[1, 2]", b"\xff"])
def test_anything_that_is_not_a_mapping_reads_as_nothing_said(payload: bytes) -> None:
    """A frame from something that is not this is answered rather than raised about."""
    assert proto.asked(payload) == {}

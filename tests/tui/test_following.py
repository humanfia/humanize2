"""The transcript stays at the end while it is at the end, and only somebody else moves it.

What a flow writes is written at the bottom, so a transcript that is not following the end is
a transcript with the run happening off the screen. It stops following when somebody scrolls
up to read something -- that is the point of it -- and it must not stop for anything else, and
everything else on this screen shares the terminal with it: a list of commands opens over it,
the editor grows a row for every line typed into it, the terminal is resized. Each of those
leaves the last line further up the screen without anybody having asked for it, and the
transcript has to be at the end again by the time the next thing is written.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.panel import Panel
from textual.events import MouseScrollDown, MouseScrollUp

from hmz.tui import Humanize
from hmz.tui.selecting import Transcript

if TYPE_CHECKING:
    from textual.pilot import Pilot


async def filled(driver: Pilot[None], lines: int = 60) -> Transcript:
    """Puts more in the transcript than the terminal can hold, so that there is an end to be at.

    Long enough lines to be wrapped over more rows in a narrower terminal, since a transcript
    that came out the same height at every width would say nothing about a resize.

    Args:
      driver: The interface being driven.
      lines: How many lines to write.

    Returns:
      The transcript, scrolled to the end of them.
    """
    transcript = driver.app.query_one("#transcript", Transcript)
    transcript.clear()
    for at in range(lines):
        transcript.write(f"line {at} {'word ' * 12}")
    await driver.pause()
    assert transcript.max_scroll_y > 0  # or there is no end to be away from
    return transcript


async def wheeled(driver: Pilot[None], *, up: bool, times: int = 1) -> None:
    """Rolls the wheel over the transcript, which is how somebody scrolls away from the end.

    Args:
      driver: The interface being driven.
      up: Whether to roll it up, away from the end, rather than down towards it.
      times: How many notches.
    """
    for _ in range(times):
        await driver._post_mouse_events(
            [MouseScrollUp if up else MouseScrollDown],
            widget="#transcript",
            offset=(5, 5),
        )
    await driver.pause()


async def test_what_is_written_is_at_the_end_of_it() -> None:
    """The plain case: a flow writing a line at a time is read where it is being written."""
    app = Humanize()
    async with app.run_test(size=(80, 24)) as driver:
        transcript = await filled(driver)

        assert transcript.scroll_offset.y == transcript.max_scroll_y


async def test_something_opening_over_it_does_not_stop_it_following() -> None:
    """A slash opens the commands above the prompt, which takes ten rows off the transcript.

    Nobody scrolled anything: the transcript is shorter than it was, and its end is further
    down than it was. This is the everyday way for a transcript to be left behind, since it
    happens to anybody who starts typing a command while a flow is running.
    """
    app = Humanize()
    async with app.run_test(size=(80, 24)) as driver:
        transcript = await filled(driver)
        was = transcript.container_size.height

        await driver.press("/")
        await driver.pause()
        assert transcript.container_size.height < was  # the offers did open over it

        assert transcript.scroll_offset.y == transcript.max_scroll_y
        transcript.write("said while the offers are up")
        await driver.pause()
        assert transcript.scroll_offset.y == transcript.max_scroll_y


async def test_a_resize_does_not_stop_it_following() -> None:
    """A narrower terminal wraps the same transcript over more rows, and the end moves down.

    Wider, and it moves up. Either way what is written next belongs on the screen.
    """
    app = Humanize()
    async with app.run_test(size=(80, 24)) as driver:
        transcript = await filled(driver)

        for width, height in ((50, 24), (100, 24), (100, 40)):
            await driver.resize_terminal(width, height)
            await driver.pause()
            assert transcript.scroll_offset.y == transcript.max_scroll_y
            transcript.write(f"said at {width} by {height}")
            await driver.pause()
            assert transcript.scroll_offset.y == transcript.max_scroll_y


async def test_it_stays_where_somebody_scrolled_it_to() -> None:
    """Which is the whole reason it is not simply pinned: what is being read stays readable."""
    app = Humanize()
    async with app.run_test(size=(80, 24)) as driver:
        transcript = await filled(driver)

        await wheeled(driver, up=True, times=3)
        reading = transcript.scroll_offset.y
        assert reading < transcript.max_scroll_y

        for at in range(5):
            transcript.write(f"written under it {at}")
            await driver.pause()
        assert transcript.scroll_offset.y == reading

        # nor does the terminal changing size carry them off to the end of it
        await driver.resize_terminal(70, 24)
        await driver.pause()
        assert transcript.scroll_offset.y < transcript.max_scroll_y


async def test_scrolling_back_down_to_the_end_follows_it_again() -> None:
    """Coming back to the bottom is how somebody says they are done reading further up."""
    app = Humanize()
    async with app.run_test(size=(80, 24)) as driver:
        transcript = await filled(driver)

        await wheeled(driver, up=True, times=3)
        assert transcript.scroll_offset.y < transcript.max_scroll_y

        await wheeled(driver, up=False, times=20)
        assert transcript.scroll_offset.y == transcript.max_scroll_y

        transcript.write("said once they are back at the end")
        await driver.pause()
        assert transcript.scroll_offset.y == transcript.max_scroll_y


async def test_coming_back_to_the_end_leaves_it_where_it_is_scrolled_sideways() -> None:
    """A box Rich drew too wide for the terminal is read by scrolling across it.

    Which is a place to be reading from as much as a line further up is, and reaching the end
    of the transcript again is not a reason to be taken back to the left of it.
    """
    app = Humanize()
    async with app.run_test(size=(80, 24)) as driver:
        transcript = await filled(driver)
        transcript.write(Panel("wide" * 40, width=200), shrink=False)
        await driver.pause()
        assert transcript.max_scroll_x > 40  # the box is wider than the terminal

        transcript.scroll_to(x=40, animate=False)
        await wheeled(driver, up=True, times=3)
        await wheeled(driver, up=False, times=20)

        assert transcript.scroll_offset.x == 40
        assert transcript.scroll_offset.y == transcript.max_scroll_y

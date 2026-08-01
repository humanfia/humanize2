"""Taking text off the screen with the mouse: what comes back is what was written.

The interface has the mouse -- it draws the highlight itself, and the terminal never sees the
drag -- so a selection is only worth anything if what it gives back is the text rather than
the screen. These check the difference: a line that took four rows comes back as one line,
with no break where the terminal ran out of room and no spaces where a row was padded out to
the edge, and letting go of it puts it on the clipboard.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.panel import Panel
from textual.events import MouseDown, MouseMove, MouseUp
from textual.widgets.option_list import Option

from hmz.tui import Humanize
from hmz.tui.app import Editor
from hmz.tui.selecting import Choices, Transcript

if TYPE_CHECKING:
    from textual.events import MouseEvent
    from textual.pilot import Pilot

#: A line far longer than any terminal, whose words are all different: a selection out of the
#: middle of it can only have come from where it says it did.
LONG = " ".join(f"word{at:02d}" for at in range(40))

#: The same, in a script whose characters are two columns wide apiece -- where a count of
#: columns and a count of characters are two different numbers, and only one of them is what
#: a selection is measured in.
WIDE = "".join(f"第{at:02d}个字" for at in range(20))


async def drag(
    driver: Pilot[None],
    start: tuple[int, int],
    end: tuple[int, int],
    over: str = "#transcript",
) -> None:
    """Drags across something, from one place on it to another.

    Args:
      driver: The interface being driven.
      start: Where the drag begins, as a column and a row of what is dragged across.
      end: Where it ends.
      over: What is dragged across.
    """
    for moment, offset in ((MouseDown, start), (MouseMove, end), (MouseUp, end)):
        happens: list[type[MouseEvent]] = [moment]
        await driver._post_mouse_events(happens, widget=over, offset=offset, button=1)
    await driver.pause()


def written(app: Humanize, *lines: str) -> Transcript:
    """Puts known lines in the transcript, with nothing else on it.

    Args:
      app: The interface.
      lines: What to write, a line apiece.

    Returns:
      The transcript, so that what it made of them can be read.
    """
    transcript = app.query_one("#transcript", Transcript)
    transcript.clear()
    for line in lines:
        transcript.write(line)
    return transcript


async def test_a_line_that_wrapped_comes_back_as_the_line() -> None:
    """Which is the whole point: no newline where the terminal ran out of room."""
    app = Humanize()
    async with app.run_test(size=(60, 24)) as driver:
        transcript = written(app, LONG)
        await driver.pause()
        assert len(transcript._rows) > 1  # it did wrap, or this proves nothing

        await drag(driver, (0, 0), (10, 2))

        taken = app.screen.get_selected_text()
        assert taken is not None
        assert "\n" not in taken
        assert "  " not in taken  # nor the spaces a row is padded out to the edge with
        assert LONG.startswith(taken)
        assert len(taken) > 60  # over a row's worth, so it did come off more than one


async def test_a_selection_across_lines_keeps_the_breaks_that_were_written() -> None:
    """One newline per line that was written, however many rows each of them took."""
    app = Humanize()
    async with app.run_test(size=(60, 24)) as driver:
        transcript = written(app, LONG, "the second line")
        await driver.pause()
        rows = len(transcript._rows)

        await drag(driver, (0, 0), (15, rows - 1))

        taken = app.screen.get_selected_text()
        assert taken == f"{LONG}\nthe second line"


async def test_a_selection_is_measured_in_characters_rather_than_columns() -> None:
    """A character two columns wide is one character, and is where the selection says."""
    app = Humanize()
    async with app.run_test(size=(60, 24)) as driver:
        written(app, WIDE)
        await driver.pause()

        await drag(driver, (4, 0), (10, 0))

        # Column four is the fourth column and the fourth character, `第` having taken two of
        # them; and the character the far end lands on is taken too, as a terminal's own
        # selection takes it.
        assert app.screen.get_selected_text() == WIDE[3:7]


async def test_letting_go_of_a_selection_copies_it() -> None:
    """A clipboard is the only place a selection can go: the terminal never saw the drag."""
    app = Humanize()
    async with app.run_test(size=(60, 24)) as driver:
        written(app, LONG)
        await driver.pause()

        await drag(driver, (0, 0), (10, 1))

        assert app._clipboard == app.screen.get_selected_text()
        assert app._clipboard
        assert "copied" in str(app.query_one("#status").render())


async def test_clicking_twice_takes_the_word_and_three_times_the_line() -> None:
    """Rather than the whole transcript, which is what textual's own answer to both is."""
    app = Humanize()
    async with app.run_test(size=(60, 24)) as driver:
        written(app, LONG)
        await driver.pause()

        await driver.click("#transcript", offset=(3, 0), times=2)
        await driver.pause()
        assert app.screen.get_selected_text() == "word00"
        assert app._clipboard == "word00"

        await driver.click("#transcript", offset=(3, 1), times=3)
        await driver.pause()
        assert app.screen.get_selected_text() == LONG


async def test_the_terminal_changing_width_wraps_it_again() -> None:
    """The rows are wrapped again, and the text they are rows of is the same text."""
    app = Humanize()
    async with app.run_test(size=(60, 24)) as driver:
        transcript = written(app, LONG)
        await driver.pause()
        narrow = len(transcript._rows)

        await driver.resize_terminal(40, 24)
        await driver.pause()

        assert transcript.text == LONG
        assert len(transcript._rows) > narrow


async def test_the_terminal_changing_width_lets_go_of_a_selection() -> None:
    """A box Rich drew is as many lines as it has rows, so the lines under it move."""
    app = Humanize()
    async with app.run_test(size=(80, 24)) as driver:
        transcript = written(app)
        transcript.write(
            Panel("a box, which is as many lines as it is rows"), shrink=False
        )
        for line in ("first line", "second line", "third line"):
            transcript.write(line)
        await driver.pause()
        rows = len(transcript._rows)

        await drag(driver, (0, rows - 2), (8, rows - 1))
        assert app.screen.get_selected_text() == "second line\nthird lin"
        await driver.resize_terminal(50, 24)
        await driver.pause()

        # Gone rather than moved: what it was over is not where it was.
        assert not app.screen.get_selected_text()


async def test_the_transcript_is_selected_from_without_taking_the_prompt() -> None:
    """A click that starts a selection must not be a click that stops the typing working."""
    app = Humanize()
    async with app.run_test(size=(60, 24)) as driver:
        written(app, LONG)
        await driver.pause()

        await drag(driver, (0, 0), (10, 1))

        assert app.focused is app.query_one(Editor)


async def test_what_is_typed_is_copied_off_the_editor_too() -> None:
    """The one thing on the screen that holds a selection of its own, being typed into."""
    app = Humanize()
    async with app.run_test(size=(60, 24)) as driver:
        await driver.press(*"hello world")
        await driver.pause()

        await drag(driver, (0, 0), (5, 0), over="#editor")

        assert app._clipboard == "hello"


async def test_the_transcript_is_exported_as_it_was_written() -> None:
    """A file of lines broken where the terminal ran out of room is one nothing reads back."""
    app = Humanize()
    async with app.run_test(size=(60, 24)) as driver:
        transcript = written(app, LONG, "the second line")
        await driver.pause()

        assert transcript.text == f"{LONG}\nthe second line"


async def test_a_drag_from_a_line_with_nothing_on_it_takes_what_it_covered() -> None:
    """A blank line says nothing about itself, and textual reads that as the whole widget."""
    app = Humanize()
    async with app.run_test(size=(60, 24)) as driver:
        written(app, "first line", "", "second line", "", "third line")
        await driver.pause()

        # The far end of a drag takes the character it lands on, as a terminal's does.
        await drag(driver, (0, 1), (6, 2))

        assert app.screen.get_selected_text() == "\nsecond "


async def test_a_drag_from_under_the_last_line_takes_from_the_end_of_it() -> None:
    """The room below a short transcript is a place a drag begins, not the whole of it."""
    app = Humanize()
    async with app.run_test(size=(60, 24)) as driver:
        written(app, "first line", "second line")
        await driver.pause()

        # Upwards, out of the empty room three rows below the text.
        await drag(driver, (10, 5), (6, 0))

        assert app.screen.get_selected_text() == "line\nsecond line"


async def test_a_list_is_selected_and_copied_as_the_rows_it_offers() -> None:
    """A model id in a list is a thing to put in a command line, so it can be taken."""
    app = Humanize()
    async with app.run_test(size=(80, 24)) as driver:
        offers = app.query_one("#offers", Choices)
        offers.add_options([Option("first choice"), Option("second choice")])
        offers.add_class("offering")
        await driver.pause()

        await drag(driver, (0, 0), (4, 1), over="#offers")

        taken = app.screen.get_selected_text() or ""
        # Both rows, without the spaces each is padded out to the width of the list with.
        assert taken.startswith("first choice\n")
        assert "second choice".startswith(taken.split("\n")[1])
        assert "  " not in taken
        assert app._clipboard == taken


async def test_a_row_of_a_list_too_long_for_it_comes_back_as_one_line() -> None:
    """A list wraps a row it cannot hold, and the row is still the line it was written as."""
    app = Humanize()
    async with app.run_test(size=(40, 24)) as driver:
        offers = app.query_one("#offers", Choices)
        offers.add_options([Option(LONG)])
        offers.add_class("offering")
        await driver.pause()

        await drag(driver, (0, 0), (10, 2), over="#offers")

        taken = app.screen.get_selected_text()
        assert taken is not None
        assert "\n" not in taken
        assert LONG.startswith(taken)
        assert len(taken) > 40  # over a row's worth, so it did come off more than one


async def test_a_spacer_between_two_groups_of_choices_takes_only_itself() -> None:
    """A row with nothing on it is a blank line rather than a reason to take the lot."""
    app = Humanize()
    async with app.run_test(size=(80, 24)) as driver:
        offers = app.query_one("#offers", Choices)
        offers.add_options(
            [Option("first choice"), Option("", disabled=True), Option("second choice")]
        )
        offers.add_class("offering")
        await driver.pause()

        await drag(driver, (0, 1), (6, 2), over="#offers")

        taken = app.screen.get_selected_text() or ""
        assert taken.startswith("\n")  # the spacer, which is a line with nothing on it
        assert "second choice".startswith(taken[1:])
        assert taken[1:]  # and the row under it, which the drag ended on


async def test_clicking_twice_on_a_row_of_a_list_takes_the_word_under_it() -> None:
    """Under it: a list is drawn a couple of columns in, and a word is where it looks."""
    app = Humanize()
    async with app.run_test(size=(80, 24)) as driver:
        offers = app.query_one("#offers", Choices)
        offers.add_options([Option("alpha beta gamma"), Option("second choice")])
        offers.add_class("offering")
        await driver.pause()

        # Column eight of the widget is column six of the row, which is `beta`.
        await driver.click("#offers", offset=(8, 0), times=2)
        await driver.pause()

        assert app.screen.get_selected_text() == "beta"
        assert app._clipboard == "beta"


async def test_a_list_that_can_be_selected_is_still_a_list_that_is_picked_from() -> (
    None
):
    """A click is a choice and only a drag is a selection, or the sheets stop working."""
    app = Humanize()
    async with app.run_test(size=(80, 24)) as driver:
        offers = app.query_one("#offers", Choices)
        offers.add_options([Option("first choice"), Option("second choice")])
        offers.add_class("offering")
        await driver.pause()

        await driver.click("#offers", offset=(2, 1))
        await driver.pause()

        assert offers.highlighted == 1
        assert not app.screen.get_selected_text()

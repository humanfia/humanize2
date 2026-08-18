"""Enter, when it does not arrive by itself: a pasted line, or a proxy writing one at a time.

A terminal hands over whatever has arrived since it was last read, so a bracketed paste and
anything driving the interface through a pty deliver a line and its carriage return in one
go. What is checked here is that the line still goes -- for a person a lost enter is a key to
press again, and for a driver that writes once and never retries it is a command that
silently did nothing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from textual import events
from textual.keys import _character_to_key
from textual.widgets import OptionList

from hmz.tui import Humanize
from hmz.tui.app import Editor
from hmz.tui.selecting import Transcript

if TYPE_CHECKING:
    from collections.abc import Sequence

    from textual.pilot import Pilot


async def in_one_read(app: Humanize, driver: Pilot[None], keys: Sequence[str]) -> None:
    """Delivers several keystrokes with nothing pumped between them.

    Which is what a terminal does: one read of the tty is however many bytes had arrived,
    and each of them reaches the interface before any of them has been acted on. The pilot
    settles the interface between one key and the next, so it cannot say this by itself.

    Args:
      app: The interface.
      driver: What is pumping it, waited on once every key is in.
      keys: The keys, as characters -- and any key of a name of its own, such as `enter`.
    """
    for key in keys:
        # Named the way the parser names them, so that what lands is what a terminal sends.
        named = _character_to_key(key) if len(key) == 1 else key
        pressed = events.Key(named, key if len(key) == 1 else None)
        pressed.set_sender(app)
        app.post_message(pressed)
    await driver.pause()


def _transcript(app: Humanize) -> str:
    """Everything the interface has shown, as one searchable string."""
    return app.query_one("#transcript", Transcript).text


@pytest.mark.timeout(60)
async def test_a_whole_line_and_its_enter_in_one_read_is_still_sent() -> None:
    """A pasted line goes, rather than being left in the prompt with its enter dropped."""
    app = Humanize()
    async with app.run_test() as driver:
        editor = app.query_one(Editor)

        await in_one_read(app, driver, [*"paste this", "enter"])

        assert editor.text == ""  # nothing left behind for a second enter to send
        assert app.history.back("") == "paste this"  # all of it, not a tail of it
        assert "no coding agent is installed here" in _transcript(app)


@pytest.mark.timeout(60)
async def test_two_lines_pasted_together_go_one_after_the_other() -> None:
    """A paste of several lines is several things said, in the order they were written."""
    app = Humanize()
    async with app.run_test() as driver:
        editor = app.query_one(Editor)

        await in_one_read(app, driver, [*"first", "enter", *"second", "enter"])

        assert editor.text == ""
        assert app.history.back("") == "second"  # newest first, walking back
        assert app.history.back("") == "first"


@pytest.mark.timeout(60)
async def test_a_line_typed_a_key_at_a_time_is_still_sent() -> None:
    """The way somebody types it, which is the one that always worked."""
    app = Humanize()
    async with app.run_test() as driver:
        editor = app.query_one(Editor)

        await driver.press(*"typed out")
        await driver.press("enter")
        await driver.pause()

        assert editor.text == ""
        assert app.history.back("") == "typed out"
        assert "no coding agent is installed here" in _transcript(app)


@pytest.mark.timeout(60)
async def test_enter_still_takes_what_is_offered() -> None:
    """Over an open list enter means take the one under the cursor, as it always did."""
    app = Humanize()
    async with app.run_test() as driver:
        editor = app.query_one(Editor)

        await driver.press(*"/fl")
        await driver.pause()
        assert app.query_one("#offers", OptionList).has_class("offering")

        await driver.press("enter")
        await driver.pause()

        assert editor.text == "/flow "  # taken, not sent
        assert "no such command" not in _transcript(app)


@pytest.mark.timeout(60)
async def test_an_offer_that_no_longer_finishes_the_line_is_not_taken() -> None:
    """The list is drawn from a message, so it can be a keystroke behind what was typed.

    `/f` offers `/fallback` first; the `l` that arrived with the enter makes it an offer
    about a line nobody is typing any more, and enter over it must not put it in.
    """
    app = Humanize()
    async with app.run_test() as driver:
        editor = app.query_one(Editor)
        await driver.press(*"/f")
        await driver.pause()
        offers = app.query_one("#offers", OptionList)
        under = offers.get_option_at_index(offers.highlighted or 0)
        assert str(under.id) == "/fallback"

        await in_one_read(app, driver, ["l", "enter"])

        assert "/fallback" not in editor.text
        assert app.history.back("") == "/fl"  # sent as it stood instead
        assert "no such command: /fl" in _transcript(app)


@pytest.mark.timeout(60)
async def test_a_line_break_lands_where_it_was_typed_rather_than_ahead_of_the_line() -> (
    None
):
    """The break waits its turn too, or the enter behind it sends two lines joined.

    Applied as it is matched, the break goes in ahead of the characters still queued at the
    editor: `abc` and `def` become one line and what is sent is neither of them.
    """
    app = Humanize()
    async with app.run_test() as driver:
        editor = app.query_one(Editor)

        await in_one_read(app, driver, [*"abc", "ctrl+j", *"def", "enter"])

        assert editor.text == ""
        assert app.history.back("") == "abc\ndef"


@pytest.mark.timeout(60)
async def test_esc_arriving_with_the_enter_puts_the_offers_away_first() -> None:
    """Which is what esc means, and the enter behind it is then about the line itself."""
    app = Humanize()
    async with app.run_test() as driver:
        editor = app.query_one(Editor)
        await driver.press(*"/fl")
        await driver.pause()
        assert app.query_one("#offers", OptionList).has_class("offering")

        await in_one_read(app, driver, ["escape", "enter"])

        assert editor.text == ""
        assert app.history.back("") == "/fl"  # sent as it stood, not completed


@pytest.mark.timeout(60)
async def test_tab_arriving_with_the_enter_takes_the_offer_once() -> None:
    """Tab is what takes one; the enter behind it sends what taking it left."""
    app = Humanize()
    async with app.run_test() as driver:
        editor = app.query_one(Editor)
        await driver.press(*"/fl")
        await driver.pause()

        await in_one_read(app, driver, ["tab", "enter"])

        assert editor.text == ""
        assert app.history.back("") == "/flow"  # taken once, then sent

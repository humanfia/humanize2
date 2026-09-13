"""Where a sheet's keys are said, which is one place and once.

A menu has a row of keys under it and a line about itself above it, and for a long time both
said what the keys were: nine sheets named a key in the line about them and named it again at
the bottom, and one of them said a whole sentence twice. That is a key learned twice, and it
is width taken off a list to say nothing.

So the row is built in one place -- :meth:`hmz.tui.pick.Sheet._footed` -- and what that buys
is the rule being checkable rather than remembered. These are the checks: that row is the
only place `#keys` is written, no sheet names a key twice in it, and the line about a sheet
names no key at all.

And the two things that row now has to say: saving a menu, which is a row set below the
choices and a chord, and the key that cycles whatever the arrows adjust.
"""

from __future__ import annotations

import re
import unittest.mock
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from textual.widgets import Label, OptionList

import hmz.tui.pick
from hmz.coganchor.backends import Model
from hmz.tui import Humanize
from hmz.tui.pick import (
    _ADD,
    _SAVE,
    Adjusts,
    Agent,
    Alike,
    Confirms,
    Epics,
    Fallbacks,
    Falls,
    Fetches,
    Flows,
    Flowverses,
    Leaves,
    Providers,
    Reports,
    Retries,
    Sheet,
    Speaks,
    Unbounded,
)

from .test_app import into_agent, into_flows, onto, rows, until

if TYPE_CHECKING:
    from collections.abc import Callable

    from textual.screen import Screen

#: One installed CLI at two efforts, so that the sheets an agent is set up on have both a
#: list to pick from and a rung to step along.
CLAUDE = {"claude": (Model("claude-opus-5", ("max", "high")),)}

#: How a key reads when it is named in prose. The line about a sheet MUST NOT name one -- the
#: row under the list is where the keys are said -- so this is what to look for up there. A
#: letter key is looked for as the idiom this interface wrote them in, `a adds one`, rather
#: than on its own: a bare `a` is also the commonest word in English.
_NAMES = re.compile(
    r"\b(?:enter|esc|escape|tab|space|backspace|arrows?)\b"
    r"|[←→↑↓]"
    r"|\b(?:ctrl|shift)\+\w+"
    r"|\b[a-z] (?:to |adds?|asks?|makes?|opens?|copies|fetches|puts|says|twice)\b",
    re.IGNORECASE,
)


def once(sheet: Screen[Any]) -> None:
    """Asserts that one sheet says each of its keys once, and says them only at the bottom.

    Args:
      sheet: The sheet, as it is drawn now. What its keys are depends on which row the cursor
        is on and on whether a search is running, so this is asked of whatever is on the
        screen rather than of the class it is of.
    """
    assert isinstance(sheet, Sheet)
    keyed = [one.key for one in sheet._keyed]

    assert keyed, f"{type(sheet).__name__} says no keys at all"
    assert len(keyed) == len(set(keyed)), f"{type(sheet).__name__} says {keyed}"
    # And the line about the sheet says what the sheet is, and nothing about how to work it.
    about = str(sheet.query_one("#about", Label).content)
    found = _NAMES.search(about)
    assert found is None, f"{type(sheet).__name__} names {found and found.group()!r}"


def test_the_keys_are_written_in_one_place() -> None:
    """Which is what makes `said once` a thing to check rather than a thing to remember."""
    source = Path(str(hmz.tui.pick.__file__)).read_text(encoding="utf-8")

    assert source.count('"#keys"') == 1


@pytest.mark.timeout(60)
@pytest.mark.parametrize(
    "opens",
    [
        pytest.param(Confirms, id="confirms"),
        pytest.param(Unbounded, id="unbounded"),
        pytest.param(partial(Leaves, held=True), id="leaves"),
        pytest.param(Reports, id="reports"),
        pytest.param(Fetches, id="fetches"),
        pytest.param(Speaks, id="speaks"),
        pytest.param(Flowverses, id="flowverses"),
        pytest.param(partial(Falls, "claude", "one"), id="falls"),
        pytest.param(
            partial(Retries, "claude/m:high", 3, "exponential", 60.0), id="retries"
        ),
        pytest.param(Epics, id="epics"),
        pytest.param(partial(Fallbacks, dict(CLAUDE)), id="fallbacks"),
        pytest.param(Providers, id="providers"),
        pytest.param(
            partial(
                Adjusts,
                enable_sentry=None,
                workspace="/tmp/somewhere",
                flow="chat",
                agents=1,
                flows=1,
            ),
            id="adjusts",
        ),
    ],
)
async def test_a_sheet_says_each_of_its_keys_once(
    opens: Callable[[], Sheet[Any]],
) -> None:
    app = Humanize()
    async with app.run_test() as driver:
        await app.push_screen(opens())
        await until(lambda: isinstance(app.screen, Sheet), driver)
        await driver.pause()

        once(app.screen)


@pytest.mark.timeout(60)
@unittest.mock.patch("hmz.tui.app.installed", return_value=CLAUDE)
async def test_the_menus_walked_into_say_each_of_their_keys_once(
    _installed: unittest.mock.MagicMock,  # noqa: PT019 -- `mock.patch` hands it over
) -> None:
    """The ones that are not made but reached: the flows, a flow's agents, one agent."""
    app = Humanize()
    async with app.run_test() as driver:
        await into_flows(app, driver)
        once(app.screen)

        await into_agent(app, driver)
        once(app.screen)

        # And on the row that is stepped rather than opened, where the keys are not the same.
        await onto(app, driver, "effort")
        once(app.screen)
        assert "←/→ or space" in str(app.screen.query_one("#keys", Label).content)


@pytest.mark.timeout(60)
async def test_a_search_says_what_the_keys_do_while_it_runs() -> None:
    """The letters are the search's then, and esc comes out of it before it leaves."""
    app = Humanize()
    async with app.run_test() as driver:
        await app.push_screen(Flowverses())
        await until(lambda: isinstance(app.screen, Flowverses), driver)
        sheet = app.screen
        assert isinstance(sheet, Flowverses)
        await driver.pause()
        assert "a add" in str(sheet.query_one("#keys", Label).content)

        await driver.press("s")
        await until(lambda: sheet._searching, driver)
        said = str(sheet.query_one("#keys", Label).content)

        once(sheet)
        # The letters reach the search, so they are not offered as keys of the sheet.
        assert "a add" not in said
        assert "esc leave search" in said


@pytest.mark.timeout(60)
@unittest.mock.patch("hmz.tui.app.installed", return_value=CLAUDE)
async def test_saving_is_a_row_below_the_choices_rather_than_one_of_them(
    _installed: unittest.mock.MagicMock,  # noqa: PT019 -- `mock.patch` hands it over
) -> None:
    """A menu whose way out looks like one of its answers is a menu hiding the way out."""
    app = Humanize()
    async with app.run_test() as driver:
        await into_flows(app, driver)
        await into_agent(app, driver)
        listing = app.screen.query_one("#choices", OptionList)

        assert rows(app)[-1] == _SAVE
        # Out of the numbering, and with a row of air above it: what is left to do about the
        # menu rather than one more thing to pick out of it.
        last = str(listing.get_option_at_index(listing.option_count - 1).prompt)
        assert last.startswith("\n")
        assert "save" in last
        assert f"{listing.option_count}." not in last


@pytest.mark.timeout(60)
@pytest.mark.parametrize("key", ["shift+enter", "ctrl+j"])
@unittest.mock.patch("hmz.tui.app.installed", return_value=CLAUDE)
async def test_either_spelling_of_the_chord_saves(
    _installed: unittest.mock.MagicMock,  # noqa: PT019 -- `mock.patch` hands it over
    key: str,
) -> None:
    """Only one of them always arrives, so a menu is bound to both and says both."""
    app = Humanize()
    async with app.run_test() as driver:
        await into_flows(app, driver)
        await into_agent(app, driver)
        assert "shift+enter/ctrl+j save" in str(
            app.screen.query_one("#keys", Label).content
        )

        await driver.press(key)
        await until(lambda: not isinstance(app.screen, Agent), driver)


@pytest.mark.timeout(60)
@unittest.mock.patch("hmz.tui.app.installed", return_value=CLAUDE)
async def test_space_cycles_whatever_the_arrows_adjust(
    _installed: unittest.mock.MagicMock,  # noqa: PT019 -- `mock.patch` hands it over
) -> None:
    """And comes round at the end of the range, which is what tells it from an arrow."""
    app = Humanize()
    async with app.run_test() as driver:
        await into_flows(app, driver)
        await into_agent(app, driver)
        sheet = app.screen
        assert isinstance(sheet, Agent)
        await onto(app, driver, "effort")
        was = sheet._effort
        efforts = sheet._efforts()
        assert len(efforts) > 1  # or there would be nothing to cycle through

        await driver.press("space")
        await driver.pause()
        assert sheet._effort != was

        # Round to where it started rather than stopping at the end of the range: a key that
        # means `the next one` and did nothing would look broken to whoever walked there.
        for _ in range(len(efforts) - 1):
            await driver.press("space")
            await driver.pause()
        assert sheet._effort == was


@pytest.mark.timeout(60)
async def test_the_settings_menu_has_the_same_row_and_the_same_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """What is true of one menu that holds what is changed in it is true of all of them."""
    from hmz.runtime.settings import Settings

    monkeypatch.chdir(tmp_path)
    Settings(tmp_path).answers(enable_sentry=True)
    app = Humanize()
    async with app.run_test() as driver:
        await driver.press(*"/settings")
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Adjusts), driver)
        sheet = app.screen
        assert isinstance(sheet, Adjusts)
        once(sheet)
        assert rows(app) == ["reports", "sent", _SAVE]

        # Space turns the row under the cursor round, as the arrows do.
        listing = sheet.query_one("#choices", OptionList)
        assert "on " in str(listing.get_option_at_index(0).prompt)
        await driver.press("space")
        await driver.pause()
        assert "off " in str(listing.get_option_at_index(0).prompt)

        # And the chord lands the lot without walking out and answering a box about it.
        await driver.press("ctrl+j")
        await until(lambda: not isinstance(app.screen, Adjusts), driver)

    assert Settings(tmp_path).enable_sentry is False


@pytest.mark.timeout(60)
async def test_adding_is_a_row_of_every_list_that_is_added_to() -> None:
    """A letter said only at the bottom of the screen is a letter nobody finds."""
    app = Humanize()
    async with app.run_test() as driver:
        await app.push_screen(Flowverses())
        await until(lambda: isinstance(app.screen, Flowverses), driver)
        await driver.pause()

        assert rows(app)[-1] == _ADD

        # And the cursor walks on to it and stays there, it being a row like any other: the
        # list is built again on every keystroke, off which flowverse the cursor is on.
        listing = app.screen.query_one("#choices", OptionList)
        await onto(app, driver, _ADD)
        await driver.pause()
        assert listing.highlighted == listing.option_count - 1


@pytest.mark.timeout(60)
async def test_the_question_about_what_a_menu_holds_is_five_words() -> None:
    """It arrives over a menu somebody just spent a minute in, and either answer is a word."""
    app = Humanize()
    async with app.run_test() as driver:
        await app.push_screen(Confirms())
        await until(lambda: isinstance(app.screen, Confirms), driver)
        sheet = app.screen
        await driver.pause()

        assert str(sheet.query_one("#asked", Label).content) == "Save?"
        assert not str(sheet.query_one("#about", Label).content)
        assert rows(app) == ["keep", "drop"]
        said = " ".join(
            str(sheet.query_one(one, Label).content) for one in ("#asked", "#keys")
        )
        # Every word in the box, keys and all, less the dot that separates two keys.
        words = said.replace("·", " ").split()
        assert len(words) <= 5, words


@pytest.mark.timeout(60)
async def test_a_sheet_is_answered_once_however_fast_the_key_is_pressed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two answers to one question pops the screen under it, which on a first start is a crash."""
    from hmz.runtime import telemetry

    monkeypatch.delenv(telemetry.SAYS, raising=False)
    monkeypatch.chdir(tmp_path)
    app = Humanize()
    async with app.run_test() as driver:
        await until(lambda: isinstance(app.screen, Reports), driver)
        listing = app.screen.query_one("#choices", OptionList)

        # Both presses before either is handled, which is what a terminal delivers when
        # somebody leans on enter: the list posts one message apiece and both are answered.
        listing.action_select()
        listing.action_select()
        await until(lambda: not isinstance(app.screen, Reports), driver)
        await driver.pause()

        # The interface is still standing, which is the whole of it: a second answer that
        # popped the screen under this one would have taken the interface with it.
        assert app.is_running
        assert not isinstance(app.screen, Sheet)


@pytest.mark.timeout(60)
async def test_the_sheet_of_switches_is_flipped_on_the_same_key() -> None:
    """Which other backends an account could be run as is switches, and space flips one."""
    from hmz.coganchor.providers import Provider

    one = Provider(cli="claude", name="shared", way="key", env={"K": "v"})
    app = Humanize()
    async with app.run_test() as driver:
        await app.push_screen(Alike(one, ["codex", "pi"]))
        await until(lambda: isinstance(app.screen, Alike), driver)
        sheet = app.screen
        assert isinstance(sheet, Alike)
        await driver.pause()
        once(sheet)

        # Nothing is installed in a test, so every one of them starts off.
        assert sheet._on == set()
        await driver.press("space")
        await driver.pause()
        assert sheet._on == {"codex"}


@pytest.mark.timeout(60)
@unittest.mock.patch("hmz.tui.app.installed", return_value=CLAUDE)
async def test_the_flow_menu_says_the_chord_on_both_of_its_pages(
    _installed: unittest.mock.MagicMock,  # noqa: PT019 -- `mock.patch` hands it over
) -> None:
    """One menu walked into, so the way to save it is the same key in both halves of it."""
    app = Humanize()
    async with app.run_test() as driver:
        await into_flows(app, driver)
        sheet = app.screen
        assert isinstance(sheet, Flows)
        assert not sheet._inside
        assert "shift+enter/ctrl+j save" in str(sheet.query_one("#keys", Label).content)

        await driver.press("enter")
        await until(lambda: sheet._inside, driver)
        once(sheet)
        assert rows(app)[-1] == _SAVE
        assert "shift+enter/ctrl+j save" in str(sheet.query_one("#keys", Label).content)

        # And what lands is what the menu was holding, flow and agents together.
        await driver.press("shift+enter")
        await until(lambda: not isinstance(app.screen, Flows), driver)

    assert app._models

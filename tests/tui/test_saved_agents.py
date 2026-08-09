"""The agents written down under a name, and what a flow does with one.

An agent is a CLI, an account, a model at an effort and what it may do without being asked,
and none of that is a thing about the flow that happens to be driving it. So it is worth
saying once and reaching for -- the reviewer you always use, the cheap one you fan out across
-- which is what `/agents` keeps and what the sheet a flow's agent is set up on imports from.

A flow imports a copy. An agent tuned inside a flow is that flow's, and writing the change
back into the thing it was copied from would change every other flow that had imported it.
"""

from __future__ import annotations

import unittest.mock
from typing import TYPE_CHECKING, cast

import pytest
from textual.widgets import Label, OptionList

from hmz.backends import Model
from hmz.kept import Kept, Runs, Templates
from hmz.tui import Humanize
from hmz.tui.pick import Agent, Catalogue, Clis, Imports, Names, Saved

from .test_app import drops, into_agent, into_flows, keeps, onto, opens, rows, until

if TYPE_CHECKING:
    from textual.pilot import Pilot

#: What one installed CLI looks like, for every menu here.
CLAUDE = {"claude": (Model("claude-opus-5", ("max", "high")),)}


def _under(app: Humanize) -> str:
    """What is said under the list, which is where a menu reports itself."""
    return str(app.screen.query_one("#tuning", Label).content)


async def _into_saved(app: Humanize, driver: Pilot[None]) -> Saved:
    """Opens the agents menu and waits for it to be drawn."""
    await driver.press(*"/agents")
    await driver.press("enter")
    await until(lambda: isinstance(app.screen, Saved), driver)
    return cast("Saved", app.screen)


@pytest.mark.timeout(60)
@unittest.mock.patch("hmz.tui.app.installed", return_value=CLAUDE)
async def test_the_menu_lists_what_has_been_written_down(
    _installed: unittest.mock.MagicMock,  # noqa: PT019  -- `mock.patch` hands it over
) -> None:
    """One named agent apiece, with what each of them is beside the name."""
    Templates().keep(
        [
            Kept("reviewer", Runs("claude/claude-opus-5:max")),
            Kept("cheap", Runs("claude/claude-opus-5:high", "", "read-only")),
        ]
    )
    app = Humanize()
    async with app.run_test() as driver:
        sheet = await _into_saved(app, driver)

        assert rows(app) == ["reviewer", "cheap"]
        assert "Agents" in str(sheet.query_one("#tabs", Label).content)
        listing = sheet.query_one("#choices", OptionList)
        assert "claude/claude-opus-5:max" in str(listing.get_option_at_index(0).prompt)
        assert "read-only" in str(listing.get_option_at_index(1).prompt)


@pytest.mark.timeout(60)
@unittest.mock.patch("hmz.tui.app.installed", return_value=CLAUDE)
async def test_one_is_added_named_and_written_down_when_the_menu_is_saved(
    _installed: unittest.mock.MagicMock,  # noqa: PT019  -- `mock.patch` hands it over
) -> None:
    """`a` opens a sheet with nothing on it, and the name is a row of that sheet."""
    app = Humanize()
    async with app.run_test() as driver:
        await _into_saved(app, driver)
        assert "no agents saved yet" in _under(app)

        await driver.press("a")
        await until(lambda: isinstance(app.screen, Agent), driver)
        # A saved agent has a name of its own, which a flow's agent has not: a flow's is
        # called what the flow calls it.
        assert rows(app)[0] == "name"
        assert "import" not in rows(app)

        await onto(app, driver, "name")
        await driver.press(*"reviewer")
        await driver.pause()
        await keeps(app, driver)
        await until(lambda: isinstance(app.screen, Saved), driver)

        # Held rather than written: nothing lands until the menu itself is saved.
        assert rows(app) == ["reviewer"]
        assert Templates().all() == []

        await keeps(app, driver)
        await until(lambda: not isinstance(app.screen, Saved), driver)

    assert [one.name for one in Templates().all()] == ["reviewer"]
    assert Templates().all()[0].runs == Runs("claude/claude-opus-5:high")


@pytest.mark.timeout(60)
@unittest.mock.patch("hmz.tui.app.installed", return_value=CLAUDE)
async def test_save_accepts_a_named_agent_without_backing_out(
    _installed: unittest.mock.MagicMock,  # noqa: PT019  -- `mock.patch` hands it over
) -> None:
    """The explicit action returns to the outer draft, which still saves the complete list."""
    Templates().keep([Kept("reviewer", Runs("claude/claude-opus-5:max"))])
    app = Humanize()
    async with app.run_test() as driver:
        await _into_saved(app, driver)
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Agent), driver)

        await onto(app, driver, "effort")
        await driver.press("left")
        await driver.pause()
        await opens(app, driver, "save")
        await until(lambda: isinstance(app.screen, Saved), driver)

        assert Templates().all()[0].runs == Runs("claude/claude-opus-5:max")
        await keeps(app, driver)

    assert Templates().all()[0].runs == Runs("claude/claude-opus-5:high")


@pytest.mark.timeout(60)
@unittest.mock.patch("hmz.tui.app.installed", return_value=CLAUDE)
async def test_one_is_taken_away_by_pressing_d_twice(
    _installed: unittest.mock.MagicMock,  # noqa: PT019  -- `mock.patch` hands it over
) -> None:
    """Once arms it and says so; twice takes it away, and the menu saving writes that down."""
    Templates().keep(
        [
            Kept("reviewer", Runs("claude/claude-opus-5:max")),
            Kept("cheap", Runs("claude/claude-opus-5:high")),
        ]
    )
    app = Humanize()
    async with app.run_test() as driver:
        await _into_saved(app, driver)

        await driver.press("d")
        await until(lambda: "press d again" in _under(app), driver)
        assert rows(app) == ["reviewer", "cheap"]  # armed, and nothing gone

        await driver.press("d")
        await until(lambda: rows(app) == ["cheap"], driver)
        assert [one.name for one in Templates().all()] == ["reviewer", "cheap"]

        await keeps(app, driver)
        await until(lambda: not isinstance(app.screen, Saved), driver)

    assert [one.name for one in Templates().all()] == ["cheap"]


@pytest.mark.timeout(60)
@unittest.mock.patch("hmz.tui.app.installed", return_value=CLAUDE)
async def test_walking_out_of_the_menu_without_saving_writes_nothing(
    _installed: unittest.mock.MagicMock,  # noqa: PT019  -- `mock.patch` hands it over
) -> None:
    """Which is what makes it a draft: it is asked about, and discarding is an answer."""
    Templates().keep([Kept("reviewer", Runs("claude/claude-opus-5:max"))])
    app = Humanize()
    async with app.run_test() as driver:
        await _into_saved(app, driver)

        await driver.press("d")
        await driver.press("d")
        await until(lambda: rows(app) == [], driver)

        await drops(app, driver)
        await until(lambda: not isinstance(app.screen, Saved), driver)

    assert [one.name for one in Templates().all()] == ["reviewer"]


@pytest.mark.timeout(60)
@unittest.mock.patch("hmz.tui.app.installed", return_value=CLAUDE)
async def test_a_flow_imports_a_copy_rather_than_a_link(
    _installed: unittest.mock.MagicMock,  # noqa: PT019  -- `mock.patch` hands it over
) -> None:
    """Changing it inside the flow must not change every other flow that imported it."""
    Templates().keep(
        [
            Kept(
                "reviewer",
                Runs("claude/claude-opus-5:max", "", "read-only"),
            )
        ]
    )
    app = Humanize()
    async with app.run_test() as driver:
        await into_flows(app, driver)
        await into_agent(app, driver)

        await opens(app, driver, "import")
        await until(lambda: isinstance(app.screen, Imports), driver)
        assert rows(app) == ["reviewer"]
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Agent), driver)
        await until(lambda: "copied from reviewer" in _under(app), driver)

        # Everything the saved one is, on this one.
        listing = app.screen.query_one("#choices", OptionList)
        assert "max" in str(
            listing.get_option_at_index(rows(app).index("effort")).prompt
        )
        assert "read-only" in str(
            listing.get_option_at_index(rows(app).index("permission")).prompt
        )

        # And changing it here changes this one alone.
        await onto(app, driver, "effort")
        await driver.press("left")
        await driver.pause()

        await keeps(app, driver)
        await keeps(app, driver)

    assert app._models == [Runs("claude/claude-opus-5:high", "", "read-only")]
    assert Templates().all()[0].runs == Runs(
        "claude/claude-opus-5:max", "", "read-only"
    )


@pytest.mark.timeout(60)
@unittest.mock.patch("hmz.tui.app.installed", return_value=CLAUDE)
async def test_a_flows_agent_is_saved_out_under_a_new_name_or_over_one(
    _installed: unittest.mock.MagicMock,  # noqa: PT019  -- `mock.patch` hands it over
) -> None:
    """The other half of importing: what was tuned in a flow is worth keeping."""
    Templates().keep([Kept("reviewer", Runs("claude/claude-opus-5:max"))])
    app = Humanize()
    was = (app._flow_named, list(app._models))
    async with app.run_test() as driver:
        await into_flows(app, driver)
        await into_agent(app, driver)

        await opens(app, driver, "save as")
        await until(lambda: isinstance(app.screen, Names), driver)
        # The ones already there, to be written over, and what this one is called as a new
        # one under them.
        assert rows(app)[0] == "reviewer"

        await driver.press("s")
        await driver.press(*"builder")
        await driver.pause()
        assert rows(app) == ["builder"]
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Agent), driver)
        await until(lambda: "saved as builder" in _under(app), driver)
        assert (app._flow_named, app._models) == was

    held = {one.name: one.runs for one in Templates().all()}
    assert held["reviewer"] == Runs("claude/claude-opus-5:max")
    assert held["builder"] == Runs("claude/claude-opus-5:high")


@pytest.mark.timeout(60)
@unittest.mock.patch("hmz.tui.app.installed", return_value=CLAUDE)
async def test_a_saved_agent_is_set_up_on_the_same_sheet_a_flows_is(
    _installed: unittest.mock.MagicMock,  # noqa: PT019  -- `mock.patch` hands it over
) -> None:
    """One sheet for what an agent is, wherever the agent came from."""
    Templates().keep([Kept("reviewer", Runs("claude/claude-opus-5:max"))])
    app = Humanize()
    async with app.run_test() as driver:
        await _into_saved(app, driver)

        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Agent), driver)
        assert "reviewer" in str(app.screen.query_one("#asked", Label).content)
        # Where it works is asked about, no flow having settled it: a saved agent belongs to
        # no flow, so nothing has ruled the question out.
        assert "where" in rows(app)

        await opens(app, driver, "cli")
        await until(lambda: isinstance(app.screen, Clis), driver)
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Agent), driver)
        await opens(app, driver, "model")
        await until(lambda: isinstance(app.screen, Catalogue), driver)
        await until(
            lambda: bool(app.screen.query_one("#choices", OptionList).options), driver
        )
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Agent), driver)

        await keeps(app, driver)
        await keeps(app, driver)

    assert [one.name for one in Templates().all()] == ["reviewer"]

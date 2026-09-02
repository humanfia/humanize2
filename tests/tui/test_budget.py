"""What a run of a flow may spend, set from the menu that sets everything else up.

A row on the page the flow's agents are on, because it is a setting of the run rather than of
the flow: the flow declares at most a default and never holds itself to one. What is checked
is that the row says what the run is held to without being opened, that what is set there is
written down beside what the flow was set up with and read back, and that saving a run with
nothing at all to stop it asks whether that is what was meant -- except of a flow that says in
its own file that it is meant to run that way, which `chat` does.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pytest
from textual.widgets import OptionList

from hmz.coganchor.agents import Allowance
from hmz.coganchor.backends import Model
from hmz.runtime.kept import Runs
from hmz.runtime.settings import Settings
from hmz.tui import Humanize
from hmz.tui.pick import (
    _BUDGET,
    _SAVE,
    Configures,
    Flows,
    Unbounded,
    budget_of,
)
from tests.stubs import written

from .test_app import onto, opens, rows, until

if TYPE_CHECKING:
    from pathlib import Path

    from textual.pilot import Pilot

#: One backend, so that the menu has something to set an agent up as and can be saved.
_INSTALLED = {"claude": (Model("m", ("high",)),)}

#: A flow with no opinion about what a run of it is worth, which is what most flows are.
QUIET = """
from hmz.flows import Agent, flow


@flow
def run(agents: tuple[Agent], task: str) -> None:
    pass
"""

#: And one that says it is meant to run under nothing at all, as `chat` does.
LOOSE = """
from hmz.flows import Agent, Allowance, flow


@flow(budget=Allowance())
def run(agents: tuple[Agent], task: str) -> None:
    pass
"""


@pytest.fixture
def flows(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Puts the two flows where this project's own would be, with a backend to run them."""
    import hmz.tui.app
    import hmz.tui.pick

    monkeypatch.setattr(hmz.tui.app, "installed", lambda: dict(_INSTALLED))
    monkeypatch.setattr(hmz.tui.pick, "installed", lambda: dict(_INSTALLED))
    where = tmp_path / ".humanize" / "flows"
    where.mkdir(parents=True)
    written(where, "quiet", QUIET)
    written(where, "loose", LOOSE)
    return where


async def _into(app: Humanize, driver: Pilot[None], flow: str) -> Flows:
    """Opens the menu already inside one flow, which is where the budget row is."""
    await driver.press(*f"/flow local/{flow}")
    await driver.press("enter")
    await until(lambda: isinstance(app.screen, Flows), driver)
    sheet = cast("Flows", app.screen)
    await until(lambda: sheet._inside, driver)
    return sheet


def _said(app: Humanize) -> str:
    """What the budget row says, which is what it is for: read without opening it."""
    listing = app.screen.query_one("#choices", OptionList)
    return str(listing.get_option_at_index(rows(app).index(_BUDGET)).prompt)


@pytest.mark.timeout(60)
async def test_the_row_says_what_the_run_is_held_to_without_being_opened(
    flows: Path,
) -> None:
    """An allowance nobody can see without opening something is one nobody checks."""
    app = Humanize()
    async with app.run_test() as driver:
        await _into(app, driver, "quiet")

        assert rows(app) == ["0", _BUDGET, _SAVE]
        assert "nothing stops this run" in _said(app)


@pytest.mark.timeout(60)
async def test_what_is_set_there_is_kept_and_read_back(
    flows: Path, tmp_path: Path
) -> None:
    """Beside what the flow was set up with, since it is a setting of the run beside it."""
    app = Humanize()
    async with app.run_test() as driver:
        await _into(app, driver, "quiet")
        await opens(app, driver, _BUDGET)
        await until(lambda: isinstance(app.screen, Configures), driver)
        sheet = cast("Configures", app.screen)

        # Three rows and nothing else: hours, millions of output tokens, dollars.
        assert rows(app) == ["hours", "tokens", "dollars"]

        await driver.press("right")  # hours: 0 -> 1
        await driver.press("down", "right")  # tokens: 0 -> 1
        await driver.pause()
        assert (sheet._typed_in["hours"], sheet._typed_in["tokens"]) == ("1.0", "1.0")
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Flows), driver)

        # Said on the row it came back to, so that it is read rather than remembered.
        assert "stops at 1h, 1M out" in _said(app)

        await onto(app, driver, _SAVE)
        await driver.press("enter")
        await until(lambda: not isinstance(app.screen, Flows), driver)

    # Written down under the flow, beside its agents, and read back by the next interface.
    assert Settings(tmp_path).budget("local/quiet") == {
        "hours": 1.0,
        "tokens": 1.0,
        "dollars": 0.0,
    }
    again = Humanize()
    assert again._budget == Allowance(hours=1.0, tokens=1.0)


@pytest.mark.timeout(60)
async def test_saving_a_run_nothing_will_stop_asks_whether_that_is_what_was_meant(
    flows: Path, tmp_path: Path
) -> None:
    """Three caps and none of them set is a run that goes until somebody notices.

    A fair thing to ask for and a poor thing to arrive at by not answering three questions,
    and the two look identical afterwards -- so it is asked once, where it can be changed.
    """
    app = Humanize()
    async with app.run_test() as driver:
        await _into(app, driver, "quiet")
        await onto(app, driver, _SAVE)
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Unbounded), driver)

        # And the second answer goes back to the menu holding everything it was holding,
        # which is where a budget is set.
        await driver.press("down", "enter")
        await until(lambda: isinstance(app.screen, Flows), driver)
        assert Settings(tmp_path).flow != "local/quiet"

        # Asked again on the way past, and meant this time.
        await onto(app, driver, _SAVE)
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Unbounded), driver)
        await driver.press("enter")
        await until(lambda: not isinstance(app.screen, Flows), driver)

    assert Settings(tmp_path).flow == "local/quiet"


@pytest.mark.timeout(60)
async def test_a_run_with_a_cap_on_it_is_not_asked_about(
    flows: Path, tmp_path: Path
) -> None:
    """The question is about a run nothing will stop, and one cap is something."""
    Settings(tmp_path).remember(
        "local/quiet", ("",), [Runs("claude/m:high")], budget={"hours": 2}
    )
    app = Humanize()
    async with app.run_test() as driver:
        sheet = await _into(app, driver, "quiet")
        assert "stops at 2h" in _said(app)

        await onto(app, driver, _SAVE)
        await driver.press("enter")
        await until(lambda: app.screen is not sheet, driver)

        assert not isinstance(app.screen, Unbounded)


@pytest.mark.timeout(60)
async def test_a_flow_run_without_the_menu_is_still_held_to_what_was_set(
    flows: Path, tmp_path: Path
) -> None:
    """`$flow <task>` runs a flow this workspace has set up without opening the menu.

    Which is the whole point of that line -- and a path that dropped the allowance on the way
    would start an unbounded run out of a workspace whose settings say six hours, with nothing
    asked either, the question living on the menu that did not open.
    """
    Settings(tmp_path).remember(
        "local/quiet", ("",), [Runs("claude/m:high")], budget={"hours": 6}
    )
    app = Humanize()
    async with app.run_test():
        held = app._remembered_for("local/quiet")

        assert held is not None
        assert held.budget == Allowance(hours=6)


@pytest.mark.timeout(60)
async def test_setting_every_dimension_back_to_nothing_forgets_it(
    flows: Path, tmp_path: Path
) -> None:
    """Rather than writing three zeros down, which would override the flow for good.

    A flow is back under what it says for itself by there being nothing remembered for it, so
    an allowance that caps nothing has to be written down as nothing.
    """
    Settings(tmp_path).remember(
        "local/quiet", ("",), [Runs("claude/m:high")], budget={"hours": 6}
    )
    app = Humanize()
    async with app.run_test() as driver:
        await _into(app, driver, "quiet")
        assert "stops at 6h" in _said(app)

        await opens(app, driver, _BUDGET)
        await until(lambda: isinstance(app.screen, Configures), driver)
        await driver.press("left")  # hours: 6 -> 5
        for _ in range(5):
            await driver.press("left")  # and down to nothing
        await driver.pause()
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Flows), driver)
        await onto(app, driver, _SAVE)
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Unbounded), driver)
        await driver.press("enter")
        await until(lambda: not isinstance(app.screen, Flows), driver)

    assert Settings(tmp_path).budget("local/quiet") == {}
    assert budget_of("local/quiet") is None


@pytest.mark.timeout(60)
async def test_a_flow_that_says_it_runs_unbounded_is_never_asked(
    flows: Path, tmp_path: Path
) -> None:
    """`@flow(budget=Allowance())` is a flow claiming an unbounded run is what it is for.

    Which is the whole of the exemption and the whole of why `chat` is not named in the menu,
    the command line and the settings: it is one line in the flow's own file, and any flow may
    make the same claim.
    """
    app = Humanize()
    async with app.run_test() as driver:
        sheet = await _into(app, driver, "loose")
        assert "nothing stops this run" in _said(app)

        await onto(app, driver, _SAVE)
        await driver.press("enter")
        await until(lambda: app.screen is not sheet, driver)

        assert not isinstance(app.screen, Unbounded)

    assert Settings(tmp_path).flow == "local/loose"

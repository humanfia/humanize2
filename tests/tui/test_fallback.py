"""`/fallback`: where a turn goes when what was taking it cannot, on both of its scales.

A menu of its own rather than a row of the accounts, because half of it is not about accounts
at all. An account that goes down is answered by another account of the same backend, inside
the conversation that was running. An agent that has nowhere left to run -- a model retired, a
CLI that will not start, a rate limit on the whole account -- is answered by another agent,
which is a step written down between the two.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from textual.widgets import Label, OptionList

from hmz import fallbacks, providers
from hmz.backends import Model
from hmz.tui import Humanize
from hmz.tui.pick import Agent, Fallbacks, Falls

from .test_app import keeps, onto, rows, until

if TYPE_CHECKING:
    from textual.pilot import Pilot

#: One installed CLI, for the walk that chooses an agent.
CLAUDE = {"claude": (Model("claude-opus-5", ("max", "high")),)}


def _under(app: Humanize) -> str:
    """What is said under the list, which is where a menu reports itself."""
    return str(app.screen.query_one("#tuning", Label).content)


async def _opens(app: Humanize, driver: Pilot[None]) -> None:
    """Opens `/fallback` and waits for it to be up."""
    await driver.press(*"/fallback")
    await driver.press("enter")
    await until(lambda: isinstance(app.screen, Fallbacks), driver)


async def _chooses(app: Humanize, driver: Pilot[None], *, harder: bool = False) -> None:
    """Takes the agent sheet as it comes, or one rung harder so the two are two agents.

    Args:
      app: The interface.
      driver: What is pumping it.
      harder: Whether to step the effort on one rung first, which is the cheapest way of
        choosing a second agent where one CLI at one model is all there is here.
    """
    await until(lambda: isinstance(app.screen, Agent), driver)
    if harder:
        await onto(app, driver, "effort")
        await driver.press("right")
        await driver.pause()
    await onto(app, driver, "save")
    await driver.press("enter")


@pytest.fixture(autouse=True)
def _installed(monkeypatch: pytest.MonkeyPatch) -> None:
    """One CLI here, so the sheet an agent is chosen on has something to offer."""
    import hmz.tui.app

    monkeypatch.setattr(hmz.tui.app, "installed", lambda: dict(CLAUDE))
    monkeypatch.setattr(hmz.tui.app, "installable", dict)


@pytest.mark.timeout(60)
async def test_the_menu_opens_on_the_steps_between_agents() -> None:
    """Which is the half that is new, and the half nothing else has a place for."""
    fallbacks.points("claude/claude-opus-5:high", "codex/gpt-5.6-sol:high")
    app = Humanize()
    async with app.run_test() as driver:
        await _opens(app, driver)
        await until(
            lambda: bool(app.screen.query_one("#choices", OptionList).options), driver
        )

        assert rows(app) == ["claude/claude-opus-5:high"]
        listing = app.screen.query_one("#choices", OptionList)
        assert "falls back to codex/gpt-5.6-sol:high" in str(listing.options[0].prompt)


@pytest.mark.timeout(60)
async def test_an_empty_menu_says_which_key_writes_one_down() -> None:
    """An empty list that explains nothing reads as a feature that does not work."""
    app = Humanize()
    async with app.run_test() as driver:
        await _opens(app, driver)
        await driver.pause()

        assert "a says one does" in _under(app)


@pytest.mark.timeout(60)
async def test_a_step_is_two_agents_chosen_and_is_held_until_the_menu_is_saved() -> (
    None
):
    """The agent that cannot run, and then the agent that takes its turns."""
    app = Humanize()
    async with app.run_test() as driver:
        await _opens(app, driver)
        await driver.press("a")
        await _chooses(app, driver)  # the one that cannot run
        await _chooses(app, driver, harder=True)  # and the one that takes over
        await until(lambda: isinstance(app.screen, Fallbacks), driver)

        # Said, and nothing on disk until the menu is saved.
        assert rows(app) == ["claude/claude-opus-5:high"]
        assert fallbacks.falls() == []

        await keeps(app, driver)
        await until(lambda: not isinstance(app.screen, Fallbacks), driver)

    assert fallbacks.falls() == [
        fallbacks.Falls("claude/claude-opus-5:high", "claude/claude-opus-5:max")
    ]


@pytest.mark.timeout(60)
async def test_an_agent_cannot_fall_back_to_itself() -> None:
    """A step that pointed at itself would be a turn that never ran out of places to go."""
    app = Humanize()
    async with app.run_test() as driver:
        await _opens(app, driver)
        await driver.press("a")
        await _chooses(app, driver)
        await _chooses(app, driver)
        await until(lambda: isinstance(app.screen, Fallbacks), driver)

        assert "cannot fall back to itself" in _under(app)


@pytest.mark.timeout(60)
async def test_a_step_is_taken_away_on_the_key_everything_is_taken_away_on() -> None:
    """D twice, which is what a day's work behind a key that is also pressed by mistake is."""
    fallbacks.points("claude/claude-opus-5:high", "codex/gpt-5.6-sol:high")
    app = Humanize()
    async with app.run_test() as driver:
        await _opens(app, driver)
        await until(
            lambda: bool(app.screen.query_one("#choices", OptionList).options), driver
        )
        await driver.press("d")
        await driver.pause()

        assert "press d again" in _under(app)
        assert fallbacks.falls()  # still there: one press says what the next one does

        await driver.press("d")
        await driver.pause()

        assert rows(app) == []
        await keeps(app, driver)
        await until(lambda: not isinstance(app.screen, Fallbacks), driver)

    assert fallbacks.falls() == []


@pytest.mark.timeout(60)
async def test_the_accounts_are_the_other_page_of_the_same_menu() -> None:
    """The one place fallback is asked about, whichever of the two somebody meant."""
    providers.add("codex", "work", way="key", env={"OPENAI_API_KEY": "k"})
    providers.add("codex", "spare", way="key", env={"OPENAI_API_KEY": "s"})
    app = Humanize()
    async with app.run_test() as driver:
        await _opens(app, driver)
        await driver.press("tab")
        await until(
            lambda: bool(app.screen.query_one("#choices", OptionList).options), driver
        )

        assert rows(app) == ["codex/", "codex/spare", "codex/work"]

        await onto(app, driver, "codex/spare")
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Falls), driver)
        listing = app.screen.query_one("#choices", OptionList)
        await until(lambda: bool(listing.options), driver)
        # The end of the line first, and never the account it is about.
        assert [str(one.id) for one in listing.options] == ["=", "=work"]

        await driver.press("down", "enter")
        await until(lambda: isinstance(app.screen, Fallbacks), driver)
        held = providers.find("codex", "spare")
        assert held is not None
        assert not held.fallback  # held until the menu is saved, as everything here is

        await keeps(app, driver)
        await until(lambda: not isinstance(app.screen, Fallbacks), driver)

    chained = providers.find("codex", "spare")
    assert chained is not None
    assert chained.fallback == "work"


@pytest.mark.timeout(60)
async def test_the_keys_that_are_the_agents_say_why_they_are_not_the_accounts() -> None:
    """An account is made and taken away in `/providers`; this says where one goes."""
    providers.add("codex", "work", way="key", env={"OPENAI_API_KEY": "k"})
    app = Humanize()
    async with app.run_test() as driver:
        await _opens(app, driver)
        await driver.press("tab")
        await driver.pause()

        await driver.press("a")
        await driver.pause()
        assert "/providers" in _under(app)

        await driver.press("d")
        await driver.pause()
        assert "/providers" in _under(app)

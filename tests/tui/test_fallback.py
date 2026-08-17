"""`/fallback`: where a turn goes when the place taking it cannot take it at all.

A place is a CLI, an account and a model, and a step is written between two of them. How many
times over a failed turn is taken again before the step happens is written there too, both
being answers to the one thing that went wrong.

Not the accounts. An account that goes down is answered by another account of the same
backend, inside the conversation that was running, and that is `/providers`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from textual.widgets import Label, OptionList

from hmz import fallbacks
from hmz.backends import Model
from hmz.tui import Humanize
from hmz.tui.pick import Accounts, Catalogue, Clis, Failing, Fallbacks, Retries

from .test_app import keeps, onto, rows, until

if TYPE_CHECKING:
    from textual.pilot import Pilot

#: Two installed CLIs, so that choosing a place has something to choose between.
INSTALLED = {
    "claude": (Model("claude-opus-5", ("max", "high")),),
    "codex": (Model("gpt-5.6-sol", ("xhigh", "high")),),
}


def _under(app: Humanize) -> str:
    """What is said under the list, which is where a menu reports itself."""
    return str(app.screen.query_one("#tuning", Label).content)


async def _opens(app: Humanize, driver: Pilot[None]) -> None:
    """Opens `/fallback` and waits for it to be up."""
    await driver.press(*"/fallback")
    await driver.press("enter")
    await until(lambda: isinstance(app.screen, Fallbacks), driver)


async def _place(app: Humanize, driver: Pilot[None], cli: str) -> None:
    """Walks the three questions a place is: the CLI, its account, and the model it runs.

    Args:
      app: The interface.
      driver: What is pumping it.
      cli: Which backend to pick, the account being the machine's own and the model the one
        that CLI named.
    """
    await until(lambda: isinstance(app.screen, Clis), driver)
    await onto(app, driver, cli)
    await driver.press("enter")
    await until(lambda: isinstance(app.screen, Accounts), driver)
    await until(
        lambda: bool(app.screen.query_one("#choices", OptionList).options), driver
    )
    await driver.press("enter")  # the machine's own, which is the first row
    await until(lambda: isinstance(app.screen, Catalogue), driver)
    await until(
        lambda: bool(app.screen.query_one("#choices", OptionList).options), driver
    )
    await driver.press("enter")


@pytest.fixture(autouse=True)
def _installed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Two CLIs here, so the walk that chooses a place has something to offer."""
    import hmz.tui.app

    monkeypatch.setattr(hmz.tui.app, "installed", lambda: dict(INSTALLED))
    monkeypatch.setattr(hmz.tui.app, "installable", dict)


@pytest.mark.timeout(60)
async def test_the_menu_is_the_steps_between_places() -> None:
    """One page: a place is a CLI, an account and a model, and nothing else is asked."""
    fallbacks.points("claude/claude-opus-5", "codex/gpt-5.6-sol")
    app = Humanize()
    async with app.run_test() as driver:
        await _opens(app, driver)
        await until(
            lambda: bool(app.screen.query_one("#choices", OptionList).options), driver
        )

        assert rows(app) == ["claude/claude-opus-5"]
        listing = app.screen.query_one("#choices", OptionList)
        assert "falls back to codex/gpt-5.6-sol" in str(listing.options[0].prompt)


@pytest.mark.timeout(60)
async def test_an_empty_menu_says_which_key_writes_one_down() -> None:
    """An empty list that explains nothing reads as a feature that does not work."""
    app = Humanize()
    async with app.run_test() as driver:
        await _opens(app, driver)
        await driver.pause()

        assert "a says one does" in _under(app)


@pytest.mark.timeout(90)
async def test_a_step_is_two_places_chosen_and_is_held_until_the_menu_is_saved() -> (
    None
):
    """The place that cannot run, and then the place that takes its turns."""
    app = Humanize()
    async with app.run_test() as driver:
        await _opens(app, driver)
        await driver.press("a")
        await _place(app, driver, "claude")  # the one that cannot run
        await _place(app, driver, "codex")  # and the one that takes over
        await until(lambda: isinstance(app.screen, Fallbacks), driver)

        # Said, and nothing on disk until the menu is saved.
        assert rows(app) == ["claude/claude-opus-5"]
        assert fallbacks.falls() == []

        await keeps(app, driver)
        await until(lambda: not isinstance(app.screen, Fallbacks), driver)

    assert fallbacks.falls() == [
        fallbacks.Falls("claude/claude-opus-5", "codex/gpt-5.6-sol")
    ]


@pytest.mark.timeout(90)
async def test_a_place_cannot_fall_back_to_itself() -> None:
    """A step that pointed at itself would be a turn that never ran out of places to go."""
    app = Humanize()
    async with app.run_test() as driver:
        await _opens(app, driver)
        await driver.press("a")
        await _place(app, driver, "claude")
        await _place(app, driver, "claude")
        await until(lambda: isinstance(app.screen, Fallbacks), driver)

        assert "cannot fall back to itself" in _under(app)


@pytest.mark.timeout(60)
async def test_a_step_is_taken_away_on_the_key_everything_is_taken_away_on() -> None:
    """D twice, which is what a day's work behind a key that is also pressed by mistake is."""
    fallbacks.points("claude/claude-opus-5", "codex/gpt-5.6-sol")
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


@pytest.mark.timeout(90)
async def test_how_often_a_failed_turn_is_taken_again_is_on_the_same_step() -> None:
    """One thing went wrong, so one row says both what to try and where to go."""
    fallbacks.points("claude/claude-opus-5", "codex/gpt-5.6-sol")
    app = Humanize()
    async with app.run_test() as driver:
        await _opens(app, driver)
        await until(
            lambda: bool(app.screen.query_one("#choices", OptionList).options), driver
        )
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Failing), driver)
        listing = app.screen.query_one("#choices", OptionList)
        await until(lambda: bool(listing.options), driver)
        assert [str(one.id) for one in listing.options] == ["=goes", "=tried"]

        await driver.press("down", "enter")
        await until(lambda: isinstance(app.screen, Retries), driver)
        stepping = app.screen.query_one("#choices", OptionList)
        await until(lambda: bool(stepping.options), driver)
        assert [str(one.id) for one in stepping.options] == [
            "=tries",
            "=policy",
            "=for",
        ]

        await driver.press("right")  # one try beyond the first
        await driver.press("down", "right")  # and the wait after it stepped on one
        await driver.pause()
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Fallbacks), driver)

        # Said, and held until the menu is saved.
        assert "1 more tries" in str(
            app.screen.query_one("#choices", OptionList).options[0].prompt
        )
        assert fallbacks.tried("claude/claude-opus-5").tries == 0

        await keeps(app, driver)
        await until(lambda: not isinstance(app.screen, Fallbacks), driver)

    said = fallbacks.tried("claude/claude-opus-5")
    assert said.tries == 1
    assert said.policy == "fibonacci"
    assert said.to == "codex/gpt-5.6-sol"  # and where it goes is still where it goes

"""The models a sheet offers, which are the ones its CLI said it runs as the chosen account.

Nothing is written down, so a list is only ever as good as the last time somebody asked --
which is what the key on this sheet is for, and what making an account does on its own.

Driven headlessly, as every test of the interface is, so what is checked is where a keystroke
lands rather than how it is drawn.
"""

from __future__ import annotations

import unittest.mock
from typing import TYPE_CHECKING

import pytest
from textual.widgets import Label, OptionList

from hmz.backends import Model
from hmz.tui import Humanize
from hmz.tui.pick import Models, RunsAs

from .test_app import until

if TYPE_CHECKING:
    from pathlib import Path

    from textual.pilot import Pilot

#: One installed CLI that has said what it runs, for the walks that need one.
CLAUDE = {"claude": (Model("claude-nine", ("max", "high")),)}

#: The same CLI, installed and never asked, which is every machine before the first asking.
UNASKED: dict[str, tuple[Model, ...]] = {"claude": ()}

#: A flow of one agent that works where the flow is, so the walk is two steps rather than
#: three and the second is the one this is about.
HERE = '''
"""One agent, working where the flow is."""

from typing import NamedTuple

from hmz.agents import AgentBase


class Agents(NamedTuple):
    """Just the one."""

    builder: AgentBase


def run(agents: Agents, task: str) -> None:
    pass
'''


@pytest.fixture
def flows(tmp_path: Path) -> Path:
    """Puts the flow where this project's own would be."""
    where = tmp_path / ".humanize" / "flows"
    where.mkdir(parents=True)
    (where / "here.py").write_text(HERE)
    return where


async def _to_the_models(app: Humanize, driver: Pilot[None]) -> None:
    """Walks in as far as the models, which is the step after the CLI and the account."""
    await driver.press(*"/flow here")
    await driver.press("enter")
    await until(lambda: isinstance(app.screen, RunsAs), driver)
    await driver.press("enter")
    await until(lambda: isinstance(app.screen, Models), driver)


def _under(app: Humanize) -> str:
    """The line under the list, which says what became of asking."""
    return str(app.screen.query_one("#tuning", Label).content)


def _rows(app: Humanize) -> int:
    """How many models are on the sheet."""
    return len(app.screen.query_one("#choices", OptionList).options)


@pytest.mark.timeout(60)
@unittest.mock.patch("hmz.tui.app.installed", return_value=UNASKED)
async def test_a_cli_that_has_not_said_what_it_runs_says_which_key_asks_it(
    _installed: unittest.mock.MagicMock,  # noqa: PT019  -- `mock.patch` hands it over
    flows: Path,
) -> None:
    """An empty list that explains nothing reads as a CLI with no models at all."""
    app = Humanize()
    async with app.run_test() as driver:
        await _to_the_models(app, driver)

        assert _rows(app) == 0
        await until(lambda: "has not said what it runs" in _under(app), driver)
        assert "ctrl+r" in _under(app)


@pytest.mark.timeout(60)
@unittest.mock.patch("hmz.tui.app.installed", return_value=UNASKED)
async def test_the_key_asks_the_cli_and_puts_up_what_it_says(
    _installed: unittest.mock.MagicMock,  # noqa: PT019  -- `mock.patch` hands it over
    flows: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Which is the whole of what the key is for: the list was short, and now it is not."""
    import hmz.models

    def says(cli: str, provider: str = "", seconds: float = 0.0) -> tuple[Model, ...]:
        return (Model("claude-ten", ("max", "high")),)

    monkeypatch.setattr(hmz.models, "ask", says)
    app = Humanize()
    async with app.run_test() as driver:
        await _to_the_models(app, driver)
        assert _rows(app) == 0

        await driver.press("ctrl+r")

        await until(lambda: _rows(app) == 1, driver)
        await until(lambda: "max effort" in _under(app), driver)


@pytest.mark.timeout(60)
@unittest.mock.patch("hmz.tui.app.installed", return_value=CLAUDE)
async def test_a_cli_that_will_not_say_says_so_under_the_list(
    _installed: unittest.mock.MagicMock,  # noqa: PT019  -- `mock.patch` hands it over
    flows: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Said where it was asked for rather than raised at whoever opened the sheet."""
    import hmz.models

    def refuses(cli: str, provider: str = "", seconds: float = 0.0) -> None:
        raise ValueError("claude exited 1: not logged in")

    monkeypatch.setattr(hmz.models, "ask", refuses)
    app = Humanize()
    async with app.run_test() as driver:
        await _to_the_models(app, driver)

        await driver.press("ctrl+r")

        await until(lambda: "not logged in" in _under(app), driver)
        # And the sheet is still the sheet: the question it asks is still worth answering.
        assert isinstance(app.screen, Models)
        assert _rows(app) == 1


@pytest.mark.timeout(60)
@unittest.mock.patch("hmz.tui.app.installed", return_value=CLAUDE)
async def test_the_models_are_the_chosen_accounts_rather_than_this_machines(
    _installed: unittest.mock.MagicMock,  # noqa: PT019  -- `mock.patch` hands it over
    flows: Path,
) -> None:
    """Two accounts of one CLI are two catalogues, and the step before settles which."""
    from hmz import models, providers

    providers.add("claude", "mine", "key", {"ANTHROPIC_API_KEY": "sk-x"})
    kept = models.where("claude", "mine")
    kept.parent.mkdir(parents=True, exist_ok=True)
    kept.write_text(
        '{"asked": "now", "models": [{"name": "claude-theirs", "efforts": ["high"]}]}'
    )
    app = Humanize()
    async with app.run_test() as driver:
        await driver.press(*"/flow here")
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, RunsAs), driver)
        # The row under "as installed", which is the account just written down.
        await driver.press("down", "enter")
        await until(lambda: isinstance(app.screen, Models), driver)

        await until(lambda: _rows(app) == 1, driver)
        assert "claude-theirs" in str(
            app.screen.query_one("#choices", OptionList).options[0].prompt
        )


@pytest.mark.timeout(60)
@unittest.mock.patch("hmz.tui.app.installed", return_value=UNASKED)
async def test_a_backend_that_has_never_been_asked_is_asked_as_the_interface_opens(
    _installed: unittest.mock.MagicMock,  # noqa: PT019  -- `mock.patch` hands it over
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Before the first asking there is nothing to offer and nothing to open talking to."""
    import hmz.models

    asked: list[str] = []

    def note(cli: str, provider: str = "", seconds: float = 0.0) -> tuple[Model, ...]:
        asked.append(cli)
        return (Model("claude-ten", ("max", "high")),)

    monkeypatch.setattr(hmz.models, "ask", note)
    app = Humanize()
    async with app.run_test() as driver:
        await until(lambda: asked == ["claude"], driver)


@pytest.mark.timeout(60)
@unittest.mock.patch("hmz.tui.app.installed", return_value=CLAUDE)
async def test_a_backend_that_has_already_said_is_not_asked_again_on_its_own(
    _installed: unittest.mock.MagicMock,  # noqa: PT019  -- `mock.patch` hands it over
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Asking is a coding agent starting up, and the key on the models is what asks again."""
    import hmz.models
    from hmz import models

    kept = models.where("claude")
    kept.parent.mkdir(parents=True, exist_ok=True)
    kept.write_text('{"asked": "before", "models": []}')
    asked: list[str] = []

    def note(cli: str, provider: str = "", seconds: float = 0.0) -> tuple[Model, ...]:
        asked.append(cli)
        return ()

    monkeypatch.setattr(hmz.models, "ask", note)
    app = Humanize()
    async with app.run_test() as driver:
        await driver.pause()
        await driver.pause()

    assert asked == []

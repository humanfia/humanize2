"""Choosing a flow out of the places flows come from, and adding a place to the list.

The flows are a tab apiece by where they came from -- humanize's own, its repository of the
rest, whatever else has been added, and then this project's and yours -- so what is checked
here is that the tabs are those places, that the arrows walk them, and that the three things
that can happen to a flowverse happen from the same sheet the flow is chosen at.

Driven headlessly, as every test of the interface is, so what is checked is where a keystroke
lands rather than how it is drawn.
"""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

import pytest
from textual.widgets import Label, OptionList

from humanize.flows import OFFICIAL, flowverses
from humanize.flows import verses as store
from humanize.tui import Humanize
from humanize.tui.pick import Fetches, Flows

from .test_app import until

if TYPE_CHECKING:
    from pathlib import Path

    from textual.pilot import Pilot

#: A flow, as short as one can be: what is being fetched is the file, not what it does.
FLOW = '''"""Somebody else's loop, fetched from somewhere else."""

from humanize.agents import AgentBase


def run(agents: tuple[AgentBase], task: str) -> None:
    (agent,) = agents
    agent.new()(task)
'''


def _git(*said: str, at: Path) -> None:
    """Runs one git command in a directory, failing the test if it fails."""
    subprocess.run(["git", "-C", str(at), *said], check=True, capture_output=True)


@pytest.fixture
def theirs(tmp_path: Path) -> Path:
    """A repository of one flow, to be fetched from."""
    where = tmp_path / "theirs"
    where.mkdir()
    (where / "loop.py").write_text(FLOW)
    _git("init", "-b", "main", at=where)
    _git("config", "user.email", "t@example.com", at=where)
    _git("config", "user.name", "t", at=where)
    _git("add", "-A", at=where)
    _git("commit", "-m", "one flow", at=where)
    return where


async def _open(app: Humanize, driver: Pilot[None]) -> Flows:
    """Opens the flow sheet, as `/flow` does, and waits for it to be drawn."""
    await driver.press(*"/flow")
    await driver.press("enter")
    await until(lambda: isinstance(app.screen, Flows), driver)
    sheet = app.screen
    assert isinstance(sheet, Flows)
    await until(lambda: bool(sheet.query_one("#choices", OptionList).options), driver)
    return sheet


def _rows(sheet: Flows) -> list[str]:
    """What the list is offering now, by name."""
    return [str(one.id) for one in sheet.query_one("#choices", OptionList).options]


def _tabs(sheet: Flows) -> str:
    """The row of tabs, as it is drawn."""
    return str(sheet.query_one("#tabs", Label).content)


def _under(sheet: Flows) -> str:
    """What is said under the list, which is where a fetch reports itself."""
    return str(sheet.query_one("#tuning", Label).content)


@pytest.mark.timeout(60)
async def test_the_tabs_are_the_places_flows_come_from() -> None:
    """Two of them always: the package, and the repository the rest come from."""
    app = Humanize()
    async with app.run_test() as driver:
        sheet = await _open(app, driver)

        assert "builtin" in _tabs(sheet)
        assert OFFICIAL in _tabs(sheet)
        # The tab that is open is the first, which is the flows humanize itself ships.
        assert _rows(sheet) == ["chat", "ralph_loop", "stateful_ralph"]


@pytest.mark.timeout(60)
async def test_the_arrows_walk_the_tabs(theirs: Path) -> None:
    """Up and down are the flows under one, so left and right are the tabs themselves."""
    store.add(str(theirs))
    app = Humanize()
    async with app.run_test() as driver:
        sheet = await _open(app, driver)

        await driver.press("right")  # official, which has not been fetched
        await driver.pause()
        assert _rows(sheet) == []
        assert "has not been fetched yet" in _under(sheet)

        await driver.press("right")  # and the one that was added, which has
        await driver.pause()
        assert _rows(sheet) == ["theirs/loop"]

        await driver.press("left", "left")  # back round to where it opened
        await driver.pause()
        assert _rows(sheet) == ["chat", "ralph_loop", "stateful_ralph"]


@pytest.mark.timeout(60)
async def test_a_flow_says_what_it_does_beside_its_name() -> None:
    """Which is what the column that used to say where it came from is for now."""
    app = Humanize()
    async with app.run_test() as driver:
        sheet = await _open(app, driver)
        drawn = str(sheet.query_one("#choices", OptionList).get_option("chat").prompt)

        assert "one agent, one session" in drawn


@pytest.mark.timeout(60)
async def test_the_flows_of_your_own_are_a_tab_of_their_own(tmp_path: Path) -> None:
    """A directory is not a flowverse, but it is a place flows come from, so it is a tab."""
    where = tmp_path / ".humanize" / "flows"
    where.mkdir(parents=True)
    (where / "mine.py").write_text(FLOW)
    app = Humanize()
    async with app.run_test() as driver:
        sheet = await _open(app, driver)

        assert "local" in _tabs(sheet)
        await driver.press("left")  # the last tab, which is the nearest place
        await driver.pause()
        assert _rows(sheet) == [".humanize/flows/mine.py"]


@pytest.mark.timeout(60)
async def test_one_is_fetched_from_the_sheet_it_would_be_chosen_at(
    theirs: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Somebody who finds out here that it is not downloaded fixes that here."""
    monkeypatch.setattr(store, "OFFICIAL_URL", str(theirs))
    app = Humanize()
    async with app.run_test() as driver:
        sheet = await _open(app, driver)
        await driver.press("right")
        await driver.pause()
        assert _rows(sheet) == []

        await driver.press("ctrl+r")
        await until(lambda: _rows(sheet) == ["official/loop"], driver)

        assert store.named(OFFICIAL) is not None
        assert "has not been fetched" not in _under(sheet)


@pytest.mark.timeout(60)
async def test_a_fetch_that_failed_is_said_under_the_list(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rather than raised at whoever opened the sheet, which would lose the sheet."""
    monkeypatch.setattr(store, "OFFICIAL_URL", str(tmp_path / "nowhere"))
    app = Humanize()
    async with app.run_test() as driver:
        sheet = await _open(app, driver)
        await driver.press("right")
        await driver.pause()

        await driver.press("ctrl+r")
        await until(lambda: "does not exist" in _under(sheet), driver)

        assert isinstance(app.screen, Flows)  # still here, still asking
        assert store.named(OFFICIAL) is not None  # and still offered, still unfetched


@pytest.mark.timeout(60)
async def test_there_is_nothing_to_fetch_for_the_ones_in_the_package() -> None:
    """The flows humanize ships are in the package: a fetch is not what would change them."""
    app = Humanize()
    async with app.run_test() as driver:
        sheet = await _open(app, driver)

        await driver.press("ctrl+r")
        await until(lambda: "nothing to fetch" in _under(sheet), driver)


@pytest.mark.timeout(60)
async def test_one_is_added_from_the_same_sheet(theirs: Path) -> None:
    """A repository typed in, cloned, and its flows offered under the name it is kept under."""
    app = Humanize()
    async with app.run_test() as driver:
        sheet = await _open(app, driver)

        await driver.press("ctrl+n")
        await until(lambda: isinstance(app.screen, Fetches), driver)
        await driver.press(*str(theirs))
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Flows), driver)

        # Fetched, and the tab it was fetched into is the one now open.
        await until(lambda: _rows(sheet) == ["theirs/loop"], driver)
        assert [one.name for one in flowverses()][-1] == "theirs"


@pytest.mark.timeout(60)
async def test_a_flowverse_with_no_repository_named_is_refused_where_it_was_typed() -> (
    None
):
    app = Humanize()
    async with app.run_test() as driver:
        await _open(app, driver)
        await driver.press("ctrl+n")
        await until(lambda: isinstance(app.screen, Fetches), driver)
        sheet = app.screen

        await driver.press("enter")
        await driver.pause()

        assert isinstance(app.screen, Fetches)  # still asking, rather than gone
        assert "none was named" in str(sheet.query_one("#tuning", Label).content)


@pytest.mark.timeout(60)
async def test_a_name_that_is_not_one_is_refused_before_anything_is_cloned() -> None:
    """A flowverse is a directory under humanize's home, and a name that climbs out is not one."""
    app = Humanize()
    async with app.run_test() as driver:
        await _open(app, driver)
        await driver.press("ctrl+n")
        await until(lambda: isinstance(app.screen, Fetches), driver)
        sheet = app.screen

        await driver.press(*"somewhere")
        await driver.press("down")
        await driver.press(*"../..")
        await driver.press("enter")
        await driver.pause()

        assert isinstance(app.screen, Fetches)
        assert "not a flowverse name" in str(sheet.query_one("#tuning", Label).content)


@pytest.mark.timeout(60)
async def test_one_that_was_added_may_be_taken_away_from_here(theirs: Path) -> None:
    store.add(str(theirs))
    app = Humanize()
    async with app.run_test() as driver:
        sheet = await _open(app, driver)
        await driver.press("right", "right")
        await driver.pause()
        assert _rows(sheet) == ["theirs/loop"]

        await driver.press("ctrl+x")
        await driver.pause()

        assert [one.name for one in flowverses()] == ["builtin", OFFICIAL]
        assert "no longer here" in _under(sheet)


@pytest.mark.timeout(60)
async def test_neither_of_humanize_s_own_may_be_taken_away() -> None:
    """One is the package and one is where the rest come from: both are always in the list."""
    app = Humanize()
    async with app.run_test() as driver:
        sheet = await _open(app, driver)

        await driver.press("ctrl+x")
        await driver.pause()

        assert "always here" in _under(sheet)
        assert _rows(sheet) == ["chat", "ralph_loop", "stateful_ralph"]


@pytest.mark.timeout(60)
async def test_the_flow_that_is_picked_is_the_one_that_was_chosen(theirs: Path) -> None:
    """The name a flowverse's flow is offered under is the name that is answered with."""
    store.add(str(theirs))
    app = Humanize()
    async with app.run_test() as driver:
        sheet = await _open(app, driver)
        await driver.press("right", "right")
        await until(lambda: _rows(sheet) == ["theirs/loop"], driver)

        await driver.press("enter")
        await driver.pause()

        assert not isinstance(
            app.screen, Flows
        )  # on to what it runs, which is the next step

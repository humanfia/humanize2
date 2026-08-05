"""`/flowverses` -- the places flows come from, and the four things to do with one.

Its own menu rather than three keys on the sheet a flow is chosen at. Adding a repository,
fetching one again and taking one away are things done to the list of places rather than to
the flow under the cursor, and a sheet that asks `which flow` with keys on it about something
else is a sheet asking two questions. What one holds is the fourth: it is the one question
about a flowverse that costs something to answer, since reading a flow means running it.

Driven headlessly, as every test of the interface is, so what is checked is where a keystroke
lands rather than how it is drawn.
"""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

import pytest
from textual.widgets import Label, OptionList

from hmz.flows import OFFICIAL, flowverses
from hmz.flows import verses as store
from hmz.tui import Humanize
from hmz.tui.pick import Fetches, Flowverses, Holds
from tests.stubs import written

from .test_app import onto, rows, until

if TYPE_CHECKING:
    from pathlib import Path

    from textual.pilot import Pilot

#: A flow, as short as one can be: what is being fetched is the file, not what it does.
FLOW = '''"""Somebody else's loop, fetched from somewhere else."""

from hmz.agents import AgentBase
from hmz.flows import flow


@flow
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
    (where / store.FLOWS).mkdir(parents=True)
    written(where / store.FLOWS, "loop", FLOW)
    _git("init", "-b", "main", at=where)
    _git("config", "user.email", "t@example.com", at=where)
    _git("config", "user.name", "t", at=where)
    _git("add", "-A", at=where)
    _git("commit", "-m", "one flow", at=where)
    return where


async def _open(app: Humanize, driver: Pilot[None]) -> Flowverses:
    """Opens the places flows come from, as `/flowverses` does."""
    await driver.press(*"/flowverses")
    await driver.press("enter")
    await until(lambda: isinstance(app.screen, Flowverses), driver)
    sheet = app.screen
    assert isinstance(sheet, Flowverses)
    await until(lambda: bool(sheet.query_one("#choices", OptionList).options), driver)
    return sheet


def _under(sheet: Flowverses | Holds) -> str:
    """What is said under the list, which is where a fetch reports itself."""
    return str(sheet.query_one("#tuning", Label).content)


@pytest.mark.timeout(60)
async def test_every_place_flows_come_from_is_listed(theirs: Path) -> None:
    """Two of them always -- the package and the repository the rest come from -- and yours."""
    store.add(str(theirs))
    app = Humanize()
    async with app.run_test() as driver:
        sheet = await _open(app, driver)

        assert rows(app) == ["builtin", OFFICIAL, "theirs"]
        drawn = str(
            sheet.query_one("#choices", OptionList).get_option("=builtin").prompt
        )
        assert "the flows humanize ships" in drawn


def test_a_private_url_is_not_shown_with_what_was_signed_into_it(
    tmp_path: Path,
) -> None:
    """A token drawn on a screen is a token in a photograph, as on the command line.

    A private flowverse is added as `https://x-access-token:$TOKEN@...`, git keeps that
    verbatim, and where one came from is on every row of this list.
    """
    from hmz.tui.pick import _came_from

    said = _came_from(
        store.Flowverse(
            name="mine",
            url="https://x-access-token:ghp_secret@github.com/org/flows",
            at=tmp_path,
            fetched=True,
            fixed=False,
        )
    )

    assert "ghp_secret" not in said
    assert said == "https://***@github.com/org/flows"


@pytest.mark.timeout(60)
async def test_what_one_holds_is_read_when_it_is_asked_for(theirs: Path) -> None:
    """Reading a flow means running it, so it is asked of the one somebody opened."""
    store.add(str(theirs))
    app = Humanize()
    async with app.run_test() as driver:
        await _open(app, driver)
        await onto(app, driver, "theirs")
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Holds), driver)

        assert rows(app) == ["theirs/loop"]
        assert "Somebody else's loop" in str(
            app.screen.query_one("#choices", OptionList).get_option_at_index(0).prompt
        )


@pytest.mark.timeout(60)
async def test_one_that_has_not_been_fetched_says_so_where_its_flows_would_be() -> None:
    """Rather than saying it holds nothing, which is what an empty list reads as."""
    app = Humanize()
    async with app.run_test() as driver:
        sheet = await _open(app, driver)
        drawn = str(
            sheet.query_one("#choices", OptionList).get_option(f"={OFFICIAL}").prompt
        )
        assert "not fetched yet" in drawn

        await onto(app, driver, OFFICIAL)
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Holds), driver)

        assert rows(app) == []
        assert "not fetched yet" in _under(app.screen)  # pyright: ignore[reportArgumentType]


@pytest.mark.timeout(60)
async def test_one_is_fetched_from_here(
    theirs: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Somebody who finds out that it is not downloaded fixes that where they found out."""
    monkeypatch.setattr(store, "OFFICIAL_URL", str(theirs))
    app = Humanize()
    async with app.run_test() as driver:
        sheet = await _open(app, driver)
        await onto(app, driver, OFFICIAL)

        await driver.press("r")
        await until(lambda: "is fetched" in _under(sheet), driver)

        one = store.named(OFFICIAL)
        assert one is not None
        assert one.fetched


@pytest.mark.timeout(60)
async def test_a_fetch_that_failed_is_said_under_the_list(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rather than raised at whoever opened the sheet, which would lose the sheet."""
    monkeypatch.setattr(store, "OFFICIAL_URL", str(tmp_path / "nowhere"))
    app = Humanize()
    async with app.run_test() as driver:
        sheet = await _open(app, driver)
        await onto(app, driver, OFFICIAL)

        await driver.press("r")
        await until(lambda: "does not exist" in _under(sheet), driver)

        assert isinstance(app.screen, Flowverses)  # still here, still asking
        assert store.named(OFFICIAL) is not None  # and still offered, still unfetched


@pytest.mark.timeout(60)
async def test_there_is_nothing_to_fetch_for_the_ones_in_the_package() -> None:
    """The flows humanize ships are in the package: a fetch is not what would change them."""
    app = Humanize()
    async with app.run_test() as driver:
        sheet = await _open(app, driver)
        await onto(app, driver, "builtin")

        await driver.press("r")
        await until(lambda: "nothing to fetch" in _under(sheet), driver)


@pytest.mark.timeout(60)
async def test_one_is_added_from_here(theirs: Path) -> None:
    """A repository typed in, cloned, and its flows offered under the name it is kept under."""
    app = Humanize()
    async with app.run_test() as driver:
        sheet = await _open(app, driver)

        await driver.press("a")
        await until(lambda: isinstance(app.screen, Fetches), driver)
        await driver.press(*str(theirs))
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Flowverses), driver)
        await until(lambda: "theirs" in rows(app), driver)

        assert [one.name for one in flowverses()][-1] == "theirs"
        assert "is fetched" in _under(sheet)


@pytest.mark.timeout(60)
async def test_a_flowverse_with_no_repository_named_is_refused_where_it_was_typed() -> (
    None
):
    app = Humanize()
    async with app.run_test() as driver:
        await _open(app, driver)
        await driver.press("a")
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
        await driver.press("a")
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
    """Twice on the same key, since it cannot be undone: flows and all."""
    store.add(str(theirs))
    app = Humanize()
    async with app.run_test() as driver:
        sheet = await _open(app, driver)
        await onto(app, driver, "theirs")

        await driver.press("d")
        await until(lambda: "press d again" in _under(sheet), driver)
        assert [one.name for one in flowverses()] == ["builtin", OFFICIAL, "theirs"]

        await driver.press("d")
        await until(lambda: "no longer here" in _under(sheet), driver)

        assert [one.name for one in flowverses()] == ["builtin", OFFICIAL]
        assert rows(app) == ["builtin", OFFICIAL]


@pytest.mark.timeout(60)
async def test_neither_of_humanize_s_own_may_be_taken_away() -> None:
    """One is the package and one is where the rest come from: both are always in the list."""
    app = Humanize()
    async with app.run_test() as driver:
        sheet = await _open(app, driver)
        await onto(app, driver, "builtin")

        await driver.press("d")
        await driver.press("d")
        await until(lambda: "always here" in _under(sheet), driver)

        assert rows(app) == ["builtin", OFFICIAL]


@pytest.mark.timeout(60)
async def test_what_happened_while_it_was_open_is_said_in_the_transcript(
    theirs: Path,
) -> None:
    """A menu that ran git and said nothing afterwards is one nobody can read back."""
    from .test_app import _transcript

    store.add(str(theirs))
    app = Humanize()
    async with app.run_test() as driver:
        await _open(app, driver)
        await onto(app, driver, "theirs")
        await driver.press("d")
        await driver.press("d")
        await driver.press("escape")
        await until(lambda: not isinstance(app.screen, Flowverses), driver)

        assert "theirs is no longer here" in _transcript(app)

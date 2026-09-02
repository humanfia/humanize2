"""Choosing a flow out of the places flows come from.

The flows are read a place at a time -- humanize's own, whatever else has been added, and then
this project's and yours -- so what is checked here is that the arrows step between those
places, and that the list holds the one being read and nothing else.
What can happen to a flowverse is `/flowverses` and is checked beside it: this page is about
which flow to run.

Driven headlessly, as every test of the interface is, so what is checked is where a keystroke
lands rather than how it is drawn.
"""

from __future__ import annotations

import asyncio
import re
import subprocess
import unittest.mock
from typing import TYPE_CHECKING

import pytest
from textual.widgets import Label, OptionList

from hmz.coganchor.backends import Model
from hmz.flows import ENTRY, OFFICIAL
from hmz.flows import verses as store
from hmz.tui import Humanize
from hmz.tui.pick import Agent, Configures, Flows
from tests.stubs import written

from .test_app import into_agent, onto, until

if TYPE_CHECKING:
    from pathlib import Path

    from textual.pilot import Pilot

#: A flow, as short as one can be: what is being fetched is the file, not what it does.
FLOW = '''"""Somebody else's loop, fetched from somewhere else."""

from hmz.coganchor.agents import AgentBase
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


async def _open(app: Humanize, driver: Pilot[None]) -> Flows:
    """Opens the flow sheet, as `/flow` does, and waits for it to be drawn."""
    await driver.press(*"/flow")
    await driver.press("enter")
    await until(lambda: isinstance(app.screen, Flows), driver)
    sheet = app.screen
    assert isinstance(sheet, Flows)
    await until(lambda: bool(sheet.query_one("#choices", OptionList).options), driver)
    return sheet


def _rows(sheet: Flows, whose: str = "") -> list[str]:
    """What the list is offering now, by name, out of the place being read."""
    listed = [
        str(one.id or "").partition("\x1f")
        for one in sheet.query_one("#choices", OptionList).options
        if one.id
    ]
    return [name for where, _, name in listed if name and where.startswith(whose)]


#: What a sheet colours a word with, which is what a test reading one back is not after.
_MARKUP = re.compile(r"\[[^\]]*\]")


def _places(sheet: Flows) -> list[str]:
    """The places flows come from, as the strip the arrows step along says them."""
    said = str(sheet.query_one("#tabs", Label).content).splitlines()[-1]
    return [
        one.strip()
        for one in _MARKUP.sub("", said.split("←")[0]).split("·")
        if one.strip()
    ]


async def _steps(app: Humanize, driver: Pilot[None], whose: str) -> Flows:
    """Steps the flows page round to the place of that name, as the arrows do.

    Args:
      app: The interface.
      driver: What is pumping it.
      whose: The place to read.

    Returns:
      The sheet, now reading that place.
    """
    sheet = app.screen
    assert isinstance(sheet, Flows)
    for _ in range(len(_places(sheet)) + 1):
        if sheet._where == whose:
            return sheet
        await driver.press("right")
        await driver.pause()
    raise AssertionError(f"{whose} is not a place the arrows step to")


def _under(sheet: Flows) -> str:
    """What is said under the list, which is where a fetch reports itself."""
    return str(sheet.query_one("#tuning", Label).content)


def _fetched() -> bool:
    """Whether humanize's own flowverse has been cloned yet."""
    verse = store.named(OFFICIAL)
    return verse is not None and verse.fetched


@pytest.mark.timeout(60)
async def test_the_strip_is_the_places_flows_come_from() -> None:
    """One of them always: humanize's own, which is both of the places it keeps flows."""
    app = Humanize()
    async with app.run_test() as driver:
        sheet = await _open(app, driver)

        assert _places(sheet) == [OFFICIAL]
        # And it opens on the place the flow it is set up on came from, which is humanize's.
        assert sheet._where == OFFICIAL
        # The half of it that is in the package, nothing having been fetched here.
        assert _rows(sheet) == ["chat"]


@pytest.mark.timeout(60)
async def test_the_arrows_step_between_the_places(theirs: Path) -> None:
    """A list apiece rather than every flow there is run together under headings."""
    store.add(str(theirs))
    app = Humanize()
    async with app.run_test() as driver:
        sheet = await _open(app, driver)

        assert _places(sheet) == [OFFICIAL, "theirs"]
        assert _rows(sheet) == ["chat"]

        await driver.press("right")
        await until(lambda: sheet._where == "theirs", driver)
        assert _rows(sheet) == ["theirs/loop"]

        # And round again, which is what the far end of a strip is for.
        await driver.press("right")
        await until(lambda: sheet._where == OFFICIAL, driver)
        await driver.press("left")
        await until(lambda: sheet._where == "theirs", driver)


@pytest.mark.timeout(60)
async def test_a_search_steps_to_the_places_it_found_something_in() -> None:
    """Nobody remembers which flowverse a flow is in; that is what a search is for."""
    app = Humanize()
    async with app.run_test() as driver:
        sheet = await _open(app, driver)

        await driver.press("s")
        await driver.press(*"cha")
        await until(lambda: _rows(sheet) == ["chat"], driver)

        # Only the places holding one, so that nothing steps through empty lists.
        assert _places(sheet) == [OFFICIAL]


@pytest.mark.timeout(60)
async def test_the_keys_stay_inside_the_terminal(tmp_path: Path) -> None:
    """A place of twenty flows is a list shortened to fit, not a sheet with no keys on it."""
    where = tmp_path / ".humanize" / "flows"
    where.mkdir(parents=True)
    for n in range(20):
        written(where, f"flow_{n:02d}", FLOW)
    app = Humanize()
    async with app.run_test(size=(80, 20)) as driver:
        await _open(app, driver)
        sheet = await _steps(app, driver, "local")
        keys = sheet.query_one("#keys", Label)
        listing = sheet.query_one("#choices", OptionList)

        assert len(_rows(sheet)) == 20  # every one of them offered, all the same
        assert sheet.query_one("#rule", Label).region.y >= 0
        assert keys.region.bottom <= app.size.height
        # And the line of them wrapped rather than run off the side.
        assert keys.region.right <= app.size.width
        short = listing.size.height

        # A taller terminal is more of them read at once, rather than the same few.
        await driver.resize_terminal(80, 40)
        await driver.pause()

        assert listing.size.height > short
        assert keys.region.bottom <= app.size.height


@pytest.mark.timeout(60)
async def test_a_flow_says_what_it_does_beside_its_name() -> None:
    """Which is what the column that used to say where it came from is for now."""
    app = Humanize()
    async with app.run_test() as driver:
        sheet = await _open(app, driver)
        drawn = str(
            sheet.query_one("#choices", OptionList)
            .get_option("official\x1fchat")
            .prompt
        )

        assert "one agent, one session" in drawn


@pytest.mark.timeout(60)
async def test_the_flows_of_your_own_are_a_place_of_their_own(tmp_path: Path) -> None:
    """A directory is not a flowverse, but it is a place flows come from, so it is one."""
    where = tmp_path / ".humanize" / "flows"
    where.mkdir(parents=True)
    written(where, "mine", FLOW)
    app = Humanize()
    async with app.run_test() as driver:
        sheet = await _open(app, driver)

        assert "local" in _places(sheet)
        await _steps(app, driver, "local")
        assert _rows(sheet) == ["local/mine"]


@pytest.mark.timeout(60)
@pytest.mark.usefixtures("catching_up")
async def test_what_was_never_fetched_is_fetched_as_the_menu_opens(
    theirs: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """It is here because its flows are wanted; a key to press for them is a key nobody would."""
    monkeypatch.setattr(store, "OFFICIAL_URL", str(theirs))
    app = Humanize()
    async with app.run_test() as driver:
        sheet = await _open(app, driver)

        await until(_fetched, driver)
        # And it left what was being read where it was: the menu opened on the place the
        # flow in force came from, and nobody asked to be taken anywhere else.
        assert sheet._where == OFFICIAL

        # What came down is offered beside the half that was already here, under the one name.
        await until(lambda: _rows(sheet) == ["chat", "loop"], driver)


@pytest.mark.timeout(60)
@pytest.mark.usefixtures("freshening")
async def test_every_flowverse_is_fetched_as_the_interface_starts(
    theirs: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A flowverse only ever fetched on a keypress is one that is months behind.

    Quietly: there is already a list of flows to show, nobody asked for a download, and the
    prompt is up before any of it starts.

    The one nobody has fetched yet included. That is the one whose flows nobody can run at
    all, so it is the one most worth getting -- and a first fetch that waited for somebody to
    open the flow menu was a first fetch the menu then drew the list from before.
    """
    monkeypatch.setattr(store, "OFFICIAL_URL", str(theirs))
    store.add(str(theirs), name="theirs")
    written(theirs / store.FLOWS, "second", FLOW)
    _git("add", "-A", at=theirs)
    _git("commit", "-m", "another flow", at=theirs)
    app = Humanize()

    async with app.run_test() as driver:
        added = store.named("theirs")
        assert added is not None
        await until(lambda: store.flows(added) == ["loop", "second"], driver)

        # And the one nobody had fetched, which is now here to be run.
        await until(lambda: (store.named(OFFICIAL) or added).fetched, driver)
        one = store.named(OFFICIAL)
        assert one is not None
        assert one.fetched


@pytest.mark.timeout(60)
@pytest.mark.usefixtures("freshening")
async def test_a_flowverse_somebody_has_written_into_is_left_where_it_is(
    theirs: Path,
) -> None:
    """A fetch resets the clone, and a weaver editing a flow in one would lose the morning."""
    added = store.add(str(theirs))
    (held,) = store.holds(added)
    (held / "loop" / ENTRY).write_text(FLOW.replace("Somebody", "Mine now"))
    written(theirs / store.FLOWS, "second", FLOW)
    _git("add", "-A", at=theirs)
    _git("commit", "-m", "another flow", at=theirs)
    app = Humanize()

    async with app.run_test() as driver:
        # Pumped a while, what is being waited for here being something that must not happen.
        for _ in range(40):
            await driver.pause()
            await asyncio.sleep(0.02)

        assert "Mine now" in (held / "loop" / ENTRY).read_text()
        assert store.flows(added) == ["loop"]  # nor what it would have fetched

    # And with the edit put back the way the repository has it, the next start does fetch --
    # so what held it back was the edit rather than nothing having run at all.
    (held / "loop" / ENTRY).write_text(FLOW)
    again = Humanize()
    async with again.run_test() as driver:
        await until(lambda: store.flows(added) == ["loop", "second"], driver)


@pytest.mark.timeout(60)
async def test_the_flow_that_is_picked_is_the_one_that_was_chosen(theirs: Path) -> None:
    """The name a flowverse's flow is offered under is the name that is answered with."""
    store.add(str(theirs))
    app = Humanize()
    async with app.run_test() as driver:
        await _open(app, driver)
        sheet = await _steps(app, driver, "theirs")
        await until(lambda: _rows(sheet) == ["theirs/loop"], driver)

        await driver.press("enter")
        await until(lambda: sheet._inside, driver)

        # And into what it runs, which is that flow's own agents.
        assert sheet._flow == "theirs/loop"


#: A file that is three flows and no `run`, which is what humanize1 is.
THREE = '''"""Three phases of one thing, which are three things to run."""

from typing import NamedTuple

from pydantic import BaseModel

from hmz.coganchor.agents import AgentBase
from hmz.flows import flow


class Drafting(NamedTuple):
    """The one that writes."""

    drafter: AgentBase


class Building(NamedTuple):
    """The one that builds, and the one that reads it."""

    builder: AgentBase
    reviewer: AgentBase


class Wide(BaseModel):
    """What the first phase takes."""

    n: int = 6


@flow(name="gen-idea")
def gen_idea(agents: Drafting, task: str, config: Wide | None = None) -> None:
    """Opens a loose idea into a draft."""


@flow(name="rlcr")
def rlcr(agents: Building, task: str) -> None:
    """Builds it, under review."""
'''


@pytest.mark.timeout(60)
@unittest.mock.patch(
    "hmz.tui.app.installed",
    return_value={"claude": (Model("claude-opus-5", ("max", "high")),)},
)
async def test_one_of_the_flows_a_file_holds_is_chosen_like_any_other(
    _installed: unittest.mock.MagicMock,  # noqa: PT019  -- `mock.patch` hands it over
    tmp_path: Path,
) -> None:
    """The walk on from it is that flow's own: its agents, and the settings it takes."""
    where = tmp_path / ".humanize" / "flows"
    where.mkdir(parents=True)
    written(where, "three", THREE)
    app = Humanize()
    async with app.run_test() as driver:
        await _open(app, driver)
        sheet = await _steps(app, driver, "local")

        assert _rows(sheet) == [
            "local/three:gen-idea",
            "local/three:rlcr",
        ]

        # The second of them, which drives two agents.
        await onto(app, driver, "local\x1flocal/three:rlcr")
        await driver.press("enter")

        # On to what that flow drives, rather than a refusal that the file has no `run`.
        await until(lambda: sheet._inside, driver)
        await into_agent(app, driver)
        assert isinstance(app.screen, Agent)
        assert "builder" in str(app.screen.query_one("#asked", Label).content)


@pytest.mark.timeout(60)
@unittest.mock.patch(
    "hmz.tui.app.installed",
    return_value={"claude": (Model("claude-opus-5", ("max", "high")),)},
)
async def test_each_of_them_is_set_up_with_its_own_settings(
    _installed: unittest.mock.MagicMock,  # noqa: PT019  -- `mock.patch` hands it over
    tmp_path: Path,
) -> None:
    """Choosing one asks what that phase takes, which is not what the one beside it takes."""
    where = tmp_path / ".humanize" / "flows"
    where.mkdir(parents=True)
    written(where, "three", THREE)
    app = Humanize()
    async with app.run_test() as driver:
        await _open(app, driver)
        sheet = await _steps(app, driver, "local")
        await until(lambda: bool(_rows(sheet)), driver)

        # The first of them, which says it takes an `n`.
        await onto(app, driver, "local\x1flocal/three:gen-idea")
        await driver.press("enter")

        await until(lambda: isinstance(app.screen, Configures), driver)
        assert "n" in str(app.screen.query_one("#choices", OptionList).options[0].id)

        # And the one beside it takes nothing, so choosing it asks nothing.
        await driver.press("escape")
        await until(lambda: sheet._inside, driver)
        await driver.press("escape")
        await until(lambda: not sheet._inside, driver)
        await onto(app, driver, "local\x1flocal/three:rlcr")
        await driver.press("enter")
        await until(lambda: sheet._inside, driver)

        assert isinstance(app.screen, Flows)


@pytest.mark.timeout(60)
async def test_a_flow_is_copied_here_to_be_changed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`f` on one is the way to change a flow at all, since a fetched one is fetched over.

    A flow is a directory, so a copy of one is a flow: what it imports and the skills it
    brings come across with it, under the name it already had -- and your own flows are
    looked in first, so from then on that name means the copy.
    """
    monkeypatch.chdir(tmp_path)
    app = Humanize()
    async with app.run_test() as driver:
        sheet = await _open(app, driver)
        await onto(app, driver, "official\x1fchat")

        await driver.press("f")
        await until(lambda: "copied to" in _under(sheet), driver)

        assert "chat now means it" in _under(sheet)
        # And it is a flow of your own from here on, listed where your own are.
        await _steps(app, driver, "local")
        assert _rows(sheet) == ["local/chat"]

    at = tmp_path / ".humanize" / "flows" / "chat"
    assert "one agent, one session" in (at / "__init__.py").read_text()
    from hmz.flows import find

    assert find("chat") == str(at / "__init__.py")


@pytest.mark.timeout(60)
async def test_copying_one_twice_says_the_copy_is_already_there(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A copy already made is one to edit, run or take away rather than one to write over."""
    monkeypatch.chdir(tmp_path)
    app = Humanize()
    async with app.run_test() as driver:
        sheet = await _open(app, driver)
        await onto(app, driver, "official\x1fchat")
        await driver.press("f")
        await until(lambda: "copied to" in _under(sheet), driver)

        await _steps(app, driver, OFFICIAL)
        await onto(app, driver, "official\x1fchat")
        await driver.press("f")
        await until(lambda: "already a flow of your own" in _under(sheet), driver)


@pytest.mark.timeout(60)
@pytest.mark.usefixtures("freshening")
async def test_a_fetch_that_lands_makes_an_open_menu_read_the_flows_again(
    theirs: Path,
) -> None:
    """The menu holds what it read, and a download landing under it makes that the old list.

    Which is the whole of what the fetch is for: a flow that arrived in it is a flow nobody
    can run until the list is read again, and a restart to pick up what is already on the disk
    is the fetch having worked and nothing showing it.
    """
    store.add(str(theirs))
    app = Humanize()
    async with app.run_test() as driver:
        sheet = await _open(app, driver)
        await _steps(app, driver, "theirs")
        await until(lambda: _rows(sheet) == ["theirs/loop"], driver)

        # A second flow lands in the repository the menu is reading, and is fetched.
        written(theirs / store.FLOWS, "second", FLOW)
        _git("add", "-A", at=theirs)
        _git("commit", "-m", "another flow", at=theirs)
        added = store.named("theirs")
        assert added is not None
        await asyncio.to_thread(store.fetch, "theirs")
        app._flows_changed()

        # Without the interface having been closed and opened again.
        await until(lambda: _rows(sheet) == ["theirs/loop", "theirs/second"], driver)


@pytest.mark.timeout(60)
async def test_a_flow_that_will_not_load_says_why_it_would_not(tmp_path: Path) -> None:
    """A flow that will not load is a dead end until it says which reason it was.

    They are nothing alike -- a flowverse not fetched, a module that is not installed, a
    syntax error somebody just wrote -- and each is fixed somewhere else.
    """
    where = tmp_path / ".humanize" / "flows"
    where.mkdir(parents=True)
    written(where, "broken", "import a_module_that_is_not_installed_anywhere\n")
    app = Humanize()
    async with app.run_test() as driver:
        sheet = await _open(app, driver)
        await _steps(app, driver, "local")
        await onto(app, driver, "local\x1flocal/broken")
        await driver.press("enter")
        await until(lambda: "will not load" in _under(sheet), driver)

        said = _under(sheet)
        assert "local/broken will not load" in said
        # And what refused it, which is the half that says where to go and fix it.
        assert "a_module_that_is_not_installed_anywhere" in said

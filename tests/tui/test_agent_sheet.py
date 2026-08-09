"""One agent of a flow, set up on one sheet reached from the page the flow's agents are on.

Everything an agent is is a row: the CLI that takes its turns, the account they run as, the
model at an effort, what it is loaded with, what it may do, and -- only where the flow said
that agent may be pointed at a machine -- where its work lands. Which is the point: an agent
is one thing rather than three questions, and changing the effort of one already set up is a
row and an arrow rather than a walk through two sheets that had nothing to say.

Driven headlessly, as every test of the interface is, so what is checked is where a keystroke
lands rather than how it is drawn.
"""

from __future__ import annotations

import unittest.mock
from typing import TYPE_CHECKING, cast

import pytest
from textual.widgets import Label, OptionList

from hmz.backends import Model
from hmz.kept import Runs
from hmz.settings import Settings
from hmz.tui import Humanize
from hmz.tui.pick import Agent, Anchors, Catalogue, Clis, Confirms, Flows
from tests.stubs import written

from .test_app import drops, into_agent, keeps, onto, opens, rows, until

if TYPE_CHECKING:
    from pathlib import Path

    from textual.pilot import Pilot

#: What one installed CLI looks like, for every sheet here.
CLAUDE = {"claude": (Model("claude-opus-5", ("max", "high")),)}

#: A flow whose agent it says nothing about, which is one that works here and is not asked.
HERE = '''
"""One agent, working where the flow is."""

from typing import NamedTuple

from hmz.agents import AgentBase
from hmz.flows import flow


class Agents(NamedTuple):
    """Just the one."""

    builder: AgentBase


@flow
def run(agents: Agents, task: str) -> None:
    pass
'''

#: A flow that says its agent may be pointed at a machine, which is a row of its own.
REMOTE = '''
"""One agent, which may work anywhere it is pointed at."""

from typing import Annotated, NamedTuple

from hmz.agents import AgentBase, Remote
from hmz.flows import flow


class Agents(NamedTuple):
    """Just the one, and it moves."""

    builder: Annotated[AgentBase, Remote]


@flow
def run(agents: Agents, task: str) -> None:
    pass
'''

#: A flow that settles the container itself, which is a machine nobody configures.
BOXED = '''
"""One agent, in a container of the flow's own."""

from typing import Annotated, NamedTuple

from hmz.agents import AgentBase, Isolated
from hmz.flows import flow


class Agents(NamedTuple):
    """Just the one, in a box."""

    tester: Annotated[AgentBase, Isolated("python:3.12")]


@flow
def run(agents: Agents, task: str) -> None:
    pass
'''

#: Two agents that may both be pointed somewhere, which is a sheet apiece.
PAIR = '''
"""Two agents, both of which may work elsewhere."""

from typing import Annotated, NamedTuple

from hmz.agents import AgentBase, Remote
from hmz.flows import flow


class Agents(NamedTuple):
    """One writes, one reads."""

    builder: Annotated[AgentBase, Remote]
    reviewer: Annotated[AgentBase, Remote]


@flow
def run(agents: Agents, task: str) -> None:
    pass
'''


@pytest.fixture
def flows(tmp_path: Path) -> Path:
    """Puts the four flows where this project's own would be."""
    where = tmp_path / ".humanize" / "flows"
    where.mkdir(parents=True)
    written(where, "here", HERE)
    written(where, "remote", REMOTE)
    written(where, "boxed", BOXED)
    written(where, "pair", PAIR)
    return where


def _asked(app: Humanize) -> str:
    """What the sheet on top is asking, which says which agent it is asking about."""
    return str(app.screen.query_one("#asked", Label).content)


def _value(app: Humanize, held: str) -> str:
    """What one row of the agent sheet is set to, as it is drawn."""
    listing = app.screen.query_one("#choices", OptionList)
    return str(listing.get_option_at_index(rows(app).index(held)).prompt)


async def _open(app: Humanize, driver: Pilot[None], flow: str) -> None:
    """Opens the flow menu already holding one flow, and turns to its agents."""
    await driver.press(*f"/flow {flow}")
    await driver.press("enter")
    await until(lambda: isinstance(app.screen, Flows), driver)
    await into_agent(app, driver)


@pytest.mark.timeout(60)
@unittest.mock.patch("hmz.tui.app.installed", return_value=CLAUDE)
async def test_one_agent_is_one_sheet_of_rows_in_the_order_they_depend(
    _installed: unittest.mock.MagicMock,  # noqa: PT019  -- `mock.patch` hands it over
    flows: Path,
) -> None:
    """The CLI settles the accounts and the models, so it comes above both of them."""
    app = Humanize()
    async with app.run_test() as driver:
        await _open(app, driver, "remote")

        assert "builder" in _asked(app)
        assert rows(app) == [
            "import",
            "cli",
            "provider",
            "model",
            "effort",
            "skills",
            "permission",
            "goals",
            "where",
            "save",
            "save as",
        ]
        # The account nobody chose is always the first row of the list it is chosen from.
        assert "as local" in _value(app, "provider")


@pytest.mark.timeout(60)
@unittest.mock.patch("hmz.tui.app.installed", return_value=CLAUDE)
async def test_two_agents_are_two_rows_and_a_sheet_apiece(
    _installed: unittest.mock.MagicMock,  # noqa: PT019  -- `mock.patch` hands it over
    flows: Path,
) -> None:
    """The page lists what the flow drives, by the name the flow calls each of them."""
    app = Humanize()
    async with app.run_test() as driver:
        await driver.press(*"/flow pair")
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Flows), driver)
        sheet = cast("Flows", app.screen)
        await driver.press("tab")
        await until(lambda: sheet._tab == 1, driver)
        listing = sheet.query_one("#choices", OptionList)
        await until(lambda: len(listing.options) == 3, driver)

        assert rows(app) == ["0", "1", "save"]
        assert "builder" in str(listing.get_option_at_index(0).prompt)
        assert "reviewer" in str(listing.get_option_at_index(1).prompt)

        # And each is opened on its own, saying which one it is about.
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Agent), driver)
        assert "builder" in _asked(app)
        await drops(app, driver)

        await until(lambda: isinstance(app.screen, Flows), driver)
        await onto(app, driver, "1")
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Agent), driver)
        assert "reviewer" in _asked(app)


@pytest.mark.timeout(60)
@unittest.mock.patch("hmz.tui.app.installed", return_value=CLAUDE)
async def test_explicit_saves_accept_two_agents_then_apply_the_complete_flow(
    _installed: unittest.mock.MagicMock,  # noqa: PT019  -- `mock.patch` hands it over
    flows: Path,
    tmp_path: Path,
) -> None:
    """A two-agent flow can be set up and saved without backing through either sheet."""
    app = Humanize()
    async with app.run_test() as driver:
        await _open(app, driver, "pair")
        await onto(app, driver, "effort")
        await driver.press("left")
        await driver.pause()

        await opens(app, driver, "save")
        await until(lambda: isinstance(app.screen, Flows), driver)
        assert rows(app) == ["0", "1", "save"]

        await onto(app, driver, "1")
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Agent), driver)
        await onto(app, driver, "effort")
        await driver.press("right")
        await driver.pause()
        await opens(app, driver, "save")
        await until(lambda: isinstance(app.screen, Flows), driver)

        await onto(app, driver, "save")
        await driver.press("enter")
        await until(lambda: not isinstance(app.screen, Flows), driver)

    chosen = [
        Runs("claude/claude-opus-5:high"),
        Runs("claude/claude-opus-5:max"),
    ]
    assert app._flow_named == "pair"
    assert app._models == chosen
    assert Settings(tmp_path).agents("pair") == chosen


@pytest.mark.timeout(60)
@unittest.mock.patch("hmz.tui.app.installed", return_value={})
async def test_explicit_flow_save_refuses_an_agent_with_no_model(
    _installed: unittest.mock.MagicMock,  # noqa: PT019  -- `mock.patch` hands it over
    flows: Path,
) -> None:
    """The save row uses the same completeness check as saving on the way out."""
    app = Humanize()
    async with app.run_test() as driver:
        await driver.press(*"/flow here")
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Flows), driver)
        sheet = cast("Flows", app.screen)
        if sheet._tab != 1:
            await driver.press("tab")
            await until(lambda: sheet._tab == 1, driver)

        await onto(app, driver, "save")
        await driver.press("enter")
        await driver.pause()

        assert app.screen is sheet
        assert "builder has no model yet" in str(
            sheet.query_one("#tuning", Label).content
        )


@pytest.mark.timeout(60)
@pytest.mark.parametrize("flow", ["here", "boxed"])
@unittest.mock.patch("hmz.tui.app.installed", return_value=CLAUDE)
async def test_where_it_works_is_asked_only_where_the_flow_says_it_moves(
    _installed: unittest.mock.MagicMock,  # noqa: PT019  -- `mock.patch` hands it over
    flows: Path,
    flow: str,
) -> None:
    """A place that said nothing works here; one in a container was settled by the flow."""
    app = Humanize()
    async with app.run_test() as driver:
        await _open(app, driver, flow)

        if flow == "here":
            # Nothing to say: an agent that works where the flow does is what every agent
            # nobody said anything about has always been.
            assert "where" not in rows(app)
        else:
            # Read rather than opened: the flow settled it, so nobody is being asked.
            assert "in a container of python:3.12" in _value(app, "where")
            await opens(app, driver, "where")
            await driver.pause()
            assert isinstance(app.screen, Agent)
            assert "the flow settled" in str(
                app.screen.query_one("#tuning", Label).content
            )


@pytest.mark.timeout(60)
@unittest.mock.patch(
    "hmz.tui.pick.machines", return_value=[("ssh://box", "ssh config")]
)
@unittest.mock.patch("hmz.tui.app.installed", return_value=CLAUDE)
async def test_where_an_agent_works_rides_along_with_what_it_runs(
    _installed: unittest.mock.MagicMock,  # noqa: PT019  -- `mock.patch` hands it over
    _machines: unittest.mock.MagicMock,  # noqa: PT019
    flows: Path,
    tmp_path: Path,
) -> None:
    """It is a setting of the agent, so it is kept beside the model and read back with it."""
    app = Humanize()
    async with app.run_test() as driver:
        await _open(app, driver, "remote")
        await opens(app, driver, "where")
        await until(lambda: isinstance(app.screen, Anchors), driver)
        listing = app.screen.query_one("#choices", OptionList)
        await until(lambda: bool(listing.options), driver)
        # This machine first, then the ones there are to be found.
        assert rows(app) == ["", "ssh://box"]

        await driver.press("down")
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Agent), driver)

        await keeps(app, driver)
        await keeps(app, driver)

    chosen = Runs("claude/claude-opus-5:high", "ssh://box")
    assert app._models == [chosen]
    assert Settings(tmp_path).agents("remote") == [chosen]
    # And a second interface opens on what this workspace was left set up to run.
    again = Humanize()
    assert again._models == [chosen]


@pytest.mark.timeout(60)
@unittest.mock.patch("hmz.tui.pick.machines", return_value=[])
@unittest.mock.patch("hmz.tui.app.installed", return_value=CLAUDE)
async def test_a_machine_nothing_here_can_see_is_a_target_that_is_typed(
    _installed: unittest.mock.MagicMock,  # noqa: PT019  -- `mock.patch` hands it over
    _machines: unittest.mock.MagicMock,  # noqa: PT019
    flows: Path,
) -> None:
    """The list is a convenience; a target is a string, and any string that reads as one goes."""
    app = Humanize()
    async with app.run_test() as driver:
        await _open(app, driver, "remote")
        await opens(app, driver, "where")
        await until(lambda: isinstance(app.screen, Anchors), driver)
        listing = app.screen.query_one("#choices", OptionList)
        await until(lambda: bool(listing.options), driver)

        await driver.press("s")
        await driver.press(*"nonsense")
        await driver.pause()
        # Not a target and not a row, so there is nothing there to choose.
        assert rows(app) == []

        for _ in range(len("nonsense")):
            await driver.press("backspace")
        await driver.press(*"docker://box")
        await driver.pause()

        assert rows(app) == ["docker://box"]


@pytest.mark.timeout(60)
@unittest.mock.patch("hmz.tui.app.installed", return_value=CLAUDE)
async def test_nothing_is_applied_until_the_menu_is_saved_on_the_way_out(
    _installed: unittest.mock.MagicMock,  # noqa: PT019  -- `mock.patch` hands it over
    flows: Path,
) -> None:
    """A draft until it is confirmed, and then the whole of it at once.

    Which is what makes the pages one menu rather than two sheets in a row.
    """
    app = Humanize()
    async with app.run_test() as driver:
        was = (app._flow_named, list(app._models))
        await _open(app, driver, "remote")
        await onto(app, driver, "effort")
        await driver.press("left")  # one effort down, which is a change
        await driver.pause()
        assert "high" in _value(app, "effort")

        await drops(app, driver)  # asked about, and thrown away
        await until(lambda: isinstance(app.screen, Flows), driver)
        await drops(app, driver)
        await until(lambda: not isinstance(app.screen, Flows), driver)

        assert (app._flow_named, app._models) == was

        # And the same walk saved lands the lot, flow and agent together.
        await _open(app, driver, "remote")
        await onto(app, driver, "effort")
        await driver.press("left")
        await driver.pause()
        await keeps(app, driver)
        await keeps(app, driver)
        await until(lambda: not isinstance(app.screen, Flows), driver)

    assert app._flow_named == "remote"
    assert app._models == [Runs("claude/claude-opus-5:high")]


@pytest.mark.timeout(60)
@unittest.mock.patch("hmz.tui.app.installed", return_value=CLAUDE)
async def test_the_question_on_the_way_out_is_two_answers_and_esc(
    _installed: unittest.mock.MagicMock,  # noqa: PT019  -- `mock.patch` hands it over
    flows: Path,
) -> None:
    """Going back to the menu is what esc is everywhere else, so it is not a row as well."""
    app = Humanize()
    async with app.run_test() as driver:
        await _open(app, driver, "remote")
        await onto(app, driver, "effort")
        await driver.press("left")
        await driver.pause()

        await driver.press("escape")
        await until(lambda: isinstance(app.screen, Confirms), driver)
        sheet = app.screen
        assert isinstance(sheet, Confirms)
        assert sheet.query_one("#choices", OptionList).option_count == 2

        # And esc off it is the sheet again, holding what it was holding.
        await driver.press("escape")
        await until(lambda: isinstance(app.screen, Agent), driver)

        assert "high" in _value(app, "effort")


@pytest.mark.timeout(60)
@unittest.mock.patch("hmz.tui.app.installed", return_value=CLAUDE)
async def test_walking_out_of_an_unchanged_sheet_asks_nothing(
    _installed: unittest.mock.MagicMock,  # noqa: PT019  -- `mock.patch` hands it over
    flows: Path,
) -> None:
    """A walk in to look and out again is not a question anybody wants asked of them."""
    app = Humanize()
    async with app.run_test() as driver:
        await _open(app, driver, "remote")
        await driver.press("escape")
        await until(lambda: isinstance(app.screen, Flows), driver)
        # Straight back, rather than through a question about a change nobody made.
        assert isinstance(app.screen, Flows)


@pytest.mark.timeout(60)
@unittest.mock.patch("hmz.tui.app.installed", return_value=CLAUDE)
async def test_a_flow_that_puts_its_agent_here_refuses_one_that_was_pointed_away(
    _installed: unittest.mock.MagicMock,  # noqa: PT019  -- `mock.patch` hands it over
    flows: Path,
) -> None:
    """Which is why the row is only offered where the flow allows it.

    The refusal is the runner's, since where an agent works is the flow's to say -- and it is
    a line at this prompt rather than a traceback out of a flow's own thread.
    """
    from .test_app import _transcript

    app = Humanize()
    async with app.run_test() as driver:
        app._flow_named = "here"
        app._wanted = app._places_of("here")
        app._models = [Runs("claude/claude-opus-5:max", "ssh://box")]
        await driver.press(*"go")
        await driver.press("enter")
        await until(lambda: "hmz:" in _transcript(app), driver)
        said = _transcript(app)

    # Wrapped as the transcript wraps it, so it is read a phrase at a time.
    assert "builder runs on this machine" in said
    assert "cannot be pointed at one" in said
    assert "Traceback" not in said  # said at the prompt, not raised out of a thread
    assert not app._agents  # and nothing started


@pytest.mark.timeout(60)
@unittest.mock.patch(
    "hmz.tui.app.installed",
    return_value=CLAUDE | {"opencode": (Model("anthropic/opus", ("high",)),)},
)
async def test_the_flow_may_rule_a_backend_out_of_the_clis_offered(
    _installed: unittest.mock.MagicMock,  # noqa: PT019  -- `mock.patch` hands it over
    tmp_path: Path,
) -> None:
    """A CLI that cannot do what the place needs is one choosing would refuse to start on."""
    where = tmp_path / ".humanize" / "flows"
    where.mkdir(parents=True)
    written(
        where,
        "goal",
        '''
"""One agent, under a goal of its own."""

from typing import Annotated, NamedTuple

from hmz.agents import AgentBase, Goal
from hmz.flows import flow


class Agents(NamedTuple):
    """The one that pursues."""

    worker: Annotated[AgentBase, Goal]


@flow
def run(agents: Agents, task: str) -> None:
    pass
''',
    )
    app = Humanize()
    async with app.run_test() as driver:
        await _open(app, driver, "goal")
        await opens(app, driver, "cli")
        await until(lambda: isinstance(app.screen, Clis), driver)

        # Only the ones with a goal feature of their own, which opencode has not.
        assert "opencode" not in rows(app)
        assert "claude" in rows(app)


@pytest.mark.timeout(60)
@unittest.mock.patch("hmz.tui.app.installed", return_value=CLAUDE)
async def test_the_models_are_what_that_cli_last_said_and_are_asked_again_on_r(
    _installed: unittest.mock.MagicMock,  # noqa: PT019  -- `mock.patch` hands it over
    flows: Path,
) -> None:
    """A CLI ships a model without asking anybody, so the list is asked for rather than kept."""
    app = Humanize()
    async with app.run_test() as driver:
        await _open(app, driver, "remote")
        await opens(app, driver, "model")
        await until(lambda: isinstance(app.screen, Catalogue), driver)
        keys = str(app.screen.query_one("#keys", Label).content)

        assert "r to ask it again" in keys
        assert "ctrl" not in keys.lower()

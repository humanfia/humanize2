"""One agent of a flow, configured in three steps: which CLI and account, what, and where.

The order is the order of what depends on what -- an account belongs to a backend and a model
belongs to the CLI that runs it -- and the third step exists only where the flow said that
agent may be pointed at a machine at all. Which is the point of it: a flow that declares one
is a flow expecting to be told where that agent works, and a flow that says nothing has said
its agent works here.

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
from hmz.tui.pick import Anchors, Models, Runs, RunsAs
from hmz.tui.settings import Settings

from .test_app import _transcript, until

if TYPE_CHECKING:
    from pathlib import Path

    from textual.pilot import Pilot

#: What one installed CLI looks like, for every walk here.
CLAUDE = {"claude": (Model("claude-opus-5", ("max", "high")),)}

#: A flow whose agent it says nothing about, which is one that works here and is not asked.
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

#: A flow that says its agent may be pointed at a machine, which is the third step.
REMOTE = '''
"""One agent, which may work anywhere it is pointed at."""

from typing import Annotated, NamedTuple

from hmz.agents import AgentBase, Remote


class Agents(NamedTuple):
    """Just the one, and it moves."""

    builder: Annotated[AgentBase, Remote]


def run(agents: Agents, task: str) -> None:
    pass
'''

#: A flow that settles the container itself, which is a machine nobody configures.
BOXED = '''
"""One agent, in a container of the flow's own."""

from typing import Annotated, NamedTuple

from hmz.agents import AgentBase, Isolated


class Agents(NamedTuple):
    """Just the one, in a box."""

    tester: Annotated[AgentBase, Isolated("python:3.12")]


def run(agents: Agents, task: str) -> None:
    pass
'''

#: Two agents that may both be pointed somewhere, which is three steps apiece.
PAIR = '''
"""Two agents, both of which may work elsewhere."""

from typing import Annotated, NamedTuple

from hmz.agents import AgentBase, Remote


class Agents(NamedTuple):
    """One writes, one reads."""

    builder: Annotated[AgentBase, Remote]
    reviewer: Annotated[AgentBase, Remote]


def run(agents: Agents, task: str) -> None:
    pass
'''


@pytest.fixture
def flows(tmp_path: Path) -> Path:
    """Puts the four flows where this project's own would be."""
    where = tmp_path / ".humanize" / "flows"
    where.mkdir(parents=True)
    (where / "here.py").write_text(HERE)
    (where / "remote.py").write_text(REMOTE)
    (where / "boxed.py").write_text(BOXED)
    (where / "pair.py").write_text(PAIR)
    return where


def _asked(app: Humanize) -> str:
    """What the sheet on top is asking, which says which agent it is asking about."""
    return str(app.screen.query_one("#asked", Label).content)


async def _walk_in(app: Humanize, driver: Pilot[None], flow: str) -> None:
    """Opens the walk on one flow, as `/flow` does, and waits for its first step."""
    await driver.press(*f"/flow {flow}")
    await driver.press("enter")
    await until(lambda: isinstance(app.screen, RunsAs), driver)


@pytest.mark.timeout(60)
@unittest.mock.patch("hmz.tui.app.installed", return_value=CLAUDE)
async def test_one_agent_is_three_steps_in_this_order(
    _installed: unittest.mock.MagicMock,  # noqa: PT019  -- `mock.patch` hands it over
    flows: Path,
) -> None:
    """Which CLI and account, which model and effort, and where the work lands."""
    app = Humanize()
    async with app.run_test() as driver:
        await _walk_in(app, driver, "remote")

        # One: the CLI whose turns these are, and under its tab that CLI's own accounts.
        assert "builder" in _asked(app)
        assert "account" in _asked(app)
        assert "claude" in str(app.screen.query_one("#tabs", Label).content)
        await driver.press("enter")

        # Two: that CLI's models, and the effort on the arrows.
        await until(lambda: isinstance(app.screen, Models), driver)
        assert "builder" in _asked(app)
        tuning = app.screen.query_one("#tuning", Label)
        await until(lambda: "max effort" in str(tuning.content), driver)
        await driver.press("enter")

        # Three: where it works, which this flow says may be somewhere else.
        await until(lambda: isinstance(app.screen, Anchors), driver)
        assert "builder" in _asked(app)
        await driver.press("enter")
        await until(lambda: not isinstance(app.screen, Anchors), driver)

    # And answering the last step of the last agent is what commits.
    assert app._flow_named == "remote"
    assert app._models == [Runs("claude/claude-opus-5:max")]


@pytest.mark.timeout(60)
@unittest.mock.patch("hmz.tui.app.installed", return_value=CLAUDE)
async def test_two_agents_are_six_sheets_one_agent_at_a_time(
    _installed: unittest.mock.MagicMock,  # noqa: PT019  -- `mock.patch` hands it over
    flows: Path,
) -> None:
    """The steps are per agent, so the second one's three come after the first one's."""
    app = Humanize()
    walked: list[str] = []
    async with app.run_test() as driver:
        await _walk_in(app, driver, "pair")
        for _ in range(6):
            walked.append(f"{type(app.screen).__name__} {_asked(app)}")
            await driver.press("enter")
            await driver.pause()
            if isinstance(app.screen, Models):
                await until(
                    lambda: bool(app.screen.query_one("#choices", OptionList).options),
                    driver,
                )
        await until(lambda: not isinstance(app.screen, Anchors), driver)

    assert [line.split()[0] for line in walked] == [
        "RunsAs",
        "Models",
        "Anchors",
        "RunsAs",
        "Models",
        "Anchors",
    ]
    # Which agent is being configured is on every one of them.
    assert all("builder" in line for line in walked[:3])
    assert all("reviewer" in line for line in walked[3:])
    assert app._models == [Runs("claude/claude-opus-5:max")] * 2


@pytest.mark.timeout(60)
@unittest.mock.patch("hmz.tui.app.installed", return_value=CLAUDE)
async def test_esc_off_each_step_is_the_step_before_it(
    _installed: unittest.mock.MagicMock,  # noqa: PT019  -- `mock.patch` hands it over
    flows: Path,
) -> None:
    """And off the first step of the first agent, out of the walk, changing nothing."""
    app = Humanize()
    was = ""
    async with app.run_test() as driver:
        was, held = app._flow_named, list(app._models)
        await _walk_in(app, driver, "remote")
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Models), driver)
        await driver.press("left")  # one effort down from the one it opens on
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Anchors), driver)

        await driver.press("escape")  # off where it works, back to what it runs
        await until(lambda: isinstance(app.screen, Models), driver)
        # And as it was left rather than as it opened: a step back that had forgotten its
        # own answer would be a different question.
        tuning = app.screen.query_one("#tuning", Label)
        await until(lambda: "high effort" in str(tuning.content), driver)

        await driver.press("escape")  # off what it runs, back to which CLI and account
        await until(lambda: isinstance(app.screen, RunsAs), driver)

        await driver.press("escape")  # and off that, out of the walk altogether
        await until(lambda: not isinstance(app.screen, RunsAs), driver)
        await driver.pause()

    assert app._flow_named == was  # the flow was not switched to
    assert app._models == held  # and nothing was chosen for it


@pytest.mark.timeout(60)
@unittest.mock.patch(
    "hmz.tui.app.installed",
    return_value=CLAUDE | {"codex": (Model("gpt-5.6-sol", ("xhigh",)),)},
)
async def test_stepping_back_and_turning_to_another_cli_asks_about_that_one(
    _installed: unittest.mock.MagicMock,  # noqa: PT019  -- `mock.patch` hands it over
    flows: Path,
) -> None:
    """A model, an effort and a set of skills are the backend's own, so none of them carries."""
    app = Humanize()
    async with app.run_test() as driver:
        await _walk_in(app, driver, "remote")
        await driver.press("enter")  # claude, as this machine is signed in
        await until(lambda: isinstance(app.screen, Models), driver)
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Anchors), driver)

        await driver.press(
            "escape", "escape"
        )  # back to which CLI, and turn to the other
        await until(lambda: isinstance(app.screen, RunsAs), driver)
        await driver.press("right")
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Models), driver)
        listing = app.screen.query_one("#choices", OptionList)
        await until(lambda: bool(listing.options), driver)

        assert [str(option.id) for option in listing.options] == ["codex/gpt-5.6-sol"]
        tuning = app.screen.query_one("#tuning", Label)
        assert "xhigh effort" in str(tuning.content)


@pytest.mark.timeout(60)
@unittest.mock.patch("hmz.tui.app.installed", return_value=CLAUDE)
async def test_esc_off_the_second_agent_is_the_last_step_of_the_first(
    _installed: unittest.mock.MagicMock,  # noqa: PT019  -- `mock.patch` hands it over
    flows: Path,
) -> None:
    """The steps run on from one agent to the next, so stepping back crosses that seam."""
    app = Humanize()
    async with app.run_test() as driver:
        await _walk_in(app, driver, "pair")
        for _ in range(3):  # the builder, whole
            await driver.press("enter")
            await driver.pause()
        await until(
            lambda: isinstance(app.screen, RunsAs) and "reviewer" in _asked(app), driver
        )

        await driver.press("escape")
        await until(lambda: isinstance(app.screen, Anchors), driver)

        assert "builder" in _asked(app)


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
        await _walk_in(app, driver, flow)
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Models), driver)
        await driver.press("enter")
        # Two steps and no third: answering the model is the whole of that agent.
        await until(lambda: not isinstance(app.screen, Models), driver)
        await driver.pause()

        assert not isinstance(app.screen, Anchors)

    assert app._flow_named == flow
    assert app._models == [Runs("claude/claude-opus-5:max")]


@pytest.mark.timeout(60)
@unittest.mock.patch("hmz.tui.app.installed", return_value=CLAUDE)
async def test_a_container_the_flow_settled_is_shown_rather_than_asked_about(
    _installed: unittest.mock.MagicMock,  # noqa: PT019  -- `mock.patch` hands it over
    flows: Path,
) -> None:
    """The step's absence has to be visible: nobody configures it, and it is not this machine."""
    app = Humanize()
    async with app.run_test() as driver:
        await _walk_in(app, driver, "boxed")
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Models), driver)
        tuning = app.screen.query_one("#tuning", Label)
        await until(lambda: "effort" in str(tuning.content), driver)

        assert "in a container of python:3.12" in str(tuning.content)
        # Read rather than adjusted: there is no key on it, the flow having settled it.
        assert "to move" not in str(tuning.content)


@pytest.mark.timeout(60)
@unittest.mock.patch("hmz.tui.app.installed", return_value=CLAUDE)
async def test_an_agent_that_works_here_says_nothing_new(
    _installed: unittest.mock.MagicMock,  # noqa: PT019  -- `mock.patch` hands it over
    flows: Path,
) -> None:
    """Which is what every agent nobody said anything about has always done."""
    app = Humanize()
    async with app.run_test() as driver:
        await _walk_in(app, driver, "here")
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Models), driver)
        tuning = app.screen.query_one("#tuning", Label)
        await until(lambda: "effort" in str(tuning.content), driver)

        # No container, since the flow named none, and nothing about a machine: the account
        # is the only thing on this line that mentions one, and it is this one.
        assert "in a container" not in str(tuning.content)
        assert "◉ on " not in str(tuning.content)


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
        await _walk_in(app, driver, "remote")
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Models), driver)
        await driver.press("enter")

        await until(lambda: isinstance(app.screen, Anchors), driver)
        listing = app.screen.query_one("#choices", OptionList)
        await until(lambda: bool(listing.options), driver)
        # This machine first, then the ones there are to be found.
        assert [str(option.id) for option in listing.options] == ["=", "=ssh://box"]

        await driver.press("down")
        await driver.press("enter")
        await until(lambda: not isinstance(app.screen, Anchors), driver)
        await driver.pause()

    chosen = Runs("claude/claude-opus-5:max", "ssh://box")
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
        await _walk_in(app, driver, "remote")
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Models), driver)
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Anchors), driver)
        listing = app.screen.query_one("#choices", OptionList)
        await until(lambda: bool(listing.options), driver)

        await driver.press(*"nonsense")
        await driver.pause()
        # Not a target and not a row, so there is nothing there to choose.
        assert [str(option.id) for option in listing.options] == []

        for _ in range(len("nonsense")):
            await driver.press("backspace")
        await driver.press(*"docker://box")
        await driver.pause()

        assert [str(option.id) for option in listing.options] == ["=docker://box"]


@pytest.mark.timeout(60)
@unittest.mock.patch("hmz.tui.app.installed", return_value=CLAUDE)
async def test_a_flow_that_puts_its_agent_here_refuses_one_that_was_pointed_away(
    _installed: unittest.mock.MagicMock,  # noqa: PT019  -- `mock.patch` hands it over
    flows: Path,
) -> None:
    """Which is why the step is only offered where the flow allows it.

    The refusal is the runner's, since where an agent works is the flow's to say -- and it is
    a line at this prompt rather than a traceback out of a flow's own thread.
    """
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

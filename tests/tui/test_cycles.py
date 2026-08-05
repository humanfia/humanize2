"""`/cycles` -- the runs of this directory, and what there is to do with one.

A run is written down as it happens and until now nothing showed them. What they are for is
two things: reading one back afterwards, which is what the links to its sessions are, and
carrying one on, which is what a flow that says it can be picked up is for. So this is a list
of runs, newest first, and a menu under each of them.

Driven headlessly, as every test of the interface is, so what is checked is where a keystroke
lands rather than how it is drawn.
"""

from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING

import pytest
from textual.widgets import Label, OptionList

from hmz.cycle import cycles, state
from hmz.tui import Humanize
from hmz.tui.pick import Cycles, Does
from tests.stubs import written

from .test_app import onto, rows, until

if TYPE_CHECKING:
    from pathlib import Path

    from textual.pilot import Pilot

#: A flow that says it can be picked up, and counts the runs of itself in what it is handed.
COUNTS = '''"""Counts the runs of itself."""

from pathlib import Path
from typing import Any

from hmz.agents import AgentBase
from hmz.flows import flow


@flow(resumable=True)
def run(agents: tuple[AgentBase], task: str, state: dict[str, Any]) -> None:
    state["rounds"] = state.get("rounds", 0) + 1
    Path("rounds.txt").write_text(str(state["rounds"]))
'''

#: One that says nothing, which is a run to read rather than a run to carry on.
PLAIN = '''"""Runs once, and says nothing about being picked up."""

from pathlib import Path

from hmz.agents import AgentBase
from hmz.flows import flow


@flow
def run(agents: tuple[AgentBase], task: str) -> None:
    Path("plain.txt").write_text(task)
'''

#: A `claude` that answers whatever it is told, since what is being tested is the run rather
#: than what the agent said.
QUIET = """
import json, sys

flags = dict(zip(sys.argv, sys.argv[1:]))
print(json.dumps({"type": "system", "session_id": flags["--session-id"]}), flush=True)
print(json.dumps({"type": "result", "result": "done"}), flush=True)
"""


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A directory with the two flows in it and a fake `claude` to drive them."""
    binaries = tmp_path / "bin"
    binaries.mkdir()
    fake = binaries / "claude"
    fake.write_text(f"#!{sys.executable}\n{QUIET}")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{binaries}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude-home"))
    where = tmp_path / ".humanize/flows"
    where.mkdir(parents=True)
    written(where, "counts", COUNTS)
    written(where, "plain", PLAIN)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _ran(flow: str, task: str) -> None:
    """Runs one flow here, the way a command line would, so there is a cycle to look at.

    On the fake `claude` this suite puts on PATH rather than on a stand-in of our own: what a
    run is picked up as is a command line naming what each agent runs, so the agents of a run
    have to be agents something can name.
    """
    from hmz.agents import driver
    from hmz.runner import Runner

    agent, config = driver("claude")
    Runner(flow, [agent(config(model="m", effort="high"))]).run(task)


async def _open(app: Humanize, driver: Pilot[None]) -> Cycles:
    """Opens the runs of this directory, as `/cycles` does."""
    await driver.press(*"/cycles")
    await driver.press("enter")
    await until(lambda: isinstance(app.screen, Cycles), driver)
    sheet = app.screen
    assert isinstance(sheet, Cycles)
    return sheet


@pytest.mark.timeout(60)
async def test_the_runs_of_this_directory_are_listed_newest_first(
    workspace: Path,
) -> None:
    """Which is what somebody opening this came to see: the run that has just happened."""
    _ran("plain", "the first thing")
    _ran("counts", "the second thing")

    app = Humanize()
    async with app.run_test() as driver:
        sheet = await _open(app, driver)

        newest, oldest = (one.name for one in reversed(cycles(workspace)))
        assert rows(app) == [newest, oldest]
        shown = "\n".join(
            str(one.prompt) for one in sheet.query_one("#choices", OptionList).options
        )
        assert "counts" in shown
        assert "the second thing" in shown


@pytest.mark.timeout(60)
async def test_a_run_of_a_flow_that_can_be_picked_up_says_so(workspace: Path) -> None:
    """The mark on the row, and the row in the menu under it: the one is why the other is there."""
    _ran("counts", "go")

    app = Humanize()
    async with app.run_test() as driver:
        await _open(app, driver)
        shown = str(
            app.screen.query_one("#choices", OptionList).get_option_at_index(0).prompt
        )
        assert "can be picked up" in shown

        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Does), driver)

        assert rows(app) == ["carry-on", "collect", "where"]


@pytest.mark.timeout(60)
async def test_a_run_of_a_flow_that_says_nothing_is_a_run_to_read(
    workspace: Path,
) -> None:
    """There is nothing to carry on from, and the menu says why rather than offering it."""
    _ran("plain", "go")

    app = Humanize()
    async with app.run_test() as driver:
        await _open(app, driver)
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Does), driver)

        assert rows(app) == ["collect", "where"]
        assert "does not say it can be picked up" in str(
            app.screen.query_one("#tuning", Label).render()
        )


@pytest.mark.timeout(60)
async def test_where_a_run_is_written_down_is_said_under_the_list(
    workspace: Path,
) -> None:
    """Which is where its sessions are linked, and what somebody analysing a run opens."""
    _ran("plain", "go")

    app = Humanize()
    async with app.run_test() as driver:
        sheet = await _open(app, driver)
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Does), driver)
        await onto(app, driver, "where")
        await driver.press("enter")
        await until(lambda: app.screen is sheet, driver)

        (cycle,) = cycles(workspace)
        assert str(cycle) in str(sheet.query_one("#tuning", Label).render())


@pytest.mark.timeout(90)
async def test_carrying_a_run_on_runs_the_flow_again_on_what_it_left(
    workspace: Path,
) -> None:
    """The whole of it: the run is picked up, and the flow goes on rather than starting over."""
    _ran("counts", "keep going")
    assert (workspace / "rounds.txt").read_text() == "1"
    first = cycles(workspace)[0]

    app = Humanize()
    async with app.run_test() as driver:
        sheet = await _open(app, driver)
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Does), driver)
        await onto(app, driver, "carry-on")
        await driver.press("enter")
        await until(lambda: app.screen is not sheet, driver)
        await until(lambda: len(cycles(workspace)) == 2, driver)
        await until(lambda: (workspace / "rounds.txt").read_text() == "2", driver)

    second = next(one for one in cycles(workspace) if one != first)
    # A run of its own, on what the run it was picked up from left behind.
    assert state(second) == {"rounds": 2}
    assert app._flow_named == "counts"


@pytest.mark.timeout(60)
async def test_a_directory_nothing_has_been_run_in_says_so(workspace: Path) -> None:
    """An empty list that explained nothing would read as a list that failed to load."""
    del workspace
    app = Humanize()
    async with app.run_test() as driver:
        sheet = await _open(app, driver)

        assert rows(app) == []
        assert "no flow has been run" in str(sheet.query_one("#tuning", Label).render())


@pytest.mark.timeout(90)
async def test_a_trace_of_a_run_is_gathered_from_the_menu_under_it(
    workspace: Path,
) -> None:
    """Every run has one to gather, whatever its flow says about being picked up.

    And it lands beside the run rather than in this directory: a cycle already holds what
    happened and what each session was logged to, and the trace is one of those.
    """
    from .test_app import _transcript

    _ran("plain", "go")

    app = Humanize()
    async with app.run_test() as driver:
        sheet = await _open(app, driver)
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Does), driver)
        await onto(app, driver, "collect")
        await driver.press("enter")
        await until(lambda: app.screen is sheet, driver)
        await until(lambda: "sessions" in _under(sheet), driver)

        (cycle,) = cycles(workspace)
        (written,) = (cycle / "traces").glob("*.trace.json")
        assert str(written) in _under(sheet)

        await driver.press("escape")
        await until(lambda: not isinstance(app.screen, Cycles), driver)
        # And said where it can be read back afterwards, rather than only under a list that
        # has since been closed.
        assert str(written) in _transcript(app)


def _under(sheet: Cycles) -> str:
    """What is said under the list, which is where a collection reports itself."""
    from textual.widgets import Label

    return str(sheet.query_one("#tuning", Label).content)

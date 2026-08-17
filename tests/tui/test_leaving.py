"""What is closed when the interface is closed, and what goes on running.

Closing the interface and stopping the run are two things wherever the run is being held
somewhere a terminal closing cannot reach: the flow goes on taking its turns, and `hmz` in
this directory opens it again. So `/exit` asks and `/detach` says it outright, and what is
checked here is that each of them does what it says and leaves the other alone.
"""

from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING

import pytest

from hmz.kept import Runs
from hmz.tui import Humanize
from hmz.tui.pick import DETACHES, STAYS, STOPS, Leaves
from tests.stubs import written
from tests.tui.conftest import transcript, until

if TYPE_CHECKING:
    from pathlib import Path

    from textual.pilot import Pilot

#: A flow whose one turn does not end until something else is said to it, so that a test can
#: ask what happens to a run that is still running.
FLOW = """
from pathlib import Path

from hmz.agents import AgentBase
from hmz.flows import flow


@flow
def run(agents: tuple[AgentBase], task: str) -> None:
    session = agents[0].new()
    Path("said.txt").write_text(session(task) + "\\n")
"""

#: A `claude` that does not answer until it is told something else, so that a turn stays open.
PATIENT = """
import json
import sys

for line in sys.stdin:
    said = json.loads(line)
    print(json.dumps({"type": "system", "subtype": "init", "session_id": "one"}))
    sys.stdout.flush()
"""


class Holding:
    """A stand-in for whatever is holding a run, which is all the interface is told of one."""

    def __init__(self, reading: int = 1) -> None:
        self.reading = reading
        self.let_go = 0

    @property
    def attached(self) -> int:
        return self.reading

    def detach(self) -> int:
        self.let_go += 1
        self.reading = 0
        return 1


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A directory of our own, with a coding agent that keeps its turn open on PATH."""
    binaries = tmp_path / "bin"
    binaries.mkdir()
    fake = binaries / "claude"
    fake.write_text(f"#!{sys.executable}\n{PATIENT}")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{binaries}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.chdir(tmp_path)
    return tmp_path


async def _says(app: Humanize, driver: Pilot[None], line: str) -> None:
    """Types one line and sends it, as somebody at the prompt would."""
    app.query_one("#editor").text = line  # pyright: ignore[reportAttributeAccessIssue]
    await driver.press("enter")
    await driver.pause()


@pytest.mark.timeout(60)
async def test_detach_is_offered_as_a_command() -> None:
    """Since nothing here is chosen from a dialog: a `/` offers what there is."""
    from hmz.tui.app import _OWN
    from hmz.tui.complete import about

    assert "detach" in _OWN
    assert about("detach")


@pytest.mark.timeout(60)
async def test_detach_lets_go_of_the_terminal_and_leaves_the_run() -> None:
    holding = Holding()
    app = Humanize(session=holding)
    async with app.run_test() as driver:
        await _says(app, driver, "/detach")

        assert holding.let_go == 1
        assert app.is_running  # the interface is not closed: the terminal is let go of


@pytest.mark.timeout(60)
async def test_detach_says_so_where_nothing_is_holding_the_run() -> None:
    """Closing the terminal it was opened in is what closes it, so there is nothing to do."""
    app = Humanize()
    async with app.run_test() as driver:
        await _says(app, driver, "/detach")
        await until(lambda: "nothing to" in transcript(app), driver)

        assert "closing the terminal closes the run" in transcript(app)
        assert app.is_running


@pytest.mark.timeout(60)
async def test_detach_says_so_where_nothing_is_reading() -> None:
    holding = Holding(reading=0)
    app = Humanize(session=holding)
    async with app.run_test() as driver:
        await _says(app, driver, "/detach")
        await until(lambda: "nothing is reading" in transcript(app), driver)

        assert "nothing is reading this run" in transcript(app)
        assert holding.let_go == 0
        assert app.is_running


@pytest.mark.timeout(120)
async def test_the_key_that_leaves_asks_what_leaving_asks(workspace: Path) -> None:
    """ctrl+q is Textual's own, and must not be a way round the question `/exit` puts."""
    written(workspace, "flow", FLOW)
    app = Humanize(session=Holding())
    async with app.run_test() as driver:
        app._flow_named, app._models = "flow", [Runs("claude/m:high")]
        await _says(app, driver, "start")
        await until(
            lambda: bool(app._agents and any(agent.sessions for agent in app._agents)),
            driver,
        )
        await driver.press("ctrl+q")
        await until(lambda: isinstance(app.screen, Leaves), driver)

        assert isinstance(app.screen, Leaves)
        assert app.is_running
        app.screen.dismiss(None)
        await driver.pause()


@pytest.mark.timeout(60)
async def test_exit_with_nothing_running_asks_nothing() -> None:
    """A window being closed is a window being closed."""
    app = Humanize()
    async with app.run_test() as driver:
        await _says(app, driver, "/exit")
        await until(lambda: not app.is_running, driver)

    assert not app.is_running


async def _asks(app: Humanize, driver: Pilot[None]) -> None:
    """Starts the flow, waits for its turn to be open, and asks the interface to close."""
    app._flow_named, app._models = "flow", [Runs("claude/m:high")]
    await _says(app, driver, "start")
    await until(
        lambda: bool(app._agents and any(agent.sessions for agent in app._agents)),
        driver,
    )
    await _says(app, driver, "/exit")
    await until(lambda: isinstance(app.screen, Leaves), driver)


@pytest.mark.timeout(120)
async def test_exit_asks_what_is_to_become_of_a_flow_that_is_running(
    workspace: Path,
) -> None:
    """A day's work is behind three letters that mean `close this` everywhere else."""
    written(workspace, "flow", FLOW)
    app = Humanize(session=Holding())
    async with app.run_test() as driver:
        await _asks(app, driver)

        assert isinstance(app.screen, Leaves)
        assert app.is_running  # nothing has been closed and nothing has been stopped
        app.screen.dismiss(None)
        await driver.pause()


@pytest.mark.timeout(120)
async def test_stopping_the_flow_is_what_closes_the_interface(
    workspace: Path,
) -> None:
    written(workspace, "flow", FLOW)
    holding = Holding()
    app = Humanize(session=holding)
    async with app.run_test() as driver:
        await _asks(app, driver)
        app.screen.dismiss(STOPS)
        await until(lambda: not app.is_running, driver)

    assert not app.is_running
    assert holding.let_go == 0  # it was stopped, not walked away from


@pytest.mark.timeout(120)
async def test_leaving_it_running_lets_go_of_the_terminal_instead(
    workspace: Path,
) -> None:
    written(workspace, "flow", FLOW)
    holding = Holding()
    app = Humanize(session=holding)
    async with app.run_test() as driver:
        await _asks(app, driver)
        app.screen.dismiss(DETACHES)
        await until(lambda: holding.let_go == 1, driver)

        assert holding.let_go == 1
        assert app.is_running  # the flow is still going, where nothing is reading it
        assert app._agents


def test_the_second_answer_is_whichever_one_is_true_here() -> None:
    """An answer that cannot be carried out is not one to offer."""
    assert [answer for answer, _, _ in Leaves(held=True).rows()] == [STOPS, DETACHES]
    assert [answer for answer, _, _ in Leaves(held=False).rows()] == [STOPS, STAYS]

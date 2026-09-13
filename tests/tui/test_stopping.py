"""`/stop` -- the stop that is typed rather than pressed, and so is asked once.

The key is asked twice because a day's work is behind a key that a finger also lands on by
mistake. A command is written out and sent, and that typing is the deliberation the second
press stands in for -- so what is checked here is that one line does what two presses do,
that it says so where the key is silent, and that it leaves the key's own gesture exactly
where it stands.

Driven headlessly, as every test of the interface is, so what is checked is what a typed line
did rather than how it was drawn.
"""

from __future__ import annotations

import os
import sys
import unittest.mock
from typing import TYPE_CHECKING

import pytest

from hmz.runtime.epic import epics
from hmz.runtime.kept import Runs
from hmz.tui import Humanize
from tests.stubs import events as recorded
from tests.stubs import written
from tests.tui.conftest import transcript, until

if TYPE_CHECKING:
    from pathlib import Path

    from textual.pilot import Pilot

#: A flow that drives one agent for one turn, which is enough to have something to stop.
FLOW = """
from pathlib import Path

from hmz.coganchor.agents import AgentBase
from hmz.flows import flow


@flow
def run(agents: tuple[AgentBase], task: str) -> None:
    session = agents[0].new()
    Path("said.txt").write_text(session(task) + "\\n")
"""

#: A `claude` that never answers, so that the turn is still open when the line is typed.
PATIENT = """
import json, sys

flags = dict(zip(sys.argv, sys.argv[1:]))
print(json.dumps({"type": "system", "session_id": flags["--session-id"]}), flush=True)
for line in sys.stdin:
    print(json.dumps({"type": "assistant", "message": {"content": [
        {"type": "text", "text": "working"}]}}), flush=True)
"""


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


async def _typed(driver: Pilot[None], line: str) -> None:
    """Types one line a character at a time and sends it, as somebody at the prompt does.

    Character by character rather than assigned, so that the offers the line opens on its way
    are open exactly as they would be -- enter over an open list takes what is under the
    cursor rather than sending, and a line typed in one go would never find that out.

    Args:
      driver: What is pumping the interface.
      line: What to type.
    """
    await driver.press(*line)
    await driver.pause()
    await driver.press("enter")
    await driver.pause()


@pytest.mark.timeout(90)
async def test_a_typed_stop_stops_the_flow_as_the_second_press_does(
    workspace: Path,
) -> None:
    """One line does what two presses do: the loop ends rather than handing on.

    And the run ends with it -- an epic is one run of one flow, and a run stopped by hand is
    written down as stopped rather than as one that finished.
    """
    written(workspace, "flow", FLOW)
    app = Humanize()
    async with app.run_test() as driver:
        app._flow_named, app._models = "flow", [Runs("claude/m:high")]
        await _typed(driver, "start")
        await until(
            lambda: bool(app._agents and any(agent.sessions for agent in app._agents)),
            driver,
        )

        await _typed(driver, "/stop")
        await until(lambda: not app._agents, driver)

        assert "stopping the flow" in transcript(app)
        (epic,) = epics(workspace)
        assert recorded(epic)[-1] == {
            "event": "ended",
            "at": unittest.mock.ANY,
            "how": "stopped",
        }


@pytest.mark.timeout(60)
async def test_a_typed_stop_says_so_where_there_is_nothing_to_stop() -> None:
    """The key is silent here; a command typed on purpose must not be.

    Silence is right for a press in the middle of a gesture, since the press after it has an
    answer of its own. A line somebody spelled out and sent that answered with nothing reads
    as a line that did not work.
    """
    app = Humanize()
    async with app.run_test() as driver:
        await _typed(driver, "/stop")
        await until(lambda: "nothing to stop" in transcript(app), driver)

        assert app.is_running


@pytest.mark.timeout(60)
async def test_a_flow_already_stopping_is_said_to_be_rather_than_told_again() -> None:
    """Telling it again would drop the agents the third press has to reach.

    Stopping hands the agents it holds on to the ones on their way out. Run over an empty
    list it would hand nothing on and let go of the ones already there, so the press that
    does not wait for the flow would find no conversation left to close.
    """
    from hmz.coganchor.agents import ClaudeCodeAgent, ClaudeCodeAgentConfig

    app = Humanize()
    async with app.run_test() as driver:
        app._stopping = [
            ClaudeCodeAgent(ClaudeCodeAgentConfig(model="claude-opus-5", effort="high"))
        ]
        held = app._stopping

        await _typed(driver, "/stop")
        await until(lambda: "already stopping" in transcript(app), driver)

        assert app._stopping is held


def test_stop_is_offered_among_the_commands_and_says_it_is_asked_once() -> None:
    """The list is where somebody reads what a command does before they type it.

    That it is not asked twice is the one thing about this command that the key it stands in
    for does differently, so the line beside it is where that is said.
    """
    from hmz.tui.app import _BY_NAME, _COMMANDS
    from hmz.tui.complete import offered

    assert "/stop" in offered("/", _COMMANDS)
    assert _BY_NAME["stop"].takes == ""  # there is nothing to write after it
    assert "twice" in _BY_NAME["stop"].about
    # And it names no key: the row under the editor is where the keys are said, so a line
    # here naming the one this stands in for would be that key read twice on one screen.
    assert "ctrl" not in _BY_NAME["stop"].about


@pytest.mark.timeout(60)
async def test_a_typed_stop_leaves_no_half_made_gesture_behind_it() -> None:
    """A press made before the command and one made after it are not one gesture.

    With nothing running the key is asked twice before it leaves. A `/stop` typed between the
    two presses that left the first of them counted would make the second the one that
    leaves -- the interface closing on one key after a line that said there was nothing to
    stop, which is a day at the prompt ended by a command about something else.
    """
    app = Humanize()
    async with app.run_test() as driver:
        await driver.press("ctrl+c")
        await driver.pause()
        assert app._presses == 1  # the press that asks, and is then typed past

        await _typed(driver, "/stop")
        await until(lambda: "nothing to stop" in transcript(app), driver)
        assert not app._presses  # counted from nothing, so the next press is a first press

        await driver.press("ctrl+c")
        await driver.pause()

        assert app._presses == 1
        assert "press ctrl+c again to leave" in transcript(app)
        assert app.is_running


@pytest.mark.timeout(90)
async def test_the_press_after_a_typed_stop_does_not_close_the_interface(
    workspace: Path,
) -> None:
    """The same, over a flow that was stopped and has finished unwinding.

    Nothing is running by then and nothing is on its way out, so a press left standing by the
    command would meet the rung that leaves -- and the run somebody stopped on purpose would
    take the terminal with it.
    """
    written(workspace, "flow", FLOW)
    app = Humanize()
    async with app.run_test() as driver:
        app._flow_named, app._models = "flow", [Runs("claude/m:high")]
        await _typed(driver, "start")
        await until(
            lambda: bool(app._agents and any(agent.sessions for agent in app._agents)),
            driver,
        )
        await driver.press("ctrl+c")
        await driver.pause()
        assert app._presses == 1

        await _typed(driver, "/stop")
        await until(lambda: not app._agents and not app._stopping, driver)

        await driver.press("ctrl+c")
        await driver.pause()

        assert app.is_running
        assert "press ctrl+c again to leave" in transcript(app)


@pytest.mark.timeout(60)
async def test_the_keys_name_what_the_press_after_a_typed_stop_does() -> None:
    """A flow on its way out is one rung, and the row of keys has to name that one.

    The row reads the count of presses first, so a `/stop` typed after a press that asked
    would offer to leave on a key that closes the conversations still open under their turns.
    Counting from nothing again is what keeps the row true as well as the key.
    """
    from hmz.coganchor.agents import ClaudeCodeAgent, ClaudeCodeAgentConfig

    app = Humanize()
    async with app.run_test() as driver:
        await driver.press("ctrl+c")  # the press that asks, and is then typed past
        await driver.pause()
        assert app._presses == 1
        app._stopping = [
            ClaudeCodeAgent(ClaudeCodeAgentConfig(model="claude-opus-5", effort="high"))
        ]

        await _typed(driver, "/stop")
        await until(lambda: "already stopping" in transcript(app), driver)

        assert "ctrl+c close them" in app._keys()
        assert "ctrl+c again to exit" not in app._keys()

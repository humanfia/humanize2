"""The one prompt: a command reaches the command it names, and a plain line reaches the agent.

Driven headlessly, so what is checked is what a keystroke actually does rather than how it is
drawn -- the interface's own job being to have one line mean both of those things.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from collections.abc import Callable
from pathlib import Path

import pytest
from textual.pilot import Pilot
from textual.widgets import Static

from amflows.tui import Amflows

#: A flow that drives one agent for two turns, so a line can be typed while it is running.
FLOW = """
from pathlib import Path

from amflows.janus import AgentBase


def run(agents: tuple[AgentBase], task: str) -> None:
    session = agents[0].launch()
    Path("said.txt").write_text(session.run(task) + "\\n")
"""

#: A `claude` that answers each thing it is told with a turn of its own, as the real one
#: does, but withholds the first answer until a second thing arrives -- which is what makes
#: the interjection observable: the turn cannot end before the typed line lands.
PATIENT = """
import json, sys

flags = dict(zip(sys.argv, sys.argv[1:]))
print(json.dumps({"type": "system", "session_id": flags["--session-id"]}), flush=True)
heard = []
for line in sys.stdin:
    heard.append(json.loads(line)["message"]["content"][0]["text"])
    if len(heard) == 1:
        print(json.dumps({"type": "assistant", "message": {"content": [
            {"type": "text", "text": "working"}]}}), flush=True)
        continue
    for answer in (heard[0], " then ".join(heard)):
        print(json.dumps({"type": "result", "result": answer}), flush=True)
"""


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Puts the patient fake `claude` on PATH and works in a directory of our own."""
    binaries = tmp_path / "bin"
    binaries.mkdir()
    fake = binaries / "claude"
    fake.write_text(f"#!{sys.executable}\n{PATIENT}")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{binaries}{os.pathsep}{os.environ['PATH']}")
    # Hidden, as the collector's own suite hides them: `/collect` reads the agents' home
    # directories, and the real ones hold a developer's whole history of sessions.
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    for variable in ("CLAUDE_CONFIG_DIR", "CODEX_HOME", "KIMI_CODE_HOME"):
        monkeypatch.setenv(variable, str(tmp_path / variable.lower()))
    monkeypatch.chdir(tmp_path)
    return tmp_path


async def until(ready: Callable[[], bool], driver: Pilot[None]) -> None:
    """Pumps the interface until something is true, or gives up after a while.

    Waited on the clock rather than counted in pump cycles: a cycle can pass in microseconds,
    so counting them is a spin that finishes before the worker thread has done anything.

    Args:
      ready: What is being waited for.
      driver: The interface to keep pumping while waiting.
    """
    deadline = time.monotonic() + 30.0
    while not ready() and time.monotonic() < deadline:
        await driver.pause()
        await asyncio.sleep(0.02)


def _transcript(app: Amflows) -> str:
    """Everything the interface has shown, as one searchable string.

    Read while the interface is still up: its widgets go with it when it exits.
    """
    from textual.widgets import RichLog

    return "\n".join(line.text for line in app.query_one("#transcript", RichLog).lines)


@pytest.mark.timeout(60)
async def test_a_slash_command_reaches_the_command_it_names(workspace: Path) -> None:
    """`/collect .` is `amflows collect .`: one implementation, reached a second way."""
    app = Amflows()
    async with app.run_test() as driver:
        await driver.press(*"/collect .")
        await driver.press("enter")
        await driver.pause()
        await until(lambda: bool(list(workspace.glob(".amflows/*.trace.json"))), driver)

        shown = _transcript(app)

    assert list(workspace.glob(".amflows/*.trace.json")), shown


@pytest.mark.timeout(60)
async def test_a_line_typed_while_a_flow_runs_reaches_the_agent(
    workspace: Path,
) -> None:
    """The whole point: the turn is still running, and what is typed lands inside it."""
    (workspace / "flow.py").write_text(FLOW)
    app = Amflows()
    async with app.run_test() as driver:
        await driver.press(*"/run -f flow.py -a claude/m/high start")
        await driver.press("enter")
        # The turn will not end until it has been told something else, so this cannot race.
        await until(
            lambda: bool(app._agents and any(agent.sessions for agent in app._agents)),
            driver,
        )
        await driver.press(*"and this")
        await driver.press("enter")
        await until(lambda: bool((workspace / "said.txt").exists()), driver)

    assert (workspace / "said.txt").read_text().strip() == "start then and this"


@pytest.mark.timeout(60)
async def test_a_line_with_nothing_running_says_so_rather_than_vanishing() -> None:
    app = Amflows()
    async with app.run_test() as driver:
        await driver.press(*"hello?")
        await driver.press("enter")
        await driver.pause()

        assert "nothing is running" in _transcript(app)


@pytest.mark.timeout(60)
async def test_a_command_that_is_not_one_is_said_so() -> None:
    app = Amflows()
    async with app.run_test() as driver:
        await driver.press(*"/fly")
        await driver.press("enter")
        await driver.pause()

        assert "no such command" in _transcript(app)


@pytest.mark.timeout(60)
async def test_a_bad_run_line_is_a_line_to_correct_and_not_the_end_of_the_session() -> (
    None
):
    app = Amflows()
    async with app.run_test() as driver:
        await driver.press(*"/run -f nowhere.py")  # no -a, and no task
        await driver.press("enter")
        await driver.pause()

        assert app.is_running  # still there to be typed at
        assert "amflows run" in _transcript(app)


def test_a_flag_offers_what_it_is_for() -> None:
    """A flow file and an agent are chosen by being offered, not by a dialog asking for them."""
    from amflows.cli import COMMANDS
    from amflows.tui.complete import offered

    found = offered("/run -f ", tuple(COMMANDS))
    assert any(path.endswith("ralph_loop.py") for path in found), found

    agents = offered("/run -a claude/", tuple(COMMANDS))
    assert all(spec.startswith("claude/") for spec in agents) and agents


@pytest.mark.timeout(60)
async def test_what_the_flow_did_is_shown_beside_it(workspace: Path) -> None:
    """Who worked, who handed to whom, and what it cost -- none of which the flow reports."""
    (workspace / "flow.py").write_text(FLOW)
    app = Amflows()
    async with app.run_test() as driver:
        await driver.press(*"/run -f flow.py -a claude/m/high start")
        await driver.press("enter")
        await until(
            lambda: bool(app._agents and any(agent.sessions for agent in app._agents)),
            driver,
        )
        await driver.press(*"and this")
        await driver.press("enter")
        await until(lambda: bool((workspace / "said.txt").exists()), driver)
        app._draw()

        beside = str(app.query_one("#flow", Static).content)
        assert "×1" in beside  # the one agent, and its one turn
        assert app._monitor.turns.total() == 1


@pytest.mark.timeout(60)
async def test_a_half_typed_command_is_offered_the_rest_of_itself() -> None:
    """Offered in a list under the editor, and taken with tab: nothing is ever guessed at."""
    from textual.widgets import OptionList

    from amflows.tui.app import Editor

    app = Amflows()
    async with app.run_test() as driver:
        await driver.press(*"/ru")
        await driver.pause()

        offers = app.query_one("#offers", OptionList)
        assert offers.has_class("offering")
        assert [
            str(offers.get_option_at_index(i).prompt)
            for i in range(offers.option_count)
        ] == ["/run"]

        await driver.press("tab")

        assert app.query_one(Editor).text == "/run "


@pytest.mark.timeout(60)
async def test_nothing_is_offered_for_what_is_not_a_command() -> None:
    from textual.widgets import OptionList

    from amflows.tui.app import Editor

    app = Amflows()
    async with app.run_test() as driver:
        offers = app.query_one("#offers", OptionList)

        await driver.press(*"hello")
        await driver.pause()
        assert not offers.has_class(
            "offering"
        )  # a line said to the agent offers nothing

        app.query_one(
            Editor
        ).text = ""  # ctrl+a is "start of line" here, not "select all"
        await driver.press(*"/zz")
        await driver.pause()
        assert not offers.has_class("offering")  # nor does a command that is not one


@pytest.mark.timeout(60)
async def test_the_offer_is_taken_from_the_commands_there_actually_are() -> None:
    """A command the command line grows must be offered without being listed twice."""
    from amflows.cli import COMMANDS
    from amflows.tui.app import _OWN
    from amflows.tui.complete import offered

    offers = offered("/", (*COMMANDS, *_OWN))

    assert {f"/{name}" for name in COMMANDS} <= set(offers)

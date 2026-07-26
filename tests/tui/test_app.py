"""The one prompt: a command reaches the command it names, and a plain line reaches the agent.

Driven headlessly, so what is checked is what a keystroke actually does rather than how it is
drawn -- the interface's own job being to have one line mean both of those things.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
import unittest.mock
from collections.abc import Callable
from pathlib import Path

import pytest
from textual.pilot import Pilot
from textual.widgets import OptionList, Static

from amflows.tui import Amflows
from amflows.tui.app import _OWN

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
        app._flow_named, app._models = "flow.py", ["claude/m/high"]
        await driver.press(*"start")
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

        # Nothing chosen and nothing running: a line has nowhere to go, and says so.
        assert "pick a flow first" in _transcript(app)


@pytest.mark.timeout(60)
async def test_a_command_that_is_not_one_is_said_so() -> None:
    app = Amflows()
    async with app.run_test() as driver:
        await driver.press(*"/fly")
        await driver.press("enter")
        await driver.pause()

        assert "no such command" in _transcript(app)


@pytest.mark.timeout(60)
async def test_a_flow_that_is_not_there_is_a_line_to_correct_and_not_the_end() -> None:
    """A flow chosen that will not load is said so, and the interface stays up."""
    app = Amflows()
    async with app.run_test() as driver:
        app._flow_named, app._models = "nowhere.py", ["claude/m/high"]
        await driver.press(*"do it")
        await driver.press("enter")
        await until(lambda: "nowhere.py" in _transcript(app), driver)

        assert app.is_running  # still there to be typed at
        assert "nowhere.py" in _transcript(app)


def test_only_the_flows_amflows_came_with_are_offered() -> None:
    """A flow of your own is a path typed out, not something found by walking the tree."""
    from amflows.cli import COMMANDS
    from amflows.janus.flows import prebuilt
    from amflows.tui.complete import offered

    assert offered("/agents ", tuple(COMMANDS)) == prebuilt()


@pytest.mark.timeout(60)
async def test_what_the_flow_did_is_shown_beside_it(workspace: Path) -> None:
    """Who worked, who handed to whom, and what it cost -- none of which the flow reports."""
    (workspace / "flow.py").write_text(FLOW)
    app = Amflows()
    async with app.run_test() as driver:
        app._flow_named, app._models = "flow.py", ["claude/m/high"]
        await driver.press(*"start")
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
        await driver.press(*"/ag")
        await driver.pause()

        offers = app.query_one("#offers", OptionList)
        assert offers.has_class("offering")
        # The name is what is taken; what is shown is the name and what it is for.
        assert [
            str(offers.get_option_at_index(i).id) for i in range(offers.option_count)
        ] == ["/agents"]
        assert "Switch flow" in str(offers.get_option_at_index(0).prompt)

        await driver.press("tab")

        assert app.query_one(Editor).text == "/agents "


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
    """A command the command line grows must be offered without being listed twice.

    Not every one of them, though: `run` is what the first thing you say already does, and
    `tui` is this -- neither is a command to offer from inside the interface.
    """
    from amflows.cli import COMMANDS
    from amflows.tui.complete import about, offered

    offers = offered("/", (*COMMANDS, *_OWN))

    assert {f"/{name}" for name in COMMANDS if about(name)} <= set(offers)
    assert "/run" not in offers and "/tui" not in offers


@pytest.mark.timeout(90)
async def test_escape_stops_the_flow_and_not_just_the_turn(workspace: Path) -> None:
    """Esc ends the loop, rather than letting it hand on to the next agent.

    A flow is a loop, so stopping the turn under way is not stopping anything: the loop
    would go round again. Every agent is told, and the one that raises `Stopped` takes the
    loop with it -- which is why `Stopped` is not the failed turn a flow's own `|| true`
    catches.
    """
    (workspace / "flow.py").write_text(FLOW)
    app = Amflows()
    async with app.run_test() as driver:
        app._flow_named, app._models = "flow.py", ["claude/m/high"]
        await driver.press(*"start")
        await driver.press("enter")
        await until(
            lambda: bool(app._agents and any(agent.sessions for agent in app._agents)),
            driver,
        )
        await driver.press("escape")
        await until(lambda: not app._agents, driver)  # the flow itself is over

        assert "stopping the flow" in _transcript(app)


@pytest.mark.timeout(90)
async def test_a_line_to_a_running_flow_is_never_turned_away(workspace: Path) -> None:
    """Between two turns there is no turn to steer, and the line still has to land.

    A flow that is running takes what is typed either way: into the turn under way, or into
    whichever turn starts next. There is no third answer -- a flow that is not running is
    what makes the first thing you say the task.
    """
    from amflows.janus.agents.claude import ClaudeCodeAgent, ClaudeCodeAgentConfig

    (workspace / "flow.py").write_text(FLOW)
    app = Amflows()
    async with app.run_test() as driver:
        # A flow that is running, with nobody mid-turn: an agent that has launched nothing.
        app._flow_named, app._models = "flow.py", ["claude/m/high"]
        app._agents = [ClaudeCodeAgent(ClaudeCodeAgentConfig(model="m", effort="high"))]
        app._queued = []
        await driver.press(*"and this")
        await driver.press("enter")
        await driver.pause()

        assert app._queued == ["and this"]  # held, not refused
        assert "nothing is running to be told" not in _transcript(app)


@pytest.mark.timeout(60)
async def test_exit_leaves() -> None:
    """`/exit`, as opencode spells it."""
    app = Amflows()
    async with app.run_test() as driver:
        await driver.press(*"/exit")
        await driver.press("enter")
        await driver.pause()

        assert not app.is_running


def test_what_the_agents_run_is_known_without_starting_one() -> None:
    """Starting a backend to ask it costs a minute here, which no prompt can wait on.

    `claude --help` took over thirty seconds on the machine this was written on, and
    `codex app-server` seventy-six -- so what they run is known rather than asked for.
    """
    from amflows.tui.discover import installed

    with unittest.mock.patch("subprocess.Popen") as started:
        found = installed()

    assert not started.called  # nothing was run to find this out
    # And an effort a model does not take is not offered against it.
    efforts = {model.name: model.efforts for model in found.get("codex", ())}
    if efforts:
        assert efforts["gpt-5.5"] != efforts["gpt-5.6-sol"]


@pytest.mark.timeout(60)
async def test_a_turn_reads_the_way_opencode_renders_one() -> None:
    """The shapes were read off opencode itself, running, and are pinned here.

    Watched at v1.18.14 against a stub provider: what you said goes down a `┃`; what the
    agent said is bare and indented three; a tool call is three spaces, the icon opencode
    picks for that tool, one space, the label; and the line closing a turn is `▣` and two
    spaces before the parts, which a middle dot separates.
    """
    from amflows.janus import Event
    from amflows.janus.agents.claude import ClaudeCodeAgent, ClaudeCodeAgentConfig

    agent = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="m", effort="high"), name="one")
    app = Amflows()
    async with app.run_test() as driver:
        app._said_by_you("do it")
        # From another thread, which is where a turn always says these from.
        await asyncio.to_thread(
            lambda: [
                app._heard(agent, event)
                for event in (
                    Event(kind="text", text="Looking at math.py now."),
                    Event(kind="tool", text="Read math.py"),
                    Event(kind="tool", text="Bash ls -la"),
                    Event(kind="ends", text=""),
                )
            ]
        )
        await driver.pause()
        shown = _transcript(app)

    assert "┃  do it" in shown
    assert "\n   Looking at math.py now." in shown
    assert (
        "\n   → Read math.py\n   $ Bash ls -la" in shown
    )  # rows pack, no blank between
    assert "\n   ▣  one · m · " in shown


@pytest.mark.timeout(90)
async def test_tab_picks_a_flow_and_then_what_each_agent_runs() -> None:
    """Tab switches flow the way opencode's tab switches agent, then `/models` follows.

    Only the flows amflows came with are listed -- a flow of your own is a path typed out.
    """
    from amflows.janus.flows import prebuilt
    from amflows.tui.pick import Flows

    app = Amflows()
    async with app.run_test() as driver:
        await driver.press("tab")
        await until(lambda: isinstance(app.screen, Flows), driver)
        listing = app.screen.query_one("#choices", OptionList)
        offered = [option.id for option in listing._options if option.id]

        assert offered == prebuilt()
        assert listing.highlighted == 1  # past the heading, on the first real choice

        await driver.press("enter")
        # Which lands on the models sheet, since a flow says how many agents it drives.
        await until(lambda: app._flow_named == prebuilt()[0], driver)

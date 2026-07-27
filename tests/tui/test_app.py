"""The one prompt: a command reaches the command it names, and a plain line reaches the agent.

Driven headlessly, so what is checked is what a keystroke actually does rather than how it is
drawn -- the interface's own job being to have one line mean both of those things.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import unittest.mock
from collections.abc import Callable
from pathlib import Path

import pytest
from textual.pilot import Pilot
from textual.widgets import OptionList, Static

from amflows.janus import cycles
from amflows.tui import Amflows
from amflows.tui.app import _OWN
from amflows.tui.discover import Model
from amflows.tui.pick import Models

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
    from amflows.janus.flows import found
    from amflows.tui.complete import offered

    assert offered("/flow ", tuple(COMMANDS)) == [name for _, name in found()]


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
        await driver.press(*"/fl")
        await driver.pause()

        offers = app.query_one("#offers", OptionList)
        assert offers.has_class("offering")
        # The name is what is taken; what is shown is the name and what it is for.
        assert [
            str(offers.get_option_at_index(i).id) for i in range(offers.option_count)
        ] == ["/flow"]
        assert "Switch flow" in str(offers.get_option_at_index(0).prompt)

        await driver.press("tab")

        assert app.query_one(Editor).text == "/flow "


@pytest.mark.timeout(60)
async def test_enter_takes_what_is_offered_rather_than_sending_the_half_typed_line() -> (
    None
):
    """Over an open list, enter means take what is under the cursor -- as it does anywhere.

    And the offers run out, so enter goes back to sending: `/flow` takes one flow, and a
    line that already names it has nothing left to be finished with.
    """
    from amflows.janus.flows import found
    from amflows.tui.app import Editor

    app = Amflows()
    async with app.run_test() as driver:
        editor = app.query_one(Editor)

        await driver.press(*"/fl")
        await driver.press("enter")
        await driver.pause()

        assert editor.text == "/flow "  # taken, not sent
        assert "no such command" not in _transcript(app)

        await driver.press("enter")  # and again, for the flow it is offering now
        await driver.pause()

        assert editor.text == f"/flow {found()[0][1]} "

        await driver.press("enter")  # nothing left to offer, so this is the line going
        await driver.pause()

        assert editor.text == ""
        assert f"/flow {found()[0][1]}" in _transcript(app)


@pytest.mark.timeout(60)
async def test_the_arrows_walk_what_was_typed_before_it() -> None:
    """Up for older and down for newer, and what was half typed is given back at the end.

    Which is the whole reason the draft is kept: an arrow pressed by mistake over a prompt
    somebody spent five minutes writing must not be what takes it away.
    """
    from amflows.tui.app import Editor

    app = Amflows()
    async with app.run_test() as driver:
        editor = app.query_one(Editor)
        for said in ("first", "second"):
            await driver.press(*said)
            await driver.press("enter")
        await driver.press(*"half written")

        await driver.press("up")
        assert editor.text == "second"  # newest first

        await driver.press("up")
        assert editor.text == "first"

        await driver.press("up")
        assert editor.text == "first"  # the far end of it, and nothing is lost there

        await driver.press("down")
        assert editor.text == "second"

        await driver.press("down")
        assert editor.text == "half written"  # what was being typed, back again


@pytest.mark.timeout(60)
async def test_the_arrows_are_the_editor_s_own_inside_a_prompt_of_more_than_one_line() -> (
    None
):
    """A prompt of several lines is moved around in; only its ends walk the history."""
    from amflows.tui.app import Editor

    app = Amflows()
    async with app.run_test() as driver:
        editor = app.query_one(Editor)
        await driver.press(*"remembered")
        await driver.press("enter")
        editor.text = "one\ntwo"
        editor.move_cursor((1, 3))  # the end of the second line, which is the last

        await driver.press("up")  # up the prompt, not back through what was typed

        assert editor.text == "one\ntwo"
        assert editor.cursor_location[0] == 0

        await driver.press(
            "up"
        )  # and off the top of it, which is the history after all

        assert editor.text == "remembered"


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
    # And a command typed in full has nothing left to be finished with, so enter sends it.
    assert offered("/exit", (*COMMANDS, *_OWN)) == []


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
        # And the run is over with it: a cycle is one run of one flow, and esc ends one.
        (cycle,) = cycles(workspace)
        assert json.loads(cycle.read_text().splitlines()[-1]) == {
            "event": "ended",
            "at": unittest.mock.ANY,
            "how": "stopped",
        }


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


@pytest.mark.timeout(60)
async def test_a_flow_between_two_turns_is_a_flow_that_is_running() -> None:
    """It sleeps off a round, commits, reads what the last turn wrote -- and that is the run.

    Which is why the rate is measured over the whole of it: the status line says the same
    thing, naming the flow and how long the run has been going rather than falling back to
    saying where it is, as if nothing were happening.
    """
    from amflows.janus.agents.claude import ClaudeCodeAgent, ClaudeCodeAgentConfig

    app = Amflows()
    async with app.run_test() as driver:
        # A flow that is running, with nobody mid-turn: the flow's own code has the time.
        app._flow_named = "rlcr"
        app._agents = [ClaudeCodeAgent(ClaudeCodeAgentConfig(model="m", effort="high"))]
        app._monitor.began = time.monotonic() - 90
        app._draw()
        await driver.pause()

        status = str(app.query_one("#status", Static).content)

    assert "rlcr" in status  # what is running
    assert "90s" in status  # and for how long the run has been going, turn or no turn


@pytest.mark.timeout(60)
async def test_a_turn_that_has_gone_quiet_still_reads_as_one_that_is_running() -> None:
    """A model thinks for minutes without a word, and the clock is what says it is alive."""
    from amflows.janus import Event
    from amflows.janus.agents.claude import ClaudeCodeAgent, ClaudeCodeAgentConfig

    agent = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="m", effort="high"), name="one")
    app = Amflows()
    async with app.run_test() as driver:
        app._heard(agent, Event(kind="begins", text="do it"))
        app._began["one"] = time.monotonic() - 42  # a turn that started a while ago
        app._draw()
        await driver.pause()

        status = str(app.query_one("#status", Static).content)

    assert "one" in status  # who is working
    assert "42s" in status  # and for how long, which a turn saying nothing does not say


@pytest.mark.timeout(90)
async def test_tab_picks_a_flow_and_then_what_each_agent_runs() -> None:
    """Tab switches flow the way opencode's tab switches agent, then `/agents` follows.

    Only the flows amflows came with are listed -- a flow of your own is a path typed out.
    """
    from amflows.janus.flows import found
    from amflows.tui.pick import Flows

    app = Amflows()
    async with app.run_test() as driver:
        await driver.press("tab")
        await until(lambda: isinstance(app.screen, Flows), driver)
        listing = app.screen.query_one("#choices", OptionList)
        offered = [option.id for option in listing._options if option.id]

        assert offered == [name for _, name in found()]
        assert listing.highlighted == 1  # past the heading, on the first real choice

        await driver.press("enter")
        # Which lands on the models sheet, since a flow says how many agents it drives.
        await until(lambda: app._flow_named == found()[0][1], driver)


@pytest.mark.timeout(60)
async def test_the_flow_itself_is_walked_back_into_from_what_it_runs_on() -> None:
    """The walk is one walk: esc off the first thing asked about a flow is that flow again.

    Rather than a way out of both, which would mean picking the flow over from tab.
    """
    from amflows.tui.pick import Flows

    app = Amflows()
    # Whatever this machine has installed, since the sheet is only put up if there is one.
    with unittest.mock.patch(
        "amflows.tui.app.installed",
        return_value={"claude": (Model("opus", ("high",)),)},
    ):
        async with app.run_test() as driver:
            await driver.press("tab")
            await until(lambda: isinstance(app.screen, Flows), driver)
            await driver.press("enter")
            await until(lambda: isinstance(app.screen, Models), driver)

            await driver.press("escape")
            await until(lambda: isinstance(app.screen, Flows), driver)

            assert isinstance(app.screen, Flows)  # back in the list, not out of both
            assert app._models == []


def _column(sheet: Models, part: str) -> list[str]:
    """What one column of the models sheet is holding, bare.

    Args:
      sheet: The sheet to read.
      part: Which of its columns.

    Returns:
      The choices in it, in the order they read.
    """
    return [
        str(option.id) for option in sheet.query_one(f"#{part}", OptionList).options
    ]


@pytest.mark.timeout(60)
async def test_what_an_agent_runs_is_chosen_a_part_at_a_time() -> None:
    """Three columns, each holding what the one to its left has under the cursor.

    Rather than one list of every backend crossed with every model crossed with every
    effort, which is what a flat list of them would be.
    """
    app = Amflows()
    async with app.run_test() as driver:
        sheet = Models(
            "flow.py",
            1,
            {
                "claude": (Model("opus", ("low", "high")),),
                "codex": (Model("gpt-5.6-sol", ("max",)),),
            },
        )
        app.push_screen(sheet)
        await driver.pause()

        assert _column(sheet, "agent") == ["claude", "codex"]
        assert _column(sheet, "model") == ["opus"]
        assert _column(sheet, "effort") == ["low", "high"]

        await driver.press("down")  # to codex, which runs something else
        await driver.pause()

        assert _column(sheet, "model") == ["gpt-5.6-sol"]
        assert _column(sheet, "effort") == ["max"]  # and takes only the one effort


@pytest.mark.timeout(60)
async def test_a_choice_made_is_walked_back_rather_than_started_over() -> None:
    """Esc steps left, and off the leftmost column back into the agent chosen before it.

    Which is the whole of it: a flow driving two agents used to mean that the first one,
    once answered, could not be answered again.
    """
    app = Amflows()
    async with app.run_test() as driver:
        sheet = Models("flow.py", 2, {"claude": (Model("opus", ("low", "high")),)})
        app.push_screen(sheet)
        await driver.pause()

        for key in ("enter", "enter", "down", "enter"):  # agent, model, high, taken
            await driver.press(key)
            await driver.pause()

        assert sheet._chosen == ["claude/opus/high"]
        assert (
            sheet.focused is not None and sheet.focused.id == "agent"
        )  # onto the next

        await driver.press(
            "escape"
        )  # off the leftmost column, back into the first agent
        await driver.pause()

        assert sheet._chosen == []
        assert sheet.focused is not None and sheet.focused.id == "effort"
        assert sheet._picked("effort") == "high"  # as it was left

        await driver.press("escape")  # and left again, through the columns
        await driver.pause()

        assert sheet.focused is not None and sheet.focused.id == "model"

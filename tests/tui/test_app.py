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
from typing import TYPE_CHECKING, cast

import pytest
from textual.widgets import Label, Static

from humanize.backends import Model
from humanize.cycle import cycles
from humanize.tui import Humanize
from humanize.tui.app import _OWN, Editor
from humanize.tui.pick import Flows, Models, Runs

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from textual.pilot import Pilot

#: A flow that drives one agent for two turns, so a line can be typed while it is running.
FLOW = """
from pathlib import Path

from humanize.agents import AgentBase


def run(agents: tuple[AgentBase], task: str) -> None:
    session = agents[0].new()
    Path("said.txt").write_text(session(task) + "\\n")
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


def _transcript(app: Humanize) -> str:
    """Everything the interface has shown, as one searchable string.

    Read while the interface is still up: its widgets go with it when it exits.
    """
    from textual.widgets import RichLog

    return "\n".join(line.text for line in app.query_one("#transcript", RichLog).lines)


@pytest.mark.timeout(60)
async def test_the_command_line_own_commands_are_not_commands_here(
    workspace: Path,
) -> None:
    """`collect` and `anchor` are not things to do to a flow that is running."""
    app = Humanize()
    async with app.run_test() as driver:
        await driver.press(*"/collect .")
        await driver.press("enter")
        await until(lambda: "no such command" in _transcript(app), driver)

        assert "no such command: /collect" in _transcript(app)
        assert app.is_running  # and a line to correct leaves the interface up
    assert not list(workspace.glob(".humanize/*.trace.json"))  # noqa: ASYNC240


@pytest.mark.timeout(60)
async def test_a_line_typed_while_a_flow_runs_reaches_the_agent(
    workspace: Path,
) -> None:
    """The whole point: the turn is still running, and what is typed lands inside it."""
    (workspace / "flow.py").write_text(FLOW)
    app = Humanize()
    async with app.run_test() as driver:
        app._flow_named, app._models = "flow.py", [Runs("claude/m:high")]
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
async def test_a_line_with_nothing_to_run_it_on_says_so_rather_than_vanishing() -> None:
    """A flow is always chosen now, so the only thing a line can be short of is an agent."""
    app = Humanize()
    async with app.run_test() as driver:
        await driver.press(*"hello?")
        await driver.press("enter")
        await driver.pause()

        assert app._models == []  # nothing installed, so nothing was set up to run
        assert "no coding agent is installed here" in _transcript(app)


@pytest.mark.timeout(60)
async def test_a_command_that_is_not_one_is_said_so() -> None:
    app = Humanize()
    async with app.run_test() as driver:
        await driver.press(*"/fly")
        await driver.press("enter")
        await driver.pause()

        assert "no such command" in _transcript(app)


@pytest.mark.timeout(60)
async def test_a_flow_that_is_not_there_is_a_line_to_correct_and_not_the_end() -> None:
    """A flow chosen that will not load is said so, and the interface stays up."""
    app = Humanize()
    async with app.run_test() as driver:
        app._flow_named, app._models = "nowhere.py", [Runs("claude/m:high")]
        await driver.press(*"do it")
        await driver.press("enter")
        await until(lambda: "nowhere.py" in _transcript(app), driver)

        assert app.is_running  # still there to be typed at
        assert "nowhere.py" in _transcript(app)


def test_only_the_flows_humanize_came_with_are_offered() -> None:
    """A flow of your own is a path typed out, not something found by walking the tree."""
    from humanize.flows import found
    from humanize.tui.complete import offered

    assert offered("/flow ", _OWN) == [name for _, name in found()]


@pytest.mark.timeout(60)
async def test_what_the_flow_did_is_on_status(workspace: Path) -> None:
    """Who worked, who handed to whom, and what it cost -- none of which the flow reports."""
    (workspace / "flow.py").write_text(FLOW)
    app = Humanize()
    async with app.run_test() as driver:
        app._flow_named, app._models = "flow.py", [Runs("claude/m:high")]
        await driver.press(*"start")
        await driver.press("enter")
        await until(
            lambda: bool(app._agents and any(agent.sessions for agent in app._agents)),
            driver,
        )
        await driver.press(*"and this")
        await driver.press("enter")
        await until(lambda: bool((workspace / "said.txt").exists()), driver)

        # Read while the flow is still running, which is the whole point of a sheet for it.
        app.action_status()
        await driver.pause()
        said = str(app.screen.query_one("#said", Label).content)
        assert "×1" in said  # the one agent, and its one turn
        assert "flow.py" in said
        assert app._monitor.turns.total() == 1


@pytest.mark.timeout(60)
async def test_a_half_typed_command_is_offered_the_rest_of_itself() -> None:
    """Offered in a list under the editor, and taken with tab: nothing is ever guessed at."""
    from textual.widgets import OptionList

    from humanize.tui.app import Editor

    app = Humanize()
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
    from humanize.flows import found
    from humanize.tui.app import Editor

    app = Humanize()
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
    from humanize.tui.app import Editor

    app = Humanize()
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
    from humanize.tui.app import Editor

    app = Humanize()
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

    from humanize.tui.app import Editor

    app = Humanize()
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
    """A command this interface grows must be offered without being listed twice.

    And nothing the command line has: `exec` is what the first thing you say already does,
    and `collect` and `anchor` are not things to do to a flow that is running.
    """
    from humanize.cli import COMMANDS
    from humanize.tui.complete import about, offered

    offers = offered("/", _OWN)

    assert {f"/{name}" for name in _OWN if about(name)} == set(offers)
    assert not {f"/{name}" for name in COMMANDS} & set(offers)
    # And a command typed in full has nothing left to be finished with, so enter sends it.
    assert offered("/exit", _OWN) == []


@pytest.mark.timeout(90)
async def test_what_is_running_is_not_swapped_underneath_itself(
    workspace: Path,
) -> None:
    """A flow drives the agents it was handed, so choosing others mid-run changes nothing.

    Except what the interface says it is running, which would then be a lie. Stop it first.
    """
    (workspace / "flow.py").write_text(FLOW)
    app = Humanize()
    async with app.run_test() as driver:
        app._flow_named, app._models = "flow.py", [Runs("claude/m:high")]
        await driver.press(*"start")
        await driver.press("enter")
        await until(
            lambda: bool(app._agents and any(agent.sessions for agent in app._agents)),
            driver,
        )

        app.action_agents()
        app.action_cycle_flow()
        await driver.press(*"/flow")
        await driver.press("enter")
        await driver.pause()

        assert app._flow_named == "flow.py"  # none of the three got anywhere
        assert app._models == [Runs("claude/m:high")]
        assert _transcript(app).count("while a flow is running") == 3
        # And `/status` is not one of them: it is read, so there is nothing to conflict with.
        app.action_status()
        await driver.pause()
        assert "flow.py" in str(app.screen.query_one("#said", Label).content)


@pytest.mark.timeout(90)
async def test_escape_stops_the_flow_and_not_just_the_turn(workspace: Path) -> None:
    """Esc ends the loop, rather than letting it hand on to the next agent.

    A flow is a loop, so stopping the turn under way is not stopping anything: the loop
    would go round again. Every agent is told, and the one that raises `Stopped` takes the
    loop with it -- which is why `Stopped` is not the failed turn a flow's own `|| true`
    catches.
    """
    (workspace / "flow.py").write_text(FLOW)
    app = Humanize()
    async with app.run_test() as driver:
        app._flow_named, app._models = "flow.py", [Runs("claude/m:high")]
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
    from humanize.agents.claude import ClaudeCodeAgent, ClaudeCodeAgentConfig

    (workspace / "flow.py").write_text(FLOW)
    app = Humanize()
    async with app.run_test() as driver:
        # A flow that is running, with nobody mid-turn: an agent that has launched nothing.
        app._flow_named, app._models = "flow.py", [Runs("claude/m:high")]
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
    app = Humanize()
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
    from humanize.tui.discover import installed

    with unittest.mock.patch("subprocess.Popen") as started:
        found = installed()

    assert not started.called  # nothing was run to find this out
    # And an effort a model does not take is not offered against it.
    efforts = {model.name: model.efforts for model in found.get("codex", ())}
    if efforts:
        assert efforts["gpt-5.5"] != efforts["gpt-5.6-sol"]


@pytest.mark.timeout(60)
async def test_a_flow_between_two_turns_is_a_flow_that_is_running() -> None:
    """It sleeps off a round, commits, reads what the last turn wrote -- and that is the run.

    Which is why the rate is measured over the whole of it: the status line says the same
    thing, naming the flow and how long the run has been going rather than falling back to
    saying where it is, as if nothing were happening.
    """
    from humanize.agents.claude import ClaudeCodeAgent, ClaudeCodeAgentConfig

    app = Humanize()
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
    from humanize.agents import Event
    from humanize.agents.claude import ClaudeCodeAgent, ClaudeCodeAgentConfig

    agent = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="m", effort="high"), name="one")
    app = Humanize()
    async with app.run_test() as driver:
        app._heard(agent, Event(kind="begins", text="do it"))
        app._began["one"] = time.monotonic() - 42  # a turn that started a while ago
        app._draw()
        await driver.pause()

        status = str(app.query_one("#status", Static).content)

    assert "one" in status  # who is working
    assert "42s" in status  # and for how long, which a turn saying nothing does not say


@pytest.mark.timeout(60)
async def test_the_flow_itself_is_walked_back_into_from_what_it_runs_on() -> None:
    """The walk is one walk: esc off the first thing asked about a flow is that flow again.

    Rather than a way out of both, which would mean picking the flow over from tab.
    """
    from humanize.tui.pick import Flows

    app = Humanize()
    # Whatever this machine has installed, since the sheet is only put up if there is one.
    with unittest.mock.patch(
        "humanize.tui.app.installed",
        return_value={"claude": (Model("opus", ("high",)),)},
    ):
        async with app.run_test() as driver:
            await driver.press(*"/flow")
            await driver.press("enter")
            await until(lambda: isinstance(app.screen, Flows), driver)
            await driver.press("enter")
            await until(lambda: isinstance(app.screen, Models), driver)

            await driver.press("escape")
            await until(lambda: isinstance(app.screen, Flows), driver)

            assert isinstance(app.screen, Flows)  # back in the list, not out of both
            assert app._models == []


#: A `claude` that stops to ask before it answers, as the real one does when it reaches for
#: the tool that puts a question to a person: a control request on the same stream the turn is
#: read from, which the turn cannot get past until it is answered.
ASKING = """
import json, sys

flags = dict(zip(sys.argv, sys.argv[1:]))
print(json.dumps({"type": "system", "session_id": flags["--session-id"]}), flush=True)
for line in sys.stdin:
    print(json.dumps({"type": "control_request", "request_id": "req_1", "request": {
        "subtype": "can_use_tool", "tool_name": "AskUserQuestion", "tool_use_id": "t_1",
        "requires_user_interaction": True, "input": {"questions": [
            {"header": "Way", "question": "Which way?",
             "options": [{"label": "left"}, {"label": "right"}]}]}}}), flush=True)
    answered = json.loads(sys.stdin.readline())["response"]["response"]
    print(json.dumps({"type": "result", "result": json.dumps(answered)}), flush=True)
"""


@pytest.fixture
def asking(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Puts a `claude` on PATH that stops to ask before it answers."""
    binaries = tmp_path / "bin"
    binaries.mkdir()
    fake = binaries / "claude"
    fake.write_text(f"#!{sys.executable}\n{ASKING}")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{binaries}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.mark.timeout(90)
async def test_an_agent_that_stops_to_ask_reaches_the_prompt(asking: Path) -> None:
    """The point of the prompt being here at all: a turn that needs a person can have one."""
    (asking / "flow.py").write_text(FLOW)
    app = Humanize()
    async with app.run_test() as driver:
        app._flow_named, app._models = "flow.py", [Runs("claude/m:high")]
        await driver.press(*"start")
        await driver.press("enter")
        await until(lambda: "Which way?" in _transcript(app), driver)

        # The question and what it offers are shown, and the next line typed is the answer.
        assert "left" in _transcript(app)
        assert "right" in _transcript(app)
        await driver.press(*"right")
        await driver.press("enter")
        await until((asking / "said.txt").exists, driver)

    # Which reached the tool as its answer, against the question it was asked.
    assert json.loads((asking / "said.txt").read_text())["updatedInput"]["answers"] == {
        "Which way?": "right"
    }


@pytest.mark.timeout(90)
async def test_away_means_the_agent_is_told_nobody_is_there_rather_than_waiting(
    asking: Path,
) -> None:
    """A question nobody is going to answer is a flow that has stopped, so it is refused."""
    (asking / "flow.py").write_text(FLOW)
    app = Humanize()
    async with app.run_test() as driver:
        app._flow_named, app._models = "flow.py", [Runs("claude/m:high")]
        await driver.press(*"/afk")
        await driver.press("enter")
        assert (
            app._afk
        )  # and it starts off, so an agent may ask until you say otherwise

        await driver.press(*"start")
        await driver.press("enter")
        await until((asking / "said.txt").exists, driver)

    # Nobody answered, so the tool was declined and the turn carried on from that.
    assert json.loads((asking / "said.txt").read_text())["behavior"] == "deny"


@pytest.mark.timeout(60)
async def test_ctrl_c_takes_back_the_nearest_thing_and_leaves_on_two() -> None:
    """As a coding agent's terminal does: the line, then the flow, then the interface."""
    app = Humanize()
    async with app.run_test() as driver:
        from humanize.tui.app import Editor

        await driver.press(*"half a prompt")
        await driver.press("ctrl+c")
        await driver.pause()

        assert (
            app.query_one(Editor).text == ""
        )  # the line, and the interface is still up
        assert app.is_running

        await driver.press("ctrl+c")
        await driver.pause()

    assert not app.is_running  # two in a row, and it leaves


@pytest.mark.timeout(90)
async def test_ctrl_c_with_nothing_half_typed_stops_the_flow(workspace: Path) -> None:
    """With no line to take back, the nearest thing there is to take back is the run."""
    (workspace / "flow.py").write_text(FLOW)
    app = Humanize()
    async with app.run_test() as driver:
        app._flow_named, app._models = "flow.py", [Runs("claude/m:high")]
        await driver.press(*"start")
        await driver.press("enter")
        await until(
            lambda: bool(app._agents and any(agent.sessions for agent in app._agents)),
            driver,
        )

        await driver.press("ctrl+c")
        await until(lambda: not app._agents, driver)

        assert "stopping the flow" in _transcript(app)
        assert app.is_running  # and one press stops the flow rather than the interface


@pytest.mark.timeout(60)
async def test_details_covers_the_thinking_as_well_as_the_tools() -> None:
    """One question -- how much of the working to show -- and so one switch."""
    app = Humanize()
    async with app.run_test() as driver:
        assert app._details

        await driver.press(*"/details")
        await driver.press("enter")
        await driver.pause()

        assert not app._details
        assert "thinking" in _transcript(app)  # said to be part of the same switch


def test_only_model_ids_are_offered(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """An alias is whichever model is newest today, and something else tomorrow.

    A window written on the end of one is a setting rather than a model -- a backend asked
    for either answers that there is no such model, and a cycle that recorded one says
    nothing.
    """
    from humanize.tui import discover

    cache = tmp_path / ".claude.json"
    cache.write_text(
        json.dumps({"additionalModelOptionsCache": [{"value": "claude-fable-5[1m]"}]})
    )
    monkeypatch.setattr(discover, "_CLAUDE_CACHE", cache)

    def which(name: str) -> str:
        return f"/usr/bin/{name}"

    monkeypatch.setattr(discover.shutil, "which", which)

    named = [model.name for model in discover.installed()["claude"]]

    assert "claude-fable-5" in named  # the account's own, without the window on the end
    assert not [name for name in named if "[" in name]
    assert not {"opus", "sonnet", "fable", "haiku"} & set(named)
    assert all(name.startswith("claude-") for name in named)


#: A `claude` that answers each thing it is told with one result and nothing else, which is
#: what makes a conversation countable: one turn in, one turn out.
ANSWERING = """
import json, sys

flags = dict(zip(sys.argv, sys.argv[1:]))
print(json.dumps({"type": "system", "session_id": flags["--session-id"]}), flush=True)
for line in sys.stdin:
    said = json.loads(line)["message"]["content"][0]["text"]
    print(json.dumps({"type": "result", "result": "heard " + said}), flush=True)
"""


@pytest.fixture
def talking(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """One `claude` on PATH, and an interface that opens set up to talk to it."""
    binaries = tmp_path / "bin"
    binaries.mkdir()
    fake = binaries / "claude"
    fake.write_text(f"#!{sys.executable}\n{ANSWERING}")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{binaries}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setattr(
        "humanize.tui.app.installed",
        lambda: {"claude": (Model("claude-opus-5", ("max", "high")),)},
    )
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.mark.timeout(60)
async def test_it_opens_ready_to_be_talked_to(talking: Path) -> None:
    """Nothing has to be picked first: a flow is what you reach for once one agent is not it."""
    app = Humanize()
    async with app.run_test() as driver:
        await driver.pause()

        assert app._flow_named == "chat"
        # The first agent installed, at the first model it runs -- but never at the hardest
        # effort, which is a thing to ask for rather than to spend before anyone has.
        assert app._models == [Runs("claude/claude-opus-5:high")]


@pytest.mark.timeout(60)
async def test_it_opens_saying_so_when_there_is_nothing_to_talk_to() -> None:
    """And still opens: an interface that would not start is worse than one that says why."""
    app = Humanize()
    async with app.run_test() as driver:
        await driver.pause()

        assert app._flow_named == "chat"
        assert app._models == []
        assert app.is_running


@pytest.mark.timeout(90)
async def test_every_line_typed_between_turns_is_a_turn_of_one_conversation(
    talking: Path,
) -> None:
    """The whole of what was asked for: saying something is all it takes, twice over."""
    app = Humanize()
    async with app.run_test() as driver:
        await driver.press(*"first")
        await driver.press("enter")
        await until(lambda: "heard first" in _transcript(app), driver)
        # The turn is over and the flow is waiting to be told the next one, rather than gone.
        await until(lambda: app._awaiting, driver)

        await driver.press(*"second")
        await driver.press("enter")
        await until(lambda: "heard second" in _transcript(app), driver)

        # One agent and the person, one session: the second turn resumed the first rather
        # than opening another, so the agent had the first in context.
        agent, person = app._agents
        assert person.backend == "human"
        assert agent.opened == [agent.opened[0]]
        assert "held for the next turn" not in _transcript(app)

        await driver.press("escape")
        await until(lambda: not app._agents, driver)


@pytest.mark.timeout(90)
async def test_a_flow_waiting_to_be_told_something_can_still_be_stopped(
    talking: Path,
) -> None:
    """Esc has to reach a flow that is doing nothing at all, or nothing ever releases it."""
    app = Humanize()
    async with app.run_test() as driver:
        await driver.press(*"first")
        await driver.press("enter")
        await until(lambda: app._awaiting, driver)  # waiting, with no turn open

        await driver.press("escape")
        await until(lambda: not app._agents, driver)

        # And the run is written down as stopped rather than as one that finished.
        (cycle,) = cycles(talking)
        assert json.loads(cycle.read_text().splitlines()[-1]) == {
            "event": "ended",
            "at": unittest.mock.ANY,
            "how": "stopped",
        }


@pytest.mark.timeout(60)
async def test_clearing_the_screen_clears_the_screen_and_nothing_else(
    talking: Path,
) -> None:
    """There is nothing else to clear: no turn carries context across a cycle."""
    app = Humanize()
    async with app.run_test() as driver:
        await driver.press(*"remember this")
        await driver.press("enter")
        await until(lambda: "remember this" in _transcript(app), driver)

        await driver.press(*"/clear")
        await driver.press("enter")
        await until(lambda: "remember this" not in _transcript(app), driver)

        # The screen, and only the screen: what was set up to run is still set up to run,
        # and what is running is still running.
        assert app._flow_named == "chat"
        assert app._models == [Runs("claude/claude-opus-5:high")]
        assert (
            app._agents
        )  # the flow the first line started was not stopped with the screen

        await driver.press("escape")
        await until(lambda: not app._agents, driver)


@pytest.mark.timeout(60)
async def test_looking_at_the_flows_and_walking_out_changes_nothing(
    talking: Path,
) -> None:
    """Tab is pressed to see what there is, and seeing must not cost what was set up."""
    app = Humanize()
    async with app.run_test() as driver:
        was = (app._flow_named, list(app._models))

        await driver.press(*"/flow")
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Flows), driver)
        await driver.press("escape")
        await until(lambda: not isinstance(app.screen, Flows), driver)

        assert (app._flow_named, app._models) == was


@pytest.mark.timeout(60)
async def test_it_is_drawn_in_the_terminals_own_colours() -> None:
    """Nothing here is a colour of ours, so there is nothing to read off the terminal.

    A scheme of our own is a guess about the background it lands on, and that guess is what a
    black interface in a white terminal is.
    """
    app = Humanize()
    async with app.run_test() as driver:
        await driver.pause()

        assert app.current_theme.ansi  # so ANSI reaches the terminal unconverted
        assert app.native_ansi_color
        # Every surface is the terminal's own, which is what leaves it showing through.
        for surface in ("background", "surface", "panel", "foreground"):
            assert app.theme_variables[surface] in ("transparent", "ansi_default")
        # Except where the cursor is, which is the one thing that must not be left to the
        # terminal: a row that says it is under the cursor by being a shade of the background
        # says it to nobody. Both ends of that pair are named, so it carries its own contrast.
        for end in ("block-cursor-background", "block-cursor-foreground"):
            assert app.theme_variables[end] != "ansi_default"


@pytest.mark.timeout(60)
async def test_a_theme_asked_for_is_the_theme(monkeypatch: pytest.MonkeyPatch) -> None:
    """Following the terminal is the default and not the rule: `TEXTUAL_THEME` still wins."""
    monkeypatch.setenv("TEXTUAL_THEME", "gruvbox")
    app = Humanize()
    async with app.run_test() as driver:
        await driver.pause()

        assert app.theme == "gruvbox"


def test_the_terminal_theme_names_no_colour_of_its_own() -> None:
    """Every colour in it is one of the sixteen the terminal already has a setting for."""
    from humanize.tui.app import _TERMINAL

    named = [
        _TERMINAL.primary,
        _TERMINAL.secondary,
        _TERMINAL.accent,
        _TERMINAL.warning,
        _TERMINAL.error,
        _TERMINAL.success,
        _TERMINAL.foreground,
        _TERMINAL.background,
        _TERMINAL.surface,
        _TERMINAL.panel,
        _TERMINAL.boost,
        *(
            value
            for name, value in (_TERMINAL.variables or {}).items()
            if not name.endswith("text-style")
        ),
    ]
    assert named  # or this checks nothing
    assert all(colour and colour.startswith("ansi_") for colour in named), named


@pytest.mark.timeout(60)
async def test_a_turn_reads_the_way_claude_code_renders_one() -> None:
    """What you said behind `❯`, what the agent said on `●`, and a line closing the turn.

    Which is Claude Code's own shape, read off its own screen: no bars, no boxes, nothing
    indented -- every line starts where the terminal does.
    """
    from humanize.agents import Event
    from humanize.agents.claude import ClaudeCodeAgent, ClaudeCodeAgentConfig

    app = Humanize()
    async with app.run_test() as driver:
        agent = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="m", effort="high"))
        app._said_by_you("do the thing")

        # From a thread of its own, as a turn always says things: `_heard` hands them to the
        # event loop, which it may only do from somewhere that is not the event loop.
        def turn() -> None:
            app._heard(agent, Event(kind="begins", text=""))
            app._heard(agent, Event(kind="tool", text="Bash git status"))
            app._heard(agent, Event(kind="text", text="one\ntwo"))
            app._heard(agent, Event(kind="ends", text=""))

        await asyncio.to_thread(turn)
        await until(lambda: "Worked for" in _transcript(app), driver)

        shown = _transcript(app)

    assert "❯ do the thing" in shown  # what you said
    assert (
        "● Bash(git status)" in shown
    )  # a tool on the bullet, its argument in brackets
    assert "● one" in shown
    assert "\n  two" in shown
    assert "✻ Worked for" in shown  # and the line Claude Code closes a turn with


@pytest.mark.timeout(60)
@unittest.mock.patch(
    "humanize.tui.app.installed",
    return_value={
        "claude": (Model("claude-opus-5", ("max", "high", "low")),),
        "codex": (Model("gpt-5.6-sol", ("xhigh",)),),
    },
)
async def test_what_an_agent_runs_is_one_list_and_an_effort_the_arrows_move(
    _installed: unittest.mock.MagicMock,  # noqa: PT019  -- `mock.patch` hands it over
) -> None:
    """As Claude Code's `/model` is: the models numbered, the effort on its own line.

    A CLI and a model are one choice rather than two, because they are one choice in fact --
    a model belongs to the CLI that runs it.
    """
    from textual.widgets import OptionList

    app = Humanize()
    async with app.run_test() as driver:
        # Walked into the way it is walked into: tab, a flow, then what it runs on.
        await driver.press(*"/flow")
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Flows), driver)
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Models), driver)
        sheet = app.screen
        listing = sheet.query_one("#choices", OptionList)
        await until(lambda: bool(listing.options), driver)

        # One row per CLI-and-model pair, numbered, with the cursor marked by `❯`.
        rows = [str(option.prompt) for option in listing.options]
        assert [str(option.id) for option in listing.options] == [
            "claude/claude-opus-5",
            "codex/gpt-5.6-sol",
        ]
        assert "❯" in rows[0]
        assert "1." in rows[0]
        assert "❯" not in rows[1]

        # The effort is adjusted rather than chosen, and starts on the hardest.
        tuning = sheet.query_one("#tuning", Label)
        assert "max effort" in str(tuning.content)
        await driver.press("left")
        await driver.pause()
        assert "high effort" in str(tuning.content)  # left is less
        await driver.press("right")
        await driver.pause()
        assert "max effort" in str(tuning.content)  # and right is more

        await driver.press("enter")
        await until(lambda: not isinstance(app.screen, Models), driver)

    assert cast("Models", sheet)._chosen == [Runs("claude/claude-opus-5:max")]


@pytest.mark.timeout(60)
@unittest.mock.patch(
    "humanize.tui.app.installed",
    return_value={
        "claude": (Model("claude-opus-5", ("ultracode", "max", "high")),),
        "kimi": (Model("kimi-code/k3", ("max", "low"), swarms=True),),
    },
)
async def test_a_turn_is_said_to_run_hard_and_said_to_run_wide_separately(
    _installed: unittest.mock.MagicMock,  # noqa: PT019  -- `mock.patch` hands it over
) -> None:
    """Claude's ultracode is an effort; Kimi's swarm mode is a second thing, so it is a key.

    How hard a turn thinks and how wide it runs are not two ends of one dial: a swarm at low
    effort is a real thing to ask for, and a list that mixed them could not say it.
    """
    from textual.widgets import OptionList

    app = Humanize()
    async with app.run_test() as driver:
        await driver.press(*"/flow")
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Flows), driver)
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Models), driver)
        sheet = app.screen
        await until(
            lambda: bool(sheet.query_one("#choices", OptionList).options), driver
        )
        tuning = sheet.query_one("#tuning", Label)

        # Claude opens on ultracode, which is the hardest thing it takes, and has no swarm.
        assert "ultracode effort" in str(tuning.content)
        assert "swarm" not in str(tuning.content)
        await driver.press("tab")  # nothing to toggle, so nothing happens
        await driver.pause()
        assert "swarm" not in str(tuning.content)

        # Kimi has one, and tab is what turns it on.
        await driver.press("down")
        await driver.pause()
        assert "swarm mode off" in str(tuning.content)
        await driver.press("tab")
        await driver.pause()
        assert "swarm mode on" in str(tuning.content)
        await driver.press("left")  # and it is still on at another effort
        await driver.pause()
        assert "low effort" in str(tuning.content)
        assert "swarm mode on" in str(tuning.content)

        await driver.press("enter")
        await until(lambda: not isinstance(app.screen, Models), driver)

    # One turn, at one effort, run wide -- which is how Kimi is asked for a fleet.
    assert cast("Models", sheet)._chosen == [Runs("kimi/kimi-code/k3:swarmlow")]


@pytest.mark.timeout(60)
@unittest.mock.patch(
    "humanize.tui.app.installed",
    return_value={
        "claude": (
            Model("claude-opus-5", ("high",)),
            Model("claude-haiku-4-5", ("high",)),
        ),
        "codex": (Model("gpt-5.6-sol", ("high",)),),
    },
)
async def test_a_list_too_long_to_walk_is_narrowed_by_typing_at_it(
    _installed: unittest.mock.MagicMock,  # noqa: PT019  -- `mock.patch` hands it over
) -> None:
    """Every model of every CLI is longer than a screen, so the letters go into it."""
    from textual.widgets import OptionList

    app = Humanize()
    async with app.run_test() as driver:
        await driver.press(*"/flow")
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Flows), driver)
        sheet = app.screen
        listing = sheet.query_one("#choices", OptionList)
        await until(lambda: bool(listing.options), driver)
        every = listing.option_count

        await driver.press("c", "h", "a", "t")
        await driver.pause()
        assert [str(option.id) for option in listing.options] == ["chat"]

        await driver.press("backspace")  # and one letter back is a wider list again
        await driver.pause()
        assert listing.option_count > 1

        await driver.press("z", "z")  # narrowed to nothing rather than to everything
        await driver.pause()
        assert listing.option_count == 0

        await driver.press("escape")  # which esc steps back out of before it leaves
        await driver.pause()
        assert listing.option_count == every
        assert isinstance(app.screen, Flows)

        # Spread through the name in order, rather than a prefix: `hk` finds `claude-haiku`.
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Models), driver)
        listing = app.screen.query_one("#choices", OptionList)
        await until(lambda: bool(listing.options), driver)
        await driver.press("h", "k")
        await driver.pause()

        assert [str(option.id) for option in listing.options] == [
            "claude/claude-haiku-4-5"
        ]


@pytest.mark.timeout(60)
async def test_the_cursor_can_be_seen_in_the_lists_that_are_chosen_from() -> None:
    """A list you cannot see the cursor in is one you choose from blind.

    Claude Code marks it with `❯` against the row rather than by filling the row, so what is
    checked is the marker: it is on the row the cursor is on and on no other.
    """
    from textual.widgets import OptionList

    app = Humanize()
    async with app.run_test() as driver:
        await driver.press(*"/flow")
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Flows), driver)
        listing = app.screen.query_one("#choices", OptionList)
        await until(lambda: bool(listing.options), driver)

        marked = [at for at, o in enumerate(listing.options) if "❯" in str(o.prompt)]
        assert marked == [listing.highlighted]

        await driver.press("down")
        await driver.pause()
        marked = [at for at, o in enumerate(listing.options) if "❯" in str(o.prompt)]
        assert marked == [listing.highlighted]


@pytest.mark.timeout(60)
async def test_shift_tab_steps_through_the_flows_without_asking() -> None:
    """A short list is stepped through, not opened: `/flow` is there for picking by name."""
    from humanize.flows import found

    named = [name for _, name in found()]
    with unittest.mock.patch(
        "humanize.tui.app.installed",
        return_value={"claude": (Model("claude-opus-5", ("high",)),)},
    ):
        app = Humanize()
        async with app.run_test() as driver:
            await driver.pause()
            assert app._flow_named == named[0]

            await driver.press("shift+tab")
            await until(lambda: app._flow_named == named[1], driver)
            assert not isinstance(app.screen, Flows)  # nothing was opened to do it
            assert app._models  # and it is still something you can say a thing to

            for _ in range(len(named) - 1):
                await driver.press("shift+tab")
                await driver.pause()
            assert app._flow_named == named[0]  # round again


@pytest.mark.timeout(60)
async def test_a_switch_takes_on_and_off_as_well_as_being_flipped() -> None:
    """A toggle is what you reach for; `on` is what you write down and replay."""
    app = Humanize()
    async with app.run_test() as driver:
        for said, want in (("/afk on", True), ("/afk on", True), ("/afk", False)):
            await driver.press(*said)
            await driver.press("enter")
            await driver.pause()
            assert app._afk is want, said

        await driver.press(*"/details sideways")
        await driver.press("enter")
        await driver.pause()
        assert app._details is True  # unchanged, and said so rather than guessed at
        assert "say on or off" in _transcript(app)


def test_the_commands_are_offered_in_alphabetical_order() -> None:
    """The one order a list of commands has that a reader can predict."""
    from humanize.tui.complete import offered

    offers = offered("/", _OWN)

    assert offers == sorted(offers)
    assert "/help" not in offers  # the bottom bar says what the keys are


#: A `claude` that answers each thing it is told the way the real one does: the words as it
#: says them, and then the same words again as the answer the turn settles on. Two answers
#: for two things said, which is what makes a reply counted twice countable.
TWICE = """
import json, sys

flags = dict(zip(sys.argv, sys.argv[1:]))
print(json.dumps({"type": "system", "session_id": flags["--session-id"]}), flush=True)
heard = []
for line in sys.stdin:
    heard.append(json.loads(line)["message"]["content"][0]["text"])
    if len(heard) == 1:
        # Still working, so a second thing said lands inside this same turn.
        print(json.dumps({"type": "assistant", "message": {"content": [
            {"type": "text", "text": "working"}]}}), flush=True)
        continue
    for said in heard:
        print(json.dumps({"type": "assistant", "message": {"content": [
            {"type": "text", "text": "answer to " + said}]}}), flush=True)
        print(json.dumps({"type": "result", "result": "answer to " + said}), flush=True)
"""


@pytest.mark.timeout(90)
async def test_two_things_said_get_two_answers_and_not_three(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A turn says its answer as it says it and again as it settles; one of those is enough.

    Passing both on showed every mid-turn answer twice, so saying two things read as three
    replies -- which is the whole of what is being checked here.
    """
    binaries = tmp_path / "bin"
    binaries.mkdir()
    fake = binaries / "claude"
    fake.write_text(f"#!{sys.executable}\n{TWICE}")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{binaries}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setattr(
        "humanize.tui.app.installed",
        lambda: {"claude": (Model("claude-opus-5", ("high",)),)},
    )
    monkeypatch.chdir(tmp_path)

    app = Humanize()
    async with app.run_test() as driver:
        await driver.press(*"first")
        await driver.press("enter")
        # The turn will not end until it has been told something else, so this cannot race.
        await until(
            lambda: bool(app._agents and any(a.sessions for a in app._agents)), driver
        )
        await driver.press(*"second")
        await driver.press("enter")
        await until(lambda: "answer to second" in _transcript(app), driver)
        await driver.pause()

        shown = _transcript(app)
        assert shown.count("answer to first") == 1
        assert shown.count("answer to second") == 1

        await driver.press("escape")
        await until(lambda: not app._agents, driver)


def test_the_offers_say_what_each_command_takes() -> None:
    """A switch takes `on` or `off` as well as being flipped, and only the list says so."""
    from humanize.tui.complete import about, takes

    for name in _OWN:
        assert about(name), name  # or it would not be offered at all

    assert takes("afk") == "[on|off]"
    assert takes("details") == "[on|off]"
    assert takes("exit") == ""  # a command that takes nothing says nothing


@pytest.mark.timeout(60)
async def test_taking_an_offer_types_the_command_and_not_its_arguments() -> None:
    """The brackets say what may be written; they are not themselves something to write."""
    app = Humanize()
    async with app.run_test() as driver:
        await driver.press(*"/af")
        await driver.pause()
        await driver.press("tab")
        await driver.pause()

        assert app.query_one(Editor).text == "/afk "  # not `/afk [on|off]`


@pytest.mark.timeout(60)
@unittest.mock.patch(
    "humanize.tui.pick.machines", return_value=[("ssh://box", "ssh config")]
)
@unittest.mock.patch(
    "humanize.tui.app.installed",
    return_value={"claude": (Model("claude-opus-5", ("max", "high")),)},
)
async def test_where_an_agent_works_is_set_beside_what_it_runs(
    _installed: unittest.mock.MagicMock,  # noqa: PT019  -- `mock.patch` hands it over
    _machines: unittest.mock.MagicMock,  # noqa: PT019
) -> None:
    """A second question about the agent, so it is a key on the same sheet and not a row."""
    from textual.widgets import OptionList

    from humanize.tui.pick import Anchors

    app = Humanize()
    async with app.run_test() as driver:
        await driver.press(*"/agents")
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Models), driver)
        sheet = app.screen
        tuning = sheet.query_one("#tuning", Label)
        await until(lambda: "effort" in str(tuning.content), driver)
        assert "on this machine" in str(tuning.content)

        await driver.press("ctrl+a")
        await until(lambda: isinstance(app.screen, Anchors), driver)
        anchors = app.screen
        listing = anchors.query_one("#choices", OptionList)
        await until(lambda: bool(listing.options), driver)
        # This machine first, then the ones there are to be found.
        assert [str(option.id) for option in listing.options] == ["=", "=ssh://box"]

        await driver.press("down")
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Models), driver)
        await until(lambda: "ssh://box" in str(tuning.content), driver)

        await driver.press("enter")
        await until(lambda: not isinstance(app.screen, Models), driver)

    # It rides along with what the agent runs, and is what the line above the prompt says.
    assert cast("Models", sheet)._chosen == [
        Runs("claude/claude-opus-5:max", "ssh://box")
    ]
    assert app._models == [Runs("claude/claude-opus-5:max", "ssh://box")]
    assert app.settings.agents(app._flow_named) == [
        Runs("claude/claude-opus-5:max", "ssh://box")
    ]


@pytest.mark.timeout(60)
@unittest.mock.patch("humanize.tui.pick.machines", return_value=[])
@unittest.mock.patch(
    "humanize.tui.app.installed",
    return_value={"claude": (Model("claude-opus-5", ("max", "high")),)},
)
async def test_a_machine_nothing_here_can_see_is_a_target_that_is_typed(
    _installed: unittest.mock.MagicMock,  # noqa: PT019  -- `mock.patch` hands it over
    _machines: unittest.mock.MagicMock,  # noqa: PT019
) -> None:
    """The list is a convenience; a target is a string, and any string that reads as one goes."""
    from textual.widgets import OptionList

    from humanize.tui.pick import Anchors

    app = Humanize()
    async with app.run_test() as driver:
        await driver.press(*"/agents")
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Models), driver)
        await driver.press("ctrl+a")
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

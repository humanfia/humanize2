"""`/resume` -- carrying the last run in this directory on from where it stopped.

`/epics` has offered this of whichever run the cursor is on since there was a list of runs,
and needing to find that row is the whole of what was wrong with it: a loop left running
overnight is looked at again by somebody who wants the work carried on rather than a list to
look for it in. So this is the last run here and no other, and a run that cannot be carried
on says which reason that is rather than handing the one before it over in silence.

Driven headlessly, as every test of the interface is, so what is checked is what a typed line
did rather than how it was drawn.
"""

from __future__ import annotations

import json
import os
import sys
from typing import TYPE_CHECKING

import pytest

from hmz.runtime.epic import epics, state
from hmz.tui import Humanize
from tests.stubs import written
from tests.tui.conftest import transcript, until

if TYPE_CHECKING:
    from pathlib import Path

    from textual.pilot import Pilot

#: A flow that says it can be picked up, and counts the runs of itself in what it is handed.
COUNTS = '''"""Counts the runs of itself."""

from pathlib import Path
from typing import Any

from hmz.coganchor.agents import AgentBase
from hmz.flows import flow


@flow(resumable=True)
def run(agents: tuple[AgentBase], task: str, state: dict[str, Any]) -> None:
    state["rounds"] = state.get("rounds", 0) + 1
    Path("rounds.txt").write_text(str(state["rounds"]))
'''

#: One that says nothing, which is a run to read rather than a run to carry on.
PLAIN = '''"""Runs once, and says nothing about being picked up."""

from pathlib import Path

from hmz.coganchor.agents import AgentBase
from hmz.flows import flow


@flow
def run(agents: tuple[AgentBase], task: str) -> None:
    Path("plain.txt").write_text(task)
'''

#: One that says it can be picked up and writes nothing down, which is what a run stopped
#: before it got anywhere leaves behind: the mark, and nothing under it.
BLANK = '''"""Says it can be picked up, and never writes down where it got to."""

from pathlib import Path
from typing import Any

from hmz.coganchor.agents import AgentBase
from hmz.flows import flow


@flow(resumable=True)
def run(agents: tuple[AgentBase], task: str, state: dict[str, Any]) -> None:
    Path("blank.txt").write_text(task)
'''

#: One that says it can be picked up, writes something down and then empties it, which is a
#: flow saying the next run here starts clean rather than carrying this one on.
EMPTIES = '''"""Writes down where it got to, and then says the next run starts clean."""

from typing import Any

from hmz.coganchor.agents import AgentBase
from hmz.flows import flow


@flow(resumable=True)
def run(agents: tuple[AgentBase], task: str, state: dict[str, Any]) -> None:
    state["rounds"] = state.get("rounds", 0) + 1
    state.clear()
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
    """A directory with the three flows in it and a fake `claude` to drive them."""
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
    written(where, "blank", BLANK)
    written(where, "empties", EMPTIES)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _ran(flow: str, task: str) -> None:
    """Runs one flow here, the way a command line would, so there is a run to carry on.

    On the fake `claude` this suite puts on PATH rather than on a stand-in of our own: a run
    is carried on as a command line naming what each of its agents runs, so the agents of a
    run have to be agents something can name.
    """
    from hmz.coganchor.agents import driver
    from hmz.runtime.runner import Runner

    agent, config = driver("claude")
    Runner(flow, [agent(config(model="m", effort="high"))]).run(task)


async def _resumes(app: Humanize, driver: Pilot[None]) -> None:
    """Types `/resume` at the prompt, which is the whole of the command."""
    await driver.press(*"/resume")
    await driver.press("enter")
    await driver.pause()


def _began(epic: Path) -> dict[str, object]:
    """The line a run opens its record with, which is where it says what it picked up."""
    said = (epic / "epic.jsonl").read_text(encoding="utf-8").splitlines()[0]
    return json.loads(said)


@pytest.mark.timeout(90)
async def test_the_last_run_here_is_carried_on(workspace: Path) -> None:
    """The whole of it: the flow goes on from where it stopped rather than starting over."""
    _ran("counts", "keep going")
    assert (workspace / "rounds.txt").read_text() == "1"
    (first,) = epics(workspace)

    app = Humanize()
    async with app.run_test() as driver:
        await _resumes(app, driver)
        await until(lambda: len(epics(workspace)) == 2, driver)
        await until(lambda: (workspace / "rounds.txt").read_text() == "2", driver)
        # Which run was picked up, said as it starts: somebody who has been away is owed
        # which day's work this is.
        assert first.name in transcript(app)

    second = next(one for one in epics(workspace) if one != first)
    assert state(second) == {"rounds": 2}
    # A run of its own, saying which run it came from: an epic is never reopened.
    assert _began(second)["picked_up"] == first.name


@pytest.mark.timeout(60)
async def test_a_directory_nothing_has_been_run_in_says_so(workspace: Path) -> None:
    """A command that did nothing and said nothing reads as one that is broken."""
    del workspace
    app = Humanize()
    async with app.run_test() as driver:
        await _resumes(app, driver)

        assert "no flow has been run here" in transcript(app)


@pytest.mark.timeout(60)
async def test_a_flow_that_no_longer_says_it_can_be_picked_up_says_why(
    workspace: Path,
) -> None:
    """Asked of the flow, as it is wherever it is asked -- and named, so it can be fixed."""
    _ran("plain", "go")

    app = Humanize()
    async with app.run_test() as driver:
        await _resumes(app, driver)

        assert "plain does not say it can be picked up" in transcript(app)
        assert len(epics(workspace)) == 1  # and nothing was started


@pytest.mark.timeout(60)
async def test_a_run_that_left_nothing_behind_is_not_carried_on(
    workspace: Path,
) -> None:
    """Starting from the top under a line saying which run it came from is a false record.

    And it is the last run that is asked, not the last one that left anything: a loop carried
    on from the day before yesterday, because yesterday's died before it wrote anything, is a
    day's work thrown away without anybody being told.
    """
    _ran("counts", "keep going")  # which left something
    _ran("blank", "go")  # and which is not what the last run here was

    app = Humanize()
    async with app.run_test() as driver:
        await _resumes(app, driver)

        assert "left nothing behind" in transcript(app)
        assert len(epics(workspace)) == 2
        assert (workspace / "rounds.txt").read_text() == "1"


@pytest.mark.timeout(60)
async def test_a_record_that_cannot_be_read_back_says_so(workspace: Path) -> None:
    """A run that died mid-line left a line rather than a record.

    Which is the very case this command is for -- a turn that took the process with it -- so
    it says so rather than raising out of the prompt.
    """
    from hmz.runtime.epic import under

    half = under(workspace) / "20260101T000000.000Z-halfway"
    half.mkdir(parents=True)
    (half / "epic.jsonl").write_text("", encoding="utf-8")

    app = Humanize()
    async with app.run_test() as driver:
        await _resumes(app, driver)

        assert "cannot be read back" in transcript(app)


@pytest.mark.timeout(60)
async def test_a_run_that_emptied_what_it_wrote_is_not_carried_on(
    workspace: Path,
) -> None:
    """A flow that cleared its state said the next run here starts clean.

    Which is the opposite of what handing it that state back would say. A run stopped for
    having spent its allowance is not that: it was stopped rather than finished, so it leaves
    what it kept and picking it up is the point of having kept it.
    """
    _ran("empties", "go")

    app = Humanize()
    async with app.run_test() as driver:
        await _resumes(app, driver)

        assert "left nothing behind" in transcript(app)
        assert "starts from the top" in transcript(app)
        assert len(epics(workspace)) == 1


@pytest.mark.timeout(60)
async def test_a_flow_marked_since_the_run_is_asked_of_the_flow(
    workspace: Path,
) -> None:
    """A flow is a directory on disk, and what can happen next is what it says today.

    The run of it said nothing about being picked up, so what stands in the way is what that
    run left rather than what its flow says -- which is the two questions in their order.
    """
    _ran("plain", "go")
    written(workspace / ".humanize/flows", "plain", COUNTS)

    app = Humanize()
    async with app.run_test() as driver:
        await _resumes(app, driver)

        assert "does not say it can be picked up" not in transcript(app)
        assert "left nothing behind" in transcript(app)


@pytest.mark.timeout(60)
async def test_carrying_on_is_refused_while_a_flow_is_running(workspace: Path) -> None:
    """A run picked up is a flow started, and there is one going. `ctrl+c` twice stops it."""
    from hmz.coganchor.agents.claude import ClaudeCodeAgent, ClaudeCodeAgentConfig

    _ran("counts", "keep going")

    app = Humanize()
    async with app.run_test() as driver:
        app._agents = [ClaudeCodeAgent(ClaudeCodeAgentConfig(model="m", effort="high"))]
        await _resumes(app, driver)

        assert "no picking a run up while a flow is running" in transcript(app)
        assert "ctrl+c twice stops it first" in transcript(app)
        assert len(epics(workspace)) == 1
        app._agents = []


@pytest.mark.timeout(60)
async def test_carrying_on_is_refused_while_the_flow_is_still_unwinding(
    workspace: Path,
) -> None:
    """A flow told to stop goes in its own time, and writes down where it got to as it goes.

    Picked up in that window, the next run starts from a state still moving under it and does
    a round the stopped run had already recorded. And `ctrl+c twice` is not the answer here,
    since that is what was just pressed.
    """
    from hmz.coganchor.agents.claude import ClaudeCodeAgent, ClaudeCodeAgentConfig

    _ran("counts", "keep going")

    app = Humanize()
    async with app.run_test() as driver:
        # What `ctrl+c` twice leaves behind: let go of as the running agents, kept as the
        # ones on their way out.
        app._stopping = [
            ClaudeCodeAgent(ClaudeCodeAgentConfig(model="m", effort="high"))
        ]
        await _resumes(app, driver)

        assert "while the flow is still stopping" in transcript(app)
        assert len(epics(workspace)) == 1
        app._stopping = []


@pytest.mark.timeout(60)
async def test_a_line_that_named_a_run_is_said_back_rather_than_dropped(
    workspace: Path,
) -> None:
    """There is nothing to name here, and a name quietly ignored starts the wrong run."""
    _ran("counts", "keep going")

    app = Humanize()
    async with app.run_test() as driver:
        (first,) = epics(workspace)
        await driver.press(*f"/resume {first.name}")
        await driver.press("enter")
        await driver.pause()

        assert "/resume takes nothing" in transcript(app)
        assert len(epics(workspace)) == 1


def test_the_command_is_offered_with_a_line_about_it() -> None:
    """Or it is a command only whoever wrote it knows is there."""
    from hmz.tui.app import _BY_NAME, _COMMANDS
    from hmz.tui.complete import offered

    assert "/resume" in offered("/", _COMMANDS)
    assert _BY_NAME["resume"].about
    assert _BY_NAME["resume"].takes == ""  # the last run is not something to name

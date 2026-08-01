"""One conversation at a time: what is read, what a typed line goes to, and how it is moved.

A flow drives several agents and each of them holds as many conversations as it likes, so the
transcript is one of them rather than all of them interleaved, and tab and shift+tab step
forwards and backwards through the ones the flow has open. Driven headlessly, so what is
checked is what a keystroke does rather than how it is drawn.
"""

from __future__ import annotations

import asyncio
import gc
import os
import sys
import time
import weakref
from typing import TYPE_CHECKING

import pytest
from textual.widgets import Static

from hmz.agents import AgentConfig, Event
from hmz.tui import Humanize
from hmz.tui.app import _KEPT
from hmz.tui.pick import Held, Runs, reads
from hmz.tui.selecting import Transcript
from tests.stubs import ShellAgent, ShellSession

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from textual.pilot import Pilot

    from hmz.agents import AgentBase

CONFIG = AgentConfig(model="m", effort="high")

#: A `claude --print` that says which session it is, says one thing, and then holds the turn
#: open until the workspace says it may finish. Which is what makes two turns run at once here,
#: since a turn that has ended is not one to step onto.
PATIENT = """
import json, os, pathlib, sys, time

flags = dict(zip(sys.argv, sys.argv[1:]))
taken = flags.get("--session-id") or flags["--resume"]
print(json.dumps({"type": "system", "session_id": taken}), flush=True)
where = pathlib.Path(os.environ["HUMANIZE_HELD"])
for line in sys.stdin:
    print(json.dumps({"type": "assistant", "message": {"content": [
        {"type": "text", "text": "working " + taken}]}}), flush=True)
    while not (where / "go.txt").exists():
        time.sleep(0.02)
    print(json.dumps({"type": "result", "result": "done"}), flush=True)
"""

#: A flow that holds a turn open on each of its agents, so that two of them are working at
#: once and neither ends until the flow is let go. Which is the case that matters: one
#: transcript for two agents talking at the same time is two transcripts interleaved.
HOLDING = """
import asyncio

from hmz.agents import AgentBase


def run(agents: tuple[AgentBase, AgentBase], task: str) -> None:
    async def both() -> None:
        # A turn apiece, open at the same time and neither answering until the fake CLI is
        # let go: two agents working at once is the case tab is for.
        await asyncio.gather(*(agent.aturn("hold") for agent in agents))

    asyncio.run(both())
"""


class Steerable(ShellSession):
    """A conversation a word can be put into, which a shell-backed one has no process for."""

    def __init__(
        self, agent: AgentBase, cwd: str | os.PathLike[str] | None = None
    ) -> None:
        super().__init__(agent, cwd)
        self.put_in: list[str] = []

    def interject(self, text: str) -> None:
        """Takes the word and says nothing about it, as a backend takes one off us."""
        self.put_in.append(text)


class SteerableAgent(ShellAgent):
    """An agent whose conversations record what was put into them."""

    def new(self, cwd: str | os.PathLike[str] | None = None) -> Steerable:
        """Opens one."""
        return Steerable(self, cwd)


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
    await driver.pause()


def _transcript(app: Humanize) -> str:
    """Everything the transcript is showing, as one searchable string."""
    return app.query_one("#transcript", Transcript).text


def _above(app: Humanize) -> str:
    """The line above the prompt, which says what each agent runs and what it is holding."""
    return str(app.query_one("#above", Static).content)


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A flow that holds two conversations open, and a `claude` it never launches."""
    binaries = tmp_path / "bin"
    binaries.mkdir()
    fake = binaries / "claude"
    fake.write_text(f"#!{sys.executable}\n{PATIENT}")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{binaries}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))
    # Where the fake looks for its leave to finish, since a turn is run wherever the flow is.
    monkeypatch.setenv("HUMANIZE_HELD", str(tmp_path))
    (tmp_path / "flow.py").write_text(HOLDING)
    monkeypatch.chdir(tmp_path)
    return tmp_path


async def _two_agents(app: Humanize, driver: Pilot[None], where: Path) -> None:
    """Starts the flow that holds a conversation open for each of two agents.

    Args:
      app: The interface.
      driver: What is pumping it.
      where: The workspace it is running in.
    """
    app._flow_named = "flow.py"
    app._models = [Runs("claude/m:high"), Runs("claude/m:high")]
    await driver.press(*"do it")
    await driver.press("enter")
    await until(lambda: len(app._conversations()) == 2, driver)
    # Both working, which is what tab steps between: a turn that has not started is not one
    # to step onto, and one that has ended is not either.
    await until(lambda: len(app._working) == 2, driver)
    assert app._agents  # and it holds them until it is let go, so nothing here can race
    assert not (where / "go.txt").exists()


def _let_go(where: Path) -> None:
    """Lets a held flow finish, there being no turn in it for esc to reach.

    Args:
      where: The workspace it is running in.
    """
    (where / "go.txt").write_text("")


@pytest.mark.timeout(60)
async def test_tab_reads_the_next_conversation_and_wraps(workspace: Path) -> None:
    """Two agents talking at once are two transcripts, and tab is how the second is read."""
    app = Humanize()
    async with app.run_test() as driver:
        await _two_agents(app, driver, workspace)
        first, second = (session for _, session in app._conversations())

        # The first there is, until something says otherwise: a transcript showing nothing
        # until a key has been pressed would be an interface that had to be started twice.
        assert app._reading() is first

        await driver.press("tab")
        await driver.pause()
        assert app._reading() is second

        await driver.press("tab")  # round the end, back to the first
        await driver.pause()
        assert app._reading() is first

        _let_go(workspace)
        await until(lambda: not app._agents, driver)


@pytest.mark.timeout(60)
async def test_shift_tab_reads_the_conversation_before_it(workspace: Path) -> None:
    """The other way round the same ring, which is what a pair of keys is for."""
    app = Humanize()
    async with app.run_test() as driver:
        await _two_agents(app, driver, workspace)
        first, second = (session for _, session in app._conversations())
        assert app._reading() is first

        await driver.press("shift+tab")  # backwards off the first is the last of them
        await driver.pause()
        assert app._reading() is second

        await driver.press("shift+tab")
        await driver.pause()
        assert app._reading() is first

        _let_go(workspace)
        await until(lambda: not app._agents, driver)


@pytest.mark.timeout(60)
async def test_shift_tab_no_longer_steps_to_the_next_flow(workspace: Path) -> None:
    """It reads a conversation now. `/flow` is how a flow is chosen, and the only way."""
    app = Humanize()
    async with app.run_test() as driver:
        was = app._flow_named

        await driver.press(
            "shift+tab"
        )  # with nothing running, which is where it stepped
        await driver.pause()
        assert app._flow_named == was
        assert len(app.screen_stack) == 1  # and nothing was opened to do it

        await _two_agents(app, driver, workspace)
        await driver.press("shift+tab")
        await driver.pause()

        assert app._flow_named == "flow.py"
        _let_go(workspace)
        await until(lambda: not app._agents, driver)


@pytest.mark.timeout(60)
async def test_the_transcript_is_the_conversation_being_read_and_no_other() -> None:
    """Two agents talking at once interleaved into one transcript is neither of them."""
    app = Humanize()
    async with app.run_test() as driver:
        one, two = SteerableAgent(CONFIG), SteerableAgent(CONFIG)
        app._agents = [one, two]
        first, second = one.new(), two.new()

        # A turn apiece, which is what makes them two conversations to step between.
        app._heard(one, first, Event(kind="begins", text="go"))
        app._heard(two, second, Event(kind="begins", text="go"))
        app._heard(one, first, Event(kind="text", text="from the first"))
        app._heard(two, second, Event(kind="text", text="from the second"))
        await driver.pause()

        assert "from the first" in _transcript(app)
        assert "from the second" not in _transcript(app)

        await driver.press("tab")
        await driver.pause()

        # Drawn again from what was kept against it, and only that.
        assert "from the second" in _transcript(app)
        assert "from the first" not in _transcript(app)
        assert app._reading() is second


@pytest.mark.timeout(60)
async def test_a_typed_line_goes_to_the_conversation_being_read() -> None:
    """Which is the whole point: an agent holds several, so "the one working" says nothing."""
    app = Humanize()
    async with app.run_test() as driver:
        one, two = SteerableAgent(CONFIG), SteerableAgent(CONFIG)
        app._agents = [one, two]
        app._models = [Runs("claude/m:high"), Runs("claude/m:high")]
        first, second = one.new(), two.new()
        # A turn open in each, so that either of them could have taken the line.
        app._heard(one, first, Event(kind="begins", text=""))
        app._heard(two, second, Event(kind="begins", text=""))

        await driver.press("tab")
        await driver.pause()
        assert app._reading() is second

        await driver.press(*"for the second")
        await driver.press("enter")
        await until(lambda: bool(second.put_in), driver)

        assert second.put_in == ["for the second"]
        assert first.put_in == []  # not the one that happened to be working as well
        assert app._given == [
            (two.id, "for the second")
        ]  # pinned against whoever has it


@pytest.mark.timeout(60)
async def test_nothing_is_said_to_a_conversation_between_turns() -> None:
    """One written to between turns would be answered on its own, outside the flow."""
    app = Humanize()
    async with app.run_test() as driver:
        agent = SteerableAgent(CONFIG)
        app._agents = [agent]
        app._models = [Runs("claude/m:high")]
        session = agent.new()  # open, and no turn in it

        await driver.press(*"and this")
        await driver.press("enter")
        await driver.pause()

        assert app._reading() is session  # read, and still not said to
        assert session.put_in == []
        assert app._queued == ["and this"]  # held for whichever turn starts next


@pytest.mark.timeout(60)
async def test_reading_nothing_at_all_is_a_key_that_does_nothing() -> None:
    """With no flow running there is no conversation, and a key that says so is in the way."""
    app = Humanize()
    async with app.run_test() as driver:
        opened = _transcript(app)

        await driver.press("tab")
        await driver.press("shift+tab")
        await driver.pause()

        assert app._reading() is None
        assert app.is_running
        assert (
            _transcript(app) == opened
        )  # nothing was drawn again, there being nothing to


@pytest.mark.timeout(60)
async def test_a_conversation_that_goes_moves_what_is_being_read() -> None:
    """A Ralph loop drops one a turn, and the newest of that agent's is where to look next."""
    app = Humanize()
    async with app.run_test() as driver:
        agent = SteerableAgent(CONFIG)
        app._agents = [agent]
        first, second = agent.new(), agent.new()
        assert app._reading() is first

        app._heard(agent, first, Event(kind="text", text="before it went"))
        await driver.pause()
        del first
        gc.collect()  # which is what the flow letting go of one amounts to

        assert app._reading() is second
        assert "before it went" not in _transcript(
            app
        )  # the one it moved to, drawn afresh


@pytest.mark.timeout(60)
async def test_a_line_typed_with_nothing_running_still_starts_the_flow(
    workspace: Path,
) -> None:
    """Nothing is attached before a flow has opened anything, and that is how one starts."""
    app = Humanize()
    async with app.run_test() as driver:
        app._flow_named = "flow.py"
        app._models = [Runs("claude/m:high"), Runs("claude/m:high")]
        assert app._reading() is None

        await driver.press(*"do it")
        await driver.press("enter")
        await until(lambda: bool(app._agents), driver)

        assert app._agents  # the task started it rather than being put to nobody
        assert "do it" in _transcript(app)
        _let_go(workspace)
        await until(lambda: not app._agents, driver)


@pytest.mark.timeout(60)
async def test_the_line_above_the_prompt_says_which_one_and_how_many() -> None:
    """What is being read has to be visible, and so does what is not, and who is working."""
    app = Humanize()
    async with app.run_test() as driver:
        one, two = SteerableAgent(CONFIG), SteerableAgent(CONFIG)
        app._agents = [one, two]
        app._models = [Runs("claude/m:high"), Runs("codex/n:high")]
        first, second = one.new(), two.new()
        app._heard(one, first, Event(kind="begins", text=""))
        app._heard(two, second, Event(kind="begins", text=""))
        app._draw()
        await driver.pause()

        # The one being read says which of its agent's it is; both say they are working.
        above = _above(app)
        assert "● 1 of 1" in above
        assert above.count("●") == 2

        # Something said by the one not being read is something to be told about.
        app._heard(two, second, Event(kind="text", text="over here"))
        app._draw()
        await driver.pause()
        assert "unread" in _above(app)

        # And reading it is what makes it read.
        await driver.press("tab")
        await driver.pause()
        assert app._reading() is second
        assert "unread" not in _above(app)

        # An agent that has stopped says so, in the one mark on this line that moves itself.
        app._heard(one, first, Event(kind="ends", text=""))
        app._draw()
        await driver.pause()
        assert "○" in _above(app)


def test_an_agent_holding_nothing_says_nothing_about_it() -> None:
    """Which is every agent of a flow that is not running, and how that line always read."""
    runs = [Runs("claude/claude-opus-5:max")]

    assert reads(("builder",), runs) == ["builder · claude/claude-opus-5:max"]
    assert reads(("builder",), runs, [Held()]) == ["builder · claude/claude-opus-5:max"]
    # And a running one says whether it is working, which is the one thing on this line that
    # changes by itself: a filled circle for a turn open, a hollow one for an agent stopped.
    assert reads(("builder",), runs, [Held(many=5, at=1)]) == [
        "builder · claude/claude-opus-5:max · ○ 2 of 5"
    ]
    assert reads(("builder",), runs, [Held(many=5, at=1, working=True)]) == [
        "builder · claude/claude-opus-5:max · ● 2 of 5"
    ]
    assert reads(("builder",), runs, [Held(many=5, unread=True, working=True)]) == [
        "builder · claude/claude-opus-5:max · ● 5 · unread"
    ]


@pytest.mark.timeout(60)
async def test_a_question_the_agent_itself_put_reaches_the_person() -> None:
    """A codex or kimi server speaks for every conversation of its agent, so it says none.

    It goes on the transcript of whichever of that agent's conversations is working, which is
    somewhere it can be answered from -- and on the one being read where none of them is.
    """
    app = Humanize()
    async with app.run_test() as driver:
        one, two = SteerableAgent(CONFIG), SteerableAgent(CONFIG)
        app._agents = [one, two]
        app._models = [Runs("claude/m:high"), Runs("codex/n:high")]
        first, second = one.new(), two.new()
        # Both working, since those are the ones tab steps between.
        app._heard(one, first, Event(kind="begins", text=""))
        app._heard(two, second, Event(kind="begins", text=""))

        await driver.press("tab")  # reading the second agent's
        await driver.pause()
        assert app._reading() is second

        app._heard(one, None, Event(kind="asks", text="which way?"))
        app._draw()
        await driver.pause()
        # It is the first agent's conversation, which is not the one being read.
        assert "which way?" not in _transcript(app)
        assert "unread" in _above(app)

        await driver.press("shift+tab")
        await driver.pause()
        assert app._reading() is first
        assert "which way?" in _transcript(app)

        # And with none of that agent's working, it lands on whatever is being read.
        app._heard(two, second, Event(kind="ends", text=""))
        app._heard(two, None, Event(kind="asks", text="or this way?"))
        await driver.pause()

        assert app._reading() is first
        assert "or this way?" in _transcript(app)


@pytest.mark.timeout(60)
async def test_what_is_kept_is_held_to_the_last_few_conversations() -> None:
    """A flow runs for days and a Ralph loop opens one a turn, so it cannot be all of them."""
    app = Humanize()
    async with app.run_test() as driver:
        agent = SteerableAgent(CONFIG)
        app._agents = [agent]
        held = [agent.new() for _ in range(_KEPT + 4)]
        for at, session in enumerate(held):
            app._heard(agent, session, Event(kind="text", text=f"turn {at}"))
        await driver.pause()

        assert len([one for one in app._kept if one is not None]) == _KEPT
        # The newest are the ones there is still any reason to read, and the one being read
        # is never among what is dropped, however old it is.
        assert weakref.ref(held[-1]) in app._kept
        assert weakref.ref(held[1]) not in app._kept
        assert app._reading() is held[0]

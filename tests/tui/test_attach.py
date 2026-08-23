"""A transcript per agent, and one where all of them appear: what is read, and what is said to.

A flow drives several agents and each of them holds as many conversations as it likes. Every
agent's lines interleaved into one screen is none of them readable, and a screen wiped each
time a loop opened its next conversation is one nobody can read back through -- so an agent is
what is stepped onto and all of its conversations run down the one transcript, and the one this
opens on is the one where every agent's work appears together. Driven headlessly, so what is
checked is what a keystroke does rather than how it is drawn.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from typing import TYPE_CHECKING

import pytest
from textual.widgets import OptionList, Static

from hmz.agents import AgentConfig, Event
from hmz.kept import Runs
from hmz.tui import Humanize
from hmz.tui.app import _EVERY, _KEPT
from hmz.tui.monitor import short
from hmz.tui.pick import Held, reads
from hmz.tui.selecting import Transcript
from tests.stubs import ShellAgent, ShellSession, written

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
from hmz.flows import flow


@flow
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

    Waited on the clock rather than counted in pumps: a pump can pass in microseconds,
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
    written(tmp_path, "flow", HOLDING)
    monkeypatch.chdir(tmp_path)
    return tmp_path


async def _two_agents(app: Humanize, driver: Pilot[None], where: Path) -> None:
    """Starts the flow that holds a conversation open for each of two agents.

    Args:
      app: The interface.
      driver: What is pumping it.
      where: The workspace it is running in.
    """
    app._flow_named = "flow"
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
    """Lets a held flow finish, there being no turn in it for a key to reach.

    Args:
      where: The workspace it is running in.
    """
    (where / "go.txt").write_text("")


async def _both_working(
    app: Humanize, driver: Pilot[None]
) -> tuple[SteerableAgent, Steerable, SteerableAgent, Steerable]:
    """Two agents with a turn open apiece, which is what there is to step between.

    The conversations are handed back as well as the agents: an agent holds its own weakly,
    so one nothing here keeps is one the next collection takes away.

    Args:
      app: The interface.
      driver: What is pumping it.

    Returns:
      Each agent and the conversation it is working in, in the order the flow takes them.
    """
    one, two = SteerableAgent(CONFIG), SteerableAgent(CONFIG)
    app._agents = [one, two]
    app._models = [Runs("claude/m:high"), Runs("codex/n:high")]
    first, second = one.new(), two.new()
    app._heard(one, first, Event(kind="begins", text=""))
    app._heard(two, second, Event(kind="begins", text=""))
    await driver.pause()
    return one, first, two, second


@pytest.mark.timeout(60)
async def test_it_opens_on_the_transcript_every_agent_is_on(workspace: Path) -> None:
    """A flow is watched rather than an agent of it, so that is where a run starts."""
    app = Humanize()
    async with app.run_test() as driver:
        assert app._attached == _EVERY

        await _two_agents(app, driver, workspace)

        # Still, with two of them going: stepping onto one is asked for rather than done to
        # somebody the moment a flow opens its first conversation.
        assert app._attached == _EVERY
        assert app._reading() is None
        _let_go(workspace)
        await until(lambda: not app._agents, driver)


@pytest.mark.timeout(60)
async def test_tab_steps_round_the_agents_that_are_working(workspace: Path) -> None:
    """The ones thinking, and the transcript they are all on, which is the way back."""
    app = Humanize()
    async with app.run_test() as driver:
        await _two_agents(app, driver, workspace)
        first, second = (agent.id for agent in app._agents)

        await driver.press("tab")
        await driver.pause()
        assert app._attached == first

        await driver.press("tab")
        await driver.pause()
        assert app._attached == second

        await driver.press("tab")  # round the end, back to all of them
        await driver.pause()
        assert app._attached == _EVERY

        _let_go(workspace)
        await until(lambda: not app._agents, driver)


@pytest.mark.timeout(60)
async def test_shift_tab_steps_the_other_way_round(workspace: Path) -> None:
    """The other way round the same ring, which is what a pair of keys is for."""
    app = Humanize()
    async with app.run_test() as driver:
        await _two_agents(app, driver, workspace)
        first, second = (agent.id for agent in app._agents)

        await driver.press("shift+tab")  # backwards off all of them is the last of them
        await driver.pause()
        assert app._attached == second

        await driver.press("shift+tab")
        await driver.pause()
        assert app._attached == first

        _let_go(workspace)
        await until(lambda: not app._agents, driver)


@pytest.mark.timeout(60)
async def test_an_agent_that_is_not_working_is_not_stepped_onto() -> None:
    """With ten agents going, what somebody is stepping between is the ones thinking."""
    app = Humanize()
    async with app.run_test() as driver:
        one, _first, two, second = await _both_working(app, driver)
        app._heard(two, second, Event(kind="ends", text=""))
        await driver.pause()

        await driver.press("tab")
        await driver.pause()
        assert app._attached == one.id

        await driver.press("tab")  # past the one that stopped, back to all of them
        await driver.pause()
        assert app._attached == _EVERY


@pytest.mark.timeout(60)
async def test_each_agent_reads_as_itself_and_all_of_them_read_as_the_lot() -> None:
    """Two agents talking at once interleaved into one transcript is neither of them."""
    app = Humanize()
    async with app.run_test() as driver:
        one, first, two, second = await _both_working(app, driver)
        app._heard(one, first, Event(kind="text", text="from the first"))
        app._heard(two, second, Event(kind="text", text="from the second"))
        await driver.pause()

        # All of them, which is what it opened on: both, and which of them said each.
        shown = _transcript(app)
        assert "from the first" in shown
        assert "from the second" in shown

        await driver.press("tab")
        await driver.pause()

        # That agent's own, drawn from the top: what the other one said is not in it.
        shown = _transcript(app)
        assert "from the first" in shown
        assert "from the second" not in shown
        assert "reading" in shown

        await driver.press("tab")
        await driver.pause()
        shown = _transcript(app)
        assert "from the second" in shown
        assert "from the first" not in shown


@pytest.mark.timeout(60)
async def test_every_conversation_of_one_agent_runs_down_the_same_transcript() -> None:
    """A Ralph loop opens one a turn, and a screen wiped each turn is one nobody can read."""
    app = Humanize()
    async with app.run_test() as driver:
        agent = SteerableAgent(CONFIG)
        app._agents = [agent]
        app._models = [Runs("claude/m:high")]
        first = agent.new()
        app._heard(agent, first, Event(kind="begins", text=""))
        app._heard(agent, first, Event(kind="text", text="the first round"))
        app._heard(agent, first, Event(kind="ends", text=""))
        await driver.pause()

        await driver.press("tab")
        await driver.pause()
        assert (
            app._attached == _EVERY
        )  # nothing is working, so there is nowhere to step
        app._now_reading(agent.id)
        await driver.pause()

        second = agent.new()
        app._heard(agent, second, Event(kind="begins", text=""))
        app._heard(agent, second, Event(kind="text", text="the second round"))
        await driver.pause()

        # Both rounds, on the one screen, with nothing cleared between them.
        shown = _transcript(app)
        assert "the first round" in shown
        assert "the second round" in shown
        assert shown.index("the first round") < shown.index("the second round")
        # And each of them says which conversation it was, since there are two now.
        assert "conversation 2 of 2" in shown


@pytest.mark.timeout(60)
async def test_a_typed_line_goes_to_the_agent_being_read() -> None:
    """Which is the whole point: a flow drives several, and one of them is on the screen."""
    app = Humanize()
    async with app.run_test() as driver:
        _one, first, two, second = await _both_working(app, driver)

        await driver.press("tab")
        await driver.press("tab")
        await driver.pause()
        assert app._attached == two.id

        await driver.press(*"for the second")
        await driver.press("enter")
        await until(lambda: bool(second.put_in), driver)

        assert second.put_in == ["for the second"]
        assert first.put_in == []  # not the one that happened to be working as well
        assert app._given == [
            (two.id, "for the second")
        ]  # pinned against whoever has it


@pytest.mark.timeout(60)
async def test_a_word_put_into_a_turn_is_kept_against_the_agent_that_took_it() -> None:
    """It is part of that conversation, so it reads back as part of it wherever it was typed."""
    app = Humanize()
    async with app.run_test() as driver:
        _one, _first, two, second = await _both_working(app, driver)

        # Typed while all of them are on the screen, and taken by the second agent.
        await driver.press("tab")
        await driver.press("tab")
        await driver.pause()
        await driver.press(*"try the other way")
        await driver.press("enter")
        await until(lambda: bool(second.put_in), driver)
        app._heard(two, second, Event(kind="took", text="try the other way"))
        await driver.pause()

        assert "try the other way" in _transcript(app)
        # And on the one they all appear on, which is where the run is watched from.
        app._now_reading(_EVERY)
        await driver.pause()
        assert "try the other way" in _transcript(app)


@pytest.mark.timeout(60)
async def test_a_line_typed_with_every_agent_read_goes_to_whoever_is_working() -> None:
    """There is no one agent to have meant, so it is the one the screen is showing."""
    app = Humanize()
    async with app.run_test() as driver:
        _one, first, _two, _second = await _both_working(app, driver)

        await driver.press(*"anybody")
        await driver.press("enter")
        await until(lambda: bool(first.put_in), driver)

        assert first.put_in == ["anybody"]


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

        assert session.put_in == []
        assert app._queued == ["and this"]  # held for whichever turn starts next


@pytest.mark.timeout(60)
async def test_reading_nothing_at_all_is_a_key_that_does_nothing() -> None:
    """With no flow running there is nothing working, and a key that says so is in the way."""
    app = Humanize()
    async with app.run_test() as driver:
        opened = _transcript(app)

        await driver.press("tab")
        await driver.press("shift+tab")
        await driver.pause()

        assert app._attached == _EVERY
        assert app._reading() is None
        assert app.is_running
        assert (
            _transcript(app) == opened
        )  # nothing was drawn again, there being nothing to


@pytest.mark.timeout(60)
async def test_a_flow_starting_reads_the_transcript_they_are_all_on(
    workspace: Path,
) -> None:
    """What was being read belonged to a flow that has gone, and this is where a run starts."""
    app = Humanize()
    async with app.run_test() as driver:
        agent = SteerableAgent(CONFIG)
        app._agents = [agent]
        app._heard(agent, agent.new(), Event(kind="text", text="the run before"))
        app._now_reading(agent.id)
        await driver.pause()
        assert app._attached == agent.id
        app._agents = []

        await _two_agents(app, driver, workspace)

        assert app._attached == _EVERY
        assert "that flow has gone" in _transcript(app)
        _let_go(workspace)
        await until(lambda: not app._agents, driver)


@pytest.mark.timeout(60)
async def test_the_line_above_the_prompt_says_which_agent_and_how_many() -> None:
    """What is being read has to be visible, and so does what is not, and who is working."""
    app = Humanize()
    async with app.run_test() as driver:
        one, first, two, second = await _both_working(app, driver)
        app._draw()
        await driver.pause()

        # Both working, and neither being read: it opened on all of them.
        above = _above(app)
        assert above.count("●") == 2
        assert "reading" not in above

        # Nothing is unread while all of them are being read: it is on that screen too.
        app._heard(two, second, Event(kind="text", text="over here"))
        app._draw()
        await driver.pause()
        assert "unread" not in _above(app)

        # Read one of them, and what the other says is something to be told about.
        await driver.press("tab")
        await driver.pause()
        assert app._attached == one.id
        assert "reading" in _above(app)
        app._heard(two, second, Event(kind="text", text="and again"))
        app._draw()
        await driver.pause()
        assert "unread" in _above(app)

        # And reading it is what makes it read.
        await driver.press("tab")
        await driver.pause()
        assert app._attached == two.id
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
    assert reads(("builder",), runs, [Held(many=5)]) == [
        "builder · claude/claude-opus-5:max · ○ 5"
    ]
    assert reads(("builder",), runs, [Held(many=5, working=True)]) == [
        "builder · claude/claude-opus-5:max · ● 5"
    ]
    assert reads(("builder",), runs, [Held(many=5, reading=True, working=True)]) == [
        "builder · claude/claude-opus-5:max · ● 5 · reading"
    ]
    assert reads(("builder",), runs, [Held(many=5, unread=True, working=True)]) == [
        "builder · claude/claude-opus-5:max · ● 5 · unread"
    ]


@pytest.mark.timeout(60)
async def test_a_question_the_agent_itself_put_reaches_the_person() -> None:
    """A codex or kimi server speaks for every conversation of its agent, so it says none.

    It goes against the agent, all of whose conversations are the one transcript -- and onto
    the one they all appear on, which is where somebody watching the flow will come across it.
    """
    app = Humanize()
    async with app.run_test() as driver:
        one, _first, two, _second = await _both_working(app, driver)

        await driver.press("tab")
        await driver.press("tab")
        await driver.pause()
        assert app._attached == two.id

        app._heard(one, None, Event(kind="asks", text="which way?"))
        app._draw()
        await driver.pause()
        # It is the first agent's, which is not the one being read.
        assert "which way?" not in _transcript(app)
        assert "unread" in _above(app)

        await driver.press("shift+tab")
        await driver.pause()
        assert app._attached == one.id
        assert "which way?" in _transcript(app)


@pytest.mark.timeout(60)
async def test_the_diagram_reads_an_agent_that_is_not_working() -> None:
    """Stepping is held to the ones thinking, so this reaches the one that has stopped."""
    from hmz.tui.pick import Status

    app = Humanize()
    async with app.run_test() as driver:
        one, _first, two, second = await _both_working(app, driver)
        app._heard(two, second, Event(kind="text", text="then it stopped"))
        app._heard(two, second, Event(kind="ends", text=""))
        await driver.pause()
        assert app._working_agents() == [one.id]  # so tab cannot reach the second

        await driver.press("escape")
        await until(lambda: isinstance(app.screen, Status), driver)
        boxes = app.screen.query_one("#choices", OptionList)
        drawn = [
            str(boxes.get_option_at_index(at).id) for at in range(boxes.option_count)
        ]
        assert drawn == [_EVERY, one.id, two.id]

        # Clicked rather than walked to: a box is drawn where it is in order to be pointed at.
        # Row nought is the one they all appear on, and a box is four rows under the one above.
        await driver.click(boxes, offset=(4, 1 + 4 + 4))
        await until(lambda: app._attached == two.id, driver)

        assert "then it stopped" in _transcript(app)


@pytest.mark.timeout(60)
async def test_the_diagram_marks_who_is_working_and_who_handed_to_whom() -> None:
    """The shape of a run is not written anywhere: it is read off the turns going past."""
    from hmz.tui.pick import Status

    app = Humanize()
    async with app.run_test() as driver:
        one, two = SteerableAgent(CONFIG), SteerableAgent(CONFIG)
        app._agents = [one, two]
        app._models = [Runs("claude/m:high"), Runs("codex/n:high")]
        first, second = one.new(), two.new()
        # A turn, and then a turn of the other agent: which is a handover between them.
        app._heard(one, first, Event(kind="begins", text=""))
        app._heard(one, first, Event(kind="ends", text=""))
        app._heard(two, second, Event(kind="begins", text=""))
        await driver.pause()

        await driver.press("escape")
        await until(lambda: isinstance(app.screen, Status), driver)
        boxes = app.screen.query_one("#choices", OptionList)
        drawn = "\n".join(
            str(boxes.get_option_at_index(at).prompt)
            for at in range(boxes.option_count)
        )

        assert "┌" in drawn  # a box apiece
        assert "└" in drawn
        assert "↓ 1" in drawn  # the handover from the first to the second
        assert "1 of 2 working" in drawn
        assert "1 turn" in drawn


@pytest.mark.timeout(60)
async def test_a_cleared_screen_still_says_which_agent_a_line_is_from() -> None:
    """The name is said once as it changes, so a screen cleared under one has to forget it."""
    app = Humanize()
    async with app.run_test() as driver:
        one, first, _two, _second = await _both_working(app, driver)
        app._heard(one, first, Event(kind="text", text="before the clear"))
        await driver.pause()
        app.action_clear()
        await driver.pause()
        assert "before the clear" not in _transcript(app)

        app._heard(one, first, Event(kind="text", text="after the clear"))
        await driver.pause()

        shown = _transcript(app)
        assert "after the clear" in shown
        assert (
            short(one.id) in shown
        )  # said again, there being nothing above it that said it


@pytest.mark.timeout(60)
async def test_what_is_kept_is_held_to_the_last_few_agents() -> None:
    """A machine that has run twenty flows cannot keep every agent of all of them."""
    app = Humanize()
    async with app.run_test() as driver:
        agents = [SteerableAgent(CONFIG) for _ in range(_KEPT + 4)]
        app._agents = list(agents)
        for at, agent in enumerate(agents):
            app._heard(agent, agent.new(), Event(kind="text", text=f"agent {at}"))
        await driver.pause()

        assert len(app._kept) == _KEPT
        # The newest are the ones there is still any reason to read, and neither the one
        # being read nor the one they are all on is ever among what is dropped.
        assert _EVERY in app._kept
        assert agents[-1].id in app._kept
        assert agents[0].id not in app._kept

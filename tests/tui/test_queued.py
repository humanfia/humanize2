"""What was said to a running flow and has not been taken yet, and where it is shown.

Everything typed at a running flow joins one queue and leaves it one line at a time: a line
is a thing said, and two words handed to a backend together come back as one answer. Until a
line goes it is pinned above the prompt rather than written into the transcript -- it has not
been said to anybody yet. Which is what Claude Code does with a queued message, and for the
same reason: a transcript is what happened, and this has not happened yet.
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import TYPE_CHECKING

import pytest
from textual.widgets import Static

from hmz.agents import AgentBase, AgentConfig, Event
from hmz.tui import Humanize
from hmz.tui.app import _PINNED
from hmz.tui.monitor import short
from hmz.tui.pick import Runs
from hmz.tui.selecting import Transcript
from tests.stubs import ShellAgent, ShellSession

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from textual.pilot import Pilot

CONFIG = AgentConfig(model="m", effort="high")


class Steerable(ShellSession):
    """A session a word can be put into, which a shell-backed one has no process for."""

    def __init__(
        self, agent: AgentBase, cwd: str | os.PathLike[str] | None = None
    ) -> None:
        super().__init__(agent, cwd)
        self.put_in: list[str] = []

    def interject(self, text: str) -> None:
        """Takes the word and says nothing about it, as a backend takes one off us."""
        self.put_in.append(text)


class SteerableAgent(ShellAgent):
    """An agent whose sessions take a word put in rather than refusing it."""

    def new(self, cwd: str | os.PathLike[str] | None = None) -> Steerable:
        """Opens one."""
        return Steerable(self, cwd)


#: A flow that runs until a file appears, so that a line can be typed while it is up and the
#: flow can then be let finish of its own accord.
FLOW = """
import time
from pathlib import Path

from hmz.agents import AgentBase
from hmz.flows import flow


@flow
def run(agents: tuple[AgentBase], task: str) -> None:
    while not Path("go.txt").exists():
        time.sleep(0.02)
"""


async def until(ready: Callable[[], bool], driver: Pilot[None]) -> None:
    """Waits for the interface to catch up with what was asked of it."""
    deadline = time.monotonic() + 10.0
    while not ready() and time.monotonic() < deadline:
        await driver.pause()
        await asyncio.sleep(0.02)
    await driver.pause()


def _transcript(app: Humanize) -> str:
    """Everything the interface has shown, as one searchable string."""
    return app.query_one("#transcript", Transcript).text


def _pinned(app: Humanize) -> str:
    """What is pinned above the prompt, as it reads, or "" with the pin not showing at all."""
    said = app.query_one("#queued", Static)
    return str(said.content) if said.has_class("waiting") else ""


async def _running(app: Humanize, driver: Pilot[None]) -> None:
    """Puts the interface in the one state this is about: a flow up, and no turn open.

    Which is a flow between two turns, or one inside a sleep of its own -- the moment a line
    has nowhere to go but the queue.
    """
    app._flow_named, app._models = "flow.py", [Runs("claude/m:high")]
    app._agents = [ShellAgent(CONFIG)]
    app._queued = []
    await driver.pause()


@pytest.fixture
def waiting(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A flow that runs until it is let go, and a `claude` on PATH it never launches."""
    binaries = tmp_path / "bin"
    binaries.mkdir()
    fake = binaries / "claude"
    fake.write_text("#!/bin/sh\nexit 0\n")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{binaries}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    (tmp_path / "flow.py").write_text(FLOW)
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.mark.timeout(60)
async def test_a_line_with_nowhere_to_go_yet_is_pinned_rather_than_written_down() -> (
    None
):
    """It has not been said to anybody, and the transcript is what was said."""
    app = Humanize()
    async with app.run_test() as driver:
        await _running(app, driver)

        await driver.press(*"and fix the tests")
        await driver.press("enter")
        await until(lambda: bool(_pinned(app)), driver)

        assert "and fix the tests" in _pinned(app)
        assert "and fix the tests" not in _transcript(app)
        assert app._queued == ["and fix the tests"]


@pytest.mark.timeout(60)
async def test_it_goes_into_the_transcript_at_the_moment_it_is_taken() -> None:
    """In front of the turn that took it, which is where it belongs -- and off the pin."""
    app = Humanize()
    async with app.run_test() as driver:
        await _running(app, driver)
        await driver.press(*"and fix the tests")
        await driver.press("enter")
        await until(lambda: bool(_pinned(app)), driver)

        # Whichever turn starts next asks for it, which is what `waiting` is for.
        assert app._take() == ["and fix the tests"]
        await until(lambda: "and fix the tests" in _transcript(app), driver)

        assert _pinned(app) == ""
        assert "and fix the tests" in _transcript(app)


@pytest.mark.timeout(60)
async def test_a_line_into_a_turn_that_is_open_is_pinned_until_the_agent_has_it() -> (
    None
):
    """What the backend takes from us is not what the agent has heard.

    Every one of them answers a word put into a turn twice: once to say it has been taken
    from us, and again -- a whole answer or a tool call later -- to say it is in front of the
    model. Only the second is the agent having heard it, so only the second writes it down.
    """
    app = Humanize()
    async with app.run_test() as driver:
        await _running(app, driver)
        agent = SteerableAgent(CONFIG)
        app._agents = [agent]
        session = agent.new()
        # A turn is open on that conversation, so there is one to steer -- and the interface
        # reads the only conversation there is, which is where a typed line goes.
        app._heard(agent, session, Event(kind="begins", text=""))

        await driver.press(*"and this")
        await driver.press("enter")
        await until(lambda: bool(_pinned(app)), driver)

        # Handed over, and not said: it is pinned against the agent that has it.
        assert app._given == [(agent.id, "and this")]
        assert app._queued == []
        assert "and this" not in _transcript(app)
        assert f"with {short(agent.id)}" in _pinned(app)

        # And written down when that agent's own stream says the turn has taken it in.
        app._heard(agent, session, Event(kind="took", text="and this"))
        await until(lambda: "and this" in _transcript(app), driver)

        assert _pinned(app) == ""
        assert app._given == []
        del session


@pytest.mark.timeout(60)
async def test_a_turn_that_ended_without_saying_it_had_it_says_that_instead() -> None:
    """Neither waiting nor taken: it was put to an agent whose turn is over.

    Nothing may stay pinned against a turn that has ended -- the pin would be claiming a word
    is still on its way to something that is not running.
    """
    app = Humanize()
    async with app.run_test() as driver:
        await _running(app, driver)
        agent = SteerableAgent(CONFIG)
        app._agents = [agent]
        session = agent.new()
        app._heard(agent, session, Event(kind="begins", text=""))

        await driver.press(*"take this")
        await driver.press("enter")
        await until(lambda: bool(_pinned(app)), driver)

        app._heard(agent, session, Event(kind="ends", text=""))
        await until(lambda: "take this" in _transcript(app), driver)

        assert _pinned(app) == ""
        assert app._given == []
        assert "without saying it had it" in _transcript(app)
        del session


@pytest.mark.timeout(60)
async def test_a_word_the_backend_would_not_take_goes_back_in_the_queue() -> None:
    """A steer codex drops or kimi refuses never went, so it waits for the next turn instead.

    Back at the head of the queue, where it was: it was typed before everything still
    waiting, and a queue that went out of order would answer the second thing first.
    """
    app = Humanize()
    async with app.run_test() as driver:
        await _running(app, driver)
        agent = app._agents[0]
        with app._saying:
            app._given.append((agent.id, "never went"))
            app._queued.append("typed after it")

        app._unreached(agent.id, "never went", "no active turn to steer")
        await driver.pause()

        assert app._given == []
        # Still on its way, by the other road, and still in front of what followed it.
        assert app._queued == ["never went", "typed after it"]
        assert "never went" in _pinned(app)
        assert "no active turn to steer" in _transcript(app)


@pytest.mark.timeout(60)
async def test_a_word_put_to_one_agent_is_not_taken_off_by_another() -> None:
    """A flow drives several, and each answers only for what was put to it."""
    app = Humanize()
    async with app.run_test() as driver:
        await _running(app, driver)
        builder = app._agents[0]
        reviewer = ShellAgent(CONFIG)
        app._agents.append(reviewer)

        with app._saying:
            app._given.append((builder.id, "for the builder"))
        app._heard(reviewer, reviewer.new(), Event(kind="took", text="for the builder"))
        await driver.pause()

        assert app._given == [(builder.id, "for the builder")]
        assert "for the builder" not in _transcript(app)


@pytest.mark.timeout(60)
async def test_more_than_a_few_are_counted_rather_than_all_pinned() -> None:
    """A pin that grew without limit would push the transcript off the screen to say so."""
    app = Humanize()
    async with app.run_test() as driver:
        await _running(app, driver)

        for at in range(_PINNED + 3):
            await driver.press(*f"line {at}")
            await driver.press("enter")
        await until(lambda: "more waiting" in _pinned(app), driver)

        shown = _pinned(app)
        assert "line 0" in shown  # oldest first, since that is the order they go in
        assert len(shown.splitlines()) <= _PINNED + 1
        assert "3 more waiting" in shown
        assert len(app._queued) == _PINNED + 3  # counted, not dropped


@pytest.mark.timeout(60)
async def test_a_line_of_several_is_pinned_as_it_was_typed() -> None:
    """As the transcript sets one: the first behind the marker, the rest lined up under it."""
    app = Humanize()
    async with app.run_test() as driver:
        await _running(app, driver)

        await driver.press(*"first")
        await driver.press("ctrl+j")
        await driver.press(*"second")
        await driver.press("enter")
        await until(lambda: bool(_pinned(app)), driver)

        first, second = _pinned(app).splitlines()
        assert first.strip().startswith("❯")
        assert first.strip().endswith("first")
        assert second.strip() == "second"


@pytest.mark.timeout(60)
async def test_what_the_stopped_flow_never_took_is_said_to_have_been_dropped() -> None:
    """A line pinned against a flow that has gone would read as one still on its way."""
    app = Humanize()
    async with app.run_test() as driver:
        await _running(app, driver)
        await driver.press(*"too late")
        await driver.press("enter")
        await until(lambda: bool(_pinned(app)), driver)

        app.action_stop_flow()
        await driver.pause()

        assert _pinned(app) == ""
        assert app._queued == []
        assert "too late" in _transcript(app)
        assert "never sent" in _transcript(app)


@pytest.mark.timeout(60)
async def test_nothing_is_pinned_with_no_flow_running() -> None:
    """The first thing said to a flow that is not running is the task, and it starts it."""
    app = Humanize()
    async with app.run_test() as driver:
        await driver.press(*"the task")
        await driver.press("enter")
        await driver.pause()

        assert _pinned(app) == ""


@pytest.mark.timeout(60)
async def test_one_that_will_not_fit_whole_is_counted_rather_than_shown_in_half() -> (
    None
):
    """A message cut across the middle reads as a message that says something it does not."""
    app = Humanize()
    async with app.run_test() as driver:
        await _running(app, driver)

        await driver.press(*"short")
        await driver.press("enter")
        for _ in range(_PINNED):  # a long one, which cannot follow it whole
            await driver.press(*"long")
            await driver.press("ctrl+j")
        await driver.press(*"end")
        await driver.press("enter")
        await until(lambda: "more waiting" in _pinned(app), driver)

        shown = _pinned(app)
        assert "short" in shown
        assert "long" not in shown  # not the half of it that would have fitted
        assert "1 more waiting" in shown


@pytest.mark.timeout(60)
@pytest.mark.parametrize(
    "typed", ["try [red]this", "fix the [TODO] item", "[$text-muted] and [ ]"]
)
async def test_what_was_typed_is_pinned_as_text_rather_than_as_markup(
    typed: str,
) -> None:
    """A bracket somebody typed is a bracket, whatever it happens to look like.

    Neither escaper is safe here: each only escapes a bracket that already looks like a tag
    to it, and Rich and Textual disagree about which do -- `[TODO]` is a word to one and a
    tag to the other. So the pin is drawn as content rather than as markup, and there is
    nothing to escape.
    """
    app = Humanize()
    async with app.run_test() as driver:
        await _running(app, driver)

        await driver.press(*typed)
        await driver.press("enter")
        await until(lambda: bool(_pinned(app)), driver)

        assert typed in _pinned(app)


@pytest.mark.timeout(60)
async def test_clearing_the_screen_leaves_what_is_waiting_where_it_is() -> None:
    """`/clear` clears the transcript, and what is waiting has not reached it yet."""
    app = Humanize()
    async with app.run_test() as driver:
        await _running(app, driver)
        await driver.press(*"still coming")
        await driver.press("enter")
        await until(lambda: bool(_pinned(app)), driver)

        await driver.press(*"/clear")
        await driver.press("enter")
        await driver.pause()

        assert "still coming" in _pinned(app)
        assert app._queued == ["still coming"]


@pytest.mark.timeout(90)
async def test_what_a_flow_that_ended_never_took_is_said_to_have_been_dropped(
    waiting: Path,
) -> None:
    """A flow ends two ways, and both leave the pin holding a line on its way nowhere.

    Stopped by hand is the other test; this is the one that ends of its own accord, which is
    how every flow that finishes ends -- and the one where the next thing typed would
    otherwise quietly take the stranded line's place.
    """
    app = Humanize()
    async with app.run_test() as driver:
        app._flow_named, app._models = "flow.py", [Runs("claude/m:high")]
        await driver.press(*"the task")
        await driver.press("enter")
        await until(lambda: bool(app._agents), driver)

        await driver.press(*"and this too")
        await driver.press("enter")
        await until(lambda: bool(_pinned(app)), driver)

        (waiting / "go.txt").write_text("")  # and the flow runs out of things to do
        await until(lambda: not app._agents, driver)
        await until(lambda: "never sent" in _transcript(app), driver)

        assert _pinned(app) == ""
        assert app._queued == []
        assert "and this too" in _transcript(app)
        assert "the flow ended first" in _transcript(app)


@pytest.mark.timeout(60)
async def test_a_pasted_paragraph_is_one_row_rather_than_twenty() -> None:
    """A pin capped in lines and not in rows would push the editor off the bottom."""
    app = Humanize()
    async with app.run_test(size=(80, 24)) as driver:
        await _running(app, driver)

        app._interject("please " * 200)  # one line, and far more than one row of it
        await until(lambda: bool(_pinned(app)), driver)

        assert len(_pinned(app).splitlines()) == 1
        assert app.query_one("#queued", Static).size.height == 1
        assert _pinned(app).endswith("…")
        # And the whole of it still goes: what was cut is what is drawn, not what is held.
        assert app._queued == ["please " * 200]


@pytest.mark.timeout(60)
async def test_the_pin_never_takes_more_than_its_share_of_the_screen() -> None:
    """Five long pastes are five rows, and the editor and the status line stay where they are."""
    app = Humanize()
    async with app.run_test(size=(80, 24)) as driver:
        await _running(app, driver)

        for at in range(_PINNED + 2):
            app._interject(f"{at} " + "x" * 900)
        await until(lambda: "more waiting" in _pinned(app), driver)

        assert app.query_one("#queued", Static).size.height <= _PINNED + 1
        # The status line is still on the screen, which is what the cap is for.
        assert app.query_one("#status", Static).region.y < 24


@pytest.mark.timeout(60)
async def test_a_message_too_long_to_show_whole_says_how_much_was_cut() -> None:
    """Half a message must never read as the whole of one -- not even the first."""
    app = Humanize()
    async with app.run_test() as driver:
        await _running(app, driver)

        app._interject("\n".join(f"line {at}" for at in range(10)))
        await until(lambda: bool(_pinned(app)), driver)

        shown = _pinned(app)
        assert "line 0" in shown
        assert len(shown.splitlines()) == _PINNED
        assert "6 more lines" in shown  # ten of them, four shown


@pytest.mark.timeout(60)
async def test_what_is_cut_off_counts_the_lines_and_the_messages_apart() -> None:
    """One number for what is left of this message, another for the messages after it."""
    app = Humanize()
    async with app.run_test() as driver:
        await _running(app, driver)

        app._interject("\n".join(f"line {at}" for at in range(10)))
        app._interject("and another")
        await until(lambda: bool(_pinned(app)), driver)

        shown = _pinned(app)
        assert "6 more lines" in shown
        assert "1 more waiting" in shown


@pytest.mark.timeout(60)
async def test_it_reaches_the_transcript_from_the_thread_a_turn_runs_on() -> None:
    """Which is the path every real run takes, and the one `call_from_thread` is there for."""
    import threading

    app = Humanize()
    async with app.run_test() as driver:
        await _running(app, driver)
        await driver.press(*"from a turn")
        await driver.press("enter")
        await until(lambda: bool(_pinned(app)), driver)

        # As a turn asks for it: off the event loop, which is the branch the tests that
        # call `_take` directly never reach.
        took: list[list[str]] = []
        asking = threading.Thread(target=lambda: took.append(app._take()))
        asking.start()
        await until(lambda: "from a turn" in _transcript(app), driver)
        asking.join(5)

        assert took == [["from a turn"]]
        assert _pinned(app) == ""
        assert "from a turn" in _transcript(app)


@pytest.mark.timeout(60)
async def test_lines_typed_in_a_row_go_into_the_turn_one_at_a_time() -> None:
    """Two words handed over in the same swallow come back as one answer, not two.

    Which is the whole of the bug this is here for: five `hi` in a row, one reply. A backend
    given a second word while it is still taking in the first runs the two together, so the
    next one goes only once the turn has said it has this one.
    """
    app = Humanize()
    async with app.run_test() as driver:
        await _running(app, driver)
        agent = SteerableAgent(CONFIG)
        app._agents = [agent]
        session = agent.new()
        app._heard(agent, session, Event(kind="begins", text=""))

        for said in ("hi", "hi again", "hi once more"):
            app._interject(said)
        await until(lambda: bool(session.put_in), driver)

        # One has gone; the two behind it wait, in the order they were typed.
        assert session.put_in == ["hi"]
        assert app._given == [(agent.id, "hi")]
        assert app._queued == ["hi again", "hi once more"]

        app._heard(agent, session, Event(kind="took", text="hi"))
        await until(lambda: len(session.put_in) > 1, driver)

        assert session.put_in == ["hi", "hi again"]
        assert app._given == [(agent.id, "hi again")]
        assert app._queued == ["hi once more"]


@pytest.mark.timeout(60)
async def test_a_turn_takes_one_waiting_line_and_leaves_the_rest() -> None:
    """Three lines typed between turns are three things said, not one prompt of three.

    Folding them all into the next turn is the same bug by the other road: the agent is told
    everything at once and answers it once.
    """
    app = Humanize()
    async with app.run_test() as driver:
        await _running(app, driver)

        for said in ("hi", "hi again", "hi once more"):
            app._interject(said)
        await until(lambda: bool(_pinned(app)), driver)

        assert app._take() == ["hi"]
        assert app._queued == ["hi again", "hi once more"]
        assert app._take() == ["hi again"]
        assert app._take() == ["hi once more"]
        assert app._take() == []


@pytest.mark.timeout(60)
async def test_what_went_to_an_agent_is_pinned_in_front_of_what_is_still_queued() -> (
    None
):
    """The pin reads oldest first, as the transcript does -- and what went, went first."""
    app = Humanize()
    async with app.run_test() as driver:
        await _running(app, driver)
        agent = SteerableAgent(CONFIG)
        app._agents = [agent]
        session = agent.new()
        app._heard(agent, session, Event(kind="begins", text=""))

        app._interject("gone to it")
        app._interject("behind that")
        await until(lambda: len(_pinned(app).splitlines()) > 1, driver)

        first, second = _pinned(app).splitlines()
        assert "gone to it" in first
        assert f"with {short(agent.id)}" in first  # since that is the one it is holding
        assert "behind that" in second
        del session


@pytest.mark.timeout(60)
async def test_a_turn_started_on_a_line_does_not_swallow_the_one_behind_it() -> None:
    """The other half of the same bug: chat asks the person, and the turn takes one more.

    A flow with a person in it starts each turn on what they said, and a turn also folds in
    whatever was waiting when it started. Both draining for the same burst would put two
    lines in front of the agent at once and have them answered together.
    """
    app = Humanize()
    async with app.run_test() as driver:
        await _running(app, driver)

        for said in ("hi", "hi again"):
            app._interject(said)
        await until(lambda: bool(_pinned(app)), driver)

        # As chat does it: ask the person, then run a turn on what they answered.
        answered = app._take()
        with app._saying:
            app._handed = True

        assert answered == ["hi"]
        assert (
            app._at_turn_start() == []
        )  # this turn's line is the one it was started on
        assert app._queued == ["hi again"]  # and the next one is the next turn's
        assert app._at_turn_start() == ["hi again"]


@pytest.mark.timeout(60)
async def test_three_lines_typed_in_a_row_are_three_turns_of_a_chat() -> None:
    """The bug as it was reported: a handful of `hi` in a row, and one answer back.

    Driven the way the chat flow drives it, from a thread of its own -- a turn, then asking
    the person what to say next -- since it is the two hooks together that got this wrong.
    """
    import threading

    app = Humanize()
    async with app.run_test() as driver:
        await _running(app, driver)
        agent = app._agents[0]
        prompts: list[str] = []

        def chatting() -> None:
            said: str | None = "the task"
            while said:
                # What a session does on the way in, then what the flow does after.
                prompts.append("\n\n".join([said, *app._at_turn_start()]))
                said = app._listen(agent)

        talking = threading.Thread(target=chatting)
        talking.start()
        try:
            for at in range(3):
                await driver.press(*f"hi {at}")
                await driver.press("enter")
            await until(lambda: len(prompts) == 4, driver)
        finally:
            app._agents = []  # which is what stopping the flow leaves behind
            app._spoke.set()
            talking.join(5)

        assert prompts == ["the task", "hi 0", "hi 1", "hi 2"]


@pytest.mark.timeout(60)
async def test_the_pin_sits_on_the_editor_beside_what_the_run_is_running_as() -> None:
    """One block above the prompt rather than two, read from the bottom up.

    The last line typed and the running total are two halves of where the run has got to,
    and the pin standing above them in a column of its own reads as two things.
    """
    app = Humanize()
    async with app.run_test(size=(80, 24)) as driver:
        await _running(app, driver)
        app._monitor.spend(app._agents[0].id, 12345, model="m")
        app._interject("hi")
        app._interject("hi again")
        await until(lambda: bool(_pinned(app)), driver)

        pin = app.query_one("#queued", Static).region
        beside = app.query_one("#above", Static).region
        rule = app.query_one("#rule-above", Static).region

        assert pin.bottom == beside.bottom  # the last line typed, and the running total
        assert pin.bottom == rule.y  # with nothing between the block and the editor
        assert pin.right <= beside.x  # side by side, rather than one above the other
        assert "12.3k tokens" in str(app.query_one("#above", Static).content)


@pytest.mark.timeout(60)
async def test_a_pinned_line_is_cut_to_what_is_left_beside_it() -> None:
    """The block to the right of it is not the pin's to draw in."""
    app = Humanize()
    async with app.run_test(size=(80, 24)) as driver:
        await _running(app, driver)

        app._interject("x" * 200)
        await until(lambda: bool(_pinned(app)), driver)

        pin = app.query_one("#queued", Static).region
        beside = app.query_one("#above", Static).region
        assert _pinned(app).endswith("…")
        assert pin.right <= beside.x  # cut short of it rather than over it
        assert beside.width >= len(
            "assistant · claude/m:high"
        )  # which still fits whole

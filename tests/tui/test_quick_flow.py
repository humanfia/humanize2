"""`$flow <prompt>`: the flow said outright, rather than chosen from a menu and then talked to.

Two lines of setup are the whole of what somebody does before a run -- choose a flow, say what
to do -- and one of them is the same answer every morning. So `$rlar fix the build` is both at
once: that flow, on that line. A flow this workspace has already set up runs on the spot; one
it has not opens the menu on it and runs when the menu is saved. What is checked here is which
of those a line gets, and that a line that merely begins with a `$` is still a line.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pytest
from textual.widgets import OptionList

from hmz.coganchor.agents import AgentConfig, Question
from hmz.coganchor.backends import Model
from hmz.runtime.kept import Runs
from hmz.runtime.settings import Settings
from hmz.tui import Humanize
from hmz.tui.app import _COMMANDS, Editor
from hmz.tui.complete import offered
from hmz.tui.pick import Flows
from hmz.tui.selecting import Transcript
from tests.stubs import ShellAgent, written

from .test_app import opens, until

if TYPE_CHECKING:
    from pathlib import Path

    from textual.pilot import Pilot

#: A backend to be set up as, so that the menu has something to fall back on for a place
#: nothing was remembered for and can therefore be saved.
_INSTALLED = {"claude": (Model("m", ("high",)),)}

#: A flow of one agent, for the workspace that has set none of them up yet.
_ONE = """
from hmz.flows import Agent, flow


@flow
def run(agents: tuple[Agent], task: str) -> None:
    agents[0].new()(task)
"""

#: A flow of two agents, for what happens to a workspace set up for one of them and then
#: handed a flow that wants both.
_PAIR = """
from typing import NamedTuple

from hmz.flows import Agent, flow


class Pair(NamedTuple):
    builder: Agent
    reviewer: Agent


@flow
def run(agents: Pair, task: str) -> None:
    agents.builder.new()(task)
"""

#: A file holding a flow of its own name and another beside it whose name has a dash in it --
#: which `humanize1:gen-idea` is, and which a sigil that stopped reading at the dash would put
#: to the conversation whole instead of running.
_PHASES = """
from hmz.flows import Agent, flow


@flow
def run(agents: tuple[Agent], task: str) -> None:
    agents[0].new()(task)


@flow(name="gen-idea")
def idea(agents: tuple[Agent], task: str) -> None:
    agents[0].new()(task)
"""


@pytest.fixture
def backend(monkeypatch: pytest.MonkeyPatch) -> None:
    """Puts one backend where the interface and its sheets look for them."""
    import hmz.tui.app
    import hmz.tui.pick

    monkeypatch.setattr(hmz.tui.app, "installed", lambda: dict(_INSTALLED))
    monkeypatch.setattr(hmz.tui.pick, "installed", lambda: dict(_INSTALLED))


@pytest.fixture
def started(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """Catches the command line each run would have been started on, and starts none.

    A run is a backend, a thread and a process; what these are about is which flow got
    started and on what, which is the line `hmz exec` would have been handed.
    """
    lines: list[list[str]] = []

    def caught(_self: Humanize, argv: list[str], resume: object = None) -> None:
        """What starting a flow comes to here, which is writing down the line."""
        lines.append(argv)

    monkeypatch.setattr(Humanize, "_flow", caught)
    return lines


def _transcript(app: Humanize) -> str:
    """Everything the interface has shown, as one searchable string."""
    return app.query_one("#transcript", Transcript).text


async def sends(app: Humanize, driver: Pilot[None], line: str) -> None:
    """Types a line and sends it, putting away any offers that are up first.

    Enter over an open list takes what is under the cursor, and a `$` opens one -- which is
    the point of it. Esc puts the list away, which is what somebody who meant the name they
    typed presses. Only then: esc with nothing offered is how `/status` is opened.

    Args:
      app: The interface.
      driver: What is pumping it.
      line: What to type.
    """
    await driver.press(*line)
    if app.query_one("#offers", OptionList).has_class("offering"):
        await driver.press("escape")
    await driver.press("enter")
    await driver.pause()


async def saves(app: Humanize, driver: Pilot[None]) -> None:
    """Saves the flow menu from the row that says so, which is the last of its agents'.

    A menu opened on a flow that was named opens inside it, there being nothing left to
    choose, so the row is already there to walk to.

    Args:
      app: The interface.
      driver: What is pumping it.
    """
    sheet = cast("Flows", app.screen)
    await until(lambda: sheet._inside, driver)
    await opens(app, driver, "save")
    await until(lambda: not isinstance(app.screen, Flows), driver)


@pytest.mark.timeout(60)
async def test_a_flow_this_workspace_has_set_up_runs_on_the_line_that_named_it(
    tmp_path: Path, started: list[list[str]]
) -> None:
    """The whole point: two answers already given are not two answers to give again."""
    Settings(tmp_path).remember("chat", ("assistant",), [Runs("claude/m:high")])
    app = Humanize()
    async with app.run_test() as driver:
        await sends(app, driver, "$chat fix the build")
        await until(lambda: bool(started), driver)

        assert started == [["-f", "chat", "-a", "claude/m:high", "fix the build"]]
        assert not isinstance(app.screen, Flows)  # no menu at all
        assert "$chat fix the build" in _transcript(app)


@pytest.mark.timeout(90)
async def test_a_flow_never_set_up_here_opens_the_menu_and_runs_once_it_is_saved(
    tmp_path: Path, backend: None, started: list[list[str]]
) -> None:
    """A flow with no agents chosen for it is a flow that stops on its first turn."""
    written(tmp_path / ".humanize" / "flows", "loop", _ONE)
    app = Humanize()
    async with app.run_test() as driver:
        await sends(app, driver, "$local/loop fix the build")
        await until(lambda: isinstance(app.screen, Flows), driver)
        assert (
            cast("Flows", app.screen)._flow == "local/loop"
        )  # opened on the one named
        assert not started  # nothing runs while the menu is up

        await saves(app, driver)
        await until(lambda: bool(started), driver)

        assert started == [["-f", "local/loop", "-a", "claude/m:high", "fix the build"]]
        assert Settings(tmp_path).flow == "local/loop"  # and it is set up now

    # And so the same line a second time is the run, with no menu in the way.
    started.clear()
    again = Humanize()
    async with again.run_test() as driver:
        await sends(again, driver, "$local/loop fix the build")
        await until(lambda: bool(started), driver)

        assert not isinstance(again.screen, Flows)
        assert started == [["-f", "local/loop", "-a", "claude/m:high", "fix the build"]]


@pytest.mark.timeout(60)
async def test_a_flow_that_grew_an_agent_is_asked_about_rather_than_run_short_of_one(
    tmp_path: Path, backend: None, started: list[list[str]]
) -> None:
    """What was remembered is one agent, and the flow drives two: a place with nobody in it.

    Written down under what the flow calls each place, so the reviewer it grew is a name with
    nothing against it rather than the builder's model quietly moved along one.
    """
    written(tmp_path / ".humanize" / "flows", "pair", _PAIR)
    Settings(tmp_path).remember("local/pair", ("builder",), [Runs("claude/m:high")])
    app = Humanize()
    async with app.run_test() as driver:
        await sends(app, driver, "$local/pair fix the build")
        await until(lambda: isinstance(app.screen, Flows), driver)

        assert not started


@pytest.mark.timeout(60)
async def test_settings_the_flow_no_longer_accepts_are_asked_again_rather_than_dropped(
    tmp_path: Path, backend: None, started: list[list[str]]
) -> None:
    """A flow that renamed a setting under what was written down for it is one to answer."""
    Settings(tmp_path).remember(
        "ralph_loop", ("",), [Runs("claude/m:high")], {"nothing-of-the-sort": 1}
    )
    app = Humanize()
    async with app.run_test() as driver:
        await sends(app, driver, "$ralph_loop fix the build")
        await until(lambda: isinstance(app.screen, Flows), driver)

        assert not started


@pytest.mark.timeout(60)
async def test_walking_out_of_the_menu_starts_nothing_and_says_so(
    tmp_path: Path, backend: None, started: list[list[str]]
) -> None:
    """A line typed to start something must not vanish without a word about it."""
    written(tmp_path / ".humanize" / "flows", "loop", _ONE)
    app = Humanize()
    async with app.run_test() as driver:
        await sends(app, driver, "$local/loop fix the build")
        await until(lambda: isinstance(app.screen, Flows), driver)
        await driver.press("escape")  # out again, having answered nothing
        await until(lambda: not isinstance(app.screen, Flows), driver)
        await until(lambda: "nothing was set up" in _transcript(app), driver)

        assert not started


@pytest.mark.timeout(60)
async def test_a_flow_that_is_not_there_is_a_line_to_correct_and_not_the_end(
    started: list[list[str]],
) -> None:
    """Said the way `/nosuchcommand` is: the sigil was meant, the name after it is the typo."""
    app = Humanize()
    async with app.run_test() as driver:
        await sends(app, driver, "$nosuchflow fix the build")
        await until(lambda: "no such flow" in _transcript(app), driver)

        assert app.is_running  # still there to be typed at
        assert not started


@pytest.mark.timeout(60)
@pytest.mark.parametrize(
    "line",
    [
        "$",  # a sigil naming nothing, which is a shell prompt somebody pasted
        "$ ls -la",
        "$5 says it is the parser",
        "$(pwd) is where it looked",
    ],
)
async def test_a_line_that_merely_begins_with_a_dollar_is_still_a_line(
    line: str, started: list[list[str]]
) -> None:
    """`$` is a sigil on a name, so a `$` with no name after it is eaten by nothing."""
    app = Humanize()
    async with app.run_test() as driver:
        await sends(app, driver, line)
        await until(lambda: "no coding agent" in _transcript(app), driver)

        # It reached the conversation -- which here has nothing to run on and says so -- and
        # was never taken for a flow that is not there.
        assert "no such flow" not in _transcript(app)
        assert line in _transcript(app)
        assert not started


@pytest.mark.timeout(60)
async def test_a_prompt_written_under_the_name_is_the_prompt(
    tmp_path: Path, started: list[list[str]]
) -> None:
    """A long prompt is broken over several lines, and the `$` is still on the first of them."""
    Settings(tmp_path).remember("chat", ("assistant",), [Runs("claude/m:high")])
    app = Humanize()
    async with app.run_test() as driver:
        await driver.press(*"$chat")
        await driver.press("ctrl+j")  # the break every terminal there is can send
        await driver.press(*"fix the build")
        await driver.press("enter")
        await until(lambda: bool(started), driver)

        assert started == [["-f", "chat", "-a", "claude/m:high", "fix the build"]]


@pytest.mark.timeout(60)
async def test_one_of_the_several_flows_a_file_holds_is_named_dash_and_all(
    tmp_path: Path, started: list[list[str]]
) -> None:
    """`<file>:<inside>` is a name like any other, and what is inside may be called anything."""
    written(tmp_path / ".humanize" / "flows", "phases", _PHASES)
    Settings(tmp_path).remember("local/phases:gen-idea", ("",), [Runs("claude/m:high")])
    app = Humanize()
    async with app.run_test() as driver:
        await sends(app, driver, "$local/phases:gen-idea fix the build")
        await until(lambda: bool(started), driver)

        assert started == [
            ["-f", "local/phases:gen-idea", "-a", "claude/m:high", "fix the build"]
        ]


@pytest.mark.timeout(60)
async def test_nothing_is_offered_against_a_dollar_while_an_agent_waits_to_be_answered(
    tmp_path: Path,
) -> None:
    """The next line typed is the answer, whatever it begins with, so enter must send it."""
    Settings(tmp_path).remember("chat", ("assistant",), [Runs("claude/m:high")])
    app = Humanize()
    async with app.run_test() as driver:
        app._asking = Question("which way?")
        await driver.press(*"$cha")
        await driver.pause()

        assert not app.query_one("#offers", OptionList).has_class("offering")

        await driver.press("enter")
        await until(lambda: app._answer == "$cha", driver)  # answered, not completed


@pytest.mark.timeout(60)
async def test_a_dollar_while_a_flow_runs_is_refused_the_way_choosing_one_is(
    tmp_path: Path, started: list[list[str]]
) -> None:
    """Choosing a flow is shut while one runs, and this is choosing a flow."""
    Settings(tmp_path).remember("chat", ("assistant",), [Runs("claude/m:high")])
    app = Humanize()
    async with app.run_test() as driver:
        app._agents = [ShellAgent(AgentConfig(model="m", effort="high"))]
        await sends(app, driver, "$chat fix the build")
        await until(lambda: "a flow is running" in _transcript(app), driver)

        assert app._agents  # left exactly as it was
        assert not started


@pytest.mark.timeout(60)
async def test_a_dollar_naming_a_flow_and_nothing_else_chooses_it_and_waits(
    tmp_path: Path, started: list[list[str]]
) -> None:
    """With nothing said after the name there is nothing to start on, so nothing starts."""
    kept = Settings(tmp_path)
    kept.remember("chat", ("assistant",), [Runs("claude/m:high")])
    kept.remember("ralph_loop", ("",), [Runs("claude/m:high")])
    app = Humanize()
    assert app._flow_named == "ralph_loop"  # the one this workspace was last run with
    async with app.run_test() as driver:
        await sends(app, driver, "$chat")
        await until(lambda: app._flow_named == "chat", driver)

        assert not started
        assert "say what to do" in _transcript(app)


def test_the_flows_there_are_are_offered_under_the_sigil_that_starts_one() -> None:
    """The same list `/flow ` offers, since it is the same question asked in one word."""
    from hmz.flows import found

    every = [f"${one.name}" for one in found()]
    assert offered("$", _COMMANDS) == every
    assert offered("$cha", _COMMANDS) == [
        one for one in every if one.startswith("$cha")
    ]
    assert (
        offered("$chat", _COMMANDS) == []
    )  # written out already, so enter sends the line
    assert offered("$chat fix the", _COMMANDS) == []  # the prompt, which is prose


@pytest.mark.timeout(60)
async def test_tab_takes_the_flow_that_is_offered_under_the_sigil() -> None:
    """Nothing is chosen from a dialog, so the name is finished where it is typed."""
    app = Humanize()
    async with app.run_test() as driver:
        await driver.press(*"$cha")
        await until(lambda: bool(app.query_one("#offers", OptionList).options), driver)
        assert "$chat" in [
            str(one.id) for one in app.query_one("#offers", OptionList).options
        ]

        await driver.press("tab")
        await driver.pause()

        assert app.query_one(Editor).text == "$chat "

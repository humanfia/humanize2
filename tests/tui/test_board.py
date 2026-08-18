"""`/status`: the agents that have worked, the fleets under them, and the board.

Three things that all belong on the one sheet, because all three are what the run *is doing*.
An agent the flow declared and never reached is not; a subagent one of them started is; and so
is what there is left to do, which is the board -- the lines the person and the flow both
write on and neither waits at.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from textual.widgets import Label, OptionList

from hmz.agents import AgentConfig, Board, Event, HumanAgent, Refused
from hmz.kept import Runs
from hmz.tui import Humanize
from hmz.tui.pick import EVERY, Entry, Status

from .test_app import until
from .test_attach import SteerableAgent

if TYPE_CHECKING:
    from textual.pilot import Pilot

    from hmz.agents import AgentBase

CONFIG = AgentConfig(model="m", effort="high")


def _drawn(app: Humanize) -> str:
    """Everything the sheet has put up, as one block to read."""
    boxes = app.screen.query_one("#choices", OptionList)
    return "\n".join(
        str(boxes.get_option_at_index(at).prompt) for at in range(boxes.option_count)
    )


def _ids(app: Humanize) -> list[str]:
    """The id of every row on the sheet, in the order they are drawn."""
    boxes = app.screen.query_one("#choices", OptionList)
    return [str(boxes.get_option_at_index(at).id) for at in range(boxes.option_count)]


async def _opens(app: Humanize, driver: Pilot[None]) -> None:
    """Opens `/status` and waits for it to be up."""
    app.action_status()
    await until(lambda: isinstance(app.screen, Status), driver)


def _two(app: Humanize) -> tuple[AgentBase, AgentBase]:
    """Two agents of a flow, neither of which has taken a turn yet."""
    one, two = SteerableAgent(CONFIG), SteerableAgent(CONFIG)
    app._agents = [one, two]
    app._models = [Runs("claude/m:high"), Runs("codex/n:high")]
    return one, two


@pytest.mark.timeout(60)
async def test_an_agent_that_has_not_worked_is_not_drawn_yet() -> None:
    """The diagram is what the run is doing, and a flow may never take the other branch."""
    app = Humanize()
    async with app.run_test() as driver:
        one, _other = _two(app)
        first = one.new()
        app._heard(one, first, Event(kind="begins", text=""))
        await driver.pause()

        await _opens(app, driver)

        # One box, for the one that has started. The other is a place the flow declared, not
        # something the run is doing.
        assert _ids(app) == [EVERY, one.id]
        assert "0 of 1 working" not in _drawn(app)
        assert "1 of 1 working" in _drawn(app)


@pytest.mark.timeout(60)
async def test_a_box_appears_as_its_agent_takes_its_first_turn() -> None:
    """Which is what makes this a picture of the run growing rather than of what was set up."""
    app = Humanize()
    async with app.run_test() as driver:
        one, two = _two(app)
        first, second = one.new(), two.new()
        app._heard(one, first, Event(kind="begins", text=""))
        await driver.pause()
        await _opens(app, driver)
        assert _ids(app) == [EVERY, one.id]

        app._heard(two, second, Event(kind="begins", text=""))
        await until(lambda: _ids(app) == [EVERY, one.id, two.id], driver)

        # And it stays once its turn is over: what it did is still worth reading.
        app._heard(two, second, Event(kind="ends", text=""))
        await driver.pause()
        assert _ids(app) == [EVERY, one.id, two.id]


@pytest.mark.timeout(60)
async def test_an_agent_a_turn_started_of_its_own_is_drawn_under_it() -> None:
    """A fleet under a turn is agents, and it is drawn as agents rather than as tool calls."""
    app = Humanize()
    async with app.run_test() as driver:
        one, _other = _two(app)
        first = one.new()
        app._heard(one, first, Event(kind="begins", text=""))
        app._heard(
            one, first, Event(kind="subagent", text="Task read the tests", whose="c1")
        )
        await driver.pause()

        await _opens(app, driver)

        drawn = _drawn(app)
        assert "read the tests" in drawn
        assert "◆" in drawn  # working, and not the mark a flow's own agents wear
        # It is not a row to attach to: nobody chose what it runs and it has no transcript.
        assert _ids(app) == [EVERY, one.id]

        app._heard(
            one,
            first,
            Event(kind="subagent-ends", text="Task read the tests", whose="c1"),
        )
        await until(lambda: "◇" in _drawn(app), driver)


@pytest.mark.timeout(60)
async def test_a_run_with_no_person_in_its_flow_has_no_board() -> None:
    """A board is what the person and the flow both write on, so it takes a person."""
    app = Humanize()
    async with app.run_test() as driver:
        _two(app)
        await _opens(app, driver)

        assert "Board" not in _drawn(app)
        await driver.press("a")
        await driver.pause()
        assert "no board on it" in str(app.screen.query_one("#tuning", Label).content)


@pytest.mark.timeout(60)
async def test_the_board_is_on_the_status_sheet_and_says_what_is_on_it() -> None:
    """Beside how far through the run is: a board somebody has to go and open is unread."""
    app = Humanize()
    async with app.run_test() as driver:
        one, _other = _two(app)
        person = HumanAgent()
        app._agents = [one, person]
        person.board.put("todo", "fix the build", about="what there is to do")
        person.board.put("progress", "two of five", whose="flow")

        await _opens(app, driver)

        drawn = _drawn(app)
        assert "Board" in drawn
        assert "fix the build" in drawn
        assert "two of five" in drawn
        assert "flow's" in drawn  # the one the person may read and not rewrite


@pytest.mark.timeout(60)
async def test_a_line_the_flow_keeps_to_itself_is_not_one_to_change_here() -> None:
    """A flow writing down how far through it is does not want that edited underneath it."""
    app = Humanize()
    async with app.run_test() as driver:
        one, _other = _two(app)
        person = HumanAgent()
        app._agents = [one, person]
        person.board.put("progress", "two of five", whose="flow")
        await _opens(app, driver)

        # Down to it, and enter: it says why rather than opening an editor.
        while (
            app.screen.query_one("#choices", OptionList).highlighted
            != len(_ids(app)) - 1
        ):
            await driver.press("down")
        await driver.press("enter")
        await driver.pause()

        assert "the flow's to change" in str(
            app.screen.query_one("#tuning", Label).content
        )
        assert isinstance(app.screen, Status)


@pytest.mark.timeout(60)
async def test_a_line_is_typed_onto_the_board_and_the_flow_reads_it_at_once() -> None:
    """Neither side waits at the board: what is written here is there the moment it is."""
    app = Humanize()
    async with app.run_test() as driver:
        one, _other = _two(app)
        person = HumanAgent()
        app._agents = [one, person]
        await _opens(app, driver)

        await driver.press("a")
        await until(lambda: isinstance(app.screen, Entry), driver)
        await driver.press(*"todo")
        await driver.press("enter")  # the name, then what it says
        await driver.pause()
        await driver.press(*"fix the build")
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Status), driver)

        assert person.board.get("todo") == "fix the build"
        assert person.board.items()[0].by == "user"
        assert "fix the build" in _drawn(app)


def test_the_board_is_named_lines_that_either_side_may_be_kept_off() -> None:
    """The store itself, which is what both the sheet and a flow are reading."""
    board = Board()
    board.put("todo", "one thing", about="what there is to do")
    board.put("progress", "nothing yet", whose="flow")
    board.put("wanted", "", whose="user")

    assert board.get("todo") == "one thing"
    assert [one.key for one in board.items()] == ["todo", "progress", "wanted"]
    # Either side writes the ordinary one.
    board.put("todo", "another", by="user")
    assert board.get("todo") == "another"
    # And neither writes the other's.
    with pytest.raises(Refused):
        board.put("progress", "no", by="user")
    with pytest.raises(Refused):
        board.put("wanted", "no", by="flow")
    with pytest.raises(Refused):
        board.drop("progress", by="user")
    # What a line is for survives writing what it says, so a value is one thing to write.
    held = board.held("todo")
    assert held is not None
    assert held.about == "what there is to do"


def test_a_renamed_line_comes_back_under_its_new_name() -> None:
    """A rename is one write, so what it wrote is what the caller is handed."""
    board = Board()
    board.put("todo", "fix the build", about="what there is to do", whose="user")

    moved = board.moves("todo", to="doing", by="user")

    assert moved.key == "doing"
    assert moved.value == "fix the build"
    assert moved.about == "what there is to do"  # everything else it said survives
    assert moved.whose == "user"
    assert moved.by == "user"
    assert [one.key for one in board.items()] == ["doing"]


def test_a_renamed_line_comes_back_where_something_watching_took_it_away() -> None:
    """The rename happened; what a watcher did on being told is the next thing, not this one.

    Which is the whole board in one call: the line is made under the lock, and what anybody
    else does to the board afterwards cannot turn the answer into a different line or into
    no line at all.
    """

    def away(one: Board) -> None:
        one.drop("doing")

    board = Board()
    board.put("todo", "fix the build")
    board.watch(away)

    moved = board.moves("todo", to="doing")

    assert moved.key == "doing"
    assert moved.value == "fix the build"
    assert board.held("doing") is None  # the watcher got what it asked for


def test_whatever_is_watching_the_board_is_told_when_a_line_moves() -> None:
    """Which is how the sheet redraws without asking the board on a clock."""
    board = Board()
    seen: list[int] = []
    board.watch(lambda one: seen.append(len(one.items())))

    board.put("todo", "one")
    board.put("todo", "two")
    board.drop("todo")

    assert seen == [1, 1, 0]


def test_a_watcher_that_raises_has_said_nothing() -> None:
    """A flow must not fail because something looking at its board did."""

    def up(_board: Board) -> None:
        raise RuntimeError("no")

    board = Board()
    board.watch(up)

    board.put("todo", "one")  # which does not raise

    assert board.get("todo") == "one"

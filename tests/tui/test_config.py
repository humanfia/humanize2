"""Setting a flow up: the sheet between choosing the flow and choosing what runs it.

A flow says what it can be set up with by declaring a model, and this is that model with a
cursor on it. Nothing here knows what any of the settings mean: the types say how a value is
moved and the model says which combinations it will not take, so what is checked is that both
of those reach the person setting it up.
"""

from __future__ import annotations

import unittest.mock
from typing import TYPE_CHECKING

import pytest
from textual.widgets import Label, OptionList, RichLog

from hmz.backends import Model
from hmz.cli import main
from hmz.tui import Humanize
from hmz.tui.pick import Configures, Flows, Models, Runs, setting
from hmz.tui.settings import Settings

from .test_app import into_models

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from textual.pilot import Pilot

#: A flow with one of each kind of setting, in two sections, and a combination it will not
#: take.
FLOW = '''
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from hmz.agents import AgentBase

FIRST = {"section": "first  ·  how loudly"}
SECOND = {"section": "second  ·  how far"}


class Config(BaseModel):
    """What this flow takes."""

    loud: bool = Field(
        default=False, description="say it twice", json_schema_extra=FIRST
    )
    rounds: int = Field(
        default=3, ge=1, le=9, description="how many times round", json_schema_extra=FIRST
    )
    mode: Literal["fast", "slow"] = Field(
        default="fast", description="which way", json_schema_extra=SECOND
    )
    named: str = Field(
        default="", description="what to call it", json_schema_extra=SECOND
    )

    @model_validator(mode="after")
    def _settles(self) -> "Config":
        if self.loud and self.mode == "slow":
            raise ValueError("loud and slow do not go together")
        return self


def run(agents: tuple[AgentBase], task: str, config: Config | None = None) -> None:
    pass
'''

#: A flow that takes settings but groups none of them, which is a sheet of one list.
UNGROUPED = '''
from pydantic import BaseModel, Field

from hmz.agents import AgentBase


class Config(BaseModel):
    """What this flow takes."""

    loud: bool = Field(default=False, description="say it twice")
    rounds: int = Field(default=3, description="how many times round")


def run(agents: tuple[AgentBase], task: str, config: Config | None = None) -> None:
    pass
'''

#: A flow that takes no setting up at all, which is what most of them are.
PLAIN = """
from hmz.agents import AgentBase


def run(agents: tuple[AgentBase], task: str) -> None:
    pass
"""


@pytest.fixture
def flows(tmp_path: Path) -> Path:
    """Puts both flows where this project's own would be."""
    where = tmp_path / ".humanize" / "flows"
    where.mkdir(parents=True)
    (where / "settable.py").write_text(FLOW)
    (where / "plain.py").write_text(PLAIN)
    (where / "ungrouped.py").write_text(UNGROUPED)
    return where


async def until(
    ready: Callable[[], bool], driver: Pilot[None], patience: float = 5.0
) -> None:
    """Waits for the interface to catch up with what was asked of it."""
    import time

    began = time.monotonic()
    while not ready() and time.monotonic() - began < patience:
        await driver.pause()
    await driver.pause()


def _opens(opened: list[Humanize]) -> Callable[[Humanize], None]:
    """A `run` that keeps the interface rather than showing it, for a line that opens one."""

    def running(app: Humanize) -> None:
        opened.append(app)

    return running


def _under(app: Humanize) -> str:
    """The row the cursor is on, as it is written -- markup and all, which is what is checked."""
    listing = app.screen.query_one("#choices", OptionList)
    at = listing.highlighted or 0
    return str(listing.get_option_at_index(at).prompt)


def _rows(app: Humanize) -> str:
    """What the sheet is showing, as one string to look for things in."""
    listing = app.screen.query_one("#choices", OptionList)
    return "\n".join(str(option.prompt) for option in listing.options)


@pytest.mark.timeout(60)
async def test_setting_up_comes_between_the_flow_and_its_agents(flows: Path) -> None:
    """Which is the only moment it can: the flow says what there is to set."""
    app = Humanize()
    with unittest.mock.patch(
        "hmz.tui.app.installed",
        return_value={"claude": (Model("opus", ("high",)),)},
    ):
        async with app.run_test() as driver:
            await driver.press(*"/flow settable")
            await driver.press("enter")
            await until(lambda: isinstance(app.screen, Configures), driver)

            assert isinstance(app.screen, Configures)
            shown = _rows(app)
            assert "loud" in shown
            assert "say it twice" in shown  # the line the field was declared with

            await driver.press("enter")
            await into_models(app, driver)
            assert isinstance(app.screen, Models)


@pytest.mark.timeout(60)
async def test_a_flow_that_takes_no_setting_up_is_not_asked_about(flows: Path) -> None:
    """The sheet is skipped rather than shown empty, and the walk is one step shorter."""
    app = Humanize()
    with unittest.mock.patch(
        "hmz.tui.app.installed",
        return_value={"claude": (Model("opus", ("high",)),)},
    ):
        async with app.run_test() as driver:
            await driver.press(*"/flow plain")
            await driver.press("enter")
            await into_models(app, driver)

            assert isinstance(app.screen, Models)


@pytest.mark.timeout(60)
async def test_the_arrows_move_a_setting_and_letters_write_one(flows: Path) -> None:
    """A switch and a literal step; a number and a word are typed, which is what they are."""
    app = Humanize()
    with unittest.mock.patch(
        "hmz.tui.app.installed",
        return_value={"claude": (Model("opus", ("high",)),)},
    ):
        async with app.run_test() as driver:
            await driver.press(*"/flow settable")
            await driver.press("enter")
            await until(lambda: isinstance(app.screen, Configures), driver)
            sheet = app.screen
            assert isinstance(sheet, Configures)

            await driver.press("right")  # loud: off -> on
            await driver.pause()
            assert sheet._typed_in["loud"] == "on"

            await driver.press("down", "right")  # rounds: 3 -> 4
            await driver.pause()
            assert sheet._typed_in["rounds"] == "4"

            await driver.press("down", "right")  # mode: fast -> slow
            await driver.pause()
            assert sheet._typed_in["mode"] == "slow"

            await driver.press("down", *"here")  # named, which is written
            await driver.pause()
            assert sheet._typed_in["named"] == "here"


@pytest.mark.timeout(60)
async def test_what_the_flow_refuses_is_said_where_it_was_typed(flows: Path) -> None:
    """The model is what refuses, so a flow's own rule is enforced before anything runs."""
    app = Humanize()
    with unittest.mock.patch(
        "hmz.tui.app.installed",
        return_value={"claude": (Model("opus", ("high",)),)},
    ):
        async with app.run_test() as driver:
            await driver.press(*"/flow settable")
            await driver.press("enter")
            await until(lambda: isinstance(app.screen, Configures), driver)
            sheet = app.screen
            assert isinstance(sheet, Configures)

            await driver.press("right")  # loud on
            await driver.press("down", "down", "right")  # mode slow
            await driver.press("enter")
            await driver.pause()

            assert isinstance(app.screen, Configures)  # still here, not moved on
            assert "loud and slow" in str(sheet.query_one("#tuning", Label).content)


@pytest.mark.timeout(60)
async def test_a_setting_outside_its_bounds_is_said_too(flows: Path) -> None:
    """The bounds are the field's own, and nothing here had to be told about them."""
    app = Humanize()
    with unittest.mock.patch(
        "hmz.tui.app.installed",
        return_value={"claude": (Model("opus", ("high",)),)},
    ):
        async with app.run_test() as driver:
            await driver.press(*"/flow settable")
            await driver.press("enter")
            await until(lambda: isinstance(app.screen, Configures), driver)
            sheet = app.screen
            assert isinstance(sheet, Configures)

            await driver.press("down", "backspace", *"99")
            await driver.press("enter")
            await driver.pause()

            assert isinstance(app.screen, Configures)
            assert "rounds" in str(sheet.query_one("#tuning", Label).content)


@pytest.mark.timeout(60)
async def test_escape_steps_back_to_the_flows(flows: Path) -> None:
    """A flow chosen by mistake is what you would be walking back from."""
    app = Humanize()
    with unittest.mock.patch(
        "hmz.tui.app.installed",
        return_value={"claude": (Model("opus", ("high",)),)},
    ):
        async with app.run_test() as driver:
            await driver.press(*"/flow")
            await driver.press("enter")
            await until(lambda: isinstance(app.screen, Flows), driver)
            await driver.press(*"settable")
            await driver.press("enter")
            await until(lambda: isinstance(app.screen, Configures), driver)

            await driver.press("escape")
            await until(lambda: isinstance(app.screen, Flows), driver)

            assert isinstance(app.screen, Flows)


@pytest.mark.timeout(60)
async def test_how_it_was_set_up_is_kept_and_read_back(
    flows: Path, tmp_path: Path
) -> None:
    """A flow of forty settings is not one to answer again every morning."""
    app = Humanize()
    with unittest.mock.patch(
        "hmz.tui.app.installed",
        return_value={"claude": (Model("opus", ("high",)),)},
    ):
        async with app.run_test() as driver:
            await driver.press(*"/flow settable")
            await driver.press("enter")
            await until(lambda: isinstance(app.screen, Configures), driver)
            await driver.press("right")  # loud on
            await driver.press("enter")
            await into_models(app, driver)
            await driver.press("enter")
            await until(lambda: app._config is not None, driver)

    assert Settings(tmp_path).config("settable")["loud"] is True
    # And a second interface opens on it, rather than back at the flow's own defaults.
    again = Humanize()
    assert again._config is not None
    assert again._config.model_dump()["loud"] is True


@pytest.mark.timeout(60)
async def test_config_opens_the_sheet_on_its_own(flows: Path) -> None:
    """`/config` is the other half of `/agents`: one asks about the flow, one about what runs it."""
    app = Humanize()
    with unittest.mock.patch(
        "hmz.tui.app.installed",
        return_value={"claude": (Model("opus", ("high",)),)},
    ):
        async with app.run_test() as driver:
            await driver.press(*"/flow settable")
            await driver.press("enter")
            await until(lambda: isinstance(app.screen, Configures), driver)
            await driver.press("enter")
            await into_models(app, driver)
            await driver.press("enter")
            await until(lambda: not isinstance(app.screen, Models), driver)

            await driver.press(*"/config")
            await driver.press("enter")
            await until(lambda: isinstance(app.screen, Configures), driver)

            assert isinstance(app.screen, Configures)


@pytest.mark.timeout(60)
async def test_config_on_a_flow_that_takes_none_says_so(flows: Path) -> None:
    """Rather than putting up a sheet with nothing on it."""
    app = Humanize()
    async with app.run_test() as driver:
        await driver.press(*"/config")
        await driver.press("enter")
        await driver.pause()

        assert any(
            "takes no setting up" in line.text
            for line in app.query_one("#transcript", RichLog).lines
        )


def test_status_says_only_what_was_changed() -> None:
    """A flow of forty settings says nothing by listing the thirty-nine nobody touched."""
    from pydantic import BaseModel, Field

    class Config(BaseModel):
        loud: bool = Field(default=False, description="")
        rounds: int = Field(default=3, description="")

    assert setting(Config()) == []
    assert setting(None) == []
    said = setting(Config(loud=True))
    assert len(said) == 1
    assert said[0].startswith("loud")
    assert said[0].endswith("on")


def test_a_config_that_no_longer_fits_the_flow_is_started_over_from(
    flows: Path, tmp_path: Path
) -> None:
    """A settings file is a convenience, and one that has gone stale is not a reason to fail."""
    Settings(tmp_path).remember(
        "settable", ("",), [Runs("claude/opus:high")], {"gone": "away", "rounds": 99}
    )

    app = Humanize()

    assert app._config_of("settable") is None


@pytest.mark.timeout(60)
async def test_the_settings_are_drawn_in_the_sections_the_flow_grouped_them_into(
    flows: Path,
) -> None:
    """Twenty settings in one list is a list nobody reads: the flow says which belong together."""
    app = Humanize()
    with unittest.mock.patch(
        "hmz.tui.app.installed",
        return_value={"claude": (Model("opus", ("high",)),)},
    ):
        async with app.run_test() as driver:
            await driver.press(*"/flow settable")
            await driver.press("enter")
            await until(lambda: isinstance(app.screen, Configures), driver)
            sheet = app.screen
            assert isinstance(sheet, Configures)

            shown = _rows(app)
            assert "first  ·  how loudly" in shown
            assert "second  ·  how far" in shown

            # And the arrows walk the settings, stepping over the heading between them: two
            # down from the first is the third setting, not the heading above it.
            await driver.press("down", "down")
            await driver.pause()
            assert sheet._under == "mode"


@pytest.mark.timeout(60)
async def test_a_flow_that_groups_nothing_is_one_list(flows: Path) -> None:
    """No headings, no blank rows, and the arrows walk it as they walk any list."""
    app = Humanize()
    with unittest.mock.patch(
        "hmz.tui.app.installed",
        return_value={"claude": (Model("opus", ("high",)),)},
    ):
        async with app.run_test() as driver:
            await driver.press(*"/flow .humanize/flows/ungrouped.py")
            await driver.press("enter")
            await until(lambda: isinstance(app.screen, Configures), driver)
            sheet = app.screen
            assert isinstance(sheet, Configures)

            listing = sheet.query_one("#choices", OptionList)
            assert listing.option_count == 2  # the two settings, and nothing else
            assert sheet._under == "loud"

            await driver.press("down")
            await driver.pause()
            assert sheet._under == "rounds"


@pytest.mark.timeout(60)
async def test_the_line_that_opens_it_can_set_it_up(
    flows: Path, tmp_path: Path
) -> None:
    """`hmz -f -c -a`: a run that is always the same run is one line, not three walks."""
    (tmp_path / "setup.yaml").write_text("loud: true\nrounds: 7\n")
    said = ["-f", ".humanize/flows/settable.py", "-c", str(tmp_path / "setup.yaml")]

    opened: list[Humanize] = []
    with unittest.mock.patch.object(Humanize, "run", _opens(opened)):
        assert main(said) == 0

    (app,) = opened
    assert app._flow_named == ".humanize/flows/settable.py"
    assert app._config is not None
    assert app._config.model_dump() == {
        "loud": True,
        "rounds": 7,
        "mode": "fast",
        "named": "",
    }


def test_a_line_that_sets_up_a_flow_that_takes_none_is_a_line_to_correct(
    flows: Path, tmp_path: Path
) -> None:
    """Rather than an interface opening with a setting nothing will ever read."""
    (tmp_path / "setup.yaml").write_text("loud: true\n")

    with pytest.raises(SystemExit) as refused:
        main(["-f", ".humanize/flows/plain.py", "-c", str(tmp_path / "setup.yaml")])

    assert refused.value.code == 2


def test_a_line_that_says_how_to_run_a_flow_without_saying_which_is_one_too(
    flows: Path,
) -> None:
    """`-a` and `-c` are both about a flow, so neither means anything without `-f`."""
    with pytest.raises(SystemExit) as refused:
        main(["-a", "claude/m:high"])

    assert refused.value.code == 2


def test_the_agents_a_line_names_have_to_be_the_ones_the_flow_drives(
    flows: Path,
) -> None:
    """Said on the line rather than found when the first thing typed starts the flow."""
    with pytest.raises(SystemExit) as refused:
        main(
            [
                "-f",
                ".humanize/flows/settable.py",
                "-a",
                "claude/m:high",
                "-a",
                "codex/n:low",
            ]
        )

    assert refused.value.code == 2


@pytest.mark.timeout(60)
async def test_what_a_line_says_beats_what_was_remembered(
    flows: Path, tmp_path: Path
) -> None:
    """An interface opened set up is opened that way, whatever this workspace last ran."""
    Settings(tmp_path).remember(
        ".humanize/flows/settable.py",
        ("",),
        [Runs("claude/kept:high")],
        {"rounds": 2},
    )

    opened: list[Humanize] = []
    with unittest.mock.patch.object(Humanize, "run", _opens(opened)):
        assert main(["-f", ".humanize/flows/settable.py", "-a", "codex/said:low"]) == 0

    (app,) = opened
    assert app._models == [Runs("codex/said:low")]


@pytest.mark.timeout(60)
async def test_agents_does_not_ask_how_the_flow_is_set_up(flows: Path) -> None:
    """The two are split: `/config` asks how the flow runs, `/agents` what it runs on."""
    app = Humanize()
    with unittest.mock.patch(
        "hmz.tui.app.installed",
        return_value={"claude": (Model("opus", ("high",)),)},
    ):
        async with app.run_test() as driver:
            await driver.press(*"/flow settable")
            await driver.press("enter")
            await until(lambda: isinstance(app.screen, Configures), driver)
            await driver.press("enter")
            await into_models(app, driver)
            await driver.press("enter")
            await until(lambda: not isinstance(app.screen, Models), driver)

            await driver.press(*"/agents")
            await driver.press("enter")
            await into_models(app, driver)

            # Straight to what the agents run, with nothing about the flow itself on the way.
            assert isinstance(app.screen, Models)


@pytest.mark.timeout(60)
async def test_agents_leaves_how_the_flow_is_set_up_alone(flows: Path) -> None:
    """A question it did not ask is one it must not answer, either -- even by keeping it."""
    app = Humanize()
    with unittest.mock.patch(
        "hmz.tui.app.installed",
        return_value={"claude": (Model("opus", ("high",)),)},
    ):
        async with app.run_test() as driver:
            await driver.press(*"/flow settable")
            await driver.press("enter")
            await until(lambda: isinstance(app.screen, Configures), driver)
            await driver.press("right")  # loud on
            await driver.press("enter")
            await into_models(app, driver)
            await driver.press("enter")
            await until(lambda: not isinstance(app.screen, Models), driver)

            await driver.press(*"/agents")
            await driver.press("enter")
            await into_models(app, driver)
            await driver.press("enter")
            await until(lambda: not isinstance(app.screen, Models), driver)

            assert app._config is not None
            assert app._config.model_dump()["loud"] is True


@pytest.mark.timeout(60)
async def test_a_setting_that_is_written_carries_a_caret_under_the_cursor(
    flows: Path,
) -> None:
    """A blank one otherwise reads as a setting nothing can be typed into."""
    app = Humanize()
    with unittest.mock.patch(
        "hmz.tui.app.installed",
        return_value={"claude": (Model("opus", ("high",)),)},
    ):
        async with app.run_test() as driver:
            await driver.press(*"/flow settable")
            await driver.press("enter")
            await until(lambda: isinstance(app.screen, Configures), driver)
            sheet = app.screen
            assert isinstance(sheet, Configures)

            # The cursor starts on a switch, which is stepped rather than written.
            assert "reverse" not in _under(app)
            assert "←/→" in str(sheet.query_one("#keys", Label).content)

            await driver.press("down", "down", "down")  # `named`, which is written
            await driver.pause()
            assert sheet._under == "named"
            assert "reverse" in _under(app)
            assert "Type to set" in str(sheet.query_one("#keys", Label).content)

            # And it stays where the next letter would land as the value grows.
            await driver.press(*"here")
            await driver.pause()
            assert "here[/][reverse] [/reverse]" in _under(app)

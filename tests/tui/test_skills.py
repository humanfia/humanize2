"""What a CLI would load here: found the way that CLI finds it, shown, and left alone.

A skill installed on this machine is the CLI's own -- installed the way that CLI installs
one and switched off the way that CLI switches one off -- so humanize reads the list and
changes nothing about it. What it does add to a session is the flow's own skills, which are
mounted rather than installed and are tested beside the flows.
"""

from __future__ import annotations

import unittest.mock
from pathlib import Path

import pytest
from textual.widgets import Label, OptionList

from hmz.agents.skills import Skill, skills
from hmz.backends import Model
from hmz.kept import Runs
from hmz.tui import Humanize
from hmz.tui.pick import Agent, Skills
from hmz.tui.settings import Settings

from .test_app import into_agent, into_flows, keeps, opens, rows, until

SKILL = """---
name: {name}
description: {about}
---

Do the thing.
"""


def _write(where: Path, name: str, about: str = "does a thing") -> None:
    """Installs one skill where a CLI would find it."""
    (where / name).mkdir(parents=True, exist_ok=True)
    (where / name / "SKILL.md").write_text(SKILL.format(name=name, about=about))


@pytest.fixture
def homes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A Claude home with two skills in it, and a project with one of its own."""
    home = tmp_path / "claude-home"
    _write(home / "skills", "writing", about="writes things down")
    _write(home / "skills", "hf-cli", about="the Hugging Face CLI")
    _write(tmp_path / "project" / ".claude" / "skills", "housekeeping")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(home))
    monkeypatch.chdir(tmp_path / "project")
    return tmp_path


def test_skills_are_found_where_the_cli_looks(homes: Path) -> None:
    """Yours and this project's, each read for the name and the line the CLI reads."""
    assert skills("claude") == [
        Skill(name="hf-cli", about="the Hugging Face CLI", whose="yours"),
        Skill(name="writing", about="writes things down", whose="yours"),
        Skill(name="housekeeping", about="does a thing", whose="this project"),
    ]
    # By any name the CLI answers to, since that is how an agent names its backend.
    assert skills("claude-code") == skills("claude")


def test_codex_is_read_from_all_four_places_it_looks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Its own home, the shared one under yours, and both of a project's own.

    `skills/list` on the real app server answers with all four, and the shared one follows
    your home rather than `CODEX_HOME` -- so a skill kept there is one it loads whatever the
    backend's own home has been moved to.
    """
    _write(tmp_path / "codex-home" / "skills", "its-own")
    _write(tmp_path / "home" / ".agents" / "skills", "shared")
    _write(tmp_path / "project" / ".agents" / "skills", "the-project-agents")
    _write(tmp_path / "project" / ".codex" / "skills", "the-project-codex")
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex-home"))
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.chdir(tmp_path / "project")

    assert [one.name for one in skills("codex")] == [
        "its-own",
        "shared",
        "the-project-agents",
        "the-project-codex",
    ]


def test_a_backend_that_keeps_none_here_finds_none(homes: Path) -> None:
    """Kimi's daemon reads no directory of them, so there is nothing here to show."""
    assert skills("kimi") == []
    assert skills("not-a-cli") == []


def test_a_skill_with_no_front_matter_is_the_directory_it_is_in(homes: Path) -> None:
    """Which is the rule these CLIs read a skill by: the file is always `SKILL.md`."""
    where = homes / "claude-home" / "skills" / "bare"
    where.mkdir()
    (where / "SKILL.md").write_text("Just the prose, no front matter.\n")

    assert Skill(name="bare", about="", whose="yours") in skills("claude")


@pytest.mark.timeout(60)
@unittest.mock.patch(
    "hmz.tui.app.installed",
    return_value={"kimi": (Model("kimi-code/k3", ("max",)),)},
)
async def test_a_cli_that_keeps_none_says_that_rather_than_none_installed(
    _installed: unittest.mock.MagicMock,  # noqa: PT019  -- `mock.patch` hands it over
    homes: Path,
) -> None:
    """Blaming the machine for what the backend does not do would be the wrong sentence."""
    app = Humanize()
    async with app.run_test() as driver:
        await into_flows(app, driver)
        await into_agent(app, driver)
        await opens(app, driver, "skills")
        await until(lambda: isinstance(app.screen, Skills), driver)
        said = str(app.screen.query_one("#tuning", Label).content)

        assert "kimi keeps no skills of its own here" in said


@pytest.mark.timeout(60)
@unittest.mock.patch(
    "hmz.tui.app.installed",
    return_value={"claude": (Model("claude-opus-5", ("max", "high")),)},
)
async def test_what_an_agent_carries_is_shown_and_not_switched(
    _installed: unittest.mock.MagicMock,  # noqa: PT019  -- `mock.patch` hands it over
    homes: Path,
) -> None:
    """The row reads, and the sheet it opens reads: neither is a choice anybody is offered."""
    app = Humanize()
    async with app.run_test() as driver:
        await into_flows(app, driver)
        await into_agent(app, driver)
        listing = app.screen.query_one("#choices", OptionList)
        held = listing.get_option_at_index(rows(app).index("skills"))
        assert "as its CLI finds them" in str(held.prompt)

        await opens(app, driver, "skills")
        await until(lambda: isinstance(app.screen, Skills), driver)
        listing = app.screen.query_one("#choices", OptionList)
        await until(lambda: bool(listing.options), driver)
        # Every skill the CLI would load, where it came from, and no box to switch.
        assert [str(option.id) for option in listing.options] == [
            "hf-cli",
            "writing",
            "housekeeping",
        ]
        assert not any("[✔]" in str(option.prompt) for option in listing.options)
        assert not any("[ ]" in str(option.prompt) for option in listing.options)
        # And the line under them says whose they are and where to go to change one.
        said = str(app.screen.query_one("#tuning", Label).content)
        assert "claude's own" in said

        await driver.press("space")  # nothing to switch, and nothing switches
        await driver.pause()
        assert not any("[✔]" in str(option.prompt) for option in listing.options)

        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Agent), driver)

        await keeps(app, driver)
        await keeps(app, driver)

    # Nothing about the skills rides along with what the agent runs: they are the CLI's,
    # and reading the list is not a change to the agent.
    assert app._models == [Runs("claude/claude-opus-5:high")]


@pytest.mark.timeout(60)
@unittest.mock.patch(
    "hmz.tui.app.installed",
    return_value={"claude": (Model("claude-opus-5", ("max", "high")),)},
)
async def test_the_letters_narrow_the_skills_shown(
    _installed: unittest.mock.MagicMock,  # noqa: PT019  -- `mock.patch` hands it over
    homes: Path,
) -> None:
    """A long list is searched here as it is searched everywhere else on these sheets."""
    app = Humanize()
    async with app.run_test() as driver:
        await into_flows(app, driver)
        await into_agent(app, driver)
        await opens(app, driver, "skills")
        await until(lambda: isinstance(app.screen, Skills), driver)
        listing = app.screen.query_one("#choices", OptionList)
        await until(lambda: bool(listing.options), driver)

        await driver.press("s")
        await driver.press(*"hous")
        await driver.pause()
        assert [str(option.id) for option in listing.options] == ["housekeeping"]

        # Esc clears the search before it leaves, as it does on every other sheet.
        await driver.press("escape")
        await driver.pause()
        assert [str(option.id) for option in listing.options] == [
            "hf-cli",
            "writing",
            "housekeeping",
        ]
        assert isinstance(app.screen, Skills)

        await driver.press("escape")
        await until(lambda: isinstance(app.screen, Agent), driver)


def test_a_workspace_writes_down_no_skills_of_its_own(tmp_path: Path) -> None:
    """What an agent is does not include them any more, so nothing about them is kept."""
    kept = Settings(tmp_path)
    kept.remember("rlar", ("actor",), [Runs("claude/m:high")])

    assert Settings(tmp_path).agents("rlar") == [Runs("claude/m:high")]
    held = Settings(tmp_path)._read()
    agents = held["workspaces"][str(tmp_path.resolve())]["flows"]["rlar"]["agents"]
    assert "skills" not in agents["actor"]


def test_a_file_that_still_says_skills_is_read_past(tmp_path: Path) -> None:
    """An agent written down when they were a setting is the agent it always was."""
    from hmz.kept import read_back

    runs = read_back(
        {"cli": "claude", "model": "m", "effort": "high", "skills": ["writing"]}
    )

    assert runs == Runs("claude/m:high")

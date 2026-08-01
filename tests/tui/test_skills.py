"""Which of a CLI's skills one agent is loaded with: found, chosen, kept, and handed over.

Found the way the CLI finds them, so nothing is typed in and nothing is asked of the CLI --
the same rule the models on the sheet beside this one are offered under. Chosen per agent,
because two agents of one flow are two agents: the reviewer reading a change need not be
carrying what the builder writing it was.
"""

from __future__ import annotations

import unittest.mock
from pathlib import Path

import pytest
from textual.widgets import Label, OptionList

from humanize.agents.skills import Skill, leaving, skills
from humanize.backends import Model
from humanize.tui import Humanize
from humanize.tui.pick import Models, Runs, Skills
from humanize.tui.settings import Settings

from .test_app import into_models, until

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


def test_a_backend_with_nowhere_to_keep_them_offers_none(homes: Path) -> None:
    """Kimi's daemon takes no `--skills-dir`, so there is nothing to be offered a choice of."""
    assert skills("kimi") == []
    assert skills("not-a-cli") == []


@pytest.mark.timeout(60)
@unittest.mock.patch(
    "humanize.tui.app.installed",
    return_value={"kimi": (Model("kimi-code/k3", ("max",)),)},
)
async def test_a_cli_that_cannot_be_told_says_that_rather_than_none_installed(
    _installed: unittest.mock.MagicMock,  # noqa: PT019  -- `mock.patch` hands it over
    homes: Path,
) -> None:
    """Blaming the machine for what the backend cannot do would be the wrong sentence."""
    app = Humanize()
    async with app.run_test() as driver:
        await driver.press(*"/agents")
        await driver.press("enter")
        await into_models(app, driver)
        await driver.press("ctrl+s")
        await until(lambda: isinstance(app.screen, Skills), driver)
        said = str(app.screen.query_one("#tuning", Label).content)

        assert "kimi cannot be told which skills to load" in said


def test_a_skill_with_no_front_matter_is_the_directory_it_is_in(homes: Path) -> None:
    """Which is the rule these CLIs read a skill by: the file is always `SKILL.md`."""
    where = homes / "claude-home" / "skills" / "bare"
    where.mkdir()
    (where / "SKILL.md").write_text("Just the prose, no front matter.\n")

    assert Skill(name="bare", about="", whose="yours") in skills("claude")


@pytest.mark.timeout(60)
@unittest.mock.patch(
    "humanize.tui.app.installed",
    return_value={"claude": (Model("claude-opus-5", ("max", "high")),)},
)
async def test_what_an_agent_is_loaded_with_is_chosen_beside_what_it_runs(
    _installed: unittest.mock.MagicMock,  # noqa: PT019  -- `mock.patch` hands it over
    homes: Path,
) -> None:
    """A side question about the agent, so it is a key on the model step and not a row."""
    app = Humanize()
    async with app.run_test() as driver:
        await driver.press(*"/agents")
        await driver.press("enter")
        await into_models(app, driver)
        sheet = app.screen
        tuning = sheet.query_one("#tuning", Label)
        await until(lambda: "effort" in str(tuning.content), driver)
        assert "every skill" in str(tuning.content)  # never asked: the CLI as it comes

        await driver.press("ctrl+s")
        await until(lambda: isinstance(app.screen, Skills), driver)
        listing = app.screen.query_one("#choices", OptionList)
        await until(lambda: bool(listing.options), driver)
        # Every skill the CLI would load, each with a ticked box: it starts with all of them.
        assert [str(option.id) for option in listing.options] == [
            "hf-cli",
            "writing",
            "housekeeping",
        ]
        assert all("[✔]" in str(option.prompt) for option in listing.options)

        await driver.press("down", "space")  # `writing`: switched off
        await driver.pause()
        assert "[ ]" in str(listing.get_option_at_index(1).prompt)
        assert "[✔]" not in str(listing.get_option_at_index(1).prompt)

        await driver.press("space")  # and on again, which is the same key
        await driver.pause()
        assert "[✔]" in str(listing.get_option_at_index(1).prompt)
        await driver.press("space")

        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Models), driver)
        await until(lambda: "2 skills" in str(tuning.content), driver)

        await driver.press("enter")
        await until(lambda: not isinstance(app.screen, Models), driver)

    # It rides along with what the agent runs, and is kept with it: the ones it has, in the
    # order the CLI lists them, rather than the one that was switched off.
    chosen = Runs("claude/claude-opus-5:max", "", ("hf-cli", "housekeeping"))
    assert app._models == [chosen]
    assert app.settings.agents(app._flow_named) == [chosen]


@pytest.mark.timeout(60)
@unittest.mock.patch(
    "humanize.tui.app.installed",
    return_value={"claude": (Model("claude-opus-5", ("max", "high")),)},
)
async def test_walking_out_of_the_skills_leaves_the_agent_loaded_as_it_was(
    _installed: unittest.mock.MagicMock,  # noqa: PT019  -- `mock.patch` hands it over
    homes: Path,
) -> None:
    """Declining to answer a side question is not declining to choose the agent."""
    app = Humanize()
    async with app.run_test() as driver:
        await driver.press(*"/agents")
        await driver.press("enter")
        await into_models(app, driver)
        await driver.press("ctrl+s")
        await until(lambda: isinstance(app.screen, Skills), driver)
        listing = app.screen.query_one("#choices", OptionList)
        await until(lambda: bool(listing.options), driver)

        await driver.press("space")  # switched off, and then walked away from
        await driver.press("escape")
        await until(lambda: isinstance(app.screen, Models), driver)
        await driver.press("enter")
        await until(lambda: not isinstance(app.screen, Models), driver)

    assert app._models == [Runs("claude/claude-opus-5:max")]


def test_what_a_workspace_is_loaded_with_is_kept_and_read_back(tmp_path: Path) -> None:
    """As the anchor is: written only where there is one, so an old file reads as before."""
    kept = Settings(tmp_path)
    kept.remember(
        "rlar",
        ("actor", "reviewer"),
        [Runs("claude/m:high", "", ("writing",)), Runs("codex/n:low")],
    )

    assert Settings(tmp_path).agents("rlar") == [
        Runs("claude/m:high", "", ("writing",)),
        Runs("codex/n:low"),
    ]
    held = Settings(tmp_path)._read()
    agents = held["workspaces"][str(tmp_path.resolve())]["flows"]["rlar"]["agents"]
    assert agents["actor"]["skills"] == ["writing"]
    # An agent nobody was asked about says nothing, which is what an entry written before
    # there were any says too -- and is read back as the CLI as it comes rather than as none.
    assert "skills" not in agents["reviewer"]


def test_an_agent_loaded_with_none_is_not_an_agent_nobody_asked_about(
    tmp_path: Path,
) -> None:
    """Which is the whole reason the two are told apart: `[]` is a choice and nothing is not."""
    kept = Settings(tmp_path)
    kept.remember("rlar", ("actor",), [Runs("claude/m:high", "", ())])

    assert Settings(tmp_path).agents("rlar") == [Runs("claude/m:high", "", ())]
    held = Settings(tmp_path)._read()
    agents = held["workspaces"][str(tmp_path.resolve())]["flows"]["rlar"]["agents"]
    assert agents["actor"]["skills"] == []


def test_what_a_backend_is_told_is_every_skill_the_agent_was_not_given(
    homes: Path,
) -> None:
    """An agent has skills; a CLI has to be talked out of the ones it would have loaded."""
    assert leaving("claude", None) == []  # never asked, so nothing to say
    assert leaving("claude", ("writing",)) == ["hf-cli", "housekeeping"]
    assert leaving("claude", ()) == ["hf-cli", "writing", "housekeeping"]
    # A name nothing here answers to is not a skill to switch off.
    assert leaving("claude", ("writing", "nonesuch")) == ["hf-cli", "housekeeping"]


def test_an_agent_is_made_with_what_it_was_told_to_have(tmp_path: Path) -> None:
    """What the sheet answered is a setting of the agent, done to it before the flow starts."""
    from humanize.agents import ClaudeCodeAgent, ClaudeCodeAgentConfig

    app = Humanize()
    app._models = [Runs("claude/m:high", "", ("writing", "hf-cli"))]
    made = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="m", effort="high"))

    (agent,) = app._as_they_were_set_up([made])

    assert agent.config.skills == ("writing", "hf-cli")
    assert agent.config.model == "m"
    assert agent.config.machine is None  # it works here, as it did before

    # And one nobody was asked about is the agent that was made, untouched.
    app._models = [Runs("claude/m:high")]
    again = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="m", effort="high"))
    assert app._as_they_were_set_up([again]) == [again]


@pytest.mark.timeout(60)
@unittest.mock.patch(
    "humanize.tui.app.installed",
    return_value={"claude": (Model("claude-opus-5", ("max", "high")),)},
)
async def test_the_letters_narrow_the_skills_and_space_switches_one(
    _installed: unittest.mock.MagicMock,  # noqa: PT019  -- `mock.patch` hands it over
    homes: Path,
) -> None:
    """A skill is named after the directory it is in, so a space is never part of one."""
    app = Humanize()
    async with app.run_test() as driver:
        await driver.press(*"/agents")
        await driver.press("enter")
        await into_models(app, driver)
        await driver.press("ctrl+s")
        await until(lambda: isinstance(app.screen, Skills), driver)
        sheet = app.screen
        listing = sheet.query_one("#choices", OptionList)
        await until(lambda: bool(listing.options), driver)

        await driver.press(*"hous")
        await driver.pause()
        assert [str(option.id) for option in listing.options] == ["housekeeping"]

        await driver.press("space")  # switched, rather than typed into the search
        await driver.pause()
        assert [str(option.id) for option in listing.options] == ["housekeeping"]
        assert "[ ]" in str(listing.get_option_at_index(0).prompt)

        # Esc clears the search before it leaves, as it does on every other sheet, so what
        # was switched is still switched and the rest of the list is back.
        await driver.press("escape")
        await driver.pause()
        assert [str(option.id) for option in listing.options] == [
            "hf-cli",
            "writing",
            "housekeeping",
        ]
        assert isinstance(app.screen, Skills)

        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Models), driver)
        await driver.press("enter")
        await until(lambda: not isinstance(app.screen, Models), driver)

    assert app._models == [Runs("claude/claude-opus-5:max", "", ("hf-cli", "writing"))]

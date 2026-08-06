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
from hmz.settings import Settings
from hmz.tui import Humanize
from hmz.tui.pick import Agent, Skills

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


def test_kimi_is_read_from_its_own_and_shared_skill_directories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Kimi web discovers the same skill roots as an interactive Kimi session."""
    _write(tmp_path / "kimi-home" / "skills", "its-own")
    _write(tmp_path / "home" / ".agents" / "skills", "shared")
    _write(tmp_path / "project" / ".kimi-code" / "skills", "project-kimi")
    _write(tmp_path / "project" / ".agents" / "skills", "project-agents")
    monkeypatch.setenv("KIMI_CODE_HOME", str(tmp_path / "kimi-home"))
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.chdir(tmp_path / "project")

    assert [one.name for one in skills("kimi")] == [
        "its-own",
        "shared",
        "project-kimi",
        "project-agents",
    ]


def test_grok_is_read_from_its_own_shared_and_compatible_directories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Everything `grok inspect` lists, at both the tiers it lists them at.

    Its own home and the shared one under yours, and the two other harnesses' directories it
    reads for compatibility -- which are on unless somebody turned them off.
    """
    _write(tmp_path / "grok-home" / "skills", "its-own")
    _write(tmp_path / "home" / ".agents" / "skills", "shared")
    _write(tmp_path / "home" / ".claude" / "skills", "claude-compat")
    _write(tmp_path / "home" / ".cursor" / "skills", "cursor-compat")
    _write(tmp_path / "project" / ".grok" / "skills", "project-grok")
    _write(tmp_path / "project" / ".agents" / "skills", "project-agents")
    monkeypatch.setenv("GROK_HOME", str(tmp_path / "grok-home"))
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.chdir(tmp_path / "project")

    assert [one.name for one in skills("grok")] == [
        "its-own",
        "shared",
        "claude-compat",
        "cursor-compat",
        "project-grok",
        "project-agents",
    ]


def test_qwen_is_read_from_its_own_and_shared_skill_directories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`.qwen` and `.agents`, which is the pair its own loader is written in terms of."""
    _write(tmp_path / "qwen-home" / "skills", "its-own")
    _write(tmp_path / "home" / ".agents" / "skills", "shared")
    _write(tmp_path / "project" / ".qwen" / "skills", "project-qwen")
    _write(tmp_path / "project" / ".agents" / "skills", "project-agents")
    monkeypatch.setenv("QWEN_HOME", str(tmp_path / "qwen-home"))
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.chdir(tmp_path / "project")

    assert [one.name for one in skills("qwen")] == [
        "its-own",
        "shared",
        "project-qwen",
        "project-agents",
    ]


@pytest.mark.parametrize(
    ("backend", "under"), [("opencode", "opencode"), ("mimo", "mimocode")]
)
def test_a_backend_keeping_its_skills_by_its_configuration_is_read_there(
    backend: str, under: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Opencode and mimocode keep skills beside their configuration rather than their data.

    Their sessions and their logins are under the data home; a skill is not. So the one that
    is read is the one `XDG_CONFIG_HOME` names, and moving that moves the skills with it.
    """
    _write(tmp_path / "config" / under / "skills", "its-own")
    _write(tmp_path / "config" / under / "skill", "its-own-singular")
    _write(tmp_path / "home" / ".agents" / "skills", "shared")
    _write(tmp_path / "home" / ".claude" / "skills", "claude-compat")
    _write(tmp_path / "project" / f".{under}" / "skills", "project-its-own")
    _write(tmp_path / "project" / ".agents" / "skills", "project-agents")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.chdir(tmp_path / "project")

    assert [one.name for one in skills(backend)] == [
        "its-own",
        "its-own-singular",
        "shared",
        "claude-compat",
        "project-its-own",
        "project-agents",
    ]


def test_a_configuration_home_defaults_to_the_one_under_yours(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`~/.config` is where it is when nothing has moved it, which is the usual case."""
    _write(tmp_path / "home" / ".config" / "opencode" / "skills", "its-own")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.chdir(tmp_path)

    assert [one.name for one in skills("opencode")] == ["its-own"]


def test_pi_is_read_from_the_two_it_loads_without_being_approved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Its own home and the shared one, and nothing under the workspace.

    pi reads `.pi/skills` and `.agents/skills` there too, but only once the project has been
    trusted -- which is `--approve` and somebody to press it, and a driven turn is neither.
    """
    _write(tmp_path / "pi-home" / "skills", "its-own")
    _write(tmp_path / "home" / ".agents" / "skills", "shared")
    _write(tmp_path / "project" / ".pi" / "skills", "untrusted")
    _write(tmp_path / "project" / ".agents" / "skills", "untrusted-shared")
    monkeypatch.setenv("PI_CODING_AGENT_DIR", str(tmp_path / "pi-home"))
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.chdir(tmp_path / "project")

    assert [one.name for one in skills("pi")] == ["its-own", "shared"]


def test_agy_is_read_from_the_root_a_printed_turn_loads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Its own home, and not the workspace: `--print` opens no project to read one from."""
    _write(tmp_path / "home" / ".gemini" / "antigravity-cli" / "skills", "its-own")
    _write(tmp_path / "project" / ".agents" / "skills", "unopened")
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.chdir(tmp_path / "project")

    assert [one.name for one in skills("agy")] == ["its-own"]


def test_a_backend_whose_sdk_carries_none_finds_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The `dsh` command line reads skill directories; the SDK humanize drives does not."""
    _write(tmp_path / "project" / ".dsh" / "skills", "unread")
    _write(tmp_path / "project" / ".agents" / "skills", "unread-shared")
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.chdir(tmp_path / "project")

    assert skills("dsh") == []


def test_an_unknown_backend_finds_no_skills(homes: Path) -> None:
    """A backend Humanize does not know has nowhere to discover a skill from."""
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
async def test_a_cli_with_no_installed_skills_says_so(
    _installed: unittest.mock.MagicMock,  # noqa: PT019  -- `mock.patch` hands it over
    homes: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A supported skill directory with no entries is empty rather than unsupported."""
    monkeypatch.setenv("KIMI_CODE_HOME", str(homes / "kimi-home"))
    monkeypatch.setattr(Path, "home", lambda: homes / "home")
    app = Humanize()
    async with app.run_test() as driver:
        await into_flows(app, driver)
        await into_agent(app, driver)
        await opens(app, driver, "skills")
        await until(lambda: isinstance(app.screen, Skills), driver)
        said = str(app.screen.query_one("#tuning", Label).content)

        assert "kimi has none installed here" in said


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

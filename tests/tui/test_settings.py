"""What a workspace was set up to run, kept so that opening it again finds it that way."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
import yaml

from hmz import home
from hmz.tui.pick import Runs
from hmz.tui.settings import Settings

if TYPE_CHECKING:
    from pathlib import Path


def test_a_workspace_that_has_run_nothing_remembers_nothing(tmp_path: Path) -> None:
    kept = Settings(tmp_path)

    assert kept.flow == ""
    assert kept.agents("chat") == []


def test_what_was_set_up_is_what_is_read_back(tmp_path: Path) -> None:
    """The whole point: a project driven by two agents is driven by them again tomorrow."""
    Settings(tmp_path).remember(
        "rlar",
        ("actor", "reviewer"),
        [Runs("claude/claude-opus-5:high"), Runs("codex/gpt-5.6-sol:xhigh")],
    )

    # A second one, as opening the interface again is.
    again = Settings(tmp_path)
    assert again.flow == "rlar"
    assert again.agents("rlar") == [
        Runs("claude/claude-opus-5:high"),
        Runs("codex/gpt-5.6-sol:xhigh"),
    ]


def test_an_agent_is_kept_under_what_its_flow_calls_it(tmp_path: Path) -> None:
    """So that a flow which grows an agent does not hand the reviewer's model to the builder."""
    Settings(tmp_path).remember(
        "rlar", ("actor", "reviewer"), [Runs("claude/m:high"), Runs("codex/n:low")]
    )
    Settings(tmp_path).remember("chat", ("",), [Runs("kimi/kimi-code/k3:max")])

    held = yaml.safe_load((home() / "settings.yaml").read_text())
    flows = held["workspaces"][str(tmp_path.resolve())]["flows"]

    assert list(flows["rlar"]["agents"]) == ["actor", "reviewer"]
    assert flows["rlar"]["agents"]["reviewer"] == {
        "cli": "codex",
        "model": "n",
        "effort": "low",
        "goals": True,
    }
    # A flow that says only how many it drives has nothing to call them, so they are
    # numbered -- and a model holding slashes of its own survives the round trip.
    assert list(flows["chat"]["agents"]) == ["1"]
    assert flows["chat"]["agents"]["1"]["model"] == "kimi-code/k3"


def test_each_flow_of_a_workspace_is_kept_beside_the_others(tmp_path: Path) -> None:
    """What an agent runs only means anything against the flow that drives it."""
    kept = Settings(tmp_path)
    kept.remember("chat", ("",), [Runs("claude/m:high")])
    kept.remember("ralph_loop", ("",), [Runs("codex/n:low")])

    again = Settings(tmp_path)
    assert again.flow == "ralph_loop"  # the one it was last run with
    assert again.agents("chat") == [
        Runs("claude/m:high")
    ]  # and the other is still there
    assert again.agents("ralph_loop") == [Runs("codex/n:low")]


def test_one_workspace_does_not_take_anothers(tmp_path: Path) -> None:
    (mine := tmp_path / "mine").mkdir()
    (theirs := tmp_path / "theirs").mkdir()
    Settings(mine).remember("chat", ("",), [Runs("claude/m:high")])

    Settings(theirs).remember(
        "rlar", ("a", "b"), [Runs("codex/n:low"), Runs("codex/n:low")]
    )

    assert Settings(mine).flow == "chat"
    assert Settings(mine).agents("chat") == [Runs("claude/m:high")]


@pytest.mark.parametrize(
    "written",
    ["", "not: a mapping of workspaces\n", "[]\n", ": : :\n", "workspaces: 3\n"],
)
def test_a_file_that_is_not_one_is_a_workspace_with_nothing_remembered(
    tmp_path: Path, written: str
) -> None:
    """Never a reason not to open: what it holds is a convenience and not a requirement."""
    home().mkdir(parents=True, exist_ok=True)
    (home() / "settings.yaml").write_text(written)

    kept = Settings(tmp_path)

    assert kept.flow == ""
    assert kept.agents("chat") == []
    kept.remember(
        "chat", ("",), [Runs("claude/m:high")]
    )  # and it is written over rather than kept
    assert Settings(tmp_path).agents("chat") == [Runs("claude/m:high")]


def test_a_home_that_cannot_be_written_is_not_a_reason_to_stop(tmp_path: Path) -> None:
    """An interface that refused to run because it could not remember would be worse."""
    home().mkdir(parents=True, exist_ok=True)
    home().chmod(0o500)
    try:
        Settings(tmp_path).remember("chat", ("",), [Runs("claude/m:high")])
    finally:
        home().chmod(0o700)


def test_where_an_agent_works_is_kept_with_what_it_runs(tmp_path: Path) -> None:
    """So that a project driven against a container is driven against it again tomorrow."""
    Settings(tmp_path).remember(
        "rlar",
        ("actor", "reviewer"),
        [Runs("claude/m:high", "ssh://box"), Runs("codex/n:low")],
    )

    held = yaml.safe_load((home() / "settings.yaml").read_text())
    agents = held["workspaces"][str(tmp_path.resolve())]["flows"]["rlar"]["agents"]
    assert agents["actor"]["anchor"] == "ssh://box"
    # An agent that works here says nothing about a machine, which is what a file written
    # before there were any also says.
    assert "anchor" not in agents["reviewer"]

    assert Settings(tmp_path).agents("rlar") == [
        Runs("claude/m:high", "ssh://box"),
        Runs("codex/n:low"),
    ]


def test_how_a_flow_was_set_up_is_kept_beside_what_its_agents_run(
    tmp_path: Path,
) -> None:
    """A flow of twenty settings is not one to answer again every morning."""
    Settings(tmp_path).remember(
        "humanize1", ("builder",), [Runs("claude/m:high")], {"max": 12, "rlcr": True}
    )

    again = Settings(tmp_path)
    assert again.config("humanize1") == {"max": 12, "rlcr": True}
    held = yaml.safe_load((home() / "settings.yaml").read_text())
    flows = held["workspaces"][str(tmp_path.resolve())]["flows"]
    assert flows["humanize1"]["config"] == {"max": 12, "rlcr": True}


def test_choosing_the_agents_again_is_not_a_way_of_forgetting_the_settings(
    tmp_path: Path,
) -> None:
    """`/agents` says nothing about how the flow itself was set up, so it changes nothing."""
    Settings(tmp_path).remember(
        "humanize1", ("builder",), [Runs("claude/m:high")], {"max": 12}
    )

    Settings(tmp_path).remember("humanize1", ("builder",), [Runs("codex/n:low")])

    assert Settings(tmp_path).config("humanize1") == {"max": 12}


def test_a_flow_that_takes_no_setting_up_keeps_nothing(tmp_path: Path) -> None:
    """Which is most of them, and is what a settings file written before this also says."""
    Settings(tmp_path).remember("chat", ("",), [Runs("claude/m:high")])

    assert Settings(tmp_path).config("chat") == {}


def test_two_flows_of_one_name_are_two_entries(tmp_path: Path) -> None:
    """A flow of yours is called by its path, so it cannot inherit a built-in's setup."""
    Settings(tmp_path).remember(
        "rlar", ("actor",), [Runs("claude/m:high")], {"deep": True}
    )
    Settings(tmp_path).remember(
        ".humanize/flows/rlar.py", ("actor",), [Runs("codex/n:low")], {"deep": False}
    )

    kept = Settings(tmp_path)
    assert kept.config("rlar") == {"deep": True}
    assert kept.config(".humanize/flows/rlar.py") == {"deep": False}
    assert kept.agents("rlar") == [Runs("claude/m:high")]


def test_what_an_agent_may_do_is_kept_and_read_back(tmp_path: Path) -> None:
    """As the anchor and the skills are: written only where it narrows anything.

    A file written before there was such a setting and one for an agent nobody was asked
    about read the same way, which is what leaving it out means.
    """
    kept = Settings(tmp_path)
    kept.remember(
        "rlar",
        ("actor", "reviewer"),
        [Runs("claude/m:high", "", None, "read-only"), Runs("codex/n:low")],
    )

    assert Settings(tmp_path).agents("rlar") == [
        Runs("claude/m:high", "", None, "read-only"),
        Runs("codex/n:low"),
    ]
    held = yaml.safe_load((home() / "settings.yaml").read_text())
    written = held["workspaces"][str(tmp_path.resolve())]["flows"]["rlar"]["agents"]
    assert written["actor"]["permission"] == "read-only"
    assert "permission" not in written["reviewer"]


def test_goal_choices_are_kept_as_on_or_off(tmp_path: Path) -> None:
    kept = Settings(tmp_path)
    kept.remember(
        "rlar",
        ("actor", "reviewer"),
        [Runs("claude/m:high", goals=False), Runs("codex/n:low", goals=True)],
    )

    assert Settings(tmp_path).agents("rlar") == [
        Runs("claude/m:high", goals=False),
        Runs("codex/n:low", goals=True),
    ]
    held = yaml.safe_load((home() / "settings.yaml").read_text())
    agents = held["workspaces"][str(tmp_path.resolve())]["flows"]["rlar"]["agents"]
    assert agents["actor"]["goals"] is False
    assert agents["reviewer"]["goals"] is True


def test_an_old_entry_takes_the_current_agent_place_suggestion(tmp_path: Path) -> None:
    kept = Settings(tmp_path)
    kept.remember("rlar", ("actor",), [Runs("claude/m:high")])
    where = home() / "settings.yaml"
    held = yaml.safe_load(where.read_text())
    agent = held["workspaces"][str(tmp_path.resolve())]["flows"]["rlar"]["agents"][
        "actor"
    ]
    del agent["goals"]
    where.write_text(yaml.safe_dump(held, sort_keys=False))

    assert Settings(tmp_path).agents("rlar", (False,)) == [
        Runs("claude/m:high", goals=False)
    ]
    assert Settings(tmp_path).agents("rlar") == [Runs("claude/m:high", goals=True)]

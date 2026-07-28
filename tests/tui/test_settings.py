"""What a workspace was set up to run, kept so that opening it again finds it that way."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
import yaml

from humanize import home
from humanize.tui.settings import Settings

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
        ["claude/claude-opus-5:high", "codex/gpt-5.6-sol:xhigh"],
    )

    # A second one, as opening the interface again is.
    again = Settings(tmp_path)
    assert again.flow == "rlar"
    assert again.agents("rlar") == [
        "claude/claude-opus-5:high",
        "codex/gpt-5.6-sol:xhigh",
    ]


def test_an_agent_is_kept_under_what_its_flow_calls_it(tmp_path: Path) -> None:
    """So that a flow which grows an agent does not hand the reviewer's model to the builder."""
    Settings(tmp_path).remember(
        "rlar", ("actor", "reviewer"), ["claude/m:high", "codex/n:low"]
    )
    Settings(tmp_path).remember("chat", ("",), ["kimi/kimi-code/k3:max"])

    held = yaml.safe_load((home() / "settings.yaml").read_text())
    flows = held["workspaces"][str(tmp_path.resolve())]["flows"]

    assert list(flows["rlar"]["agents"]) == ["actor", "reviewer"]
    assert flows["rlar"]["agents"]["reviewer"] == {
        "cli": "codex",
        "model": "n",
        "effort": "low",
    }
    # A flow that says only how many it drives has nothing to call them, so they are
    # numbered -- and a model holding slashes of its own survives the round trip.
    assert list(flows["chat"]["agents"]) == ["1"]
    assert flows["chat"]["agents"]["1"]["model"] == "kimi-code/k3"


def test_each_flow_of_a_workspace_is_kept_beside_the_others(tmp_path: Path) -> None:
    """What an agent runs only means anything against the flow that drives it."""
    kept = Settings(tmp_path)
    kept.remember("chat", ("",), ["claude/m:high"])
    kept.remember("ralph_loop", ("",), ["codex/n:low"])

    again = Settings(tmp_path)
    assert again.flow == "ralph_loop"  # the one it was last run with
    assert again.agents("chat") == ["claude/m:high"]  # and the other is still there
    assert again.agents("ralph_loop") == ["codex/n:low"]


def test_one_workspace_does_not_take_anothers(tmp_path: Path) -> None:
    (mine := tmp_path / "mine").mkdir()
    (theirs := tmp_path / "theirs").mkdir()
    Settings(mine).remember("chat", ("",), ["claude/m:high"])

    Settings(theirs).remember("rlar", ("a", "b"), ["codex/n:low", "codex/n:low"])

    assert Settings(mine).flow == "chat"
    assert Settings(mine).agents("chat") == ["claude/m:high"]


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
        "chat", ("",), ["claude/m:high"]
    )  # and it is written over rather than kept
    assert Settings(tmp_path).agents("chat") == ["claude/m:high"]


def test_a_home_that_cannot_be_written_is_not_a_reason_to_stop(tmp_path: Path) -> None:
    """An interface that refused to run because it could not remember would be worse."""
    home().mkdir(parents=True, exist_ok=True)
    home().chmod(0o500)
    try:
        Settings(tmp_path).remember("chat", ("",), ["claude/m:high"])
    finally:
        home().chmod(0o700)

"""Where a conversation works, which is what lets one agent work in several places at once.

A directory is a session's setting rather than a turn's, because that is what it is to these
backends: a conversation is opened at a directory and every turn of it is there. So a flow
with a worktree per task holds a session per worktree, and the turns of them run at the same
time in different places -- which is what is checked here, with real processes in real
directories rather than by reading a command line back.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pytest

from humanize.agents import AgentConfig
from tests.stubs import HereAnchor, ShellAgent

if TYPE_CHECKING:
    from pathlib import Path

CONFIG = AgentConfig(model="m", effort="high")


@pytest.fixture
def worktrees(tmp_path: Path) -> list[Path]:
    """Three directories to work in, each with a file saying which one it is."""
    made: list[Path] = []
    for name in ("one", "two", "three"):
        where = tmp_path / name
        where.mkdir()
        (where / "which.txt").write_text(name)
        made.append(where)
    return made


def test_a_session_opened_at_a_directory_works_in_it(worktrees: list[Path]) -> None:
    session = ShellAgent(CONFIG).new(worktrees[1])

    assert session("pwd") == str(worktrees[1])
    assert session("cat which.txt") == "two"  # and a relative path is that directory's
    assert session.cwd == str(worktrees[1])


def test_a_session_opened_at_nothing_works_where_the_flow_is(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    session = ShellAgent(CONFIG).new()

    assert session("pwd") == str(tmp_path)
    assert session.cwd == str(tmp_path)


def test_one_turn_may_name_the_directory_it_wants(worktrees: list[Path]) -> None:
    """Calling the agent opens a session of its own, so the directory is that session's."""
    agent = ShellAgent(CONFIG)

    assert agent("cat which.txt", cwd=worktrees[0]) == "one"
    assert agent("cat which.txt", cwd=worktrees[2]) == "three"


@pytest.mark.timeout(120, method="thread")
def test_one_agent_works_in_several_places_at_once(worktrees: list[Path]) -> None:
    """The whole point of it: a session per worktree, and their turns running together."""
    agent = ShellAgent(CONFIG)
    held = [agent.new(one) for one in worktrees]

    async def together() -> list[str]:
        return list(
            await asyncio.gather(
                *(one.aturn("sleep 0.1; cat which.txt") for one in held)
            )
        )

    assert asyncio.run(together()) == ["one", "two", "three"]
    # And each conversation stays where it was opened, whichever ran first.
    assert [one.cwd for one in held] == [str(one) for one in worktrees]


def test_a_batch_runs_every_turn_of_it_in_the_directory_it_was_given(
    worktrees: list[Path],
) -> None:
    agent = ShellAgent(CONFIG)

    assert agent.batch(["pwd", "cat which.txt"], cwd=worktrees[2]) == [
        str(worktrees[2]),
        "three",
    ]
    assert [one.cwd for one in agent.batch_new(2, worktrees[0])] == [
        str(worktrees[0])
    ] * 2


def test_a_directory_that_is_not_there_is_said_before_the_turn(tmp_path: Path) -> None:
    """Rather than a backend failing to start in it, which reads as a failed turn."""
    session = ShellAgent(CONFIG).new(tmp_path / "nowhere")

    with pytest.raises(ValueError, match="no directory to open a session in"):
        session("pwd")


def test_an_anchored_session_names_a_directory_on_the_machine_it_lands_on(
    tmp_path: Path,
) -> None:
    """The path is the target's, and what the agent is put in is this machine's mirror of it."""
    workspace, mirror = tmp_path / "workspace", tmp_path / "mirror"
    workspace.mkdir()
    mirror.mkdir()
    anchor = HereAnchor(target="local", workspace=str(workspace), shadow=str(mirror))
    agent = _Anchored(CONFIG, anchor)
    session = agent.new(workspace / "packages" / "one")

    assert session._workspace() == str(mirror / "packages" / "one")
    session("true")
    # The anchor is told where the session works, since it is the anchor that puts the agent
    # there: two supervisors cannot be nested, and only one of them holds the mirror.
    assert anchor.into == [str(workspace / "packages" / "one")]


def test_an_anchored_session_may_not_work_outside_the_workspace(
    tmp_path: Path,
) -> None:
    """What the anchor holds is one workspace; a directory outside it is not there at all."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    anchor = HereAnchor(target="local", workspace=str(workspace))
    session = _Anchored(CONFIG, anchor).new(tmp_path / "elsewhere")

    with pytest.raises(ValueError, match="is not inside"):
        session("true")


class _Anchored(ShellAgent):
    """A shell-backed agent whose turns land on a machine that is really this one."""

    def __init__(self, config: AgentConfig, anchor: HereAnchor) -> None:
        super().__init__(config)
        self._held = anchor

    @property
    def anchor(self) -> HereAnchor:
        return self._held

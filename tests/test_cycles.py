"""One run of one flow, written down: which agents were driven, and what each of them opened.

Nothing else knows that a session was part of a run. The backends log them one at a time, each
under an id of its own, and say nothing about whose they were or what they were for -- so a
trace of a run can only be gathered afterwards if the run itself wrote down what it opened.
"""

from __future__ import annotations

import json
import subprocess
from typing import TYPE_CHECKING

import pytest

from humanize.agents import AgentConfig, Stopped
from humanize.cycle import cycles, opened
from humanize.runner import Runner
from tests.stubs import ShellAgent

if TYPE_CHECKING:
    from pathlib import Path

CONFIG = AgentConfig(model="m", effort="high")

#: A flow that opens one session per agent, each of which names itself as it lands.
FLOW = """
from humanize.agents import AgentBase


def run(agents: tuple[AgentBase, AgentBase], task: str) -> None:
    for at, agent in enumerate(agents):
        agent.new()(f"echo session-{at}")
"""


def _lines(cycle: Path) -> list[dict[str, object]]:
    """Every event of one cycle, in the order it was written."""
    return [json.loads(line) for line in cycle.read_text().splitlines()]


def test_a_run_is_one_cycle_and_says_what_it_opened(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The whole of it: what was run, by whom, at what, and every session that came of it."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "flow.py").write_text(FLOW)
    agents = [
        ShellAgent(CONFIG, name="actor"),
        ShellAgent(CONFIG, name="reviewer"),
    ]

    Runner(tmp_path / "flow.py", agents).run("go")

    (cycle,) = cycles()
    began, *held, ended = _lines(cycle)
    assert began["flow"] == str(tmp_path / "flow.py")
    assert began["task"] == "go"
    assert began["workspace"] == str(tmp_path.resolve())
    assert began["agents"] == [
        {
            "agent": "actor",
            "backend": "shell",
            "model": "m",
            "effort": "high",
            "permission": "bypass",
        },
        {
            "agent": "reviewer",
            "backend": "shell",
            "model": "m",
            "effort": "high",
            "permission": "bypass",
        },
    ]
    assert [(said["agent"], said["session"]) for said in held] == [
        ("actor", "session-0"),
        ("reviewer", "session-1"),
    ]
    assert ended == {"event": "ended", "at": ended["at"], "how": "done"}
    # And what a trace is gathered by: whose each of those sessions was.
    assert opened(cycle) == {"actor": ["session-0"], "reviewer": ["session-1"]}


def test_a_second_run_is_a_second_cycle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A cycle is a run and not a workspace: running the flow again is another run."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "flow.py").write_text(FLOW)

    for _ in range(2):
        Runner(tmp_path / "flow.py", [ShellAgent(CONFIG), ShellAgent(CONFIG)]).run("go")

    assert len(cycles()) == 2


def test_a_run_that_was_interrupted_says_so(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Esc ends a flow, and a cycle that ended that way is not one that finished."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "flow.py").write_text(
        "from humanize.agents import AgentBase, Stopped\n\n\n"
        "def run(agents: tuple[AgentBase], task: str) -> None:\n"
        '    raise Stopped("stopped")\n'
    )

    with pytest.raises(Stopped):
        Runner(tmp_path / "flow.py", [ShellAgent(CONFIG)]).run("go")

    (cycle,) = cycles()
    assert _lines(cycle)[-1]["how"] == "stopped"


def test_a_run_that_failed_says_so(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A turn that failed takes the flow with it, and the cycle says how it went."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "flow.py").write_text(
        "from humanize.agents import AgentBase\n\n\n"
        "def run(agents: tuple[AgentBase], task: str) -> None:\n"
        '    agents[0].new()("exit 3")\n'
    )

    with pytest.raises(subprocess.CalledProcessError):
        Runner(tmp_path / "flow.py", [ShellAgent(CONFIG)]).run("go")

    (cycle,) = cycles()
    assert _lines(cycle)[-1]["how"] == "failed"


def test_the_cycles_of_one_workspace_are_not_another_workspace_s(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """They are kept under the workspace they ran in, which is what looks them up."""
    here, there = tmp_path / "here", tmp_path / "there"
    for where in (here, there):
        where.mkdir()
        (where / "flow.py").write_text(FLOW)
    monkeypatch.chdir(here)
    Runner(here / "flow.py", [ShellAgent(CONFIG), ShellAgent(CONFIG)]).run("go")

    assert len(cycles(here)) == 1
    assert cycles(there) == []


def test_an_agent_driven_by_hand_is_not_a_run_of_anything(tmp_path: Path) -> None:
    """A session opened outside a flow belongs to no cycle, and writes to none."""
    agent = ShellAgent(CONFIG)

    agent.new()("echo alone")

    assert agent.opened == ["alone"]
    assert cycles(tmp_path) == []

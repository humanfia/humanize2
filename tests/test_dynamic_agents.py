"""Agents whose count is learned while a flow is already running."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hmz.agents import AgentConfig
from hmz.cycle import cycles, read
from hmz.runner import Runner
from tests.stubs import ShellAgent, events, written

if TYPE_CHECKING:
    from pathlib import Path


CONFIG = AgentConfig(model="m", effort="high")

DYNAMIC = """
from hmz.flows import Agent, flow, spawn


@flow
def run(agents: tuple[Agent], task: str) -> None:
    experts = spawn(agents[0], (f"expert-{at + 1}" for at in range(int(task))))
    for at, expert in enumerate(experts):
        expert.new()(f"echo specialist-{at + 1}")
"""


def test_a_flow_spawns_the_number_of_agents_it_learns_at_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    written(tmp_path, "dynamic", DYNAMIC)

    template = ShellAgent(CONFIG, name="expert-template")
    runner = Runner(tmp_path / "dynamic", [template])
    runner.run("3")

    (cycle,) = cycles()
    ran = read(cycle)
    assert ran is not None
    assert [agent.agent for agent in ran.agents] == [
        "expert-template",
        "expert-1",
        "expert-2",
        "expert-3",
    ]
    assert [session.agent for session in ran.sessions] == [
        "expert-1",
        "expert-2",
        "expert-3",
    ]
    spawned = [event for event in events(cycle) if event["event"] == "spawned"]
    assert [event["parent"] for event in spawned] == ["expert-template"] * 3
    assert [event["agent"]["agent"] for event in spawned] == [
        "expert-1",
        "expert-2",
        "expert-3",
    ]
    assert [agent.id for agent in runner.agents] == [
        "expert-template",
        "expert-1",
        "expert-2",
        "expert-3",
    ]
    assert not template.stopped
    assert all(agent.stopped for agent in runner.agents[1:])


def test_zero_runtime_agents_is_a_valid_fan_out(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    written(tmp_path, "dynamic", DYNAMIC)
    runner = Runner(tmp_path / "dynamic", [ShellAgent(CONFIG, name="expert-template")])

    runner.run("0")

    assert [agent.id for agent in runner.agents] == ["expert-template"]
    (cycle,) = cycles()
    assert not any(event["event"] == "spawned" for event in events(cycle))


def test_a_runner_can_be_reused_for_another_runtime_fan_out(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    written(tmp_path, "dynamic", DYNAMIC)
    runner = Runner(tmp_path / "dynamic", [ShellAgent(CONFIG, name="expert-template")])

    runner.run("0")
    runner.run("1")

    assert [agent.id for agent in runner.agents] == ["expert-template", "expert-1"]
    assert runner.agents[1].stopped


def test_a_runtime_name_cannot_collide_with_a_declared_agent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    written(
        tmp_path,
        "collision",
        """
from hmz.flows import Agent, flow, spawn


@flow
def run(agents: tuple[Agent], task: str) -> None:
    spawn(agents[0], ("expert-template", "another"))
""",
    )
    runner = Runner(
        tmp_path / "collision", [ShellAgent(CONFIG, name="expert-template")]
    )

    with pytest.raises(ValueError, match="already in this run"):
        runner.run("go")

    assert [agent.id for agent in runner.agents] == ["expert-template"]


def test_agents_spawned_by_a_called_flow_belong_to_the_root_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    local = tmp_path / ".humanize" / "flows"
    written(
        local,
        "inner",
        """
from hmz.flows import Agent, flow, spawn


@flow
def run(agents: tuple[Agent], task: str) -> None:
    spawn(agents[0], ("nested-expert",))[0].new()("echo nested")
""",
    )
    written(
        local,
        "outer",
        """
from hmz.flows import Agent, flow, load


@flow
def run(agents: tuple[Agent], task: str) -> None:
    load("inner")(agents, task)
""",
    )
    runner = Runner("outer", [ShellAgent(CONFIG, name="expert-template")])

    runner.run("go")

    assert [agent.id for agent in runner.agents] == [
        "expert-template",
        "nested-expert",
    ]
    assert runner.agents[1].stopped
    (cycle,) = cycles()
    ran = read(cycle)
    assert ran is not None
    assert [agent.agent for agent in ran.agents] == [
        "expert-template",
        "nested-expert",
    ]
    assert [session.agent for session in ran.sessions] == ["nested-expert"]


def test_an_agent_spawned_after_stop_is_stopped_before_the_flow_can_run_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    written(
        tmp_path,
        "late",
        """
import time
from pathlib import Path

from hmz.flows import Agent, flow, spawn


@flow
def run(agents: tuple[Agent], task: str) -> None:
    while not Path("spawn-now").exists():
        time.sleep(0.01)
    late = spawn(agents[0], ("late-expert",))[0]
    Path("late-stopped").write_text(str(late.stopped))
""",
    )
    from hmz.sdk.running import Run

    running = Run(
        Runner(tmp_path / "late", [ShellAgent(CONFIG, name="expert-template")]),
        "go",
    )
    running.start()
    running.stop()
    (tmp_path / "spawn-now").touch()

    assert running.wait(5)
    assert running.raised is None
    assert (tmp_path / "late-stopped").read_text() == "True"
    assert [agent.id for agent in running.agents] == [
        "expert-template",
        "late-expert",
    ]


def test_spawn_refuses_ambiguous_agent_names() -> None:
    from hmz.flows import spawn

    template = ShellAgent(CONFIG, name="expert-template")
    with pytest.raises(ValueError, match="must be unique"):
        spawn(template, ("expert", "expert"))
    with pytest.raises(ValueError, match="must not be empty"):
        spawn(template, ("",))

"""The command line: a flow file, the agents it declares, and the task they are given.

Nothing here drives a real agent. A flow is handed agents and decides for itself whether to
launch anything, so a flow that only writes down what it was given exercises the whole path
from the command line to the entry point without a turn being run.
"""

from __future__ import annotations

import json
import re
import runpy
import shlex
import sys
from pathlib import Path
from typing import Any

import pytest

from amflows.janus import AgentConfig, NotAFlow, Runner
from amflows.janus.cli import main
from tests.janus.conftest import ShellAgent

#: A flow that drives nothing and writes down what it was handed, next to its own file. AGENTS
#: is filled in per test: what a flow declares there is how many agents it takes.
RECORD = """
import json
import os
from pathlib import Path

from amflows.janus import AgentBase


def run(agents: tuple[AGENTS], task: str) -> None:
    Path(__file__).with_suffix(".json").write_text(
        json.dumps(
            {
                "agents": [
                    [type(a).__name__, a.config.model, a.config.effort, a.id] for a in agents
                ],
                "held": type(agents).__name__,
                "task": task,
                "cwd": os.getcwd(),
            }
        )
    )
"""

#: A flow that declares its agents where only a type checker looks, which is nowhere the count
#: it declares can be read back from.
UNREADABLE = """
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from amflows.janus import AgentBase


def run(agents: tuple[AgentBase], task: str) -> None:
    pass
"""

EXAMPLES = sorted((Path(__file__).resolve().parents[2] / "examples").glob("*.py"))


def _flow(tmp_path: Path, source: str) -> str:
    """Writes a flow file and returns its path, as the command line would be given it."""
    path = tmp_path / "flow.py"
    path.write_text(source)
    return str(path)


def _seen(tmp_path: Path) -> dict[str, Any]:
    """Reads back what the flow written by :data:`RECORD` was handed."""
    return json.loads((tmp_path / "flow.json").read_text())


def test_it_drives_the_flow_with_the_agents_the_command_line_names(
    tmp_path: Path,
) -> None:
    """A model may hold slashes of its own, so only the backend and the effort are split off."""
    flow = _flow(tmp_path, RECORD.replace("AGENTS", "AgentBase, AgentBase"))
    main(
        [
            "-f",
            flow,
            "-a",
            "claude/claude-opus-4-8/high,kimi/kimi-code/k3/swarmmax",
            "fix the build",
        ]
    )
    seen = _seen(tmp_path)
    assert [agent[:3] for agent in seen["agents"]] == [
        ["ClaudeCodeAgent", "claude-opus-4-8", "high"],
        ["KimiCodeCLIAgent", "kimi-code/k3", "swarmmax"],
    ]
    assert seen["task"] == "fix the build"
    assert seen["held"] == "tuple"  # a flow unpacks what it was promised


def test_the_agents_may_be_given_in_one_option_or_several(tmp_path: Path) -> None:
    flow = _flow(tmp_path, RECORD.replace("AGENTS", "AgentBase, AgentBase, AgentBase"))
    main(["-f", flow, "-a", "claude/m/high,codex/m/high", "-a", "kimi/m/high", "task"])
    assert [agent[0] for agent in _seen(tmp_path)["agents"]] == [
        "ClaudeCodeAgent",
        "CodexAgent",
        "KimiCodeCLIAgent",
    ]


def test_two_agents_of_one_spelling_are_two_agents(tmp_path: Path) -> None:
    """An actor and the reviewer reading its work are one configuration and not one agent."""
    flow = _flow(tmp_path, RECORD.replace("AGENTS", "AgentBase, AgentBase"))
    main(["-f", flow, "-a", "claude/m/high,claude/m/high", "task"])
    ids = {agent[3] for agent in _seen(tmp_path)["agents"]}
    assert len(ids) == 2


def test_the_flow_runs_where_the_command_was_given(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """And not where the flow file happens to live: the work lands in this project."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    flow = _flow(tmp_path, RECORD.replace("AGENTS", "AgentBase"))
    monkeypatch.chdir(workspace)
    main(["-f", flow, "-a", "claude/m/high", "task"])
    assert Path(_seen(tmp_path)["cwd"]).resolve() == workspace.resolve()


@pytest.mark.parametrize(
    ("source", "complaint"),
    [
        ("flow = None\n", "run(agents, task)"),
        ("def run(agents, task):\n    pass\n", "tuple"),
        (RECORD.replace("AGENTS", "AgentBase, ..."), "fixed length"),
        (RECORD.replace("AGENTS", "AgentBase, AgentBase"), "drives 2 agents, 1 given"),
        (UNREADABLE, "cannot be read here"),
    ],
)
def test_a_file_that_is_not_the_flow_asked_for_is_a_usage_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], source: str, complaint: str
) -> None:
    with pytest.raises(SystemExit) as stopped:
        main(["-f", _flow(tmp_path, source), "-a", "claude/m/high", "task"])
    assert stopped.value.code == 2
    assert complaint in capsys.readouterr().err
    assert not (tmp_path / "flow.json").exists()  # refused before anything was driven


def test_a_flow_that_is_not_there_is_a_usage_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as stopped:
        main(["-f", str(tmp_path / "nowhere.py"), "-a", "claude/m/high", "task"])
    assert stopped.value.code == 2
    assert "nowhere.py" in capsys.readouterr().err


@pytest.mark.parametrize(
    "spec",
    ["claude/claude-opus-4-8", "claude", "gemini/g/high", "/m/high", "claude/m/"],
)
def test_an_agent_that_is_not_backend_model_and_effort_is_a_usage_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], spec: str
) -> None:
    flow = _flow(tmp_path, RECORD.replace("AGENTS", "AgentBase"))
    with pytest.raises(SystemExit) as stopped:
        main(["-f", flow, "-a", spec, "task"])
    assert stopped.value.code == 2
    assert f"bad agent {spec!r}" in capsys.readouterr().err


def test_a_flow_fails_as_it_would_anywhere_when_it_is_the_flow_that_failed(
    tmp_path: Path,
) -> None:
    """A flow whose own setup cannot find a file has not been mistyped on the command line."""
    flow = _flow(tmp_path, "open('nowhere/prompt.md')\n")
    with pytest.raises(FileNotFoundError):
        main(["-f", flow, "-a", "claude/m/high", "task"])


def test_a_flow_for_other_agents_than_these_is_refused_before_it_is_run(
    tmp_path: Path,
) -> None:
    """What the usage error is made of, for a flow driven from Python instead."""
    flow = _flow(tmp_path, RECORD.replace("AGENTS", "AgentBase, AgentBase"))
    with pytest.raises(NotAFlow):
        Runner(flow, [ShellAgent(AgentConfig(model="m", effort="high"))])


def test_python_m_amflows_janus_is_the_run_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    flow = _flow(tmp_path, RECORD.replace("AGENTS", "AgentBase"))
    monkeypatch.setattr(
        sys, "argv", ["amflows run", "-f", flow, "-a", "claude/m/high", "task"]
    )
    runpy.run_module("amflows.janus", run_name="__main__")
    assert _seen(tmp_path)["task"] == "task"


@pytest.mark.parametrize("flow", EXAMPLES, ids=lambda flow: flow.name)
def test_every_example_runs_as_the_command_line_it_shows(
    flow: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each example shows an `amflows run` line, and it is one that would start that flow."""
    shown = re.search(r"^\s*amflows run (?:.*\\\n)*.*", flow.read_text(), re.MULTILINE)
    assert shown is not None, "no `amflows run` command line to be checked against"
    monkeypatch.chdir(flow.parent.parent)  # the paths it shows are this project's own
    monkeypatch.setattr(Runner, "run", lambda self, task: None)  # nothing is driven
    main(shlex.split(shown[0].replace("\\\n", " "))[2:])

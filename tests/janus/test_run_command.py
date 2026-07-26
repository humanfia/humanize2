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

from amflows.cli import main
from amflows.janus import AgentConfig, NotAFlow, Runner
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

#: The flows amflows comes with, each of which shows the line that would start it.
PREBUILT = sorted(
    path
    for path in (Path(__file__).resolve().parents[2] / "src/amflows/janus/flows").glob(
        "*.py"
    )
    if not path.stem.startswith("_")
)


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
            "run",
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
    main(
        [
            "run",
            "-f",
            flow,
            "-a",
            "claude/m/high,codex/m/high",
            "-a",
            "kimi/m/high",
            "task",
        ]
    )
    assert [agent[0] for agent in _seen(tmp_path)["agents"]] == [
        "ClaudeCodeAgent",
        "CodexAgent",
        "KimiCodeCLIAgent",
    ]


def test_two_agents_of_one_spelling_are_two_agents(tmp_path: Path) -> None:
    """An actor and the reviewer reading its work are one configuration and not one agent."""
    flow = _flow(tmp_path, RECORD.replace("AGENTS", "AgentBase, AgentBase"))
    main(["run", "-f", flow, "-a", "claude/m/high,claude/m/high", "task"])
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
    main(["run", "-f", flow, "-a", "claude/m/high", "task"])
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
        main(["run", "-f", _flow(tmp_path, source), "-a", "claude/m/high", "task"])
    assert stopped.value.code == 2
    assert complaint in capsys.readouterr().err
    assert not (tmp_path / "flow.json").exists()  # refused before anything was driven


def test_a_flow_that_is_not_there_is_a_usage_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as stopped:
        main(["run", "-f", str(tmp_path / "nowhere.py"), "-a", "claude/m/high", "task"])
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
        main(["run", "-f", flow, "-a", spec, "task"])
    assert stopped.value.code == 2
    assert f"bad agent {spec!r}" in capsys.readouterr().err


def test_a_flow_fails_as_it_would_anywhere_when_it_is_the_flow_that_failed(
    tmp_path: Path,
) -> None:
    """A flow whose own setup cannot find a file has not been mistyped on the command line."""
    flow = _flow(tmp_path, "open('nowhere/prompt.md')\n")
    with pytest.raises(FileNotFoundError):
        main(["run", "-f", flow, "-a", "claude/m/high", "task"])


def test_a_flow_for_other_agents_than_these_is_refused_before_it_is_run(
    tmp_path: Path,
) -> None:
    """What the usage error is made of, for a flow driven from Python instead."""
    flow = _flow(tmp_path, RECORD.replace("AGENTS", "AgentBase, AgentBase"))
    with pytest.raises(NotAFlow):
        Runner(flow, [ShellAgent(AgentConfig(model="m", effort="high"))])


def test_python_m_amflows_is_the_amflows_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    flow = _flow(tmp_path, RECORD.replace("AGENTS", "AgentBase"))
    monkeypatch.setattr(
        sys, "argv", ["amflows", "run", "-f", flow, "-a", "claude/m/high", "task"]
    )
    with pytest.raises(SystemExit) as stopped:
        runpy.run_module("amflows", run_name="__main__")
    assert stopped.value.code == 0
    assert _seen(tmp_path)["task"] == "task"


@pytest.mark.parametrize("flow", PREBUILT, ids=lambda flow: flow.name)
def test_every_example_runs_as_the_command_line_it_shows(
    flow: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each one shows an `amflows run` line, and it is one that would start that flow."""
    shown = re.search(r"^\s*amflows run (?:.*\\\n)*.*", flow.read_text(), re.MULTILINE)
    assert shown is not None, "no `amflows run` command line to be checked against"
    monkeypatch.chdir(Path(__file__).resolve().parents[2])
    monkeypatch.setattr(Runner, "run", lambda self, task: None)  # nothing is driven
    main(shlex.split(shown[0].replace("\\\n", " "))[1:])


def test_a_flow_of_your_own_is_found_where_flows_live(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Nearest wins: this project, then yours, then the ones amflows came with.

    A flow written down beside the traces is one amflows knows about without being told
    where it is -- and one taking a built-in's name stands in for it, which is what makes
    a project able to mean its own `rlar` by `rlar`.
    """
    from amflows.janus.flows import find, found

    home, project = tmp_path / "home", tmp_path / "project"
    for where in (home / ".amflows/flows", project / ".amflows/flows"):
        where.mkdir(parents=True)
    mine = RECORD.replace("AGENTS", "AgentBase")
    (home / ".amflows/flows/yours.py").write_text(mine)
    (project / ".amflows/flows/theirs.py").write_text(mine)
    (project / ".amflows/flows/rlar.py").write_text(mine)  # a name amflows uses
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.chdir(project)

    listed = found()

    assert ("this project", "theirs") in listed
    assert ("yours", "yours") in listed
    # Shadowed rather than listed twice: one name, and it is the nearest that answers to it.
    assert ("this project", "rlar") in listed
    assert ("amflows", "rlar") not in listed
    assert find("rlar") == str((project / ".amflows/flows/rlar.py").resolve())
    assert find("yours") == str((home / ".amflows/flows/yours.py").resolve())
    assert find("goal").endswith("src/amflows/janus/flows/goal.py")
    assert find("nowhere") == "nowhere"  # a path is taken as given


def test_a_flow_of_your_own_runs_by_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The point of finding it: `-f theirs` starts it, with no path said anywhere."""
    project = tmp_path / "project"
    (project / ".amflows/flows").mkdir(parents=True)
    (project / ".amflows/flows/theirs.py").write_text(
        RECORD.replace("AGENTS", "AgentBase")
    )
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.chdir(project)
    driven: list[str] = []
    monkeypatch.setattr(Runner, "run", lambda self, task: driven.append(task))

    assert main(["run", "-f", "theirs", "-a", "claude/m/high", "do it"]) == 0
    assert driven == ["do it"]


def test_a_failed_turn_is_taken_again_and_only_that_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A round is hours and a review is one question about it, so they retry separately.

    Letting a failed review send the round back would pay for the expensive half twice to
    recover from the cheap half.
    """
    import subprocess as sub

    from amflows.janus.flows.rlcr import spoken

    monkeypatch.setattr("time.sleep", lambda _: None)
    taken: list[str] = []

    class _Flaky:
        def run(self, prompt: str) -> str:
            taken.append(prompt)
            if len(taken) == 1:
                raise sub.CalledProcessError(1, ["claude"])
            if len(taken) == 2:
                # How a streaming backend says its process died, which the builder runs on.
                raise RuntimeError("the agent is no longer listening")
            # Exited clean having said nothing, which is not an answer either: forwarding it
            # would spend a round asking the other side to reply to silence.
            return "" if len(taken) == 3 else "answered"

    assert spoken(_Flaky(), "do it") == "answered"
    assert taken == ["do it"] * 4  # the same turn, four times, and no other


@pytest.mark.parametrize(
    ("said", "accepted"),
    [
        ("COMPLETE", True),
        ("complete.\n", True),
        ("AC-1 has no negative test.", False),
        # A review that quotes the word back while saying what it would take to earn it. Read
        # a line at a time this would end the run; read whole, it is what it is -- a review.
        (
            "Answer with the single word\nCOMPLETE\nif it holds. It does not: AC-2.",
            False,
        ),
    ],
)
def test_only_a_review_that_is_the_word_accepts_the_work(
    said: str, accepted: bool
) -> None:
    """Nothing between the two agents parses anything, so one word has to carry the verdict."""
    from amflows.janus.flows.rlcr import ACCEPTED

    assert bool(ACCEPTED.fullmatch(said)) is accepted

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

from humanize.cli import main
from humanize.janus import AgentConfig, NotAFlow, Runner
from tests.janus.conftest import ShellAgent

#: A flow that drives nothing and writes down what it was handed, next to its own file. AGENTS
#: is filled in per test: what a flow declares there is how many agents it takes.
RECORD = """
import json
import os
from pathlib import Path

from humanize.janus import AgentBase


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

#: The same flow, declaring its agents as a named tuple: as many as there are places, and what
#: each of them is for. It reaches them by name to prove it was handed the type it asked for.
NAMED = """
import json
import os
from pathlib import Path
from typing import NamedTuple

from humanize.janus import AgentBase


class Agents(NamedTuple):
    builder: AgentBase
    reviewer: AgentBase


def run(agents: Agents, task: str) -> None:
    Path(__file__).with_suffix(".json").write_text(
        json.dumps(
            {
                "agents": [[agents.builder.id], [agents.reviewer.id]],
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
    from humanize.janus import AgentBase


def run(agents: tuple[AgentBase], task: str) -> None:
    pass
"""

#: The flows humanize comes with, each of which shows the line that would start it.
PREBUILT = sorted(
    path
    for path in (Path(__file__).resolve().parents[2] / "src/humanize/flows").glob(
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
            "exec",
            "-f",
            flow,
            "-a",
            "claude/claude-opus-4-8:high",
            "-a",
            "kimi/kimi-code/k3:swarmmax",
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


def test_one_option_is_one_agent_however_it_is_written(tmp_path: Path) -> None:
    flow = _flow(tmp_path, RECORD.replace("AGENTS", "AgentBase, AgentBase, AgentBase"))
    main(
        [
            "exec",
            "-f",
            flow,
            "-a",
            "cli=claude,model=m,effort=high",
            "-a",
            "codex/m:high",
            "-a",
            "kimi/m:high",
            "task",
        ]
    )
    assert [agent[0] for agent in _seen(tmp_path)["agents"]] == [
        "ClaudeCodeAgent",
        "CodexAgent",
        "KimiCodeCLIAgent",
    ]


def test_a_named_tuple_says_what_each_agent_is_for_as_well_as_how_many(
    tmp_path: Path,
) -> None:
    """A flow that named its agents is handed the type it asked for, and they answer to it."""
    from humanize.janus.runner import drives

    flow = _flow(tmp_path, NAMED)
    assert drives(flow) == ("builder", "reviewer")

    main(["exec", "-f", flow, "-a", "claude/m:high", "-a", "codex/m:high", "task"])

    seen = _seen(tmp_path)
    assert seen["held"] == "Agents"  # the named tuple, not a plain one
    # And the agents took those names, so a trace groups each one's sessions under a word
    # rather than under a hex tail.
    assert seen["agents"] == [["builder"], ["reviewer"]]


#: A flow that says one of the agents it drives is the person at the prompt.
PEOPLED = """
import json
import os
from pathlib import Path
from typing import NamedTuple

from humanize.janus import AgentBase, HumanAgent


class Agents(NamedTuple):
    assistant: AgentBase
    human: HumanAgent


def run(agents: Agents, task: str) -> None:
    agents.human.prompting = ["", "and then this"].pop
    Path(__file__).with_suffix(".json").write_text(
        json.dumps(
            {
                "agents": [[type(a).__name__, a.id] for a in agents],
                "held": type(agents).__name__,
                "said": [agents.human(task), agents.human(task)],
                "task": task,
                "cwd": os.getcwd(),
            }
        )
    )
"""


def test_the_person_at_the_prompt_is_an_agent_nobody_is_asked_to_configure(
    tmp_path: Path,
) -> None:
    """A flow says it talks to them; it is handed one, and what they answer with is typed."""
    from humanize.janus.runner import drives

    flow = _flow(tmp_path, PEOPLED)
    # Two places, one of them the person -- so one agent is asked for and one is given.
    assert drives(flow) == ("assistant",)

    main(["exec", "-f", flow, "-a", "claude/m:high", "task"])

    seen = _seen(tmp_path)
    assert seen["agents"] == [["ClaudeCodeAgent", "assistant"], ["HumanAgent", "human"]]
    # Said to like any other agent, and its answer is what was typed -- then "" for a
    # conversation that is over, which is what ends a flow that is one.
    assert seen["said"] == ["and then this", ""]


def test_a_plain_tuple_says_how_many_agents_and_nothing_more(tmp_path: Path) -> None:
    from humanize.janus.runner import drives

    assert drives(
        _flow(tmp_path, RECORD.replace("AGENTS", "AgentBase, AgentBase"))
    ) == (
        "",
        "",
    )


def test_two_agents_of_one_spelling_are_two_agents(tmp_path: Path) -> None:
    """An actor and the reviewer reading its work are one configuration and not one agent."""
    flow = _flow(tmp_path, RECORD.replace("AGENTS", "AgentBase, AgentBase"))
    main(["exec", "-f", flow, "-a", "claude/m:high", "-a", "claude/m:high", "task"])
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
    main(["exec", "-f", flow, "-a", "claude/m:high", "task"])
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
        main(["exec", "-f", _flow(tmp_path, source), "-a", "claude/m:high", "task"])
    assert stopped.value.code == 2
    assert complaint in capsys.readouterr().err
    assert not (tmp_path / "flow.json").exists()  # refused before anything was driven


def test_a_flow_that_is_not_there_is_a_usage_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as stopped:
        main(
            ["exec", "-f", str(tmp_path / "nowhere.py"), "-a", "claude/m:high", "task"]
        )
    assert stopped.value.code == 2
    assert "nowhere.py" in capsys.readouterr().err


@pytest.mark.parametrize(
    "spec",
    [
        "claude/claude-opus-4-8",
        "claude",
        "gemini/g:high",
        "/m:high",
        "claude/m:",
        "cli=claude,model=m,effort=high,mode=x",
    ],
)
def test_an_agent_that_is_not_cli_model_and_effort_is_a_usage_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], spec: str
) -> None:
    flow = _flow(tmp_path, RECORD.replace("AGENTS", "AgentBase"))
    with pytest.raises(SystemExit) as stopped:
        main(["exec", "-f", flow, "-a", spec, "task"])
    assert stopped.value.code == 2
    assert f"bad agent {spec!r}" in capsys.readouterr().err


def test_a_flow_fails_as_it_would_anywhere_when_it_is_the_flow_that_failed(
    tmp_path: Path,
) -> None:
    """A flow whose own setup cannot find a file has not been mistyped on the command line."""
    flow = _flow(tmp_path, "open('nowhere/prompt.md')\n")
    with pytest.raises(FileNotFoundError):
        main(["exec", "-f", flow, "-a", "claude/m:high", "task"])


def test_a_flow_for_other_agents_than_these_is_refused_before_it_is_run(
    tmp_path: Path,
) -> None:
    """What the usage error is made of, for a flow driven from Python instead."""
    flow = _flow(tmp_path, RECORD.replace("AGENTS", "AgentBase, AgentBase"))
    with pytest.raises(NotAFlow):
        Runner(flow, [ShellAgent(AgentConfig(model="m", effort="high"))])


def test_python_m_humanize_is_the_humanize_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    flow = _flow(tmp_path, RECORD.replace("AGENTS", "AgentBase"))
    monkeypatch.setattr(
        sys, "argv", ["hmz", "exec", "-f", flow, "-a", "claude/m:high", "task"]
    )
    with pytest.raises(SystemExit) as stopped:
        runpy.run_module("humanize", run_name="__main__")
    assert stopped.value.code == 0
    assert _seen(tmp_path)["task"] == "task"


@pytest.mark.parametrize("flow", PREBUILT, ids=lambda flow: flow.name)
def test_every_example_runs_as_the_command_line_it_shows(
    flow: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each one shows an `hmz exec` line, and it is one that would start that flow."""
    shown = re.search(r"^\s*hmz exec (?:.*\\\n)*.*", flow.read_text(), re.MULTILINE)
    assert shown is not None, "no `hmz exec` command line to be checked against"
    monkeypatch.chdir(Path(__file__).resolve().parents[2])
    monkeypatch.setattr(Runner, "run", lambda self, task: None)  # nothing is driven
    main(shlex.split(shown[0].replace("\\\n", " "))[1:])


def test_a_flow_of_your_own_is_found_where_flows_live(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Nearest wins: this project, then yours, then the ones humanize came with.

    A flow written down beside the traces is one humanize knows about without being told
    where it is -- and one taking a built-in's name stands in for it, which is what makes
    a project able to mean its own `rlar` by `rlar`.
    """
    from humanize.flows import find, found

    home, project = tmp_path / "home", tmp_path / "project"
    for where in (home / ".humanize/flows", project / ".humanize/flows"):
        where.mkdir(parents=True)
    mine = RECORD.replace("AGENTS", "AgentBase")
    (home / ".humanize/flows/yours.py").write_text(mine)
    (project / ".humanize/flows/theirs.py").write_text(mine)
    (project / ".humanize/flows/rlar.py").write_text(mine)  # a name humanize uses
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.chdir(project)

    listed = found()

    assert ("local", "theirs") in listed
    assert ("user", "yours") in listed
    # Shadowed rather than listed twice: one name, and it is the nearest that answers to it.
    assert ("local", "rlar") in listed
    assert ("builtin", "rlar") not in listed
    assert find("rlar") == str((project / ".humanize/flows/rlar.py").resolve())
    assert find("yours") == str((home / ".humanize/flows/yours.py").resolve())
    assert find("goal").endswith("src/humanize/flows/goal.py")
    assert find("nowhere") == "nowhere"  # a path is taken as given


def test_a_flow_of_your_own_runs_by_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The point of finding it: `-f theirs` starts it, with no path said anywhere."""
    project = tmp_path / "project"
    (project / ".humanize/flows").mkdir(parents=True)
    (project / ".humanize/flows/theirs.py").write_text(
        RECORD.replace("AGENTS", "AgentBase")
    )
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.chdir(project)
    driven: list[str] = []
    monkeypatch.setattr(Runner, "run", lambda self, task: driven.append(task))

    assert main(["exec", "-f", "theirs", "-a", "claude/m:high", "do it"]) == 0
    assert driven == ["do it"]


def test_a_failed_turn_is_taken_again_and_only_that_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A round is hours and a review is one question about it, so they retry separately.

    Letting a failed review send the round back would pay for the expensive half twice to
    recover from the cheap half.
    """
    import subprocess as sub

    from humanize.flows.humanize1 import spoken

    monkeypatch.setattr("time.sleep", lambda _: None)
    taken: list[str] = []

    class _Flaky:
        def __call__(self, prompt: str, *, suppress: bool = False) -> str:
            taken.append(prompt)
            if len(taken) <= 2:
                if not suppress:
                    # The flow has to ask for the turn suppressed, or a loop that runs for
                    # days ends on the first turn that failed.
                    raise sub.CalledProcessError(1, ["claude"])
                return ""  # what a suppressed turn that failed answers with
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
    from humanize.flows.humanize1 import ACCEPTED

    assert bool(ACCEPTED.fullmatch(said)) is accepted


def test_the_chat_flow_is_one_session_for_as_long_as_it_is_told_things(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Talking to a coding agent, with no loop around it: the turns are a conversation."""
    from humanize.flows.chat import Chat
    from humanize.flows.chat import run as chat
    from humanize.janus import HumanAgent

    agent = ShellAgent(AgentConfig(model="m", effort="high"))
    said = ["echo third", "echo second"]
    # The person is an agent like any other, and what they answer with is what they typed.
    person = HumanAgent()
    person.prompting = said.pop

    chat(Chat(agent, person), "echo first")

    # One session for all three, so the agent had the earlier turns in context: a second
    # would have opened a second id. And the run ended when there was nothing left to be
    # told, rather than looping on nothing.
    assert len(agent.opened) == 1
    assert said == []


def test_the_chat_flow_run_from_a_command_line_does_the_one_thing_it_was_given(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Nobody is at a prompt there, so there is nothing to wait for and it returns."""
    from humanize.flows.chat import Chat
    from humanize.flows.chat import run as chat
    from humanize.janus import HumanAgent

    agent = ShellAgent(AgentConfig(model="m", effort="high"))

    # Nothing is hooked up to the person, so they answer with nothing the first time.
    chat(Chat(agent, HumanAgent()), "echo once")

    assert len(agent.opened) == 1

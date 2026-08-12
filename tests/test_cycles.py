"""One run of one flow, written down: which agents were driven, and what each of them opened.

Nothing else knows that a session was part of a run. The backends log them one at a time, each
under an id of its own, and say nothing about whose they were, which account took their turns
or what they were for -- so a trace of a run can only be gathered afterwards if the run itself
wrote down what it opened, and a person can only find the logs of one if the run points at
them.
"""

from __future__ import annotations

import json
import subprocess
from typing import TYPE_CHECKING, Any

import pytest

from hmz.agents import AgentConfig, Stopped
from hmz.cycle import JOURNAL, called, cycles, linked, opened, read, sessions
from hmz.runner import Runner
from tests.stubs import ShellAgent, events, written

if TYPE_CHECKING:
    from pathlib import Path

CONFIG = AgentConfig(model="m", effort="high")

#: A flow that opens one session per agent, each of which names itself as it lands.
FLOW = """
from hmz.agents import AgentBase
from hmz.flows import flow


@flow
def run(agents: tuple[AgentBase, AgentBase], task: str) -> None:
    for at, agent in enumerate(agents):
        agent.new()(f"echo session-{at}")
"""

#: The same, for a flow that drives one agent.
ONE = """
from hmz.agents import AgentBase
from hmz.flows import flow


@flow
def run(agents: tuple[AgentBase], task: str) -> None:
    agents[0].new()("echo the-session")
"""


class ClaudeAgent(ShellAgent):
    """A stand-in that answers to a backend humanize knows where the logs of."""


def _lines(cycle: Path) -> list[dict[str, Any]]:
    """Every event of one cycle, in the order it was written."""
    return events(cycle)


def test_a_run_is_one_cycle_and_says_what_it_opened(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The whole of it: what was run, by whom, at what, and every session that came of it."""
    monkeypatch.chdir(tmp_path)
    written(tmp_path, "flow", FLOW)
    agents = [
        ShellAgent(CONFIG, name="actor"),
        ShellAgent(CONFIG, name="reviewer"),
    ]

    Runner(tmp_path / "flow", agents).run("go")

    (cycle,) = cycles()
    began, *held, ended = _lines(cycle)
    assert began["flow"] == str(tmp_path / "flow")
    assert began["task"] == "go"
    assert began["workspace"] == str(tmp_path.resolve())
    assert began["agents"] == [
        {
            "agent": "actor",
            "backend": "shell",
            "model": "m",
            "effort": "high",
            "service_tier": "default",
            "permission": "bypass",
            "provider": "",
            "goals": True,
            "person": False,
        },
        {
            "agent": "reviewer",
            "backend": "shell",
            "model": "m",
            "effort": "high",
            "service_tier": "default",
            "permission": "bypass",
            "provider": "",
            "goals": True,
            "person": False,
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
    written(tmp_path, "flow", FLOW)

    for _ in range(2):
        Runner(tmp_path / "flow", [ShellAgent(CONFIG), ShellAgent(CONFIG)]).run("go")

    assert len(cycles()) == 2


def test_a_run_that_was_interrupted_says_so(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Esc ends a flow, and a cycle that ended that way is not one that finished."""
    monkeypatch.chdir(tmp_path)
    written(
        tmp_path,
        "flow",
        "from hmz.agents import AgentBase, Stopped\n"
        "from hmz.flows import flow\n\n\n"
        "@flow\n"
        "def run(agents: tuple[AgentBase], task: str) -> None:\n"
        '    raise Stopped("stopped")\n',
    )

    with pytest.raises(Stopped):
        Runner(tmp_path / "flow", [ShellAgent(CONFIG)]).run("go")

    (cycle,) = cycles()
    assert _lines(cycle)[-1]["how"] == "stopped"


def test_a_run_that_failed_says_so(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A turn that failed takes the flow with it, and the cycle says how it went."""
    monkeypatch.chdir(tmp_path)
    written(
        tmp_path,
        "flow",
        "from hmz.agents import AgentBase\n"
        "from hmz.flows import flow\n\n\n"
        "@flow\n"
        "def run(agents: tuple[AgentBase], task: str) -> None:\n"
        '    agents[0].new()("exit 3")\n',
    )

    with pytest.raises(subprocess.CalledProcessError):
        Runner(tmp_path / "flow", [ShellAgent(CONFIG)]).run("go")

    (cycle,) = cycles()
    assert _lines(cycle)[-1]["how"] == "failed"


def test_the_cycles_of_one_workspace_are_not_another_workspace_s(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """They are kept under the workspace they ran in, which is what looks them up."""
    here, there = tmp_path / "here", tmp_path / "there"
    for where in (here, there):
        where.mkdir()
        written(where, "flow", FLOW)
    monkeypatch.chdir(here)
    Runner(here / "flow", [ShellAgent(CONFIG), ShellAgent(CONFIG)]).run("go")

    assert len(cycles(here)) == 1
    assert cycles(there) == []


def test_an_agent_driven_by_hand_is_not_a_run_of_anything(tmp_path: Path) -> None:
    """A session opened outside a flow belongs to no cycle, and writes to none."""
    agent = ShellAgent(CONFIG)

    agent.new()("echo alone")

    assert agent.opened == ["alone"]
    assert cycles(tmp_path) == []


def test_a_session_is_named_for_whose_it_is_what_ran_it_and_which_account(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The id alone says none of that, and a directory of ids is one nobody can read."""
    monkeypatch.chdir(tmp_path)
    written(tmp_path, "flow", ONE)

    Runner(tmp_path / "flow", [ClaudeAgent(CONFIG, name="builder")]).run("go")

    (cycle,) = cycles()
    (one,) = sessions(cycle)
    assert one == (
        "builder",
        "claude",
        "local",
        "the-session",
        "builder-claude@local-the-session",
        one.at,
        str(tmp_path / "flow"),
    )
    assert one.name == called("builder", "claude", "", "the-session")


def test_a_session_says_which_account_took_its_turns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two agents of one CLI are two accounts, and the backend's log says neither."""
    from hmz import providers

    monkeypatch.chdir(tmp_path)
    written(tmp_path, "flow", ONE)
    providers.add("claude", "work", "key", {"ANTHROPIC_API_KEY": "sk-nothing"})
    agent = ClaudeAgent(
        AgentConfig(model="m", effort="high", provider="work"), name="builder"
    )

    Runner(tmp_path / "flow", [agent]).run("go")

    (cycle,) = cycles()
    (one,) = sessions(cycle)
    assert one.provider == "work"
    assert one.name == "builder-claude@work-the-session"
    # And what it was configured with is what the run says it was driven by.
    ran = read(cycle)
    assert ran is not None
    assert ran.agents[0].provider == "work"
    assert ran.agents[0].spec == "claude@work/m:high"


def test_the_logs_of_a_session_are_linked_into_the_cycle_that_opened_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A link rather than a copy: humanize reads and writes the log where the backend keeps it."""
    monkeypatch.chdir(tmp_path)
    written(tmp_path, "flow", ONE)
    where = tmp_path / "claude-home"
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(where))
    log = where / "projects" / "-tmp-project" / "the-session.jsonl"
    log.parent.mkdir(parents=True)
    log.write_text('{"type":"user"}\n')

    Runner(tmp_path / "flow", [ClaudeAgent(CONFIG, name="builder")]).run("go")

    (cycle,) = cycles()
    (one,) = sessions(cycle)
    link = cycle / "sessions" / one.name / "the-session.jsonl"
    assert link.is_symlink()
    assert link.resolve() == log.resolve()
    assert linked(cycle) == {one.name: [str(log)]}


def test_a_log_written_after_the_last_turn_is_linked_when_the_run_ends(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A sub-agent's transcript is written whenever that sub-agent ran, which is later."""
    monkeypatch.chdir(tmp_path)
    written(tmp_path, "flow", ONE)
    where = tmp_path / "claude-home"
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(where))
    under = where / "projects" / "-tmp-project"
    under.mkdir(parents=True)
    (under / "the-session.jsonl").write_text("{}\n")
    late = under / "the-session" / "subagents" / "deep" / "explore.jsonl"
    late.parent.mkdir(parents=True)
    # Written after the session was opened, which is when a sub-agent's transcript is
    # written: the flow stands in for the backend finishing what it was writing.
    monkeypatch.setenv("LATE_LOG", str(late))
    written(
        tmp_path,
        "flow",
        "import os\n"
        "from pathlib import Path\n\n"
        "from hmz.agents import AgentBase\n"
        "from hmz.flows import flow\n\n\n"
        "@flow\n"
        "def run(agents: tuple[AgentBase], task: str) -> None:\n"
        '    agents[0].new()("echo the-session")\n'
        '    Path(os.environ["LATE_LOG"]).write_text("{}\\n")\n',
    )

    Runner(tmp_path / "flow", [ClaudeAgent(CONFIG, name="builder")]).run("go")

    (cycle,) = cycles()
    (one,) = sessions(cycle)
    assert sorted(p.name for p in (cycle / "sessions" / one.name).iterdir()) == [
        "explore.jsonl",
        "the-session.jsonl",
    ]


def test_a_cycle_reads_back_as_what_was_run_and_how_it_went(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Which is what a listing of them shows, and what one of them can be picked up from."""
    monkeypatch.chdir(tmp_path)
    written(tmp_path, "flow", ONE)

    Runner(tmp_path / "flow", [ClaudeAgent(CONFIG, name="builder")]).run("go")

    (cycle,) = cycles()
    ran = read(cycle)
    assert ran is not None
    assert (ran.flow, ran.task, ran.how) == (str(tmp_path / "flow"), "go", "done")
    assert ran.workspace == str(tmp_path.resolve())
    assert ran.name == cycle.name
    assert not ran.resumable
    assert [one.agent for one in ran.agents] == ["builder"]
    assert [one.ident for one in ran.sessions] == ["the-session"]


def test_a_run_written_before_calls_had_records_still_reads_as_what_it_called(
    tmp_path: Path,
) -> None:
    """A cycle is read where it was written, and older runs were written differently."""
    at = tmp_path / "cycle"
    at.mkdir()
    lines: tuple[dict[str, Any], ...] = (
        {"event": "began", "at": "1", "flow": "outer", "task": "go", "agents": []},
        {"event": "called", "at": "2", "flow": "a", "task": "one"},
        {"event": "called", "at": "3", "flow": "b", "task": "two"},
        {"event": "returned", "at": "4", "flow": "b"},
        {"event": "returned", "at": "5", "flow": "a"},
        {"event": "called", "at": "6", "flow": "a", "task": "three"},
        {"event": "ended", "at": "7", "how": "stopped"},
    )
    (at / JOURNAL).write_text(
        "\n".join(json.dumps(one) for one in lines), encoding="utf-8"
    )

    ran = read(at)
    assert ran is not None
    # Three calls and not two: a run that says only which flow is read by taking a return
    # for the last call of that flow still open, which is what nesting is.
    assert [(one.flow, one.task, one.ended) for one in ran.called] == [
        ("a", "one", "5"),
        ("b", "two", "4"),
        ("a", "three", ""),
    ]


def test_a_directory_that_holds_no_run_is_not_one(tmp_path: Path) -> None:
    """A cycle is what this wrote; anything else under there is somebody else's directory."""
    (tmp_path / "not-a-cycle").mkdir()

    assert read(tmp_path / "not-a-cycle") is None

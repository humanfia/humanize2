"""The three flows humanize itself ships: what a round of each is, and what a restart carries.

Nothing here starts a coding agent, and nothing here waits. Both loops are `while True` with a
wait between the rounds, and the wait is where they are stopped: a stop raised there is the run
ending between two rounds, which is where a loop left going for days is stopped in life.

What says a round has happened is the agent itself rather than a count of waits. The runner
reads a flow's file again to run it, so the `time` the running copy waits on is the one every
other sleeper in the process waits on -- a retry backoff, a machine coming up -- and a wait
counted as a round would be a round that never happened. Watching the agent counts turns.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hmz.agents import AgentConfig, Stopped
from hmz.cycle import STATE, cycles, state
from hmz.flows.builtin import ralph_loop, stateful_ralph
from hmz.runner import Runner, resumes
from tests.stubs import ShellAgent

if TYPE_CHECKING:
    from pathlib import Path
    from types import ModuleType

CONFIG = AgentConfig(model="m", effort="high")

#: What the agents are set to do, which the stand-in runs as the shell command it is.
TASK = "echo working"


def _ran(
    monkeypatch: pytest.MonkeyPatch, module: ModuleType, agent: ShellAgent, rounds: int
) -> None:
    """Runs one of the loops for so many rounds, and stops it after the last of them.

    The wait is made instant rather than raising out of, since it is the one clock every
    sleeper in this process waits on; what ends the run is the agent having taken as many
    turns as the test asked for, which is a round of either of these loops. The flow is named
    the way `-f` names it, so what runs is the file the flow lives in.

    Args:
      monkeypatch: The test's own, so the clock is put back when it ends.
      module: The flow, imported, for the name it is run under.
      agent: The one agent it drives.
      rounds: How many rounds to let it take before it is stopped.
    """
    taken: list[str] = []
    agent.watch(
        lambda _agent, _session, event: (
            taken.append(event.kind) if event.kind == "ends" else None
        )
    )

    def waited(seconds: float) -> None:
        if len(taken) >= rounds:
            raise Stopped("esc")

    monkeypatch.setattr(module.time, "sleep", waited)
    with pytest.raises(Stopped):
        Runner(module.__name__.rpartition(".")[2], [agent]).run(TASK)


def _said(capsys: pytest.CaptureFixture[str]) -> list[str]:
    """Which round each of the rounds said it was, out of everything the run printed."""
    return [
        line
        for line in capsys.readouterr().out.splitlines()
        if line.startswith("round ")
    ]


@pytest.mark.timeout(60)
def test_a_ralph_loop_says_which_round_it_is_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Which is the count it keeps, said where whoever is watching the loop can read it."""
    monkeypatch.chdir(tmp_path)
    agent = ShellAgent(CONFIG)

    _ran(monkeypatch, ralph_loop, agent, rounds=3)

    assert _said(capsys) == ["round 1", "round 2", "round 3"]
    assert state(cycles()[-1]) == {"rounds": 3}


@pytest.mark.timeout(60)
def test_a_ralph_loop_started_again_goes_on_from_the_round_it_reached(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The whole of what it keeps: a loop stopped on its second round says round 3 next."""
    monkeypatch.chdir(tmp_path)

    _ran(monkeypatch, ralph_loop, ShellAgent(CONFIG), rounds=2)
    capsys.readouterr()
    _ran(monkeypatch, ralph_loop, ShellAgent(CONFIG), rounds=2)

    assert _said(capsys) == ["round 3", "round 4"]
    first, second = cycles()
    assert state(first) == {"rounds": 2}
    assert state(second) == {"rounds": 4}


@pytest.mark.timeout(60)
def test_a_ralph_loop_keeps_the_count_and_nothing_of_what_was_said(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A session a round, and the state says nothing about any of them.

    Which is what there is to say: the backend logged each of those sessions, the run wrote
    down whose they were, and nothing can reopen one -- so an id kept here would be an id
    nothing could use.
    """
    monkeypatch.chdir(tmp_path)
    agent = ShellAgent(CONFIG)

    _ran(monkeypatch, ralph_loop, agent, rounds=2)

    assert len(agent.opened) == 2
    assert state(cycles()[-1]) == {"rounds": 2}


@pytest.mark.timeout(60)
def test_stateful_ralph_holds_one_session_and_a_run_after_it_opens_another(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The session is the flow, and it is the one thing picking the run up cannot carry."""
    monkeypatch.chdir(tmp_path)
    first, second = ShellAgent(CONFIG), ShellAgent(CONFIG)

    _ran(monkeypatch, stateful_ralph, first, rounds=3)
    _ran(monkeypatch, stateful_ralph, second, rounds=2)

    assert len(first.opened) == 1  # one conversation, three rounds of it
    assert len(second.opened) == 1  # and another, which has none of the first in it
    assert state(cycles()[-1]) == {"rounds": 5}


@pytest.mark.timeout(60)
def test_stateful_ralph_says_which_round_it_is_on_across_the_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The count carries where the conversation does not, which is what it is kept for."""
    monkeypatch.chdir(tmp_path)

    _ran(monkeypatch, stateful_ralph, ShellAgent(CONFIG), rounds=2)
    capsys.readouterr()
    _ran(monkeypatch, stateful_ralph, ShellAgent(CONFIG), rounds=1)

    assert _said(capsys) == ["round 3"]


@pytest.mark.timeout(60)
def test_the_loops_can_be_picked_up_and_the_conversation_cannot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Chat is a conversation with the person, and there is no carrying one of those on."""
    monkeypatch.chdir(tmp_path)

    assert resumes("ralph_loop")
    assert resumes("stateful_ralph")
    assert not resumes("chat")


@pytest.mark.timeout(60)
def test_a_run_of_chat_leaves_nothing_behind_to_pick_up(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """What was said is the backend's log, and nobody is at the prompt to say more."""
    monkeypatch.chdir(tmp_path)

    Runner("chat", [ShellAgent(CONFIG)]).run(TASK)

    (cycle,) = cycles()
    assert not (cycle / STATE).exists()

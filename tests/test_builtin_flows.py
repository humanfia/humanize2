"""The three flows humanize itself ships: what a round of each is, and what a restart carries.

Nothing here starts a coding agent, and nothing here waits. Both loops are `while True` with a
wait between the rounds, and the wait is where they are stopped by hand: a stop raised there is
the run ending between two rounds, which is where a loop left going for days is stopped in
life.

What says a round has happened is the agent itself rather than a count of waits. The runner
reads a flow's file again to run it, so the `time` the running copy waits on is the one every
other sleeper in the process waits on -- a retry backoff, a machine coming up -- and a wait
counted as a round would be a round that never happened. Watching the agent counts turns.

The other ways either loop ends are the budget and a run of rounds that did nothing. The budget
is the millions of output tokens it may spend before it stops: a stand-in that runs a shell
command spends nothing, so the agent that is driven where a budget is what is being read is one
that says each of its turns came out with something -- there being otherwise nothing for a
budget to be spent on. The run of nothing is the opposite stand-in, whose every turn fails, and
it is what the budget cannot end: a round that failed spends nothing to be counted.
"""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

import pytest

from hmz.agents import AgentConfig, Stopped, Usage
from hmz.cycle import STATE, cycles, state
from hmz.flows import resumes
from hmz.flows.builtin import ralph_loop, stateful_ralph
from hmz.runner import Runner
from tests.stubs import ShellAgent

if TYPE_CHECKING:
    from pathlib import Path
    from types import ModuleType

    from hmz.agents import AgentBase, Event, SessionBase

CONFIG = AgentConfig(model="m", effort="high")

#: What the agents are set to do, which the stand-in runs as the shell command it is.
TASK = "echo working"

#: A turn that cannot be taken at all, which is what an account the backend refused looks like
#: from inside a flow: under `suppress` it answers with nothing and spends nothing, so a budget
#: counted in output tokens stands still for every round of it.
FAILS = "exit 1"

#: Fails, fails, answers, and fails for good after that. The answer on the third round puts the
#: run of empty ones back to nothing, so what ends the loop is rounds four to six rather than
#: rounds one to three -- which is the difference between three in a row and three in all.
RECOVERS = (
    "n=$(cat n 2>/dev/null || echo 0); n=$((n + 1)); echo $n > n; "
    "[ $n = 3 ] && echo working || exit 1"
)

#: What one turn of the agent below is counted as having come out with, which is a millionth
#: of a budget written in millions -- so a budget of 3 is three rounds.
EACH = 1_000_000.0


class Spends(ShellAgent):
    """A stand-in that says each of its landed turns came out with something.

    A shell command spends no tokens and every one of these loops now ends on a budget, so an
    agent that reported nothing would be an agent no budget could ever be spent by. Counted
    off the turns it is watched taking, which is what a round of either loop is.
    """

    def __init__(self, config: AgentConfig, *, name: str | None = None) -> None:
        super().__init__(config, name=name)
        self._landed = 0
        self.watch(self._counts)

    def _counts(
        self, agent: AgentBase, session: SessionBase | None, event: Event
    ) -> None:
        """Counts a turn as it ends, which is the one moment a turn has landed."""
        if event.kind == "ends":
            self._landed += 1

    def spent(self) -> Usage:
        """What its turns are said to have come out with, and nothing on any other kind."""
        return Usage(output=EACH * self._landed)


def _ran(
    monkeypatch: pytest.MonkeyPatch,
    module: ModuleType,
    agent: ShellAgent,
    rounds: int,
    config: dict[str, object] | None = None,
    task: str = TASK,
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
      config: What to set the loop up with, or None to take it as it comes -- which is a
        budget the stand-in agent will never spend.
      task: What each round is given, which the stand-in runs as a shell command -- so a task
        that exits non-zero is a round whose turn could not be taken.
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
        Runner(module.__name__.rpartition(".")[2], [agent], config=config).run(task)


def _ran_out(
    monkeypatch: pytest.MonkeyPatch,
    module: ModuleType,
    agent: ShellAgent,
    config: dict[str, object] | None = None,
    task: str = TASK,
) -> None:
    """Runs one of the loops until it stops itself, which is the budget being spent.

    Nothing raises out of the wait here: what ends this run is the loop's own reading of what
    it has spent, so a stop from the outside would be the test answering its own question.

    Args:
      monkeypatch: The test's own, so the clock is put back when it ends.
      module: The flow, imported, for the name it is run under.
      agent: The one agent it drives.
      config: What to set the loop up with.
      task: What each round is given, which the stand-in runs as a shell command -- so a task
        that exits non-zero is a round whose turn could not be taken.
    """

    def waited(seconds: float) -> None:
        """Instant, since what ends this run is the loop's own reading of what it spent."""

    monkeypatch.setattr(module.time, "sleep", waited)
    Runner(module.__name__.rpartition(".")[2], [agent], config=config).run(task)


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
    assert state(cycles()[-1]) == {"rounds": 3, "output": 0.0}


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
    assert state(first) == {"rounds": 2, "output": 0.0}
    assert state(second) == {"rounds": 4, "output": 0.0}


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
    assert state(cycles()[-1]) == {"rounds": 2, "output": 0.0}


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
    assert state(cycles()[-1]) == {"rounds": 5, "output": 0.0}


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


@pytest.mark.timeout(60)
def test_a_chat_whose_opening_turn_cannot_be_taken_says_so(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The first turn is the one that fails out loud, and the reason is the loop's own shape.

    Suppressed, a turn that failed answers with nothing -- and nothing is what the person
    answers with where nobody is at a prompt, which this flow reads as a conversation that is
    over. So a refused account and a finished conversation would be the same run: no output,
    no error and a clean exit, on a flow that had done none of what it was asked.
    """
    monkeypatch.chdir(tmp_path)

    with pytest.raises(subprocess.CalledProcessError):
        Runner("chat", [ShellAgent(CONFIG)]).run(FAILS)


@pytest.mark.timeout(60)
def test_a_loop_whose_rounds_all_answer_with_nothing_gives_up(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The budget cannot end this one: a round that failed spends nothing to be counted."""
    monkeypatch.chdir(tmp_path)

    _ran_out(
        monkeypatch, ralph_loop, ShellAgent(CONFIG), config={"budget": 0}, task=FAILS
    )

    said = capsys.readouterr().out.splitlines()
    assert [line for line in said if line.startswith("round ")] == [
        "round 1",
        "round 2",
        "round 3",
    ]
    assert "stopping: 3 rounds in a row answered with nothing" in said


@pytest.mark.timeout(60)
def test_a_loop_that_stalled_leaves_what_it_kept_for_the_next_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Stopped rather than over: what stopped it is a thing to fix and carry on from.

    Which is the other half of the budget's rule. A loop that spent what it was given is done
    and clears what it kept; a loop nothing would answer is one somebody has to look at, and
    starting it again at round one would lose the count that says how long it had been dead.
    """
    monkeypatch.chdir(tmp_path)

    _ran_out(
        monkeypatch, ralph_loop, ShellAgent(CONFIG), config={"budget": 0}, task=FAILS
    )

    assert state(cycles()[-1]) == {"rounds": 3, "output": 0.0}


@pytest.mark.timeout(60)
def test_a_round_that_answered_puts_the_run_of_empty_ones_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Three in a row rather than three in all: a loop that recovered is not one that stalled."""
    monkeypatch.chdir(tmp_path)

    _ran_out(
        monkeypatch, ralph_loop, ShellAgent(CONFIG), config={"budget": 0}, task=RECOVERS
    )

    said = capsys.readouterr().out.splitlines()
    assert [line for line in said if line.startswith("round ")] == [
        f"round {each}" for each in range(1, 7)
    ]
    assert "stopping: 3 rounds in a row answered with nothing" in said


@pytest.mark.timeout(60)
def test_stateful_ralph_gives_up_on_a_run_of_nothing_too(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """One session rather than one a round, and the same reason to stop going round."""
    monkeypatch.chdir(tmp_path)

    _ran_out(
        monkeypatch,
        stateful_ralph,
        ShellAgent(CONFIG),
        config={"budget": 0},
        task=FAILS,
    )

    said = capsys.readouterr().out.splitlines()
    assert [line for line in said if line.startswith("round ")] == [
        "round 1",
        "round 2",
        "round 3",
    ]
    assert "stopping: 3 rounds in a row answered with nothing" in said


@pytest.mark.timeout(60)
def test_a_loop_stops_once_it_has_spent_the_budget_it_was_given(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Which is the whole of what a budget is: the loop ends itself rather than being ended.

    Three rounds at a million apiece against a budget of three, so the third is the one that
    reaches it -- checked after the turn, since what a round costs is only known once it has
    been taken.
    """
    monkeypatch.chdir(tmp_path)

    _ran_out(monkeypatch, ralph_loop, Spends(CONFIG), config={"budget": 3})

    said = capsys.readouterr().out.splitlines()
    assert [line for line in said if line.startswith("round ")] == [
        "round 1",
        "round 2",
        "round 3",
    ]
    assert "stopping: 3.00M output tokens of 3M" in said


@pytest.mark.timeout(60)
def test_a_loop_that_spent_its_budget_leaves_nothing_for_the_next_run_to_pick_up(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """What is over is not picked up: the next run here opens on a budget of its own.

    Emptied rather than left, and cleared is not the same as never written -- humanize picks
    up from the last run that left an entry, empty or not, so a run after this one is one that
    starts clean rather than one that falls back to a run before it.
    """
    monkeypatch.chdir(tmp_path)

    _ran_out(monkeypatch, ralph_loop, Spends(CONFIG), config={"budget": 2})

    assert state(cycles()[-1]) == {}


@pytest.mark.timeout(60)
def test_a_budget_of_nothing_is_a_loop_that_goes_on_until_it_is_stopped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Zero is the loop as it was before there was a budget, which somebody may still want."""
    monkeypatch.chdir(tmp_path)
    agent = Spends(CONFIG)

    _ran(monkeypatch, ralph_loop, agent, rounds=5, config={"budget": 0})

    assert state(cycles()[-1]) == {"rounds": 5, "output": 5 * EACH}


@pytest.mark.timeout(60)
def test_what_a_loop_spent_is_carried_into_the_run_that_picks_it_up(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Or a budget would be no budget at all for the loop a week of restarts is.

    Two rounds spent under a stop, and then a run picking that up with a budget of three:
    one round is what is left of it, and the run that takes it is the run that ends.
    """
    monkeypatch.chdir(tmp_path)

    _ran(monkeypatch, ralph_loop, Spends(CONFIG), rounds=2, config={"budget": 9})
    assert state(cycles()[-1]) == {"rounds": 2, "output": 2 * EACH}
    capsys.readouterr()

    _ran_out(monkeypatch, ralph_loop, Spends(CONFIG), config={"budget": 3})

    said = capsys.readouterr().out.splitlines()
    assert [line for line in said if line.startswith("round ")] == ["round 3"]
    assert "stopping: 3.00M output tokens of 3M" in said
    assert state(cycles()[-1]) == {}


@pytest.mark.timeout(60)
def test_stateful_ralph_stops_on_its_budget_too(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """One session rather than one a round, and the same reckoning of what it has come to."""
    monkeypatch.chdir(tmp_path)
    agent = Spends(CONFIG)

    _ran_out(monkeypatch, stateful_ralph, agent, config={"budget": 2})

    said = capsys.readouterr().out.splitlines()
    assert [line for line in said if line.startswith("round ")] == [
        "round 1",
        "round 2",
    ]
    assert len(agent.opened) == 1  # one conversation, both rounds of it
    assert state(cycles()[-1]) == {}


@pytest.mark.timeout(60)
def test_the_budget_a_loop_comes_with_is_ten_million_output_tokens(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A number nobody typed, which is what most runs of these will be held to."""
    monkeypatch.chdir(tmp_path)

    assert ralph_loop.Config().budget == 10.0
    assert stateful_ralph.Config().budget == 10.0
    with pytest.raises(ValueError, match="greater than or equal to 0"):
        ralph_loop.Config(budget=-1)

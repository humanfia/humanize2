"""What a run may spend: what a flow declares, what a file says, and which of them wins.

A flow never holds itself to any of this. What it may say is a default, and what settles the
run is one ranking in one place -- whoever started it, else the flow, else nothing at all --
so that a flow started from a command line, from the menu and from another flow are all held
to the same thing. What is checked here is that ranking, that the reserved `budget:` key of a
settings file never reaches the flow's own model, and that a bare number is refused with all
three meanings it could have had rather than quietly taken for one of them.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hmz.coganchor.agents import AgentConfig, Allowance
from hmz.runtime.runner import Runner, flow_and_agents, set_up_from
from tests.stubs import ShellAgent, written

if TYPE_CHECKING:
    from pathlib import Path

CONFIG = AgentConfig(model="m", effort="high")

#: A flow with no opinion about what a run of it is worth, which is every flow written before
#: there was such a thing.
QUIET = """
from hmz.coganchor.agents import AgentBase
from hmz.flows import flow


@flow
def run(agents: tuple[AgentBase], task: str) -> None:
    pass
"""

#: One that says what a run of it is worth by default.
SAYS = """
from hmz.coganchor.agents import AgentBase
from hmz.flows import Allowance, flow


@flow(budget=Allowance(hours=6, tokens=10.0, dollars=50))
def run(agents: tuple[AgentBase], task: str) -> None:
    pass
"""

#: And one that says it is meant to run under nothing at all, which `chat` is.
LOOSE = """
from hmz.coganchor.agents import AgentBase
from hmz.flows import Allowance, flow


@flow(budget=Allowance())
def run(agents: tuple[AgentBase], task: str) -> None:
    pass
"""


def _runner(at: Path, **said: object) -> Runner:
    """One loaded flow, with the agent it declares."""
    return Runner(at, [ShellAgent(CONFIG)], **said)  # pyright: ignore[reportArgumentType]


def test_a_flow_that_says_nothing_runs_under_nothing(tmp_path: Path) -> None:
    """A shipped default would cut off every flow written before this on its first run."""
    at = written(tmp_path, "quiet", QUIET)

    runner = _runner(at)

    assert runner.budget == Allowance()
    assert runner.unwatched  # and so is the thing the menu asks about


def test_what_a_flow_declares_is_what_a_run_of_it_is_held_to(tmp_path: Path) -> None:
    """Which is the default, said in the flow's own file where a reviewer reads it."""
    at = written(tmp_path, "says", SAYS)

    runner = _runner(at)

    assert runner.budget == Allowance(hours=6, tokens=10.0, dollars=50)
    assert not runner.unwatched


def test_what_the_run_was_given_wins_over_what_the_flow_says(tmp_path: Path) -> None:
    """The flow said a default; whoever started the run said what this run is worth."""
    at = written(tmp_path, "says", SAYS)

    runner = _runner(at, budget={"hours": 1})

    assert runner.budget == Allowance(hours=1)


def test_a_flow_that_declares_nothing_at_all_is_not_asked_about_it(
    tmp_path: Path,
) -> None:
    """`Allowance()` written out is a flow saying an unbounded run is what it is for.

    Which is the whole of the exemption: `chat` is a conversation that ends when the person
    stops typing, and a confirmation asked of every one of those is a confirmation nobody
    reads. It is one line in one file rather than a name in a table in three places.
    """
    at = written(tmp_path, "loose", LOOSE)

    runner = _runner(at)

    assert runner.budget == Allowance()
    assert not runner.unwatched


def test_the_budget_in_a_settings_file_never_reaches_the_flows_own_model(
    tmp_path: Path,
) -> None:
    """The flow's model refuses a field it never declared, and this is not the flow's."""
    said = tmp_path / "setup.yaml"
    said.write_text("budget:\n  tokens: 25\nrounds: 12\n", encoding="utf-8")

    held, budget = set_up_from(said)

    assert held == {"rounds": 12}
    assert budget == Allowance(tokens=25)


def test_a_budget_written_as_one_number_is_refused_with_all_three_meanings(
    tmp_path: Path,
) -> None:
    """`budget: 25` is what every flowverse loop's settings file used to say.

    Read as any one of the three it would be a run held to something nobody asked for -- a
    quarter of a day, twenty-five million tokens or twenty-five dollars are not each other --
    so it is refused and all three are named.
    """
    said = tmp_path / "setup.yaml"
    said.write_text("budget: 25\n", encoding="utf-8")

    with pytest.raises(ValueError, match="rather than one number") as refused:
        set_up_from(said)

    assert "tokens: 25" in str(refused.value)
    assert "hours: 25" in str(refused.value)
    assert "dollars: 25" in str(refused.value)


@pytest.mark.parametrize(
    ("held", "because"),
    [
        ("budget:\n  weeks: 2\n", "takes hours, tokens, dollars"),
        ("budget:\n  hours: -1\n", "less than nothing"),
        ("budget:\n  hours: yes\n", "is a number"),
    ],
)
def test_a_budget_that_cannot_be_read_names_the_file(
    tmp_path: Path, held: str, because: str
) -> None:
    """Said where it was written, rather than as a run that stops when nobody expects it."""
    said = tmp_path / "setup.yaml"
    said.write_text(held, encoding="utf-8")

    with pytest.raises(ValueError, match=because):
        set_up_from(said)


def test_the_exec_line_carries_what_the_file_said_the_run_may_spend(
    tmp_path: Path,
) -> None:
    """`-c` is one file and it now says two things: the flow's setup and the run's own."""
    (tmp_path / "b.yaml").write_text("budget:\n  hours: 0.5\n", encoding="utf-8")

    _, _, _, held, budget, _ = flow_and_agents(
        ["-f", "flow", "-c", str(tmp_path / "b.yaml"), "-a", "claude/m:high", "go"]
    )

    assert held == {}
    assert budget == Allowance(hours=0.5)


def test_a_run_nothing_in_it_can_price_says_the_dollars_cap_cannot_bite(
    tmp_path: Path,
) -> None:
    """A fifty-dollar limit on a model nobody lists is a run with no limit on it at all.

    And it reads exactly like a limit that has not been reached yet, which is why it has to
    be said out loud before the first turn rather than left to a run that never stops.
    """
    at = written(tmp_path, "quiet", QUIET)

    runner = _runner(at, budget={"dollars": 50})

    assert "dollars" in runner.unreadable()
    assert not runner.unwatched  # it is bounded; it is only unreadable


def test_a_cap_that_can_be_read_is_not_complained_about(tmp_path: Path) -> None:
    """Blindness is about a cap that will not bite, and the clock always can be read."""
    at = written(tmp_path, "quiet", QUIET)

    assert _runner(at, budget={"hours": 6}).unreadable() == ""

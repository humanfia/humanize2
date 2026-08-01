"""One file, several flows: what each is called, and how one of them is asked for.

A file with a `run` in it is one flow, which is what every flow was. A file that marks its
entry points is one flow apiece, each called `<file>:<name>` -- so three phases of one thing
are one thing to write and three to run, each asking only for the agents it drives and only
for the settings it takes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from humanize.flows import about, find, flow, found, held, inside
from humanize.runner import NotAFlow, Runner, configures, drives, wanted
from tests.stubs import ShellAgent

if TYPE_CHECKING:
    from pathlib import Path

from humanize.agents import AgentConfig

CONFIG = AgentConfig(model="m", effort="high")

#: A file that is three flows: one agent apiece, one of them named for itself.
THREE = '''"""Three phases of one thing, which are three things to run."""

from typing import NamedTuple

from pydantic import BaseModel

from humanize.agents import AgentBase
from humanize.flows import flow


class Drafting(NamedTuple):
    """The one that writes."""

    drafter: AgentBase


class Building(NamedTuple):
    """The one that builds, and the one that reads it."""

    builder: AgentBase
    reviewer: AgentBase


class Wide(BaseModel):
    """What the first phase takes."""

    n: int = 6


@flow
def gen_idea(agents: Drafting, task: str, config: Wide | None = None) -> None:
    """Opens a loose idea into a draft."""
    agents.drafter.new()(f"{task} {(config or Wide()).n}")


@flow(name="build", about="builds it, under review")
def start_it(agents: Building, task: str) -> None:
    """A docstring the decorator was told to say something else instead of."""
    agents.builder.new()(task)


def _not_a_flow(agents: Drafting, task: str) -> None:
    """Marked with nothing, so it is not one of them."""
'''

#: A file that is one flow, the way every flow was one before any of this.
ONE = '''"""Just the one, and it says what it does here."""

from humanize.agents import AgentBase


def run(agents: tuple[AgentBase], task: str) -> None:
    (agent,) = agents
    agent.new()(task)
'''

#: And one that is both: a `run` under the file's own name, and another beside it.
BOTH = '''"""One under its own name, and one beside it."""

from humanize.agents import AgentBase
from humanize.flows import flow


def run(agents: tuple[AgentBase], task: str) -> None:
    """What the file itself is."""
    (agent,) = agents
    agent.new()(task)


@flow
def twice(agents: tuple[AgentBase], task: str) -> None:
    """The other one."""
    (agent,) = agents
    agent.new()(task)
    agent.new()(task)
'''


def _written(tmp_path: Path, source: str, name: str = "three") -> str:
    """Writes a flow file out and answers with its path."""
    where = tmp_path / f"{name}.py"
    where.write_text(source)
    return str(where)


def test_a_file_says_which_flows_it_holds_and_what_each_one_does(
    tmp_path: Path,
) -> None:
    """Read off the decorator, which is where a flow says what it is."""
    said = held(_written(tmp_path, THREE))

    assert [(one.name, one.about) for one in said] == [
        ("gen-idea", "Opens a loose idea into a draft."),
        ("build", "builds it, under review"),
    ]


def test_the_name_is_the_function_s_own_with_dashes_for_underscores(
    tmp_path: Path,
) -> None:
    """Which is how these read on a command line, and `name=` is how to say otherwise."""
    named = {one.name for one in held(_written(tmp_path, THREE))}

    assert named == {"gen-idea", "build"}  # `start_it` was told to be `build`


def test_a_file_with_a_run_in_it_is_one_flow_under_its_own_name(tmp_path: Path) -> None:
    """Which is what every flow was before a file could hold several."""
    (said,) = held(_written(tmp_path, ONE, "one"))

    assert said.name == ""
    # Nothing said its own line, so the file's own first line is what it says.
    assert said.about == "Just the one, and it says what it does here."


def test_the_file_s_own_flow_is_listed_first(tmp_path: Path) -> None:
    """It is the one the file is named after, and a list that put it second would read wrong."""
    said = held(_written(tmp_path, BOTH, "both"))

    assert [one.name for one in said] == ["", "twice"]


def test_each_flow_in_a_file_is_offered_under_its_own_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`<file>:<name>`, which is what makes three of them three things to choose between."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    project = tmp_path / "project"
    (project / ".humanize/flows").mkdir(parents=True)
    (project / ".humanize/flows/three.py").write_text(THREE)
    monkeypatch.chdir(project)

    listed = [(one.name, one.about) for one in found() if one.whose == "local"]

    assert listed == [
        (".humanize/flows/three.py:gen-idea", "Opens a loose idea into a draft."),
        (".humanize/flows/three.py:build", "builds it, under review"),
    ]


def test_which_one_was_asked_for_is_the_half_after_the_colon(tmp_path: Path) -> None:
    where = _written(tmp_path, THREE)

    assert inside(f"{where}:gen-idea") == "gen-idea"
    assert inside(where) == ""  # the one a file holds under its own name
    # The file is the other half, and a path is still a path whatever is after it.
    assert find(f"{where}:gen-idea") == where


def test_each_of_them_asks_only_for_its_own_agents_and_settings(
    tmp_path: Path,
) -> None:
    """Which is the whole of what splitting one flow into three buys."""
    where = _written(tmp_path, THREE)

    assert drives(f"{where}:gen-idea") == ("drafter",)
    assert drives(f"{where}:build") == ("builder", "reviewer")
    idea = configures(f"{where}:gen-idea")
    assert idea is not None
    assert set(idea.model_fields) == {"n"}
    assert configures(f"{where}:build") is None


def test_the_one_that_was_asked_for_is_the_one_that_runs(tmp_path: Path) -> None:
    where = _written(tmp_path, THREE)
    builder, reviewer = ShellAgent(CONFIG), ShellAgent(CONFIG)

    Runner(f"{where}:build", [builder, reviewer]).run("echo built")

    assert builder.opened  # the phase that was named, and no other
    assert not reviewer.opened


def test_a_file_of_several_asked_for_by_its_own_name_says_which_ones_it_holds(
    tmp_path: Path,
) -> None:
    """A colon away from what was meant, so the answer is the list of what to put after it."""
    where = _written(tmp_path, THREE)

    with pytest.raises(NotAFlow, match="three:gen-idea, three:build"):
        drives(where)


def test_a_name_no_flow_in_the_file_answers_to_says_so(tmp_path: Path) -> None:
    where = _written(tmp_path, THREE)

    with pytest.raises(NotAFlow, match="nothing in it is a flow called 'gen-plan'"):
        drives(f"{where}:gen-plan")


def test_a_file_that_holds_one_may_still_be_asked_for_by_name(tmp_path: Path) -> None:
    """`run` is the file's own flow, so a colon on it is a name it does not have."""
    where = _written(tmp_path, ONE, "one")

    assert drives(where) == ("",)
    with pytest.raises(NotAFlow, match="nothing in it is a flow called 'nope'"):
        drives(f"{where}:nope")


def test_what_a_flow_says_about_itself_is_read_back_by_name(tmp_path: Path) -> None:
    """Which is what a list of them shows beside each, so it is asked for by the same name."""
    where = _written(tmp_path, THREE)

    assert about(f"{where}:build") == "builds it, under review"
    assert about(_written(tmp_path, ONE, "one")) == (
        "Just the one, and it says what it does here."
    )


def test_the_decorator_leaves_the_function_alone(tmp_path: Path) -> None:
    """A flow is called the way it always was: what is added is what it says about itself."""
    del tmp_path
    said: list[str] = []

    @flow(about="what it does")
    def two(one: str, other: str = "b") -> str:
        said.append(one)
        return one + other

    assert two("a") == "ab"
    assert said == ["a"]
    assert two.__name__ == "two"


def test_a_flow_a_file_holds_beside_its_own_is_reached_the_same_way(
    tmp_path: Path,
) -> None:
    """A file may be one flow and hold another, which is two names for two things."""
    where = _written(tmp_path, BOTH, "both")

    assert wanted(where) == wanted(f"{where}:twice")
    agent = ShellAgent(CONFIG)
    Runner(f"{where}:twice", [agent]).run("echo twice")

    assert (
        len(agent.opened) == 2
    )  # the one that opens two sessions, not the one that opens one

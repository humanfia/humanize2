"""What makes a function a flow, what it is called, and how one of them is asked for.

A flow is a function marked with `@flow`, and nothing else is one -- not a function called
`run`, which is a name a file is free to use for anything. `@flow` is the flow its file holds
under the file's own name; `@flow(name=...)` is one of several, called `<file>:<name>`, so
three phases of one thing are one thing to write and three to run, each asking only for the
agents it drives and only for the settings it takes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hmz.agents import AgentConfig
from hmz.flows import ENTRY, about, find, flow, found, held, inside
from hmz.runner import NotAFlow, Runner, configures, drives, wanted
from tests.stubs import ShellAgent, written

if TYPE_CHECKING:
    from pathlib import Path

CONFIG = AgentConfig(model="m", effort="high")

#: A flow that is two flows beside each other, neither of them the directory's own.
THREE = '''"""Three phases of one thing, which are three things to run."""

from typing import NamedTuple

from pydantic import BaseModel

from hmz.agents import AgentBase
from hmz.flows import flow


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


@flow(name="gen-idea")
def first_pass(agents: Drafting, task: str, config: Wide | None = None) -> None:
    """Opens a loose idea into a draft."""
    agents.drafter.new()(f"{task} {(config or Wide()).n}")


@flow(name="build", about="builds it, under review")
def start_it(agents: Building, task: str) -> None:
    """A docstring the decorator was told to say something else instead of."""
    agents.builder.new()(task)


def run(agents: Drafting, task: str) -> None:
    """Called run, marked with nothing, and so not a flow at all."""
'''

#: A file that is one flow, under a function name that says nothing about it.
ONE = '''"""Just the one, and it says what it does here."""

from hmz.agents import AgentBase
from hmz.flows import flow


@flow
def whatever_it_is_called(agents: tuple[AgentBase], task: str) -> None:
    (agent,) = agents
    agent.new()(task)
'''

#: And one that is both: the file's own flow, and another beside it.
BOTH = '''"""One under its own name, and one beside it."""

from hmz.agents import AgentBase
from hmz.flows import flow


@flow
def run(agents: tuple[AgentBase], task: str) -> None:
    """What the file itself is."""
    (agent,) = agents
    agent.new()(task)


@flow(name="twice")
def twice(agents: tuple[AgentBase], task: str) -> None:
    """The other one."""
    (agent,) = agents
    agent.new()(task)
    agent.new()(task)
'''

#: A public composition and the internal engine it calls by name.
AUXILIARY = '''"""One flow to choose and one implementation detail."""

from hmz.agents import AgentBase
from hmz.flows import flow


@flow
def run(agents: tuple[AgentBase], task: str) -> None:
    (agent,) = agents
    agent.new()(task)


@flow(name="engine", selectable=False)
def engine(agents: tuple[AgentBase], task: str) -> None:
    (agent,) = agents
    agent.new()(task)
    agent.new()(task)
'''

#: A file with a `run` in it and nothing marked, which is what a flow used to be and is not.
UNMARKED = '''"""A file that says nothing about which of its functions is a flow."""

from hmz.agents import AgentBase


def run(agents: tuple[AgentBase], task: str) -> None:
    (agent,) = agents
    agent.new()(task)
'''


def _written(tmp_path: Path, source: str, name: str = "three") -> str:
    """Writes a flow out as a flow is -- a directory -- and answers with its path."""
    return str(written(tmp_path, name, source))


def test_a_file_says_which_flows_it_holds_and_what_each_one_does(
    tmp_path: Path,
) -> None:
    """Read off the decorator, which is where a flow says what it is."""
    said = held(_written(tmp_path, THREE))

    assert [(one.name, one.about) for one in said] == [
        ("gen-idea", "Opens a loose idea into a draft."),
        ("build", "builds it, under review"),
    ]


def test_the_name_is_what_the_decorator_was_told_and_not_the_function_s(
    tmp_path: Path,
) -> None:
    """A name written down where a flow is run must not change under whoever renames it."""
    named = {one.name for one in held(_written(tmp_path, THREE))}

    assert named == {"gen-idea", "build"}  # not `first_pass`, and not `start_it`


def test_a_function_called_run_is_not_a_flow_for_being_called_that(
    tmp_path: Path,
) -> None:
    """Which is the whole of the rule: a file says which of its functions is a flow."""
    where = _written(tmp_path, UNMARKED, "unmarked")

    assert held(where) == []
    with pytest.raises(NotAFlow, match="nothing in it is marked @flow"):
        drives(where)


def test_a_file_marked_once_is_one_flow_under_its_own_name(tmp_path: Path) -> None:
    """However the function it marked is spelled, which is nothing to do with the name."""
    (said,) = held(_written(tmp_path, ONE, "one"))

    assert said.name == ""
    # Nothing said its own line, so the file's own first line is what it says.
    assert said.about == "Just the one, and it says what it does here."
    assert drives(_written(tmp_path, ONE, "one")) == ("",)


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
    written(project / ".humanize/flows", "three", THREE)
    monkeypatch.chdir(project)

    listed = [(one.name, one.about) for one in found() if one.whose == "local"]

    assert listed == [
        (".humanize/flows/three:gen-idea", "Opens a loose idea into a draft."),
        (".humanize/flows/three:build", "builds it, under review"),
    ]


def test_an_auxiliary_flow_is_callable_but_not_offered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A composition engine is an API for another flow, not a choice for a person."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    project = tmp_path / "project"
    at = written(project / ".humanize/flows", "composed", AUXILIARY)
    monkeypatch.chdir(project)

    assert [(one.name, one.selectable) for one in held(at)] == [
        ("", True),
        ("engine", False),
    ]
    assert [one.name for one in found() if one.whose == "local"] == [
        ".humanize/flows/composed"
    ]
    assert drives("composed:engine") == ("",)
    agent = ShellAgent(CONFIG)
    Runner("composed:engine", [agent]).run("echo internal")
    assert len(agent.opened) == 2


def test_which_one_was_asked_for_is_the_half_after_the_colon(tmp_path: Path) -> None:
    where = _written(tmp_path, THREE)

    assert inside(f"{where}:gen-idea") == "gen-idea"
    assert inside(where) == ""  # the one a flow holds under its own name
    # The flow is the other half, and a path is still a path whatever is after it.
    assert find(f"{where}:gen-idea") == f"{where}/{ENTRY}"


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
    """The file's own flow has no name of its own, so a colon on it names nothing."""
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


def test_a_flow_that_is_one_file_is_a_flow_too(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A flow is a module, and a single `.py` is one: it brings no skills, and runs."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    project = tmp_path / "project"
    (project / ".humanize/flows").mkdir(parents=True)
    (project / ".humanize/flows/alone.py").write_text(ONE)
    monkeypatch.chdir(project)

    assert find("alone") == str((project / ".humanize/flows/alone.py").resolve())
    assert [one.name for one in found() if one.whose == "local"] == [
        ".humanize/flows/alone"
    ]
    assert drives("alone") == ("",)
    agent = ShellAgent(CONFIG)
    Runner("alone", [agent]).run("echo alone")
    assert agent.opened


def test_a_directory_wins_a_name_a_file_also_uses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The one that says most about itself: a flow with a `skills/` cannot be a file."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    project = tmp_path / "project"
    written(project / ".humanize/flows", "both", ONE)
    (project / ".humanize/flows/both.py").write_text(UNMARKED)
    monkeypatch.chdir(project)

    assert find("both") == str((project / ".humanize/flows/both" / ENTRY).resolve())
    # And it is offered once rather than twice, under the one name it has.
    assert [one.name for one in found() if one.whose == "local"] == [
        ".humanize/flows/both"
    ]


#: A flow that reads what it does out of the module beside it, which is how a flow keeps a
#: prompt, a schedule or a table of its own without putting it in the flow itself.
BESIDE = '''"""Says what the module beside it says."""

import beside

from hmz.agents import AgentBase
from hmz.flows import flow


@flow
def run(agents: tuple[AgentBase], task: str) -> None:
    (agent,) = agents
    agent(f"echo {beside.SAYS} > said.txt")
'''


def test_each_flow_reads_the_module_beside_it_rather_than_the_last_flows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every flow may have a `beside.py`, and one process may run several of them.

    A module imported by its plain name is cached under that plain name, so the first flow
    loaded would own it: the second flow's `import beside` would be answered with the first
    one's, and drawing the menu -- which loads every flow there is -- would settle which.
    """
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    project = tmp_path / "project"
    for name in ("alpha", "beta"):
        at = written(project / ".humanize/flows", name, BESIDE)
        (at / "beside.py").write_text(f'SAYS = "{name}"\n')
    monkeypatch.chdir(project)

    held(
        str(project / ".humanize/flows/alpha")
    )  # as the menu does, to say what they are
    Runner("beta", [ShellAgent(CONFIG)]).run("")

    assert (project / "said.txt").read_text().strip() == "beta"


def test_a_module_beside_a_flow_rewritten_between_runs_is_read_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Which is what a flow that improves itself does: the prompt beside it is where it is."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    project = tmp_path / "project"
    at = written(project / ".humanize/flows", "mine", BESIDE)
    (at / "beside.py").write_text('SAYS = "first"\n')
    monkeypatch.chdir(project)

    Runner("mine", [ShellAgent(CONFIG)]).run("")
    assert (project / "said.txt").read_text().strip() == "first"

    (at / "beside.py").write_text('SAYS = "second"\n')
    Runner("mine", [ShellAgent(CONFIG)]).run("")

    assert (project / "said.txt").read_text().strip() == "second"

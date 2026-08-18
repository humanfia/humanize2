"""Running an atlas: the prophecy walked a node at a time, and picked up where it stopped.

An atlas's body is never run. What runs is the graph compiling it made, which is what puts a
run in a position to be stopped and started: the answers are written down as they arrive, so
picking a run up is walking the same graph over the same answers until it reaches the node
that has none.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hmz.agents import AgentConfig
from hmz.cycle import cycles, state
from hmz.flows import PROPHECY, NotAFlow, kept, resumes
from hmz.flows.prophesying import prophesied
from hmz.runner import Runner
from hmz.sdk import Hmz
from tests.stubs import ShellAgent, written

if TYPE_CHECKING:
    from pathlib import Path

CONFIG = AgentConfig(model="m", effort="high")

#: An atlas of three nodes that says which of them ran, and can be made to stop in the last.
THREE = '''"""Three nodes, and a file that says which of them ran."""

from pathlib import Path
from typing import NamedTuple

from pydantic import BaseModel, Field

from hmz.flows import Agent, atlas, logic, mind


class Agents(NamedTuple):
    """Who it drives."""

    writer: Agent


class Said(BaseModel):
    """What flows between them."""

    model_config = {"extra": "forbid"}

    text: str = Field(description="what the node had to say")


def ran(name: str) -> None:
    """Writes down that one node ran, since a run is what a test is watching."""
    at = Path("ran.txt")
    at.write_text((at.read_text() if at.exists() else "") + name + " ")


@mind
def first(agent: Agent, task: str) -> Said:
    """One turn, and the only one."""
    ran("first")
    agent.new()("true")
    return Said(text=task)


@logic
def middle(said: Said) -> Said:
    """Reads it, and is kept."""
    ran("middle")
    return said


@logic(rerun=RERUN)
def last(said: Said) -> None:
    """Stops the first run of it, and says whether a run picked up runs it again."""
    ran("last")
    if not Path("been.txt").exists():
        Path("been.txt").write_text("yes")
        raise RuntimeError("stopped")


@atlas
def run(agents: Agents, task: str) -> None:
    """Runs the three of them."""
    said = first(agents.writer, task)
    held = middle(said)
    last(held)
'''

#: One that loops, so that a node visited twice is two answers rather than one overwritten.
ROUNDS = '''"""Writes until the reading of it says three rounds have been."""

from pathlib import Path
from typing import NamedTuple

from pydantic import BaseModel, Field

from hmz.flows import Agent, atlas, logic, mind


class Agents(NamedTuple):
    """Who it drives."""

    writer: Agent


class Draft(BaseModel):
    """What the writer produced, and on which round."""

    model_config = {"extra": "forbid"}

    text: str = Field(description="the draft")
    round: int = Field(default=0, description="which round wrote it")


class Verdict(BaseModel):
    """Whether the loop is over."""

    model_config = {"extra": "forbid"}

    done: bool = Field(description="whether three rounds have been")


@mind
def write(agent: Agent, task: str) -> Draft:
    """One round of it."""
    at = Path("rounds.txt")
    said = at.read_text() if at.exists() else ""
    at.write_text(said + "w")
    agent.new()("true")
    return Draft(text=task, round=len(said) + 1)


@logic
def judge(said: Draft) -> Verdict:
    """Three rounds and it is done."""
    return Verdict(done=said.round >= 3)


@atlas
def run(agents: Agents, task: str) -> None:
    """Rounds until it is done."""
    draft = write(agents.writer, task)
    verdict = judge(draft)
    while not verdict.done:
        draft = write(agents.writer, task)
'''

#: And one whose node is a whole atlas of its own, reached beside it and by name.
INNER = '''"""The atlas that is reached by name."""

from pathlib import Path
from typing import NamedTuple

from pydantic import BaseModel, Field

from hmz.flows import Agent, atlas, mind


class Agents(NamedTuple):
    """Who it drives."""

    writer: Agent


class Said(BaseModel):
    """What flows through."""

    model_config = {"extra": "forbid"}

    text: str = Field(description="the text")


@mind
def deepen(agent: Agent, said: Said) -> Said:
    """One turn, inside a node that is a graph."""
    agent.new()("true")
    at = Path("ran.txt")
    at.write_text((at.read_text() if at.exists() else "") + "deepen ")
    return Said(text=said.text + "!")


@atlas
def run(agents: Agents, said: Said) -> Said:
    """One node, and it is a turn."""
    out = deepen(agents.writer, said)
    return out
'''

OUTER = '''"""The atlas with a supernode in it, twice over."""

from pathlib import Path
from typing import NamedTuple

from pydantic import BaseModel, Field

from hmz.flows import Agent, atlas, logic, sub


class Agents(NamedTuple):
    """Who it drives."""

    writer: Agent


class Said(BaseModel):
    """What flows through."""

    model_config = {"extra": "forbid"}

    text: str = Field(description="the text")


deeper = sub("inner")


@logic
def start(task: str) -> Said:
    """Opens it."""
    Path("ran.txt").write_text("start ")
    return Said(text=task)


@atlas(name="twice")
def beside(agents: Agents, said: Said) -> Said:
    """A supernode of this file's own, holding one of another file's."""
    once = deeper(agents, said)
    return once


@logic
def finish(said: Said) -> None:
    """Writes what came back out."""
    Path("out.txt").write_text(said.text)


@atlas
def run(agents: Agents, task: str) -> None:
    """Says it."""
    said = start(task)
    held = beside(agents, said)
    finish(held)
'''


@pytest.fixture(autouse=True)
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A project with atlases of its own, and a home nothing wrote to."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    where = tmp_path / "project"
    (where / ".humanize/flows").mkdir(parents=True)
    monkeypatch.chdir(where)
    return where


def _write(project: Path, name: str, source: str) -> Path:
    """Writes one atlas into this project's own flows."""
    return written(project / ".humanize/flows", name, source)


def _run(name: str, task: str = "go") -> None:
    """Runs one atlas with a stand-in agent, the way a command line runs any flow."""
    Runner(name, [ShellAgent(CONFIG)]).run(task)


def test_an_atlas_runs_its_prophecy_rather_than_its_body(project: Path) -> None:
    """The body is a declaration, and each node in it is called by the walk over the graph."""
    _write(project, "three", THREE.replace("RERUN", "True"))

    with pytest.raises(RuntimeError):
        _run("three")

    assert (project / "ran.txt").read_text() == "first middle last "


def test_an_atlas_says_it_can_be_picked_up_without_being_asked(project: Path) -> None:
    """A graph is a list of nodes with an answer apiece, so a run of one writes itself down."""
    _write(project, "three", THREE.replace("RERUN", "True"))

    assert resumes("three") is True


def test_what_a_run_has_done_is_the_answers_it_has(project: Path) -> None:
    """One line per visit to a node, which is what picking the run up walks over again."""
    _write(project, "rounds", ROUNDS)

    _run("rounds")

    held = state(cycles()[-1], "rounds")
    assert (project / "rounds.txt").read_text() == "www"
    # A node visited twice is two answers: a round that overwrote the last round's would be
    # a run nothing could be picked up in the middle of.
    assert sorted(held["done"]) == [
        "judge#1",
        "judge#2",
        "judge#3",
        "write#1",
        "write:2#1",
        "write:2#2",
    ]
    assert held["done"]["write:2#2"] == {"text": "go", "round": 3}


def test_the_node_a_run_stopped_inside_is_run_again(project: Path) -> None:
    """Work cut off partway was not done, which is what a node says by saying nothing."""
    _write(project, "three", THREE.replace("RERUN", "True"))
    with pytest.raises(RuntimeError):
        _run("three")
    (project / "ran.txt").write_text("")

    _run("three")

    # The two above it answered already, and are picked up rather than taken again.
    assert (project / "ran.txt").read_text() == "last "


def test_a_node_may_say_it_is_stepped_past_instead(project: Path) -> None:
    """One that had its effect before anything could interrupt it, and answers with nothing."""
    _write(project, "three", THREE.replace("RERUN", "False"))
    with pytest.raises(RuntimeError):
        _run("three")
    (project / "ran.txt").write_text("")

    _run("three")

    assert (project / "ran.txt").read_text() == ""


def test_a_run_is_picked_up_into_the_same_graph_or_not_at_all(project: Path) -> None:
    """An atlas rewritten is a different graph whose nodes happen to share their names."""
    at = _write(project, "three", THREE.replace("RERUN", "True"))
    with pytest.raises(RuntimeError):
        _run("three")
    at.joinpath("__init__.py").write_text(
        THREE.replace("RERUN", "True").replace(
            "    held = middle(said)",
            "    said = first(agents.writer, task)\n    held = middle(said)",
        )
    )
    (project / "ran.txt").write_text("")

    _run("three")

    assert (project / "ran.txt").read_text() == "first first middle last "


def test_a_supernode_is_the_graph_under_it_walked(project: Path) -> None:
    """One node from outside, one run from within, written down beneath the node it is."""
    _write(project, "inner", INNER)
    _write(project, "outer", OUTER)

    _run("outer", "hello")

    assert (project / "ran.txt").read_text() == "start deepen "
    assert (project / "out.txt").read_text() == "hello!"
    assert sorted(state(cycles()[-1], "outer")["done"]) == [
        "beside#1",
        "beside#1/deeper#1",
        "beside#1/deeper#1/deepen#1",
        "finish#1",
        "start#1",
    ]


def test_a_body_that_does_not_compile_is_refused_where_it_is_named(
    project: Path,
) -> None:
    """Before the first turn rather than hours in, which is what an atlas is for."""
    _write(
        project,
        "three",
        THREE.replace("RERUN", "True").replace("    last(held)", "    last(said.text)"),
    )

    with pytest.raises(NotAFlow, match="does not compile"):
        _run("three")


def test_the_prophecy_a_flowverse_ships_is_the_one_that_runs(project: Path) -> None:
    """A repository that has been through the compiling has an answer worth carrying."""
    at = _write(project, "three", THREE.replace("RERUN", "True"))
    held = prophesied(at).prophecy
    assert held is not None
    at.joinpath(PROPHECY).write_bytes(kept(held))
    # The source now says one node more, and the shipped graph says it does not.
    at.joinpath("__init__.py").write_text(
        THREE.replace("RERUN", "True").replace(
            "    last(held)", "    last(held)\n    last(held)"
        )
    )

    with pytest.raises(RuntimeError):
        _run("three")

    assert (project / "ran.txt").read_text() == "first middle last "


def test_a_shipped_prophecy_that_cannot_be_read_is_refused(project: Path) -> None:
    """What a flowverse shipped is what it meant to run, so nothing else quietly runs."""
    at = _write(project, "three", THREE.replace("RERUN", "True"))
    at.joinpath(PROPHECY).write_bytes(b"nothing here is a prophecy")

    with pytest.raises(NotAFlow, match="cannot be read"):
        _run("three")


def test_one_is_shipped_and_read_back_through_the_sdk(project: Path) -> None:
    """Which is the one call anything that compiles an atlas makes."""
    _write(project, "rounds", ROUNDS)
    flows = Hmz().flows

    where = flows.foretell("rounds")

    assert where.endswith(PROPHECY)
    said = flows.prophecy("rounds")
    assert said is not None
    assert [one.at for one in said.nodes] == ["write", "judge", "write:2"]
    assert flows.check("rounds") == ()


def test_an_atlas_may_be_one_file(project: Path) -> None:
    """A flow that is one function still is one, and so is an atlas that is one graph."""
    (project / ".humanize/flows/lone.py").write_text(ROUNDS)

    _run("lone")

    assert (project / "rounds.txt").read_text() == "www"


def test_a_flow_that_is_one_file_has_nowhere_to_ship_a_prophecy(project: Path) -> None:
    """What is beside such a flow is the other flows, and none of it came with this one."""
    (project / ".humanize/flows/lone.py").write_text(ROUNDS)

    with pytest.raises(NotAFlow, match="no directory to ship a prophecy in"):
        Hmz().flows.foretell("lone")


def test_a_supernode_answers_with_what_its_return_named(project: Path) -> None:
    """A graph may answer with something it bound three nodes before it ended."""
    inner = INNER.replace(
        """    out = deepen(agents.writer, said)
    return out""",
        """    out = deepen(agents.writer, said)
    more = deepen(agents.writer, out)
    return out""",
    )
    _write(project, "inner", inner)
    _write(project, "outer", OUTER)

    _run("outer", "hello")

    # Two turns were taken, and what came back out is the first one's answer.
    assert (project / "ran.txt").read_text() == "start deepen deepen "
    assert (project / "out.txt").read_text() == "hello!"

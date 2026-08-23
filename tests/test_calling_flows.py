"""One flow reaching for another by name, running it, and being seen to.

A flow is a loop over agents, and a loop worth having is one another loop can reach for. So a
flow asks for one the way a person does -- by the name `-f` takes -- and is handed the flow's
own function to run with the agents it already has. What is running is written down as it
happens, since a flow is a Python file and nothing can ask it what it is doing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hmz.agents import AgentConfig
from hmz.agents.skills import Loaded
from hmz.epic import JOURNAL, epics, read, records, sessions
from hmz.flows import NotAFlow, load, running
from hmz.runner import Runner
from tests.stubs import ShellAgent, events, written

if TYPE_CHECKING:
    from pathlib import Path

CONFIG = AgentConfig(model="m", effort="high")

#: The flow being called: one agent, and it says what it was given.
INNER = '''"""The one that is called."""

from pathlib import Path

from hmz.agents import AgentBase
from hmz.flows import flow


@flow
def run(agents: tuple[AgentBase], task: str) -> None:
    (agent,) = agents
    Path("inner.txt").write_text(task)
    agent.new()("echo " + task)
'''

#: The one that calls it, and then does something of its own.
OUTER = '''"""The one that calls."""

from pathlib import Path

from hmz.agents import AgentBase
from hmz.flows import flow
from hmz.flows import load, running


@flow
def run(agents: tuple[AgentBase], task: str) -> None:
    Path("running.txt").write_text(",".join(one.flow for one in running()))
    load("inner")(agents, f"inner: {task}")
    Path("outer.txt").write_text(task)
'''


#: One that calls the same flow twice, since two calls of one flow are two runs of it.
TWICE = '''"""The one that calls the same flow twice."""

from hmz.agents import AgentBase
from hmz.flows import flow
from hmz.flows import load


@flow
def run(agents: tuple[AgentBase], task: str) -> None:
    load("inner")(agents, "once")
    load("inner")(agents, "again")
'''

#: One that calls the one in the middle, so that the run is three flows deep.
NESTS = '''"""The one at the top."""

from hmz.agents import AgentBase
from hmz.flows import flow
from hmz.flows import load


@flow
def run(agents: tuple[AgentBase], task: str) -> None:
    load("deeper")(agents, "mid")
'''

#: One that opens a session of its own and then calls a flow that opens one too.
DEEPER = '''"""The one in the middle."""

from hmz.agents import AgentBase
from hmz.flows import flow
from hmz.flows import load


@flow
def run(agents: tuple[AgentBase], task: str) -> None:
    (agent,) = agents
    agent.new()("echo middle")
    load("inner")(agents, "deep")
'''


@pytest.fixture(autouse=True)
def flows(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A project with flows of its own that call each other, and a home nothing wrote to."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    where = tmp_path / "project"
    (where / ".humanize/flows").mkdir(parents=True)
    written(where / ".humanize/flows", "inner", INNER)
    written(where / ".humanize/flows", "outer", OUTER)
    written(where / ".humanize/flows", "twice", TWICE)
    written(where / ".humanize/flows", "deeper", DEEPER)
    written(where / ".humanize/flows", "nests", NESTS)
    monkeypatch.chdir(where)
    return where


def test_a_flow_runs_the_flow_it_asked_for(flows: Path) -> None:
    """Which is the whole of it: a name in, a flow to run out."""
    Runner("outer", [ShellAgent(CONFIG)]).run("do it")

    assert (flows / "inner.txt").read_text() == "inner: do it"
    assert (flows / "outer.txt").read_text() == "do it"  # and it carried on afterwards


def test_what_is_running_is_the_one_that_was_started_and_what_it_called(
    flows: Path,
) -> None:
    """A flow that called another must not read as the flow somebody chose."""
    Runner("outer", [ShellAgent(CONFIG)]).run("do it")

    # Written from inside the outer flow, before it called the inner one.
    assert (flows / "running.txt").read_text() == "outer"
    assert running() == ()  # and nothing is left behind when the run is over


def test_the_called_flow_is_running_while_it_runs(flows: Path) -> None:
    """Read from inside it, which is the only moment it is true."""
    written(
        flows / ".humanize/flows",
        "deep",
        '"""Says what is running while it runs."""\n\n'
        "from pathlib import Path\n\n"
        "from hmz.agents import AgentBase\n"
        "from hmz.flows import flow\n"
        "from hmz.flows import running\n\n\n"
        "@flow\n"
        "def run(agents: tuple[AgentBase], task: str) -> None:\n"
        '    Path("deep.txt").write_text(" > ".join(one.flow for one in running()))\n',
    )
    written(
        flows / ".humanize/flows",
        "over",
        '"""Calls the one that says."""\n\n'
        "from hmz.agents import AgentBase\n"
        "from hmz.flows import flow\n"
        "from hmz.flows import load\n\n\n"
        "@flow\n"
        "def run(agents: tuple[AgentBase], task: str) -> None:\n"
        '    load("deep")(agents, task)\n',
    )

    Runner("over", [ShellAgent(CONFIG)]).run("go")

    assert (flows / "deep.txt").read_text() == "over > deep"


def test_a_flow_asked_for_by_a_name_nothing_answers_to_says_so_when_it_is_asked() -> (
    None
):
    """At the asking rather than an hour into a loop, which is the point of asking early."""
    with pytest.raises(NotAFlow):
        load("no_such_flow_anywhere")


def test_a_called_flow_is_handed_the_agents_it_declares(flows: Path) -> None:
    """The tuple the flow declared, named where it named them."""
    written(
        flows / ".humanize/flows",
        "named",
        '"""Two agents, and it says what it calls them."""\n\n'
        "from pathlib import Path\n"
        "from typing import NamedTuple\n\n"
        "from hmz.agents import AgentBase\n"
        "from hmz.flows import flow\n\n\n"
        "class Both(NamedTuple):\n"
        '    """Two of them."""\n\n'
        "    builder: AgentBase\n"
        "    reviewer: AgentBase\n\n\n"
        "@flow\n"
        "def run(agents: Both, task: str) -> None:\n"
        '    Path("named.txt").write_text(type(agents).__name__ + " " + agents.builder.id)\n',
    )
    one, two = ShellAgent(CONFIG), ShellAgent(CONFIG)

    load("named")([one, two], "go")

    said = (flows / "named.txt").read_text()
    assert said.startswith("Both ")
    assert said.endswith(one.id)  # handed over in the order they were given


def test_a_called_flow_given_the_wrong_number_of_agents_says_so(flows: Path) -> None:
    """Before its first turn, which is where every other miscount is caught."""
    del flows
    with pytest.raises(NotAFlow, match="drives 1 agents, 2 given"):
        load("inner")([ShellAgent(CONFIG), ShellAgent(CONFIG)], "go")


def test_a_called_flow_is_set_up_the_way_a_run_of_it_is(flows: Path) -> None:
    """Read back through the flow's own model, which is what refuses one it does not take."""
    written(
        flows / ".humanize/flows",
        "settable",
        '"""Takes a setting."""\n\n'
        "from pathlib import Path\n\n"
        "from pydantic import BaseModel\n\n"
        "from hmz.agents import AgentBase\n"
        "from hmz.flows import flow\n\n\n"
        "class Config(BaseModel):\n"
        '    """What it takes."""\n\n'
        "    rounds: int = 3\n\n\n"
        "@flow\n"
        "def run(agents: tuple[AgentBase], task: str, config: Config | None = None) -> None:\n"
        '    Path("settable.txt").write_text(str((config or Config()).rounds))\n',
    )

    load("settable")([ShellAgent(CONFIG)], "go", {"rounds": 9})
    assert (flows / "settable.txt").read_text() == "9"

    load("settable")(
        [ShellAgent(CONFIG)], "go"
    )  # and as it comes, where none was given
    assert (flows / "settable.txt").read_text() == "3"

    with pytest.raises(NotAFlow, match="takes no config"):
        load("inner")([ShellAgent(CONFIG)], "go", {"rounds": 9})


def test_a_call_refused_leaves_the_caller_carrying_its_own_skills(flows: Path) -> None:
    """A call that never happened must not leave the caller driving somebody else's skills.

    A caller may catch the refusal -- to try another config, or to go on without that flow --
    and every session it opens after that is its own flow's.
    """
    card = "---\nname: {name}\ndescription: does a thing\n---\n\nDo it.\n"
    written(
        flows / ".humanize/flows",
        "deep",
        INNER,
        {"deep-notes": card.format(name="deep-notes")},
    )
    agent = ShellAgent(CONFIG)
    agent.loads([Loaded("mine", flows)])

    with pytest.raises(NotAFlow, match="takes no config"):
        load("deep")([agent], "go", {"rounds": 9})

    assert [one.name for one in agent.loaded] == ["mine"]


def test_a_flow_that_calls_one_written_as_a_coroutine_awaits_it(flows: Path) -> None:
    """A flow answers with whatever it answers with, so an async one is awaited by its caller."""
    written(
        flows / ".humanize/flows",
        "slow",
        '"""A flow written as a coroutine."""\n\n'
        "import asyncio\n"
        "from pathlib import Path\n\n"
        "from hmz.agents import AgentBase\n"
        "from hmz.flows import flow\n"
        "from hmz.flows import running\n\n\n"
        "@flow\n"
        "async def run(agents: tuple[AgentBase], task: str) -> None:\n"
        "    await asyncio.sleep(0)\n"
        '    Path("slow.txt").write_text(",".join(one.flow for one in running()))\n',
    )
    written(
        flows / ".humanize/flows",
        "waits",
        '"""Waits for the one it called."""\n\n'
        "from pathlib import Path\n\n"
        "from hmz.agents import AgentBase\n"
        "from hmz.flows import flow\n"
        "from hmz.flows import load\n\n\n"
        "@flow\n"
        "async def run(agents: tuple[AgentBase], task: str) -> None:\n"
        '    await load("slow")(agents, task)\n'
        '    Path("after.txt").write_text("and then this")\n',
    )

    Runner("waits", [ShellAgent(CONFIG)]).run("go")

    # It really was awaited: the file the called flow writes is there, and it was running
    # under the flow that called it while it wrote.
    assert (flows / "slow.txt").read_text() == "waits,slow"
    assert (flows / "after.txt").read_text() == "and then this"
    assert running() == ()


def test_the_run_writes_down_the_flow_it_called(flows: Path) -> None:
    """An epic is what a run was, and a flow that called another is part of what it was."""
    Runner("outer", [ShellAgent(CONFIG)]).run("do it")

    (epic,) = epics()
    called = [one for one in events(epic) if one["event"] in ("called", "returned")]

    assert [one["event"] for one in called] == ["called", "returned"]
    assert called[0]["flow"] == "inner"
    assert called[0]["task"] == "inner: do it"


def test_a_called_flow_is_written_down_in_a_record_of_its_own(flows: Path) -> None:
    """A flow that called another is two flows, and each of them is a flow that ran."""
    Runner("outer", [ShellAgent(CONFIG)]).run("do it")

    (epic,) = epics()
    ran = read(epic)
    assert ran is not None
    (call,) = ran.called

    assert (call.flow, call.task) == ("inner", "inner: do it")
    # Named for the flow and for this call of it, and beside the record of the run itself.
    assert call.record.startswith("epic.inner_")
    assert call.record.endswith(".jsonl")
    assert records(epic) == [epic / JOURNAL, epic / call.record]
    assert call.began
    assert call.ended
    # And it says what it was a run of, under the record that called it.
    began, *_, ended = events(epic / call.record)
    assert (began["event"], began["flow"], began["task"]) == (
        "began",
        "inner",
        "inner: do it",
    )
    assert began["under"] == JOURNAL
    assert (ended["event"], ended["how"]) == ("ended", "done")


def test_what_a_called_flow_opened_is_written_where_it_ran(flows: Path) -> None:
    """A session opened inside a called flow is that flow's, and a run has to say which."""
    Runner("outer", [ShellAgent(CONFIG)]).run("do it")

    (epic,) = epics()
    ran = read(epic)
    assert ran is not None
    (call,) = ran.called

    # Nothing of the called flow's own in the run's record but the call itself.
    assert [one["event"] for one in events(epic)] == [
        "began",
        "called",
        "returned",
        "ended",
    ]
    assert [one["event"] for one in events(epic / call.record)] == [
        "began",
        "opened",
        "ended",
    ]
    # And the run is still every session it opened, each saying which flow opened it.
    (one,) = sessions(epic)
    assert (one.ident, one.flow) == ("inner: do it", "inner")


def test_a_flow_called_twice_is_written_down_twice(flows: Path) -> None:
    """Two calls of one flow are two runs of it, each with sessions of its own."""
    Runner("twice", [ShellAgent(CONFIG)]).run("go")

    (epic,) = epics()
    ran = read(epic)
    assert ran is not None
    once, again = ran.called

    assert (once.flow, once.task) == ("inner", "once")
    assert (again.flow, again.task) == ("inner", "again")
    assert once.record != again.record
    assert sorted(one.name for one in records(epic)) == sorted(
        [JOURNAL, once.record, again.record]
    )
    assert [one.ident for one in sessions(epic)] == ["once", "again"]


def test_a_flow_a_called_flow_called_is_written_down_under_it(flows: Path) -> None:
    """A run is the shape it ran in: what called what, and not one flat list of it all."""
    Runner("nests", [ShellAgent(CONFIG)]).run("go")

    (epic,) = epics()
    ran = read(epic)
    assert ran is not None

    # The run called `deeper` and nothing else: what `deeper` called is `deeper`'s to say.
    assert [one.flow for one in ran.called] == ["deeper"]
    (deeper,) = ran.called
    (deep,) = [one for one in events(epic / deeper.record) if one["event"] == "called"]
    assert deep["flow"] == "inner"
    assert events(epic / str(deep["epic"]))[0]["under"] == deeper.record
    # And every session of the run is still the run's, each under the flow that opened it.
    assert [(one.ident, one.flow) for one in sessions(epic)] == [
        ("middle", "deeper"),
        ("deep", "inner"),
    ]


def test_a_call_that_raised_says_so_where_it_was_written(flows: Path) -> None:
    """A record closes saying how what it is a record of ended, a call as much as a run."""
    written(
        flows / ".humanize/flows",
        "bad",
        '''"""Raises."""

from hmz.agents import AgentBase
from hmz.flows import flow


@flow
def run(agents: tuple[AgentBase], task: str) -> None:
    raise RuntimeError("no")
''',
    )
    written(
        flows / ".humanize/flows",
        "catches",
        '''"""Calls the one that raises, and carries on."""

from hmz.agents import AgentBase
from hmz.flows import flow
from hmz.flows import load


@flow
def run(agents: tuple[AgentBase], task: str) -> None:
    try:
        load("bad")(agents, task)
    except RuntimeError:
        pass
''',
    )

    Runner("catches", [ShellAgent(CONFIG)]).run("go")

    (epic,) = epics()
    ran = read(epic)
    assert ran is not None
    (call,) = ran.called

    assert ran.how == "done"  # the run went on: what failed was the flow it called
    assert call.ended
    last = events(epic / call.record)[-1]
    assert (last["event"], last["how"]) == ("ended", "failed")


def test_a_flow_that_fails_is_no_longer_running(flows: Path) -> None:
    """However it ends: a list of what is running that grew would say the run never stopped."""
    written(
        flows / ".humanize/flows",
        "bad",
        '"""Raises."""\n\n'
        "from hmz.agents import AgentBase\n"
        "from hmz.flows import flow\n\n\n"
        "@flow\n"
        "def run(agents: tuple[AgentBase], task: str) -> None:\n"
        '    raise RuntimeError("no")\n',
    )
    written(
        flows / ".humanize/flows",
        "tries",
        '"""Calls the one that raises, and lets it through."""\n\n'
        "from hmz.agents import AgentBase\n"
        "from hmz.flows import flow\n"
        "from hmz.flows import load\n\n\n"
        "@flow\n"
        "def run(agents: tuple[AgentBase], task: str) -> None:\n"
        '    load("bad")(agents, task)\n',
    )

    with pytest.raises(RuntimeError, match="no"):
        Runner("tries", [ShellAgent(CONFIG)]).run("go")

    assert running() == ()


def test_a_flow_rewritten_between_calls_is_the_one_that_runs_next(flows: Path) -> None:
    """Which is what makes a loop that improves its own flows a loop that then runs them.

    A flow is a directory on disk, read by running it, and `load` reads it again at every
    call rather than holding the function it found the first time. So a flow rewritten while
    the run is going -- by hand, or by an agent this very flow is driving -- is run as it is
    now. Nothing else lets a run improve the thing it is being run by.
    """
    written(
        flows / ".humanize/flows",
        "over",
        '"""Calls the same flow twice, rewriting it in between."""\n\n'
        "from pathlib import Path\n\n"
        "from hmz.agents import AgentBase\n"
        "from hmz.flows import flow\n"
        "from hmz.flows import load\n\n\n"
        "@flow\n"
        "def run(agents: tuple[AgentBase], task: str) -> None:\n"
        '    calling = load("inner")\n'
        "    calling(agents, task)\n"
        '    at = Path(".humanize/flows/inner/__init__.py")\n'
        "    at.write_text(at.read_text().replace('Path(\"inner.txt\")', "
        "'Path(\"rewritten.txt\")'))\n"
        "    calling(agents, task)\n",
    )

    Runner("over", [ShellAgent(CONFIG)]).run("go")

    assert (flows / "inner.txt").read_text() == "go"  # the flow as it was
    assert (flows / "rewritten.txt").read_text() == "go"  # and as it had become


def test_a_called_flow_brings_its_own_skills_and_hands_the_agents_back(
    flows: Path,
) -> None:
    """A skill is the flow's, so the flow that called it goes on carrying its own."""
    from hmz.agents.skills import Loaded

    card = "---\nname: {name}\ndescription: does a thing\n---\n\nDo it.\n"
    written(
        flows / ".humanize/flows",
        "deep",
        INNER,
        {"deep-notes": card.format(name="deep-notes")},
    )
    written(
        flows / ".humanize/flows",
        "over",
        '"""Says what it is carrying, before, during and after."""\n\n'
        "from pathlib import Path\n\n"
        "from hmz.agents import AgentBase\n"
        "from hmz.flows import flow\n"
        "from hmz.flows import load\n\n\n"
        "@flow\n"
        "def run(agents: tuple[AgentBase], task: str) -> None:\n"
        "    (agent,) = agents\n"
        '    said = [",".join(one.name for one in agent.loaded)]\n'
        '    load("deep")(agents, task)\n'
        '    said.append(",".join(one.name for one in agent.loaded))\n'
        '    Path("carried.txt").write_text("|".join(said))\n',
        {"over-notes": card.format(name="over-notes")},
    )
    agent = ShellAgent(CONFIG)

    Runner("over", [agent]).run("go")

    # Its own before the call, and its own again after it.
    assert (flows / "carried.txt").read_text() == "over-notes|over-notes"
    assert [one.name for one in agent.loaded] == ["over-notes"]
    assert isinstance(agent.loaded[0], Loaded)


def test_a_called_flow_can_explicitly_inherit_its_callers_skills(flows: Path) -> None:
    """A wrapper can add a skill without copying the called flow's own bundle."""
    card = "---\nname: {name}\ndescription: does a thing\n---\n\n{says}\n"
    inner = '''"""Records everything it carries."""

from pathlib import Path

from hmz.agents import AgentBase
from hmz.flows import flow


@flow
def run(agents: tuple[AgentBase], task: str) -> None:
    (agent,) = agents
    names = ",".join(one.name for one in agent.loaded)
    shared = next(one for one in agent.loaded if one.name == "shared")
    Path("inherited.txt").write_text(names + "|" + (shared.at / "SKILL.md").read_text())
'''
    written(
        flows / ".humanize/flows",
        "deep",
        inner,
        {
            "deep-notes": card.format(name="deep-notes", says="Deep."),
            "shared": card.format(name="shared", says="Child wins."),
        },
    )
    written(
        flows / ".humanize/flows",
        "over",
        '''"""Passes its skills into a called flow."""

from pathlib import Path

from hmz.agents import AgentBase
from hmz.flows import flow
from hmz.flows import load


@flow
def run(agents: tuple[AgentBase], task: str) -> None:
    load("deep", inherit_skills=True)(agents, task)
    Path("restored.txt").write_text(",".join(one.name for one in agents[0].loaded))
''',
        {
            "over-notes": card.format(name="over-notes", says="Over."),
            "shared": card.format(name="shared", says="Parent loses."),
        },
    )
    agent = ShellAgent(CONFIG)

    Runner("over", [agent]).run("go")

    inherited = (flows / "inherited.txt").read_text()
    assert inherited.startswith("deep-notes,shared,over-notes|")
    assert "Child wins." in inherited
    assert "Parent loses." not in inherited
    assert (flows / "restored.txt").read_text() == "over-notes,shared"
    assert [one.name for one in agent.loaded] == ["over-notes", "shared"]


def test_inherited_skills_are_restored_when_the_called_flow_raises(flows: Path) -> None:
    """The template's cleanup applies to unsuccessful calls as well as returns."""
    card = "---\nname: {name}\ndescription: does a thing\n---\n\nDo it.\n"
    written(
        flows / ".humanize/flows",
        "bad",
        '''"""Fails after receiving inherited skills."""

from hmz.agents import AgentBase
from hmz.flows import flow


@flow
def run(agents: tuple[AgentBase], task: str) -> None:
    assert [one.name for one in agents[0].loaded] == ["child", "parent"]
    raise RuntimeError("no")
''',
        {"child": card.format(name="child")},
    )
    written(
        flows / ".humanize/flows",
        "over",
        '''"""Catches a failed inherited call and records its restored skills."""

from pathlib import Path

from hmz.agents import AgentBase
from hmz.flows import flow
from hmz.flows import load


@flow
def run(agents: tuple[AgentBase], task: str) -> None:
    try:
        load("bad", inherit_skills=True)(agents, task)
    except RuntimeError:
        pass
    Path("restored-after-error.txt").write_text(",".join(one.name for one in agents[0].loaded))
''',
        {"parent": card.format(name="parent")},
    )

    Runner("over", [ShellAgent(CONFIG)]).run("go")

    assert (flows / "restored-after-error.txt").read_text() == "parent"

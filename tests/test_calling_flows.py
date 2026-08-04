"""One flow reaching for another by name, running it, and being seen to.

A flow is a loop over agents, and a loop worth having is one another loop can reach for. So a
flow asks for one the way a person does -- by the name `-f` takes -- and is handed the flow's
own function to run with the agents it already has. What is running is written down as it
happens, since a flow is a Python file and nothing can ask it what it is doing.
"""

from __future__ import annotations

import json
import pathlib
from typing import TYPE_CHECKING

import pytest

from hmz.agents import AgentConfig
from hmz.runner import NotAFlow, Runner, calls, running
from tests.stubs import ShellAgent, written

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
from hmz.runner import calls, running


@flow
def run(agents: tuple[AgentBase], task: str) -> None:
    Path("running.txt").write_text(",".join(one.flow for one in running()))
    calls("inner")(agents, f"inner: {task}")
    Path("outer.txt").write_text(task)
'''


@pytest.fixture(autouse=True)
def flows(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A project with two flows of its own in it, and a home nothing else has written to."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    where = tmp_path / "project"
    (where / ".humanize/flows").mkdir(parents=True)
    written(where / ".humanize/flows", "inner", INNER)
    written(where / ".humanize/flows", "outer", OUTER)
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
        "from hmz.runner import running\n\n\n"
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
        "from hmz.runner import calls\n\n\n"
        "@flow\n"
        "def run(agents: tuple[AgentBase], task: str) -> None:\n"
        '    calls("deep")(agents, task)\n',
    )

    Runner("over", [ShellAgent(CONFIG)]).run("go")

    assert (flows / "deep.txt").read_text() == "over > deep"


def test_a_flow_asked_for_by_a_name_nothing_answers_to_says_so_when_it_is_asked() -> (
    None
):
    """At the asking rather than an hour into a loop, which is the point of asking early."""
    with pytest.raises(NotAFlow):
        calls("no_such_flow_anywhere")


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

    calls("named")([one, two], "go")

    said = (flows / "named.txt").read_text()
    assert said.startswith("Both ")
    assert said.endswith(one.id)  # handed over in the order they were given


def test_a_called_flow_given_the_wrong_number_of_agents_says_so(flows: Path) -> None:
    """Before its first turn, which is where every other miscount is caught."""
    del flows
    with pytest.raises(NotAFlow, match="drives 1 agents, 2 given"):
        calls("inner")([ShellAgent(CONFIG), ShellAgent(CONFIG)], "go")


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

    calls("settable")([ShellAgent(CONFIG)], "go", {"rounds": 9})
    assert (flows / "settable.txt").read_text() == "9"

    calls("settable")(
        [ShellAgent(CONFIG)], "go"
    )  # and as it comes, where none was given
    assert (flows / "settable.txt").read_text() == "3"

    with pytest.raises(NotAFlow, match="takes no config"):
        calls("inner")([ShellAgent(CONFIG)], "go", {"rounds": 9})


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
        "from hmz.runner import running\n\n\n"
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
        "from hmz.runner import calls\n\n\n"
        "@flow\n"
        "async def run(agents: tuple[AgentBase], task: str) -> None:\n"
        '    await calls("slow")(agents, task)\n'
        '    Path("after.txt").write_text("and then this")\n',
    )

    Runner("waits", [ShellAgent(CONFIG)]).run("go")

    # It really was awaited: the file the called flow writes is there, and it was running
    # under the flow that called it while it wrote.
    assert (flows / "slow.txt").read_text() == "waits,slow"
    assert (flows / "after.txt").read_text() == "and then this"
    assert running() == ()


def test_the_run_writes_down_the_flow_it_called(flows: Path) -> None:
    """A cycle is what a run was, and a flow that called another is part of what it was."""
    Runner("outer", [ShellAgent(CONFIG)]).run("do it")

    import os

    cycles = sorted(pathlib.Path(os.environ["HUMANIZE_HOME"]).rglob("*.jsonl"))
    said = [json.loads(line) for line in cycles[-1].read_text().splitlines()]
    called = [one for one in said if one["event"] in ("called", "returned")]

    assert [one["event"] for one in called] == ["called", "returned"]
    assert called[0]["flow"] == "inner"
    assert called[0]["task"] == "inner: do it"


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
        "from hmz.runner import calls\n\n\n"
        "@flow\n"
        "def run(agents: tuple[AgentBase], task: str) -> None:\n"
        '    calls("bad")(agents, task)\n',
    )

    with pytest.raises(RuntimeError, match="no"):
        Runner("tries", [ShellAgent(CONFIG)]).run("go")

    assert running() == ()


def test_a_flow_rewritten_between_calls_is_the_one_that_runs_next(flows: Path) -> None:
    """Which is what makes a loop that improves its own flows a loop that then runs them.

    A flow is a directory on disk, read by running it, and `calls` reads it again at every
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
        "from hmz.runner import calls\n\n\n"
        "@flow\n"
        "def run(agents: tuple[AgentBase], task: str) -> None:\n"
        '    calling = calls("inner")\n'
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
        "from hmz.runner import calls\n\n\n"
        "@flow\n"
        "def run(agents: tuple[AgentBase], task: str) -> None:\n"
        "    (agent,) = agents\n"
        '    said = [",".join(one.name for one in agent.loaded)]\n'
        '    calls("deep")(agents, task)\n'
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

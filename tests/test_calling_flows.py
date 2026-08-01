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
from tests.stubs import ShellAgent

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
    (where / ".humanize/flows/inner.py").write_text(INNER)
    (where / ".humanize/flows/outer.py").write_text(OUTER)
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
    (flows / ".humanize/flows/deep.py").write_text(
        '"""Says what is running while it runs."""\n\n'
        "from pathlib import Path\n\n"
        "from hmz.agents import AgentBase\n"
        "from hmz.flows import flow\n"
        "from hmz.runner import running\n\n\n"
        "@flow\n"
        "def run(agents: tuple[AgentBase], task: str) -> None:\n"
        '    Path("deep.txt").write_text(" > ".join(one.flow for one in running()))\n'
    )
    (flows / ".humanize/flows/over.py").write_text(
        '"""Calls the one that says."""\n\n'
        "from hmz.agents import AgentBase\n"
        "from hmz.flows import flow\n"
        "from hmz.runner import calls\n\n\n"
        "@flow\n"
        "def run(agents: tuple[AgentBase], task: str) -> None:\n"
        '    calls("deep")(agents, task)\n'
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
    (flows / ".humanize/flows/named.py").write_text(
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
        '    Path("named.txt").write_text(type(agents).__name__ + " " + agents.builder.id)\n'
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
    (flows / ".humanize/flows/settable.py").write_text(
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
        '    Path("settable.txt").write_text(str((config or Config()).rounds))\n'
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
    (flows / ".humanize/flows/slow.py").write_text(
        '"""A flow written as a coroutine."""\n\n'
        "import asyncio\n"
        "from pathlib import Path\n\n"
        "from hmz.agents import AgentBase\n"
        "from hmz.flows import flow\n"
        "from hmz.runner import running\n\n\n"
        "@flow\n"
        "async def run(agents: tuple[AgentBase], task: str) -> None:\n"
        "    await asyncio.sleep(0)\n"
        '    Path("slow.txt").write_text(",".join(one.flow for one in running()))\n'
    )
    (flows / ".humanize/flows/waits.py").write_text(
        '"""Waits for the one it called."""\n\n'
        "from pathlib import Path\n\n"
        "from hmz.agents import AgentBase\n"
        "from hmz.flows import flow\n"
        "from hmz.runner import calls\n\n\n"
        "@flow\n"
        "async def run(agents: tuple[AgentBase], task: str) -> None:\n"
        '    await calls("slow")(agents, task)\n'
        '    Path("after.txt").write_text("and then this")\n'
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
    (flows / ".humanize/flows/bad.py").write_text(
        '"""Raises."""\n\n'
        "from hmz.agents import AgentBase\n"
        "from hmz.flows import flow\n\n\n"
        "@flow\n"
        "def run(agents: tuple[AgentBase], task: str) -> None:\n"
        '    raise RuntimeError("no")\n'
    )
    (flows / ".humanize/flows/tries.py").write_text(
        '"""Calls the one that raises, and lets it through."""\n\n'
        "from hmz.agents import AgentBase\n"
        "from hmz.flows import flow\n"
        "from hmz.runner import calls\n\n\n"
        "@flow\n"
        "def run(agents: tuple[AgentBase], task: str) -> None:\n"
        '    calls("bad")(agents, task)\n'
    )

    with pytest.raises(RuntimeError, match="no"):
        Runner("tries", [ShellAgent(CONFIG)]).run("go")

    assert running() == ()

"""A flow that calls a flow that calls a flow, as deep as it likes and several at once.

One flow reaching for another is one thing; a flow that decides how deep to go and runs two
branches of itself at the same time is the thing that has to be tracked rather than listed. A
run of those is a tree -- each flow under the one that called it, two gathered siblings under
neither -- and what is checked here is that it runs as one, is written down as one, reads back
as one, and unwinds as one when it is stopped partway.
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any

import pytest

from hmz.coganchor.agents import AgentConfig
from hmz.coganchor.agents.skills import Loaded
from hmz.flows import NotAFlow, load, running
from hmz.runtime.epic import epics, records, sessions, tree
from hmz.runtime.runner import Runner
from tests.stubs import ShellAgent, events, written

if TYPE_CHECKING:
    from pathlib import Path

CONFIG = AgentConfig(model="m", effort="high")

#: A flow that calls two of itself at once until it has gone as deep as it was told to, and
#: writes down the branch it was on at every level. Dynamic in the depth, since a recursion
#: whose depth is written into the file is a recursion a test wrote rather than one a flow did.
DEEPER = '''"""Two of itself at once, until it has gone deep enough."""

import asyncio
import json
from pathlib import Path

from pydantic import BaseModel

from hmz.coganchor.agents import AgentBase
from hmz.flows import flow, load, running


class Config(BaseModel):
    """How much further to go."""

    left: int = 0
    trail: str = ""


@flow
async def run(agents: tuple[AgentBase], task: str, config: Config | None = None) -> None:
    setting = config or Config()
    with Path("branches.jsonl").open("a") as out:
        out.write(json.dumps({
            "trail": setting.trail,
            "running": [one.flow for one in running()],
            "deep": [one.depth for one in running()],
        }) + "\\n")
    if setting.left <= 0:
        agents[0].new()("echo bottom")
        return
    # An agent apiece, which is what makes two branches of one run two branches: an agent
    # both of them were driving would be writing where they were both called from.
    await asyncio.gather(*(
        load("deeper")(
            [agents[0].clone()],
            task,
            {"left": setting.left - 1, "trail": setting.trail + side},
        )
        for side in ("L", "R")
    ))
'''

#: A flow that opens a session with its sibling holding the same agent, and does not leave
#: until the sibling's session is open too. Which makes "while both of them have it" a stretch
#: of time rather than a race: what an agent is writing to is read as each session opens.
OPENS = '''"""Opens a session while its sibling is running, and stays until that one has too."""

import asyncio
import uuid
from pathlib import Path

from hmz.coganchor.agents import AgentBase
from hmz.flows import flow

MINE = uuid.uuid4().hex


async def _both(named: str) -> None:
    """Waits until this flow and the one gathered beside it have both got this far."""
    Path(f"{named}-{MINE}.txt").write_text("")
    while len(list(Path.cwd().glob(f"{named}-*.txt"))) < 2:
        await asyncio.sleep(0.001)


@flow
async def run(agents: tuple[AgentBase], task: str) -> None:
    await _both("inside")
    await agents[0].new().aturn("echo shared")
    await _both("opened")
'''

#: The one somebody starts, which says how deep the whole thing goes.
OUTER = '''"""Starts the recursion, five levels of it."""

from hmz.coganchor.agents import AgentBase
from hmz.flows import flow, load


@flow
async def run(agents: tuple[AgentBase], task: str) -> None:
    await load("deeper")(agents, task, {"left": 4, "trail": "-"})
'''


@pytest.fixture(autouse=True)
def flows(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A project holding a flow that calls itself, and a home nothing wrote to."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    where = tmp_path / "project"
    (where / ".humanize/flows").mkdir(parents=True)
    written(where / ".humanize/flows", "deeper", DEEPER)
    written(where / ".humanize/flows", "outer", OUTER)
    monkeypatch.chdir(where)
    return where


def _branches(flows: Path) -> dict[str, dict[str, Any]]:
    """What each level of the recursion said about itself, by the branch it was on."""
    said = [
        json.loads(line)
        for line in (flows / "branches.jsonl").read_text().splitlines()
        if line
    ]
    return {one["trail"]: one for one in said}


def test_a_flow_that_calls_two_of_itself_at_once_runs_every_branch(flows: Path) -> None:
    """Five levels, doubling at each of them, which is thirty-one runs of one flow."""
    Runner("outer", [ShellAgent(CONFIG)]).run("go")

    branches = _branches(flows)
    # One per node of a five-level binary tree: the root, and two children apiece.
    assert len(branches) == 31
    assert "-LLLL" in branches  # and it really went all the way down one of them
    assert "-RLRL" in branches


def test_what_is_running_inside_a_gathered_call_is_the_branch_it_is_on(
    flows: Path,
) -> None:
    """Not its sibling, which is running beside it and under neither of them."""
    Runner("outer", [ShellAgent(CONFIG)]).run("go")

    branches = _branches(flows)
    # The flow somebody started, then one entry per call that had to be made to get here --
    # and never two entries for one level, however many of that level were running at once.
    assert branches["-LRLR"]["running"] == ["outer", *["deeper"] * 5]
    assert branches["-LRLR"]["deep"] == [0, 1, 2, 3, 4, 5]
    assert branches["-"]["running"] == ["outer", "deeper"]
    assert branches["-"]["deep"] == [0, 1]
    assert running() == ()  # and nothing is left on any branch when the run is over


def test_the_epic_reads_back_as_the_tree_the_run_actually_was(flows: Path) -> None:
    """A record apiece, each inside the one that called it, however deep it went."""
    Runner("outer", [ShellAgent(CONFIG)]).run("go")

    (epic,) = epics()
    (top,) = tree(epic)

    assert top.flow == "deeper"
    assert len(top.calls) == 2  # the two it gathered, and neither under the other
    assert {one.record for one in top.calls} != {top.record}
    walked, at = 1, top
    while at.calls:
        at, walked = at.calls[0], walked + 1
    assert walked == 5  # five levels of it, read back as five
    # Every record of the epic is somewhere in that tree, and each of them once.
    seen: list[str] = []

    def walk(calls: tuple[Any, ...]) -> None:
        for one in calls:
            seen.append(one.record)
            walk(one.calls)

    walk(top.calls)
    seen.append(top.record)
    assert sorted(seen) == sorted(one.name for one in records(epic)[1:])
    assert len(seen) == len(set(seen))


def test_no_record_is_attributed_to_the_wrong_parent(flows: Path) -> None:
    """Each record says which one called it, and that is the one that says it called it."""
    Runner("outer", [ShellAgent(CONFIG)]).run("go")

    (epic,) = epics()
    for record in records(epic)[1:]:
        began = next(one for one in events(record) if one["event"] == "began")
        called = [
            one
            for one in events(epic / began["under"])
            if one["event"] == "called" and one["epic"] == record.name
        ]
        assert (
            len(called) == 1
        )  # said once, by the record that says this one is under it


def test_a_session_opened_at_the_bottom_is_written_where_it_was_opened(
    flows: Path,
) -> None:
    """Sixteen leaves open sixteen sessions, and no two of them land in one record."""
    Runner("outer", [ShellAgent(CONFIG)]).run("go")

    (epic,) = epics()
    opened = sessions(epic)

    assert len(opened) == 16  # a leaf apiece
    assert (
        len({one.record for one in opened}) == 16
    )  # each in the record that opened it
    assert all(one.flow == "deeper" for one in opened)


def test_a_recursion_stopped_partway_unwinds_every_level_of_itself(
    flows: Path,
) -> None:
    """What a ctrl+c reaches is every branch of it, each handing its agents back."""
    written(
        flows / ".humanize/flows",
        "cancels",
        '"""Goes deep and is taken down while it is down there."""\n\n'
        "import asyncio\n\n"
        "from hmz.coganchor.agents import AgentBase\n"
        "from hmz.flows import flow, load\n\n\n"
        "@flow\n"
        "async def run(agents: tuple[AgentBase], task: str) -> None:\n"
        "    going = asyncio.gather(\n"
        '        load("waits")(agents, task, {"left": 4}),\n'
        '        load("waits")(agents, task, {"left": 4}),\n'
        "    )\n"
        "    await asyncio.sleep(0.05)\n"
        "    going.cancel()\n"
        "    try:\n"
        "        await going\n"
        "    except asyncio.CancelledError:\n"
        "        pass\n",
    )
    written(
        flows / ".humanize/flows",
        "waits",
        '"""Calls itself down and then waits to be taken down."""\n\n'
        "import asyncio\n\n"
        "from pydantic import BaseModel\n\n"
        "from hmz.coganchor.agents import AgentBase\n"
        "from hmz.flows import flow, load\n\n\n"
        "class Config(BaseModel):\n"
        '    """How much further."""\n\n'
        "    left: int = 0\n\n\n"
        "@flow\n"
        "async def run(agents: tuple[AgentBase], task: str, config: Config | None = None)"
        " -> None:\n"
        "    setting = config or Config()\n"
        "    if setting.left <= 0:\n"
        "        await asyncio.sleep(30)\n"
        "        return\n"
        '    await load("waits")(agents, task, {"left": setting.left - 1})\n',
    )
    agent = ShellAgent(CONFIG)

    Runner("cancels", [agent]).run("go")

    assert running() == ()  # every level of both branches came off it
    assert agent.epic is None  # and the agent was handed back as the run found it
    (epic,) = epics()
    for record in records(epic)[1:]:
        ended = [one for one in events(record) if one["event"] == "ended"]
        assert [one["how"] for one in ended] == ["failed"]


def test_a_chain_of_flows_with_no_bottom_to_it_is_refused(flows: Path) -> None:
    """A flow that calls itself and never stops is a flow to correct, and says which one."""
    written(
        flows / ".humanize/flows",
        "forever",
        '"""Calls itself, and nothing stops it."""\n\n'
        "from hmz.coganchor.agents import AgentBase\n"
        "from hmz.flows import flow, load\n\n\n"
        "@flow\n"
        "def run(agents: tuple[AgentBase], task: str) -> None:\n"
        '    load("forever")(agents, task)\n',
    )

    with pytest.raises(NotAFlow, match="flows deep"):
        Runner("forever", [ShellAgent(CONFIG)]).run("go")

    assert running() == ()


def test_a_call_may_say_what_the_flow_it_calls_is_driven_at(flows: Path) -> None:
    """Which is a clone at that config rather than the agent set up again."""
    written(
        flows / ".humanize/flows",
        "says",
        '"""Says what it was handed."""\n\n'
        "from pathlib import Path\n\n"
        "from hmz.coganchor.agents import AgentBase\n"
        "from hmz.flows import flow\n\n\n"
        "@flow\n"
        "def run(agents: tuple[AgentBase], task: str) -> None:\n"
        '    Path("says.txt").write_text(\n'
        '        agents[0].config.effort + " " + agents[0].id\n'
        "    )\n",
    )
    agent = ShellAgent(CONFIG)

    load("says")([agent], "go", drives={agent.id: AgentConfig(model="m", effort="max")})

    said = (flows / "says.txt").read_text()
    assert said.startswith("max ")  # driven at what the call said
    assert not said.endswith(
        agent.id
    )  # and by a second agent, which is what a clone is
    assert agent.config.effort == "high"  # the caller's own is untouched


def test_a_call_that_says_what_it_drives_names_a_place_the_flow_has(
    flows: Path,
) -> None:
    """Said where the call was written, rather than caught by the flow it was aimed at."""
    written(
        flows / ".humanize/flows",
        "named",
        '"""One agent, and it says what it calls it."""\n\n'
        "from typing import NamedTuple\n\n"
        "from hmz.coganchor.agents import AgentBase\n"
        "from hmz.flows import flow\n\n\n"
        "class One(NamedTuple):\n"
        '    """The one."""\n\n'
        "    builder: AgentBase\n\n\n"
        "@flow\n"
        "def run(agents: One, task: str) -> None:\n"
        "    pass\n",
    )
    config = AgentConfig(model="m", effort="max")

    load("named")([ShellAgent(CONFIG)], "go", drives={"builder": config})

    with pytest.raises(NotAFlow, match="nothing it drives is called 'reviewer'"):
        load("named")([ShellAgent(CONFIG)], "go", drives={"reviewer": config})


def test_two_calls_sharing_one_agent_leave_it_where_they_were_both_called_from(
    flows: Path,
) -> None:
    """Neither of them may have it: a session it opens is part of the flow they share."""
    written(
        flows / ".humanize/flows",
        "shares",
        '"""Gathers two calls over one agent, and neither gets it."""\n\n'
        "import asyncio\n\n"
        "from hmz.coganchor.agents import AgentBase\n"
        "from hmz.flows import flow, load\n\n\n"
        "@flow\n"
        "async def run(agents: tuple[AgentBase], task: str) -> None:\n"
        "    await asyncio.gather(\n"
        '        load("opens")(agents, task),\n'
        '        load("opens")(agents, task),\n'
        "    )\n",
    )
    written(flows / ".humanize/flows", "opens", OPENS)
    agent = ShellAgent(CONFIG)

    Runner("shares", [agent]).run("go")

    (epic,) = epics()
    opened = sessions(epic)

    assert len(opened) == 2
    # Both in the run's own record, which is the flow that called them: writing one of them
    # into a sibling's record would be filing it under a flow that happened to be there.
    assert {one.record for one in opened} == {"epic.jsonl"}
    assert {one.flow for one in opened} == {"shares"}


def test_two_calls_sharing_an_agent_leave_it_in_the_record_of_the_flow_they_share(
    flows: Path,
) -> None:
    """The flow they were both called from, which may be five flows down and not the run."""
    written(
        flows / ".humanize/flows",
        "top",
        '"""Calls the one that gathers, so that the fork is not the run itself."""\n\n'
        "from hmz.coganchor.agents import AgentBase\n"
        "from hmz.flows import flow, load\n\n\n"
        "@flow\n"
        "async def run(agents: tuple[AgentBase], task: str) -> None:\n"
        '    await load("shares")(agents, task)\n',
    )
    written(
        flows / ".humanize/flows",
        "shares",
        '"""Gathers two calls over the one agent it was handed."""\n\n'
        "import asyncio\n\n"
        "from hmz.coganchor.agents import AgentBase\n"
        "from hmz.flows import flow, load\n\n\n"
        "@flow\n"
        "async def run(agents: tuple[AgentBase], task: str) -> None:\n"
        "    await asyncio.gather(\n"
        '        load("opens")(agents, task),\n'
        '        load("opens")(agents, task),\n'
        "    )\n",
    )
    written(flows / ".humanize/flows", "opens", OPENS)

    Runner("top", [ShellAgent(CONFIG)]).run("go")

    (epic,) = epics()
    opened = sessions(epic)

    assert len(opened) == 2
    # In `shares`, which called them both -- not in the run's own record, which is two flows
    # further out than the flow they actually share.
    assert {one.flow for one in opened} == {"shares"}
    assert len({one.record for one in opened}) == 1
    assert opened[0].record != "epic.jsonl"


def test_a_call_driving_agents_of_its_own_is_still_part_of_the_run(flows: Path) -> None:
    """A branch with none of the run's agents left must not be a branch written down nowhere."""
    written(
        flows / ".humanize/flows",
        "aims",
        '"""Calls one flow at another effort, straight from the run\'s own flow."""\n\n'
        "from dataclasses import replace\n\n"
        "from hmz.coganchor.agents import AgentBase\n"
        "from hmz.flows import flow, load\n\n\n"
        "@flow\n"
        "def run(agents: tuple[AgentBase], task: str) -> None:\n"
        '    careful = replace(agents[0].config, effort="max")\n'
        '    load("opened")(agents, task, drives={agents[0].id: careful})\n',
    )
    written(
        flows / ".humanize/flows",
        "opened",
        '"""Opens a session, so the record has something in it."""\n\n'
        "from hmz.coganchor.agents import AgentBase\n"
        "from hmz.flows import flow\n\n\n"
        "@flow\n"
        "def run(agents: tuple[AgentBase], task: str) -> None:\n"
        "    agents[0].new()('echo aimed')\n",
    )

    Runner("aims", [ShellAgent(CONFIG)]).run("go")

    (epic,) = epics()
    (one,) = tree(epic)

    assert one.flow == "opened"  # the call was written down at all
    (session,) = sessions(epic)
    assert session.record == one.record  # and what the clone opened is in that record
    assert session.flow == "opened"


def test_a_flow_called_from_a_thread_with_no_branch_on_it_is_still_written_down(
    flows: Path,
) -> None:
    """A tool a turn reached for is the flow's own code on somebody else's thread."""
    written(
        flows / ".humanize/flows",
        "elsewhere",
        '"""Calls a flow from a thread of its own, the way a tool callback would."""\n\n'
        "from concurrent.futures import ThreadPoolExecutor\n\n"
        "from hmz.coganchor.agents import AgentBase\n"
        "from hmz.flows import flow, load\n\n\n"
        "@flow\n"
        "def run(agents: tuple[AgentBase], task: str) -> None:\n"
        "    with ThreadPoolExecutor(max_workers=1) as apart:\n"
        '        apart.submit(load("opened"), agents, task).result()\n',
    )
    written(
        flows / ".humanize/flows",
        "opened",
        '"""Opens a session, so the record has something in it."""\n\n'
        "from hmz.coganchor.agents import AgentBase\n"
        "from hmz.flows import flow\n\n\n"
        "@flow\n"
        "def run(agents: tuple[AgentBase], task: str) -> None:\n"
        "    agents[0].new()('echo apart')\n",
    )

    Runner("elsewhere", [ShellAgent(CONFIG)]).run("go")

    (epic,) = epics()
    (one,) = tree(epic)

    assert one.flow == "opened"  # written down, rather than lost with the thread
    (session,) = sessions(epic)
    assert session.record == one.record


def test_a_gathered_call_cancelled_before_it_starts_takes_nothing(flows: Path) -> None:
    """A coroutine that never ran is a call that never happened, holding nothing."""
    written(
        flows / ".humanize/flows",
        "drops",
        '"""Gathers two calls and takes them down before either got a step."""\n\n'
        "import asyncio\n\n"
        "from hmz.coganchor.agents import AgentBase\n"
        "from hmz.flows import flow, load\n\n\n"
        "@flow\n"
        "async def run(agents: tuple[AgentBase], task: str) -> None:\n"
        "    going = asyncio.gather(\n"
        '        load("naps")(agents, task),\n'
        '        load("naps")(agents, task),\n'
        "    )\n"
        "    going.cancel()\n"
        "    try:\n"
        "        await going\n"
        "    except asyncio.CancelledError:\n"
        "        pass\n",
    )
    written(
        flows / ".humanize/flows",
        "naps",
        '"""Waits, and is never let to."""\n\n'
        "import asyncio\n\n"
        "from hmz.coganchor.agents import AgentBase\n"
        "from hmz.flows import flow\n\n\n"
        "@flow\n"
        "async def run(agents: tuple[AgentBase], task: str) -> None:\n"
        "    await asyncio.sleep(30)\n",
    )
    agent = ShellAgent(CONFIG)

    Runner("drops", [agent]).run("go")

    assert running() == ()  # nothing left on any branch
    assert agent.epic is None  # and the agent was handed back
    (epic,) = epics()
    # A call that never ran is a call that was never written down, rather than one with a
    # `began` and no end to it.
    assert [one.name for one in records(epic)] == ["epic.jsonl"]


def test_a_called_flow_hands_its_agents_back_however_two_calls_end(flows: Path) -> None:
    """Back to what they were before the first of them took them, not to what one saw."""
    written(
        flows / ".humanize/flows",
        "carries",
        '"""Gathers two calls that each bring skills of their own."""\n\n'
        "import asyncio\n\n"
        "from hmz.coganchor.agents import AgentBase\n"
        "from hmz.flows import flow, load\n\n\n"
        "@flow\n"
        "async def run(agents: tuple[AgentBase], task: str) -> None:\n"
        "    await asyncio.gather(\n"
        '        load("brings")(agents, task),\n'
        '        load("brings")(agents, task),\n'
        "    )\n",
    )
    card = "---\nname: brought\ndescription: does a thing\n---\n\nDo it.\n"
    written(
        flows / ".humanize/flows",
        "brings",
        '"""Brings a skill of its own."""\n\n'
        "import asyncio\n\n"
        "from hmz.coganchor.agents import AgentBase\n"
        "from hmz.flows import flow\n\n\n"
        "@flow\n"
        "async def run(agents: tuple[AgentBase], task: str) -> None:\n"
        "    await asyncio.sleep(0.02)\n",
        {"brought": card},
    )
    agent = ShellAgent(CONFIG)
    agent.loads([Loaded("mine", flows)])

    asyncio.run(_gathered(agent))

    assert [one.name for one in agent.loaded] == ["mine"]


async def _gathered(agent: ShellAgent) -> None:
    """Runs the flow that gathers two calls over one agent, from a loop of this test's own."""
    answered = load("carries")([agent], "go")
    assert answered is not None
    await answered

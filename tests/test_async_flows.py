"""A flow written as `async def run`, which is the other way one may be written.

A flow is a loop over turns, and a loop that has more than one turn going at a time is a loop
that has to be able to wait for several things at once. So `run` may be a coroutine, and what
starts it does not change: `Runner.run` waits for the flow either way, and the run is written
down, checked and stopped exactly as it was. What is checked here is that both kinds of flow
are read the same, run the same, and end the same -- finished, failed or stopped by hand.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from humanize.agents import AgentConfig, Stopped
from humanize.cli import main
from humanize.cycle import cycles, opened
from humanize.runner import NotAFlow, Runner, configures, drives, wanted
from tests.stubs import ShellAgent

if TYPE_CHECKING:
    from pathlib import Path

CONFIG = AgentConfig(model="m", effort="high")

#: A flow that is a coroutine, driving two agents at once and writing down what came back.
#: Every turn of it is awaited, which is the whole difference: `agent(task)` is the turn,
#: `await agent.aturn(task)` is the same turn with the loop handed back while it takes.
ASYNC = '''
import asyncio
import json
from pathlib import Path
from typing import NamedTuple

from humanize.agents import AgentBase


class Agents(NamedTuple):
    """The two this drives, at once rather than one after the other."""

    actor: AgentBase
    reviewer: AgentBase


async def run(agents: Agents, task: str) -> None:
    acted, reviewed = await asyncio.gather(
        agents.actor.aturn(f"echo acted-{task}"),
        agents.reviewer.aturn(f"echo reviewed-{task}"),
    )
    Path(__file__).with_suffix(".json").write_text(
        json.dumps({"task": task, "said": [acted, reviewed]})
    )
'''

#: A coroutine flow that fans one agent out over many prompts at once, which is what a batch
#: is for: one session apiece, all of them going, and the answers in the order they were asked.
FANNED = """
import json
from pathlib import Path

from humanize.agents import AgentBase


async def run(agents: tuple[AgentBase], task: str) -> None:
    (agent,) = agents
    said = await agent.abatch([f"echo {task}-{at}" for at in range(12)])
    Path(__file__).with_suffix(".json").write_text(json.dumps(said))
"""

#: A coroutine flow that can be set up, which is read off its third argument as any flow's is.
SETTABLE = '''
import json
from pathlib import Path

from pydantic import BaseModel, Field

from humanize.agents import AgentBase


class Config(BaseModel):
    """What this flow takes."""

    rounds: int = Field(default=3, ge=1, le=9, description="how many times round")


async def run(agents: tuple[AgentBase], task: str, config: Config | None = None) -> None:
    setting = config or Config()
    said = [await agents[0].aturn(f"echo round-{at}") for at in range(setting.rounds)]
    Path(__file__).with_suffix(".json").write_text(
        json.dumps({"task": task, "rounds": setting.rounds, "said": said})
    )
'''

#: A coroutine flow that fails partway, which is a flow that failed and not a flow to correct.
FAILING = """
from humanize.agents import AgentBase


async def run(agents: tuple[AgentBase], task: str) -> None:
    agents[0]("echo one")
    raise ValueError("the flow itself went wrong")
"""

#: A coroutine flow stopped by hand: the agent is told to take no further turn, and the turn
#: after that raises where the flow is waiting for it.
STOPPED = """
from humanize.agents import AgentBase


async def run(agents: tuple[AgentBase], task: str) -> None:
    (agent,) = agents
    await agent.aturn("echo one")
    agent.stop()
    await agent.aturn("echo two")  # raises Stopped, out of the await and out of the flow
"""

#: A coroutine flow that runs no turn at all, and writes down what the command line handed
#: it: which agents, under what names, and the task.
RECORDING = '''
import asyncio
import json
from pathlib import Path
from typing import NamedTuple

from humanize.agents import AgentBase


class Agents(NamedTuple):
    """The two this drives, named as the flow calls them."""

    actor: AgentBase
    reviewer: AgentBase


async def run(agents: Agents, task: str) -> None:
    await asyncio.sleep(0)  # a flow that is a coroutine, and awaits like one
    Path(__file__).with_suffix(".json").write_text(
        json.dumps(
            {
                "agents": [[type(agent).__name__, agent.id] for agent in agents],
                "task": task,
            }
        )
    )
'''

#: A flow whose agents are a tuple of any length, which is no answer to how many it drives --
#: refused for a coroutine exactly as it is for a function.
UNCOUNTED = """
from humanize.agents import AgentBase


async def run(agents: tuple[AgentBase, ...], task: str) -> None:
    pass
"""


def _flow(tmp_path: Path, source: str, called: str = "flow") -> Path:
    """Writes a flow out and answers with its path."""
    where = tmp_path / f"{called}.py"
    where.write_text(source)
    return where


def _said(flow: Path) -> object:
    """What the flow wrote down beside itself."""
    return json.loads(flow.with_suffix(".json").read_text())


def test_a_flow_may_be_a_coroutine(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    flow = _flow(tmp_path, ASYNC)
    agents = [ShellAgent(CONFIG), ShellAgent(CONFIG)]

    Runner(flow, agents).run("the task")

    assert _said(flow) == {
        "task": "the task",
        "said": ["acted-the task", "reviewed-the task"],
    }


def test_a_coroutine_flow_says_how_many_agents_it_drives_and_what_they_are_for(
    tmp_path: Path,
) -> None:
    flow = _flow(tmp_path, ASYNC)

    assert drives(flow) == ("actor", "reviewer")
    assert [place.name for place in wanted(flow)] == ["actor", "reviewer"]
    assert configures(flow) is None
    # And is held to it before its first turn, as any other flow is.
    with pytest.raises(NotAFlow, match="drives 2 agents, 1 given"):
        Runner(flow, [ShellAgent(CONFIG)])


def test_a_coroutine_flow_that_says_nothing_about_how_many_it_drives_is_refused(
    tmp_path: Path,
) -> None:
    with pytest.raises(NotAFlow, match="tuple of a fixed length"):
        Runner(_flow(tmp_path, UNCOUNTED), [ShellAgent(CONFIG)])


def test_the_agents_of_a_coroutine_flow_are_named_by_the_places_they_fill(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    flow = _flow(tmp_path, ASYNC)
    agents = [ShellAgent(CONFIG), ShellAgent(CONFIG, name="mine")]

    Runner(flow, agents).run("go")

    assert agents[0].id == "actor"  # named where the flow said what it was for
    assert agents[1].id == "mine"  # a name given is a name kept


def test_a_coroutine_flow_drives_its_agents_at_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    flow = _flow(tmp_path, FANNED)

    Runner(flow, [ShellAgent(CONFIG)]).run("said")

    assert _said(flow) == [f"said-{at}" for at in range(12)]


def test_a_coroutine_flow_is_set_up_like_any_other(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    flow = _flow(tmp_path, SETTABLE)
    setting = configures(flow)
    assert setting is not None
    assert set(setting.model_fields) == {"rounds"}

    Runner(flow, [ShellAgent(CONFIG)], {"rounds": 2}).run("go")

    assert _said(flow) == {
        "task": "go",
        "rounds": 2,
        "said": ["round-0", "round-1"],
    }


def test_a_coroutine_flow_left_unset_runs_on_its_own_defaults(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    flow = _flow(tmp_path, SETTABLE)

    Runner(flow, [ShellAgent(CONFIG)]).run("go")

    assert _said(flow) == {
        "task": "go",
        "rounds": 3,
        "said": ["round-0", "round-1", "round-2"],
    }


def test_a_coroutine_flow_is_one_cycle_saying_what_each_agent_opened(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A run is a run however the flow was written: the same cycle, and the same sessions."""
    monkeypatch.chdir(tmp_path)
    flow = _flow(tmp_path, ASYNC)

    Runner(flow, [ShellAgent(CONFIG), ShellAgent(CONFIG)]).run("the task")

    (cycle,) = cycles()
    assert opened(cycle) == {
        "actor": ["acted-the task"],
        "reviewer": ["reviewed-the task"],
    }
    assert json.loads(cycle.read_text().splitlines()[-1])["how"] == "done"


def test_what_a_coroutine_flow_raises_comes_out_of_the_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ValueError, match="the flow itself went wrong"):
        Runner(_flow(tmp_path, FAILING), [ShellAgent(CONFIG)]).run("go")

    (cycle,) = cycles()
    assert json.loads(cycle.read_text().splitlines()[-1])["how"] == "failed"


def test_a_coroutine_flow_stopped_by_hand_is_written_down_as_stopped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    with pytest.raises(Stopped):
        Runner(_flow(tmp_path, STOPPED), [ShellAgent(CONFIG)]).run("go")

    (cycle,) = cycles()
    assert json.loads(cycle.read_text().splitlines()[-1])["how"] == "stopped"


async def test_a_coroutine_flow_started_from_a_loop_of_its_own_still_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Started from a thread already running a loop -- an interface, or this test.

    The flow gets a loop of its own rather than this one: a flow run on the loop it was
    started from would be a flow waiting for turns that are waiting for the loop the flow is
    holding, which is a run that never takes its first.
    """
    monkeypatch.chdir(tmp_path)
    flow = _flow(tmp_path, ASYNC)

    Runner(flow, [ShellAgent(CONFIG), ShellAgent(CONFIG)]).run("the task")

    assert _said(flow) == {
        "task": "the task",
        "said": ["acted-the task", "reviewed-the task"],
    }


def test_a_coroutine_flow_runs_from_the_command_line_as_any_other_does(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The whole path: `hmz exec`, the agents the line named, and a flow that is awaited.

    No turn is run: a flow decides for itself whether to launch anything, so one that only
    writes down what it was handed exercises the command line without a coding agent.
    """
    monkeypatch.chdir(tmp_path)
    flow = _flow(tmp_path, RECORDING)

    main(["exec", "-f", str(flow), "-a", "claude/m:high", "-a", "codex/m:high", "go"])

    assert _said(flow) == {
        "agents": [["ClaudeCodeAgent", "actor"], ["CodexAgent", "reviewer"]],
        "task": "go",
    }


def test_a_flow_that_is_not_a_coroutine_is_run_exactly_as_it_was(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The other half of it: adding one kind of flow may not have moved the other."""
    monkeypatch.chdir(tmp_path)
    flow = _flow(
        tmp_path,
        """
import json
from pathlib import Path

from humanize.agents import AgentBase


def run(agents: tuple[AgentBase], task: str) -> None:
    Path(__file__).with_suffix(".json").write_text(
        json.dumps(agents[0](f"echo {task}"))
    )
""",
    )

    Runner(flow, [ShellAgent(CONFIG)]).run("plainly")

    assert _said(flow) == "plainly"

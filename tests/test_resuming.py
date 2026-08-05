"""A flow that says it can be picked up where the last run of it left off.

A loop meant to run for a week is a loop that will be stopped and started: a machine goes
down, somebody presses esc, a turn takes the process with it. What such a flow needs is not a
second copy of the transcript -- the backends keep that -- but the handful of things it is
itself keeping track of: which round it is on, which files it has been through, what it has
decided so far. So a flow says it can be picked up, and is handed a dict: what it wrote there
last time, kept in the run's own cycle and saved as it writes.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from hmz.agents import AgentConfig, Stopped
from hmz.cycle import STATE, cycles, read, resumed, state
from hmz.runner import NotAFlow, Runner, resumes
from tests.stubs import ShellAgent, written

if TYPE_CHECKING:
    from pathlib import Path

CONFIG = AgentConfig(model="m", effort="high")

#: A flow that counts the runs of it, which is the smallest thing a state is for.
COUNTS = '''"""Counts the runs of itself."""

from typing import Any

from hmz.agents import AgentBase
from hmz.flows import flow


@flow(resumable=True)
def run(agents: tuple[AgentBase], task: str, state: dict[str, Any]) -> None:
    state["rounds"] = state.get("rounds", 0) + 1
    agents[0].new()(f"echo round-{state['rounds']}")
'''

#: One that takes a config as well, so the state is the argument after it.
CONFIGURED = '''"""Counts, and takes a setting."""

from typing import Any

from pydantic import BaseModel

from hmz.agents import AgentBase
from hmz.flows import flow


class Config(BaseModel):
    """What it takes."""

    step: int = 1


@flow(resumable=True)
def run(
    agents: tuple[AgentBase],
    task: str,
    config: Config | None = None,
    state: dict[str, Any] | None = None,
) -> None:
    held = state if state is not None else {}
    held["at"] = held.get("at", 0) + (config or Config()).step
'''


def _state(cycle: Path) -> dict[str, object]:
    """What one cycle's state file holds, by flow."""
    return json.loads((cycle / STATE).read_text())


def test_a_resumable_flow_is_handed_what_the_last_run_of_it_left(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Which is the whole of it: run it again, and it goes on rather than starting over."""
    monkeypatch.chdir(tmp_path)
    flow = written(tmp_path, "counts", COUNTS)

    for _ in range(3):
        Runner(flow, [ShellAgent(CONFIG)]).run("go")

    first, second, third = cycles()
    assert _state(first) == {str(flow): {"rounds": 1}}
    assert _state(second) == {str(flow): {"rounds": 2}}
    assert _state(third) == {str(flow): {"rounds": 3}}
    # Each run is a run of its own, whatever it picked up: a cycle is never reopened.
    assert read(third) is not None
    assert read(third).resumable  # pyright: ignore[reportOptionalMemberAccess]


def test_a_run_says_which_run_it_was_picked_up_from(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A cycle is what a run was, and being the second half of another one is part of that."""
    monkeypatch.chdir(tmp_path)
    flow = written(tmp_path, "counts", COUNTS)

    Runner(flow, [ShellAgent(CONFIG)]).run("go")
    Runner(flow, [ShellAgent(CONFIG)]).run("go")

    first, second = cycles()
    began = json.loads((second / "cycle.jsonl").read_text().splitlines()[0])
    assert began["picked_up"] == first.name
    assert began["resumable"] is True


def test_a_run_picked_up_from_a_named_cycle_takes_that_one_s_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Which is what choosing one in `/cycles` and carrying on comes to."""
    monkeypatch.chdir(tmp_path)
    flow = written(tmp_path, "counts", COUNTS)

    for _ in range(3):
        Runner(flow, [ShellAgent(CONFIG)]).run("go")
    first, _, _ = cycles()

    Runner(flow, [ShellAgent(CONFIG)], resume=first).run("go")

    assert _state(cycles()[-1]) == {str(flow): {"rounds": 2}}


def test_a_flow_that_says_nothing_is_run_from_the_top_every_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Which is what every flow was before there was such a thing as picking one up."""
    monkeypatch.chdir(tmp_path)
    flow = written(
        tmp_path,
        "plain",
        "from hmz.agents import AgentBase\n"
        "from hmz.flows import flow\n\n\n"
        "@flow\n"
        "def run(agents: tuple[AgentBase], task: str) -> None:\n"
        '    agents[0].new()("echo one")\n',
    )

    Runner(flow, [ShellAgent(CONFIG)]).run("go")

    assert not resumes(flow)
    assert not (cycles()[0] / STATE).exists()
    assert read(cycles()[0]) is not None
    assert not read(cycles()[0]).resumable  # pyright: ignore[reportOptionalMemberAccess]


def test_the_state_of_a_run_that_was_stopped_is_there_to_be_picked_up(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The point of it: state saved only at the end is state a stopped run has none of."""
    monkeypatch.chdir(tmp_path)
    flow = written(
        tmp_path,
        "stops",
        '"""Writes, and then is stopped where it stands."""\n\n'
        "from typing import Any\n\n"
        "from hmz.agents import AgentBase, Stopped\n"
        "from hmz.flows import flow\n\n\n"
        "@flow(resumable=True)\n"
        "def run(agents: tuple[AgentBase], task: str, state: dict[str, Any]) -> None:\n"
        '    state["reached"] = "half way"\n'
        '    raise Stopped("esc")\n',
    )

    with pytest.raises(Stopped):
        Runner(flow, [ShellAgent(CONFIG)]).run("go")

    (cycle,) = cycles()
    assert state(cycle) == {"reached": "half way"}
    assert resumed(str(flow)) == cycle


def test_something_written_inside_the_state_is_saved_when_the_run_ends(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A list appended to is a change no mapping can see, and is still what the flow kept."""
    monkeypatch.chdir(tmp_path)
    flow = written(
        tmp_path,
        "appends",
        '"""Appends to a list it keeps."""\n\n'
        "from typing import Any\n\n"
        "from hmz.agents import AgentBase\n"
        "from hmz.flows import flow\n\n\n"
        "@flow(resumable=True)\n"
        "def run(agents: tuple[AgentBase], task: str, state: dict[str, Any]) -> None:\n"
        '    state.setdefault("seen", []).append(task)\n',
    )

    Runner(flow, [ShellAgent(CONFIG)]).run("one")
    Runner(flow, [ShellAgent(CONFIG)]).run("two")

    assert state(cycles()[-1]) == {"seen": ["one", "two"]}


def test_a_resumable_flow_that_takes_a_config_is_handed_both(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The state is the argument after the config, which is where the flow declared it."""
    monkeypatch.chdir(tmp_path)
    flow = written(tmp_path, "configured", CONFIGURED)

    Runner(flow, [ShellAgent(CONFIG)], {"step": 4}).run("go")
    Runner(flow, [ShellAgent(CONFIG)], {"step": 4}).run("go")

    assert state(cycles()[-1]) == {"at": 8}


def test_a_called_flow_keeps_its_own_state_under_its_own_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A flow that called another is two flows, and neither writes the other's."""
    monkeypatch.chdir(tmp_path)
    where = tmp_path / ".humanize/flows"
    where.mkdir(parents=True)
    written(where, "inner", COUNTS)
    written(
        where,
        "outer",
        '"""Calls the one that counts, and counts itself."""\n\n'
        "from typing import Any\n\n"
        "from hmz.agents import AgentBase\n"
        "from hmz.flows import flow\n"
        "from hmz.runner import calls\n\n\n"
        "@flow(resumable=True)\n"
        "def run(agents: tuple[AgentBase], task: str, state: dict[str, Any]) -> None:\n"
        '    state["outer"] = state.get("outer", 0) + 1\n'
        '    calls("inner")(agents, task)\n',
    )

    Runner("outer", [ShellAgent(CONFIG)]).run("go")
    Runner("outer", [ShellAgent(CONFIG)]).run("go")

    held = _state(cycles()[-1])
    assert held == {"outer": {"outer": 2}, "inner": {"rounds": 2}}


def test_a_flow_called_outside_a_run_is_handed_a_dict_that_is_nowhere(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A call is a call: a flow with nowhere to keep its state runs and keeps none."""
    from hmz.runner import calls

    monkeypatch.chdir(tmp_path)
    where = tmp_path / ".humanize/flows"
    where.mkdir(parents=True)
    written(where, "counts", COUNTS)

    calls("counts")([ShellAgent(CONFIG)], "go")

    assert cycles() == []


def test_a_flow_that_says_it_resumes_and_takes_no_dict_says_so(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A flow is called with what it declares, so one that declares neither is one to correct."""
    monkeypatch.chdir(tmp_path)
    flow = written(
        tmp_path,
        "short",
        "from hmz.agents import AgentBase\n"
        "from hmz.flows import flow\n\n\n"
        "@flow(resumable=True)\n"
        "def run(agents: tuple[AgentBase], task: str) -> None:\n"
        "    pass\n",
    )

    assert resumes(flow)
    with pytest.raises(TypeError):
        Runner(flow, [ShellAgent(CONFIG)]).run("go")


def test_asking_a_flow_that_is_not_one_whether_it_resumes_says_it_is_not_one(
    tmp_path: Path,
) -> None:
    """Read by running the flow, so a name nothing answers to is refused as ever."""
    del tmp_path
    with pytest.raises(NotAFlow):
        resumes("no_such_flow_anywhere")


def test_a_flow_that_emptied_its_state_starts_the_next_run_clean(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Clearing it says the next run starts clean, and is not the same as never writing.

    A run that wrote nothing at all is nothing to pick up and the search goes past it. A run
    that wrote and then emptied what it had written is a run that finished with nothing to
    hand on -- and handing the next one the state of the run before that would be answering
    the opposite of what it said.
    """
    monkeypatch.chdir(tmp_path)
    flow = written(
        tmp_path,
        "clears",
        '"""Counts, and clears what it kept when it is told to stop counting."""\n\n'
        "from typing import Any\n\n"
        "from hmz.agents import AgentBase\n"
        "from hmz.flows import flow\n\n\n"
        "@flow(resumable=True)\n"
        "def run(agents: tuple[AgentBase], task: str, state: dict[str, Any]) -> None:\n"
        '    if task == "done":\n'
        "        state.clear()\n"
        "        return\n"
        '    state["rounds"] = state.get("rounds", 0) + 1\n',
    )

    Runner(flow, [ShellAgent(CONFIG)]).run("go")
    Runner(flow, [ShellAgent(CONFIG)]).run("go")
    assert state(cycles()[-1]) == {"rounds": 2}

    Runner(flow, [ShellAgent(CONFIG)]).run("done")  # which empties it
    Runner(flow, [ShellAgent(CONFIG)]).run("go")

    # From nothing, rather than from the two rounds two runs ago.
    assert state(cycles()[-1]) == {"rounds": 1}

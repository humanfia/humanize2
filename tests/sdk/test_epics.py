"""The runs that have already happened, reached through the SDK rather than through a line.

`Epics` is what everything listing runs asks -- a command line, the interface's own `/epics` --
so what is checked here is that it is about the workspace it was given, that every way of
reading one run back agrees with the record the run itself wrote, and that the two things
gathered out of a run afterwards -- a trace of it, an archive of it -- come out of the run's
own directory rather than out of whatever directory somebody was standing in.

The run is a real one: a flow, driven by a stand-in agent that opens a session and echoes into
it. Nothing here starts a coding agent.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor.agents import AgentConfig
from hmz.runtime.runner import Runner
from hmz.sdk import Hmz
from hmz.sdk.epics import Epics
from tests.stubs import ShellAgent, written

if TYPE_CHECKING:
    from pathlib import Path

CONFIG = AgentConfig(model="m", effort="high")

#: A flow that opens one session and says something into it, so that the run has one to point
#: at -- which is the whole of what an epic is for -- and counts the runs of itself, so that
#: the run also has something to be picked up from.
FLOW = '''"""Opens a session, and counts the runs of itself."""

from typing import Any

from hmz.coganchor.agents import AgentBase
from hmz.flows import flow


@flow(resumable=True)
def run(agents: tuple[AgentBase], task: str, state: dict[str, Any]) -> None:
    state["rounds"] = state.get("rounds", 0) + 1
    agents[0].new()("echo the-session")
'''


@pytest.fixture
def ran(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """One run of one flow in a workspace of its own, and the epic it wrote."""
    monkeypatch.chdir(tmp_path)
    written(tmp_path, "flow", FLOW)
    Runner(tmp_path / "flow", [ShellAgent(CONFIG, name="actor")]).run("go")
    (epic,) = Hmz().epics.all()
    return epic


@pytest.fixture
def named(tmp_path: Path) -> str:
    """The flow, as it was named when it ran, which is what its state is written under."""
    return str(tmp_path / "flow")


def test_the_runs_are_kept_under_the_directory_this_says_they_are(ran: Path) -> None:
    held = Hmz().epics

    assert held.under() == ran.parent
    assert ran.is_dir()


def test_what_one_run_was_is_read_back_off_what_the_run_itself_wrote(ran: Path) -> None:
    read = Hmz().epics.read(ran)

    assert read is not None
    assert read.task == "go"
    assert read.flow.endswith("flow")


def test_a_run_that_is_not_one_reads_as_nothing(tmp_path: Path) -> None:
    """A directory of runs is read by people, and a directory in it may be anything."""
    stray = tmp_path / "not-a-run"
    stray.mkdir()

    assert Hmz().epics.read(stray) is None


def test_every_session_one_run_opened_is_one_it_points_at(ran: Path) -> None:
    held = Hmz().epics

    opened = held.sessions(ran)

    assert opened
    assert [one.ident for one in opened] == [
        ident for ids in held.opened(ran).values() for ident in ids
    ]


def test_what_each_agent_opened_is_under_the_name_the_run_knew_it_as(ran: Path) -> None:
    opened = Hmz().epics.opened(ran)

    assert list(opened) == ["actor"]
    assert opened["actor"]


def test_the_last_run_of_a_flow_here_is_what_a_resumable_flow_picks_up(
    ran: Path, named: str
) -> None:
    """Looked for by what the state holds, so a flow called by another is picked up too."""
    held = Hmz().epics

    assert held.resumed(named) == ran
    assert held.resumed("a-flow-nobody-ran") is None


def test_what_a_flow_left_behind_is_what_the_run_picking_it_up_is_handed(
    ran: Path, named: str
) -> None:
    held = Hmz().epics

    assert held.state(ran) == {"rounds": 1}
    # Asked for by name it is the same thing, which is how a called flow's is reached.
    assert held.state(ran, named) == {"rounds": 1}
    assert held.state(ran, "a-flow-that-never-ran") == {}


def test_the_runs_of_a_workspace_are_the_ones_run_there_and_no_others(
    ran: Path, tmp_path: Path
) -> None:
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()

    assert Hmz(tmp_path).epics.all() == [ran]
    assert Hmz(elsewhere).epics.all() == []
    assert Epics(elsewhere).under() != Epics(tmp_path).under()


def test_a_trace_of_a_run_goes_in_the_run_s_own_directory_unless_it_is_sent_elsewhere(
    ran: Path,
) -> None:
    """Which is what makes collecting one twice keep both rather than write over the first."""
    where, document = Hmz().epics.traced(ran)

    assert where.parent.parent == ran
    assert where.is_file()
    assert json.loads(where.read_text(encoding="utf-8")) == document


def test_a_trace_written_where_it_was_asked_for_is_written_there(
    ran: Path, tmp_path: Path
) -> None:
    asked = tmp_path / "out" / "run.trace.json"

    where, document = Hmz().epics.traced(ran, output=asked)

    assert where == asked
    assert json.loads(asked.read_text(encoding="utf-8")) == document


def test_a_trace_holds_the_sessions_that_run_opened_and_no_others(ran: Path) -> None:
    held = Hmz().epics
    ours = {ident for ids in held.opened(ran).values() for ident in ids}

    _, document = held.traced(ran)

    said = json.dumps(document)
    assert ours
    for ident in ours:
        assert ident in said


def test_a_trace_of_no_sessions_is_an_empty_trace_rather_than_a_refusal() -> None:
    """An empty iterable is none of them, which is what a run that opened none gathers.

    That it is *not* read as every session is the collector's own promise and is checked
    where the collector is, against sessions that were really logged. What this asks is the
    part the SDK owns: the argument arrives, and what comes back is a trace document.
    """
    document = Hmz().epics.trace(sessions=[])

    assert document["traceEvents"] == []
    assert "displayTimeUnit" in document


def test_a_run_is_packaged_up_whole_to_send_to_somebody_who_was_not_there(
    ran: Path, tmp_path: Path
) -> None:
    into = tmp_path / "bundles"
    into.mkdir()

    where, manifest = Hmz().epics.bundled(ran, output=into)

    assert where.exists()
    assert where.parent == into
    assert manifest

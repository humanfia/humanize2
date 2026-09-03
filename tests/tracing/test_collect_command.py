"""`hmz trace collect` -- the command line shell around `tracing.collect`.

What a trace is of is a run: the sessions that run opened and no others, and it goes where
that run is. A cycle is a directory holding what happened, what each session was logged to
and what the flow left behind, and the trace belongs beside those rather than in whatever
directory somebody happened to be standing in. An output named outright still wins -- a trace
is also a thing to attach to an issue.

What a directory holds whoever opened it is the other thing a trace can be of, and is asked
for outright: `--all`, or the sessions named. It is a trace of no run, so it is filed beside
the runs rather than inside one, and it is a command line and nothing else -- the interface's
own list is a list of runs.
"""

from __future__ import annotations

import itertools
import re
import unittest.mock
from typing import TYPE_CHECKING

import pytest

from hmz import cli, tracing
from tests.tracing.conftest import (
    CLAUDE_ELSEWHERE,
    CLAUDE_SESSION,
    CODEX_SUBTHREAD,
    CODEX_THREAD,
    keys,
    loaded,
)

if TYPE_CHECKING:
    import pathlib

#: What a trace is called when none was asked for: the moment it was taken, so that two
#: collections of one run keep both.
_STAMPED = re.compile(r"\d{8}T\d{6}Z\.trace\.json")


def run(*argv: str) -> int:
    """Runs the command line with the given arguments."""
    return cli.main(["trace", "collect", *argv])


@pytest.mark.parametrize(
    ("argv", "target", "options"),
    [
        (
            [],
            None,
            {
                "sessions": None,
                "agents": None,  # nothing has run here, so nobody claims a session
                "output": None,  # stands for the generated default, matched below
                "start": None,
                "end": None,
                "profile": None,  # and nothing was profiled, there being no run
                "parents": None,  # nor forked, there being no run
            },
        ),
        (
            [
                "/tmp/ws",
                "--session",
                "one,two",
                "--session",
                "three",
                "--output",
                "out.json",
                "--start",
                "1am",
                "--end",
                "2am",
            ],
            "/tmp/ws",
            {
                "sessions": ["one,two", "three"],
                "agents": None,
                "output": "out.json",
                "start": "1am",
                "end": "2am",
                "profile": None,
                "parents": None,
            },
        ),
    ],
)
def test_forwards_every_argument_to_collect(
    monkeypatch: pytest.MonkeyPatch,
    argv: list[str],
    target: str | None,
    options: dict[str, object],
) -> None:
    collect = unittest.mock.Mock(return_value={"otherData": {}})
    monkeypatch.setattr("hmz.tracing.collector.collect", collect)

    run(*argv)

    passed = dict(collect.call_args.kwargs)
    if options["output"] is None:  # the default is named after the moment it was taken
        assert _STAMPED.fullmatch(str(passed["output"]).rpartition("/")[2])
        passed["output"] = None
    else:  # named outright, however it is spelled by the time it gets there
        passed["output"] = str(passed["output"])
    # The workspace the line named, however it is spelled by the time it gets there.
    (workspace,) = collect.call_args.args
    assert (None if workspace is None else str(workspace)) == target
    assert passed == options


def test_the_run_says_whose_sessions_were_whose(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A trace of a flow needs what only the flow knows: which agent opened which session.

    Two agents at one configuration are one agent to a collector reading the logs alone, so
    the last run in this workspace is read for what it wrote down about itself.
    """
    from hmz.cycle import Cycle

    monkeypatch.chdir(tmp_path)
    cycle = Cycle("rlar", [], "go")
    cycle.write("opened", agent="actor", backend="claude", session="one")
    cycle.write("opened", agent="reviewer", backend="claude", session="two")
    collect = unittest.mock.Mock(return_value={"otherData": {}})
    monkeypatch.setattr("hmz.tracing.collector.collect", collect)

    run()

    assert collect.call_args.kwargs["agents"] == {
        "actor": ["one"],
        "reviewer": ["two"],
    }
    # And the profile of that same run, for a run that was profiled: one document holds the
    # sessions and the programs they ran.
    assert collect.call_args.kwargs["profile"] == cycle.path / "profile.jsonl"


def test_a_trace_goes_beside_the_run_it_is_a_trace_of(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The cycle holds what happened and what it left behind; the trace is one of those."""
    from hmz.cycle import Cycle

    monkeypatch.chdir(tmp_path)
    cycle = Cycle("rlar", [], "go")

    assert run() == 0

    (written,) = (cycle.path / "traces").glob("*.trace.json")
    assert _STAMPED.fullmatch(written.name)
    said = capsys.readouterr().out
    assert str(written) in said
    assert cycle.path.name in said  # and which run it is a trace of


def test_a_named_run_is_the_one_traced(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A workspace has many runs, and the last of them is not always the one being read."""
    from hmz.cycle import Cycle

    monkeypatch.chdir(tmp_path)
    first = Cycle("rlar", [], "one")
    Cycle("rlar", [], "two")

    assert run("--cycle", first.path.name) == 0

    assert list((first.path / "traces").glob("*.trace.json"))


def test_a_trace_of_a_run_holds_that_runs_own_sessions_and_no_others(
    homes: None,
    workspace: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A directory is run in over and over, and each of those runs is a run of its own.

    What the trace of one holds is what that run opened -- which the run itself wrote down --
    and not what the directory has seen since. A trace filed inside a run while holding the
    work of the runs after it is a trace of nothing anybody asked about, and it is worst
    exactly where it is most wanted: the long-running loop, read back a week later.
    """
    from hmz.cycle import Cycle

    monkeypatch.chdir(workspace)
    # A millisecond apart, said rather than waited for. Cycles sort in the order they were
    # run to the millisecond and no finer, and two of them opened in one -- which is what a
    # test does and a person never would -- are ordered by the random tail of their names.
    ticks = itertools.count(1)
    monkeypatch.setattr(
        "hmz.cycle._stamp", lambda: f"20260101T000000.{next(ticks):03d}Z"
    )
    earlier = Cycle("rlar", [], "one")
    earlier.write("opened", agent="actor", backend="codex", session=CODEX_THREAD)
    now = Cycle("rlar", [], "two")
    now.write("opened", agent="actor", backend="claude", session=CLAUDE_SESSION)

    assert run() == 0

    (written,) = (now.path / "traces").glob("*.trace.json")
    held = keys(loaded(written))
    assert held == {
        f"claude:{CLAUDE_SESSION}",
        f"claude:{CLAUDE_SESSION}:agent-abc12345",
    }
    assert "2 sessions" in capsys.readouterr().out


def test_a_run_that_worked_somewhere_else_is_still_its_own_trace(
    homes: None,
    workspace: pathlib.Path,
    elsewhere: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The sessions are asked for by id, which is the only thing that says whose they were.

    A flow that ran on a machine of its own worked in a mirror of this directory, so the
    backend logged its turns under a path this workspace has never heard of. The run wrote
    the ids down all the same, and a trace gathered by those finds them -- which a trace
    gathered by directory never could.
    """
    from hmz.cycle import Cycle

    monkeypatch.chdir(workspace)
    cycle = Cycle("rlar", [], "go")
    cycle.write("opened", agent="actor", backend="claude", session=CLAUDE_ELSEWHERE)

    assert run() == 0

    (written,) = (cycle.path / "traces").glob("*.trace.json")
    assert keys(loaded(written)) == {f"claude:{CLAUDE_ELSEWHERE}"}


def test_a_run_that_opened_nothing_is_a_trace_of_nothing(
    homes: None,
    workspace: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A run that died before its first turn left no sessions, so its trace holds none.

    The directory it ran in holds plenty. Reading those back as this run's would be the one
    answer that is certainly wrong, and is the answer a session filter that reads "none" as
    "all of them" gives.
    """
    from hmz.cycle import Cycle

    monkeypatch.chdir(workspace)
    cycle = Cycle("rlar", [], "go")

    assert run() == 0

    (written,) = (cycle.path / "traces").glob("*.trace.json")
    assert loaded(written)["traceEvents"] == []
    assert "0 sessions, 0 slices" in capsys.readouterr().out


def test_every_session_of_a_directory_is_asked_for_outright(
    homes: None,
    workspace: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`--all` is the other thing a trace can be of: a directory, whoever opened its sessions.

    Which is what reads back an afternoon at a coding agent that no flow ever drove. It is
    not a trace of any run, so it does not go inside one -- it goes where that workspace's
    runs are kept, beside them.
    """
    from hmz.cycle import Cycle, under

    monkeypatch.chdir(workspace)
    cycle = Cycle("rlar", [], "go")
    cycle.write("opened", agent="actor", backend="claude", session=CLAUDE_SESSION)

    assert run("--all") == 0

    assert not list((cycle.path / "traces").glob("*.trace.json"))
    (written,) = under(str(workspace)).glob("*.trace.json")
    held = keys(loaded(written))
    assert f"claude:{CLAUDE_SESSION}" in held
    assert f"codex:{CODEX_THREAD}" in held  # which no run of this workspace ever opened


def test_named_sessions_are_not_a_runs_trace_and_are_not_filed_as_one(
    homes: None,
    workspace: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sessions named outright are sessions, not a run: they belong beside the runs."""
    from hmz.cycle import Cycle, under

    monkeypatch.chdir(workspace)
    cycle = Cycle("rlar", [], "go")
    cycle.write("opened", agent="actor", backend="claude", session=CLAUDE_SESSION)

    assert run("--session", CODEX_THREAD) == 0

    assert not list((cycle.path / "traces").glob("*.trace.json"))
    (written,) = under(str(workspace)).glob("*.trace.json")
    assert keys(loaded(written)) == {
        f"codex:{CODEX_THREAD}",
        f"codex:{CODEX_SUBTHREAD}",
    }


@pytest.mark.parametrize("wider", [["--all"], ["--session", CODEX_THREAD]])
def test_a_run_and_a_directory_are_two_traces_and_a_line_asks_for_one(
    workspace: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    wider: list[str],
) -> None:
    """Naming a run and then naming something wider is a line asking for two things."""
    from hmz.cycle import Cycle

    monkeypatch.chdir(workspace)
    cycle = Cycle("rlar", [], "go")

    with pytest.raises(SystemExit) as failure:
        run("--cycle", cycle.path.name, *wider)

    assert failure.value.code == 2
    assert "a trace of a run holds that run's own sessions" in capsys.readouterr().err


def test_a_run_of_that_name_that_is_not_there_is_a_line_to_correct(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as failure:
        run("--cycle", "nothing-like-it")

    assert failure.value.code == 2
    assert "no run of this workspace is called" in capsys.readouterr().err


def test_a_workspace_that_has_run_nothing_still_keeps_its_trace_with_the_rest(
    homes: None,
    workspace: pathlib.Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Where the runs of that workspace would go, rather than a directory inside the project."""
    from hmz.cycle import under

    assert run(str(workspace)) == 0

    (written,) = under(workspace).glob("*.trace.json")
    assert str(written) in capsys.readouterr().out


def test_writes_the_same_trace_as_the_library(
    homes: None,
    workspace: pathlib.Path,
    tmp_path: pathlib.Path,
) -> None:
    output = tmp_path / "trace.json"

    run(str(workspace), "--output", str(output))

    assert loaded(output) == tracing.collect(workspace)


def test_reports_an_empty_workspace(
    workspace: pathlib.Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run(str(workspace))

    reported, _, counts = capsys.readouterr().out.partition(": ")
    assert _STAMPED.fullmatch(reported.rpartition("/")[2])
    assert counts == "0 sessions, 0 slices\n"


def test_rejects_a_time_it_cannot_read(
    workspace: pathlib.Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as failure:
        run(str(workspace), "--start", "not a time at all!!")

    assert failure.value.code == 2
    assert "cannot parse time: not a time at all!!" in capsys.readouterr().err


def test_the_command_with_nothing_under_it_says_what_there_is(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`hmz trace` is a thing with commands under it, so a line naming none says which."""
    assert cli.main(["trace"]) == 2
    assert "collect" in capsys.readouterr().out

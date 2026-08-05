"""`hmz trace collect` -- the command line shell around `tracing.collect`.

Where a trace goes is the run it is a trace of: a cycle is a directory holding what happened,
what each session was logged to and what the flow left behind, and the trace belongs beside
those rather than in whatever directory somebody happened to be standing in. An output named
outright still wins -- a trace is also a thing to attach to an issue.
"""

from __future__ import annotations

import re
import unittest.mock
from typing import TYPE_CHECKING

import pytest

from hmz import cli, tracing
from tests.tracing.conftest import loaded

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
    assert collect.call_args.args == (target,)
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

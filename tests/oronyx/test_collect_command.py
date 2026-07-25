"""Tests for the command line shell around oronyx.collect."""

from __future__ import annotations

import pathlib
import re
import unittest.mock

import pytest

from amflows import cli, oronyx
from tests.oronyx.conftest import loaded

#: Where a trace lands when none was asked for: this run, in this workspace.
_DEFAULT = re.compile(r"\.amflows/\d{8}T\d{6}Z\.trace\.json")


def run(*argv: str) -> None:
    """Runs the command line with the given arguments."""
    cli.main(["collect", *argv])


@pytest.mark.parametrize(
    ("argv", "target", "options"),
    [
        (
            [],
            None,
            {
                "sessions": None,
                "output": None,  # stands for the generated default, matched below
                "start": None,
                "end": None,
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
                "output": "out.json",
                "start": "1am",
                "end": "2am",
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
    monkeypatch.setattr("amflows.oronyx.collector.collect", collect)

    run(*argv)

    passed = dict(collect.call_args.kwargs)
    if options["output"] is None:  # the default is named after the moment it was taken
        assert _DEFAULT.fullmatch(str(passed["output"]))
        passed["output"] = None
    assert collect.call_args.args == (target,)
    assert passed == options


def test_writes_the_same_trace_as_the_library(
    homes: None,
    workspace: pathlib.Path,
    tmp_path: pathlib.Path,
) -> None:
    output = tmp_path / "trace.json"

    run(str(workspace), "--output", str(output))

    assert loaded(output) == oronyx.collect(workspace)


def test_writes_the_default_output_and_reports_it(
    homes: None,
    workspace: pathlib.Path,
    tmp_path: pathlib.Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run(str(workspace))

    written = list((tmp_path / ".amflows").glob("*.trace.json"))
    assert len(written) == 1  # the directory is made on the way, and holds one trace
    summary = loaded(written[0])["otherData"]
    assert capsys.readouterr().out == (
        f".amflows/{written[0].name}: {summary['sessions']} sessions, "
        f"{summary['slices']} slices\n"
    )


def test_reports_an_empty_workspace(
    workspace: pathlib.Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run(str(workspace))

    reported, _, counts = capsys.readouterr().out.partition(": ")
    assert _DEFAULT.fullmatch(reported)
    assert counts == "0 sessions, 0 slices\n"


def test_rejects_a_time_it_cannot_read(
    workspace: pathlib.Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as failure:
        run(str(workspace), "--start", "not a time at all!!")

    assert failure.value.code == 2
    assert "cannot parse time: not a time at all!!" in capsys.readouterr().err

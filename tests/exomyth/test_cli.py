"""Tests for the command line shell around exomyth.collect."""

from __future__ import annotations

import pathlib
import unittest.mock

import pytest

from amflows import exomyth
from amflows.exomyth import cli
from tests.exomyth.conftest import loaded


def run(monkeypatch: pytest.MonkeyPatch, *argv: str) -> None:
    """Runs the command line with the given arguments."""
    monkeypatch.setattr("sys.argv", ["exomyth", *argv])
    cli.main()


@pytest.mark.parametrize(
    ("argv", "target", "options"),
    [
        (
            [],
            None,
            {
                "sessions": None,
                "output": "exomyth.trace.json",
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
    monkeypatch.setattr(cli, "collect", collect)

    run(monkeypatch, "collect", *argv)

    assert collect.call_args.args == (target,)
    assert collect.call_args.kwargs == options


def test_writes_the_same_trace_as_the_library(
    homes: None,
    workspace: pathlib.Path,
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "trace.json"

    run(monkeypatch, "collect", str(workspace), "--output", str(output))

    assert loaded(output) == exomyth.collect(workspace)


def test_writes_the_default_output_and_reports_it(
    homes: None,
    workspace: pathlib.Path,
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run(monkeypatch, "collect", str(workspace))

    summary = loaded(tmp_path / "exomyth.trace.json")["otherData"]
    assert capsys.readouterr().out == (
        f"exomyth.trace.json: {summary['sessions']} sessions, {summary['slices']} slices\n"
    )


def test_reports_an_empty_workspace(
    workspace: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run(monkeypatch, "collect", str(workspace))

    assert capsys.readouterr().out == "exomyth.trace.json: 0 sessions, 0 slices\n"


def test_rejects_a_time_it_cannot_read(
    workspace: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as failure:
        run(monkeypatch, "collect", str(workspace), "--start", "not a time at all!!")

    assert failure.value.code == 2
    assert "cannot parse time: not a time at all!!" in capsys.readouterr().err


def test_requires_a_command(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(SystemExit) as failure:
        run(monkeypatch)

    assert failure.value.code == 2

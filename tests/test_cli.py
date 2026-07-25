"""The one command line, which is nothing but the routing of the four beneath it.

What each command does with the rest of the line is its own suite's; what is checked here is
that the name reaches it, that the rest arrives untouched, and that a line naming no command
is refused rather than guessed at.
"""

from __future__ import annotations

import runpy
import sys
import unittest.mock

import pytest

from amflows import cli

#: Every command, and the module whose ``main`` it is supposed to reach.
COMMANDS = [
    ("run", "amflows.janus.cli"),
    ("collect", "amflows.exomyth.cli"),
    ("moor", "amflows.coganchor.cli"),
    ("anchor", "amflows.coganchor.serve.cli"),
]


@pytest.mark.parametrize(("command", "module"), COMMANDS, ids=lambda value: value)
def test_a_command_reaches_its_own_command_line_with_the_rest_of_the_arguments(
    command: str, module: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Including the arguments a top-level parser would have eaten, such as ``--help``."""
    main = unittest.mock.Mock(return_value=None)
    monkeypatch.setattr(f"{module}.main", main)

    assert cli.main([command, "--help", "-x", "task"]) == 0
    assert main.call_args.args == (["--help", "-x", "task"],)


def test_the_status_a_command_exits_with_is_the_one_that_is_returned() -> None:
    """A command that says nothing exits 0; one that reports a failure keeps it."""
    with unittest.mock.patch("amflows.coganchor.cli.main", return_value=130):
        assert cli.main(["moor", "claude"]) == 130
    with unittest.mock.patch("amflows.janus.cli.main", return_value=None):
        assert cli.main(["run"]) == 0


@pytest.mark.parametrize("argv", [[], ["fly"], ["--target", "ssh://build-box"]])
def test_a_line_that_names_no_command_is_a_usage_error(
    argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as stopped:
        cli.main(argv)

    assert stopped.value.code == 2
    assert "amflows" in capsys.readouterr().err


def test_the_help_lists_every_command(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as stopped:
        cli.main(["--help"])

    assert stopped.value.code == 0
    shown = capsys.readouterr().out
    assert all(command in shown for command, _ in COMMANDS)


def test_python_m_amflows_is_the_amflows_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "argv", ["amflows", "--version"])
    with pytest.raises(SystemExit) as stopped:
        runpy.run_module("amflows", run_name="__main__")

    assert stopped.value.code == 0

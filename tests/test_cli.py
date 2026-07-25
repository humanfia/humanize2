"""The routing at the top of the one command line, and what it costs to reach a command.

What each command does with the rest of the line is its own file's; what is checked here is
that the name reaches it, that the rest arrives untouched, that a line naming no command is
refused rather than guessed at, and that reaching one command imports no other subpackage --
which is what lets this same file be the target half of a session, where no other subpackage
is installed.
"""

from __future__ import annotations

import subprocess
import sys
import unittest.mock

import pytest

from amflows import cli

#: Every command, and the one subpackage its work is really done in.
COMMANDS = [
    ("run", "janus"),
    ("collect", "oronyx"),
    ("anchor", "coganchor"),
]


@pytest.mark.parametrize(("command", "subpackage"), COMMANDS, ids=lambda value: value)
def test_a_command_reaches_only_the_subpackage_it_is_carried_out_in(
    command: str, subpackage: str
) -> None:
    """`amflows run` must not pay for a date parser, nor `amflows anchor` for any of it."""
    probe = (
        "import contextlib, io, sys\n"
        "from amflows import cli\n"
        # The help itself goes to stdout, so it is swallowed: what is wanted is the list below.
        "with contextlib.redirect_stdout(io.StringIO()):\n"
        "    try:\n"
        f"        cli.main([{command!r}, '--help'])\n"
        "    except SystemExit:\n"
        "        pass\n"
        "print(' '.join(m for m in sys.modules if m.startswith('amflows.')))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, check=True
    )
    reached = {name.split(".")[1] for name in result.stdout.split()}
    assert reached <= {subpackage, "cli"}


@pytest.mark.parametrize(("command", "subpackage"), COMMANDS, ids=lambda value: value)
def test_a_command_is_given_the_rest_of_the_line_untouched(
    command: str, subpackage: str
) -> None:
    """Including the arguments a top-level parser would have eaten, such as `--help`."""
    carry_out = unittest.mock.Mock(return_value=0)
    with unittest.mock.patch.dict(cli._COMMANDS, {command: (carry_out, "")}):
        assert cli.main([command, "--help", "-x", "task"]) == 0
    assert carry_out.call_args.args == (["--help", "-x", "task"],)


def test_the_status_a_command_exits_with_is_the_one_that_is_returned() -> None:
    with unittest.mock.patch.dict(cli._COMMANDS, {"anchor": (lambda argv: 130, "")}):
        assert cli.main(["anchor", "claude"]) == 130


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

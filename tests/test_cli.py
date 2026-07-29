"""The routing at the top of the one command line, and what it costs to reach a command.

What each command does with the rest of the line is its own file's; what is checked here is
that the name reaches it, that the rest arrives untouched, that a line naming no command is
refused rather than guessed at, and that reaching one command imports no other layer -- which
is what lets this same package be the target half of a session, where no other layer is
installed.
"""

from __future__ import annotations

import subprocess
import sys
import unittest.mock

import pytest

from humanize import cli

#: Every command, and what reaching it may load besides `cli` itself: the layers its work is
#: really done in, and nothing of any other command's.
COMMANDS = [
    ("exec", {"runner", "backends"}),
    ("collect", set[str]()),
    ("anchor", {"coganchor"}),
]


@pytest.mark.parametrize(("command", "layers"), COMMANDS, ids=lambda value: value)
def test_a_command_reaches_only_the_layers_it_is_carried_out_in(
    command: str, layers: set[str]
) -> None:
    """`hmz exec` must not pay for a date parser, nor `hmz anchor` for any of it."""
    probe = (
        "import contextlib, io, sys\n"
        "from humanize import cli\n"
        # The help itself goes to stdout, so it is swallowed: what is wanted is the list below.
        "with contextlib.redirect_stdout(io.StringIO()):\n"
        "    try:\n"
        f"        cli.main([{command!r}, '--help'])\n"
        "    except SystemExit:\n"
        "        pass\n"
        "print(' '.join(m for m in sys.modules if m.startswith('humanize.')))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, check=True
    )
    reached = {name.split(".")[1] for name in result.stdout.split()}
    assert reached, "the command imported nothing, so this checks nothing"
    assert reached <= layers | {"cli"}


@pytest.mark.parametrize(("command", "layers"), COMMANDS, ids=lambda value: value)
def test_a_command_is_given_the_rest_of_the_line_untouched(
    command: str, layers: set[str]
) -> None:
    """Including the arguments a top-level parser would have eaten, such as `--help`."""
    carry_out = unittest.mock.Mock(return_value=0)
    with unittest.mock.patch.dict(cli.COMMANDS, {command: (carry_out, "")}):
        assert cli.main([command, "--help", "-x", "task"]) == 0
    assert carry_out.call_args.args == (["--help", "-x", "task"],)


def test_the_status_a_command_exits_with_is_the_one_that_is_returned() -> None:
    def refused(_argv: list[str]) -> int:
        return 130

    with unittest.mock.patch.dict(cli.COMMANDS, {"anchor": (refused, "")}):
        assert cli.main(["anchor", "claude"]) == 130


@pytest.mark.parametrize("argv", [["fly"], ["--target", "ssh://build-box"]])
def test_a_line_that_names_something_that_is_not_a_command_is_a_usage_error(
    argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as stopped:
        cli.main(argv)

    assert stopped.value.code == 2
    assert "hmz" in capsys.readouterr().err


def test_a_line_naming_no_command_opens_the_interface() -> None:
    """`hmz` on its own, which is the way in: there is no command that opens it too."""
    with unittest.mock.patch("humanize.tui.Humanize.run") as opened:
        assert cli.main([]) == 0

    assert opened.called
    assert "tui" not in cli.COMMANDS


def test_the_help_lists_every_command(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as stopped:
        cli.main(["--help"])

    assert stopped.value.code == 0
    shown = capsys.readouterr().out
    assert all(command in shown for command, _ in COMMANDS)

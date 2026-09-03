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

from hmz import cli

#: Every command, and what reaching it may load besides `cli` itself: the layers its work is
#: really done in, and nothing of any other command's.
COMMANDS = [
    # And the two leaves that say whether humanize reports its own failures and where the
    # answer is kept: a command that cannot report a crash is a crash nobody hears about.
    # And what a flow is, which is where the refusal a line naming no flow is answered with
    # is written. Naming it must not cost the drivers: what a flow imports from there that
    # is written down elsewhere is fetched when a flow names it, not when the line is read.
    # And the SDK, which is the one object every way in holds: it reaches a layer only from
    # inside the call that needs it, so naming it costs nothing but itself.
    # And the process's name: the one line that carries a task renames itself once it has
    # read it, so an agent's `pkill -f` on a path the task names cannot reach the run.
    (
        "exec",
        {
            "sdk",
            "runner",
            "flows",
            "backends",
            "telemetry",
            "settings",
            "kept",
            "proctitle",
        },
    ),
    ("trace", set[str]()),
    ("anchor", {"coganchor"}),
    ("flowverses", set[str]()),
    ("check", set[str]()),
    ("agents", set[str]()),
]


@pytest.mark.parametrize(("command", "layers"), COMMANDS, ids=lambda value: value)
def test_a_command_reaches_only_the_layers_it_is_carried_out_in(
    command: str, layers: set[str]
) -> None:
    """`hmz exec` must not pay for a date parser, nor `hmz anchor` for any of it."""
    probe = (
        "import contextlib, io, sys\n"
        "from hmz import cli\n"
        # The help itself goes to stdout, so it is swallowed: what is wanted is the list below.
        "with contextlib.redirect_stdout(io.StringIO()):\n"
        "    try:\n"
        f"        cli.main([{command!r}, '--help'])\n"
        "    except SystemExit:\n"
        "        pass\n"
        "print(' '.join(m for m in sys.modules if m.startswith('hmz.')))\n"
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
    """A name no command answers to, and a flag the interface does not take."""
    with pytest.raises(SystemExit) as stopped:
        cli.main(argv)

    assert stopped.value.code == 2
    assert "hmz" in capsys.readouterr().err


def test_a_line_naming_no_command_opens_the_interface() -> None:
    """`hmz` on its own, which is the way in: there is no command that opens it too."""
    with unittest.mock.patch("hmz.tui.Humanize.run") as opened:
        assert cli.main([]) == 0

    assert opened.called
    assert "tui" not in cli.COMMANDS


@pytest.mark.parametrize(
    "terminal",
    [
        {"TERM_PROGRAM": "iTerm.app"},
        {"LC_TERMINAL": "iTerm2"},
    ],
)
def test_a_direct_iterm_session_uses_plain_terminal_input(
    terminal: dict[str, str],
) -> None:
    cli._prepare_textual_terminal(terminal)

    assert terminal["TEXTUAL_DISABLE_KITTY_KEY"] == "1"


def test_iterm_through_tmux_keeps_extended_terminal_input() -> None:
    terminal = {
        "TERM_PROGRAM": "tmux",
        "LC_TERMINAL": "iTerm2",
        "TMUX": "/tmp/tmux/default,1,0",
    }

    cli._prepare_textual_terminal(terminal)

    assert "TEXTUAL_DISABLE_KITTY_KEY" not in terminal


def test_an_explicit_textual_keyboard_choice_is_kept() -> None:
    terminal = {
        "TERM_PROGRAM": "iTerm.app",
        "TEXTUAL_DISABLE_KITTY_KEY": "0",
    }

    cli._prepare_textual_terminal(terminal)

    assert terminal["TEXTUAL_DISABLE_KITTY_KEY"] == "0"


def test_a_line_of_flags_and_no_command_opens_the_interface_set_up() -> None:
    """`hmz -f <flow>`: a run that is always the same run is one line rather than three walks."""
    with unittest.mock.patch("hmz.tui.Humanize.run") as opened:
        assert cli.main(["-f", "chat"]) == 0

    assert opened.called


def test_a_bad_permission_does_not_open_the_interface(
    capsys: pytest.CaptureFixture[str],
) -> None:
    spec = "cli=codex,model=m,effort=high,permission=readonly"
    with (
        unittest.mock.patch("hmz.tui.Humanize.run") as opened,
        pytest.raises(SystemExit) as stopped,
    ):
        cli.main(["-f", "chat", "-a", spec])

    assert stopped.value.code == 2
    assert not opened.called
    error = capsys.readouterr().err
    assert f"bad agent {spec!r}" in error
    assert "permission must be one of read-only, workspace-write, auto, bypass" in error


@pytest.mark.parametrize("argv", [["--help"], ["-h"]])
def test_the_help_lists_every_command(
    argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    """Asked for on its own, which is what somebody typing it wants: what there is to run.

    Rather than what the interface takes, which is what the same flags after `-f` are about.
    """
    with pytest.raises(SystemExit) as stopped:
        cli.main(argv)

    assert stopped.value.code == 0
    shown = capsys.readouterr().out
    assert all(command in shown for command, _ in COMMANDS)
    # And what `hmz` itself takes, which is the other half of the same line: one help says
    # both what may be opened and what may be run, because both of them are `hmz`.
    assert all(flag in shown for flag in ("--flow", "--agent", "--config"))
    # And nothing humanize spawns for itself: a listing offering the supervisor a turn is
    # run under would be offering a way to run something that is not humanize.
    assert "cred" not in shown


def test_what_humanize_spawns_for_itself_is_carried_out_but_not_listed() -> None:
    """A turn taken as an account is spawned as one of these; nobody types one."""
    assert "cred" not in cli.COMMANDS
    # Still a line that runs: it is a command line because a process is started by one.
    assert cli.main(["cred", "--map=/house/x=/store/y", "--", "true"]) in (0, 1)

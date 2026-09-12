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

#: Every command a line reaches, and what reaching it may load besides `cli` itself: the
#: layers its work is really done in, and nothing of any other command's. `anchor` is in it
#: for being the one humanize spawns that a whole layer is behind: the target half of a
#: session is this package with coganchor and nothing else on it.
COMMANDS = [
    # And the two leaves that say whether humanize reports its own failures and where the
    # answer is kept: a command that cannot report a crash is a crash nobody hears about.
    # And what a flow is, which is where the refusal a line naming no flow is answered with
    # is written. Naming it must not cost the drivers: what a flow imports from there that
    # is written down elsewhere is fetched when a flow names it, not when the line is read.
    # And the SDK, which is the one object every way in holds: it reaches a layer only from
    # inside the call that needs it, so naming it costs nothing but itself.
    (
        "exec",
        {"sdk", "runner", "flows", "backends", "telemetry", "settings", "kept"},
    ),
    ("anchor", {"coganchor"}),
]


@pytest.mark.parametrize(("command", "layers"), COMMANDS, ids=lambda value: value)
def test_a_command_reaches_only_the_layers_it_is_carried_out_in(
    command: str, layers: set[str]
) -> None:
    """`hmz exec` must not pay for the interface, nor `hmz anchor` for any of it."""
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


def test_a_command_is_given_the_rest_of_the_line_untouched() -> None:
    """Including the arguments a top-level parser would have eaten, such as `--help`."""
    carry_out = unittest.mock.Mock(return_value=0)
    with unittest.mock.patch.dict(cli.COMMANDS, {"exec": (carry_out, "")}):
        assert cli.main(["exec", "--help", "-x", "task"]) == 0
    assert carry_out.call_args.args == (["--help", "-x", "task"],)


def test_what_is_spawned_is_given_the_rest_of_the_line_untouched() -> None:
    """It is routed as every other command is; being listed is the whole of the difference."""
    carry_out = unittest.mock.Mock(return_value=0)
    with unittest.mock.patch.dict(cli._SPAWNED, {"anchor": carry_out}):
        assert cli.main(["anchor", "--help", "-x", "claude"]) == 0
    assert carry_out.call_args.args == (["--help", "-x", "claude"],)


def test_the_status_a_command_exits_with_is_the_one_that_is_returned() -> None:
    def refused(_argv: list[str]) -> int:
        return 130

    with unittest.mock.patch.dict(cli._SPAWNED, {"anchor": refused}):
        assert cli.main(["anchor", "claude"]) == 130


@pytest.mark.parametrize("argv", [["--target", "ssh://build-box"], ["-f", "chat"]])
def test_a_line_of_flags_the_interface_does_not_take_is_a_usage_error(
    argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    """`-f` and `-a` among them: what to run is chosen at the prompt, not said here."""
    with pytest.raises(SystemExit) as stopped:
        cli.main(argv)

    assert stopped.value.code == 2
    assert "hmz" in capsys.readouterr().err


def test_a_line_that_names_something_that_is_not_a_command_is_a_usage_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """And says which there are, which is now the one there is."""
    with pytest.raises(SystemExit) as stopped:
        cli.main(["fly"])

    assert stopped.value.code == 2
    said = capsys.readouterr().err
    assert "hmz" in said
    assert "exec" in said


def test_a_line_naming_no_command_opens_the_interface() -> None:
    """`hmz` on its own, which is the way in: there is no command that opens it too."""
    with unittest.mock.patch("hmz.tui.Humanize.run") as opened:
        assert cli.main([]) == 0

    assert opened.called
    assert "tui" not in cli.COMMANDS


def test_the_interface_is_opened_on_nothing_the_line_said() -> None:
    """What to run is chosen at the prompt, and read back from what was chosen there."""
    with unittest.mock.patch("hmz.tui.Humanize") as opened:
        assert cli.main([]) == 0

    assert opened.call_args.args == ()
    assert opened.call_args.kwargs == {}


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


@pytest.mark.parametrize("argv", [["--help"], ["-h"]])
def test_the_help_lists_every_command(
    argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    """Asked for on its own, which is what somebody typing it wants: what there is to run."""
    with pytest.raises(SystemExit) as stopped:
        cli.main(argv)

    assert stopped.value.code == 0
    shown = capsys.readouterr().out
    assert all(command in shown for command in cli.COMMANDS)
    # And what `hmz` itself takes, which is the other half of the same line: one help says
    # both what may be opened and what may be run, because both of them are `hmz`.
    assert "--no-daemon" in shown
    # The line that opens the interface says nothing about what it opens on, so there is
    # nothing here to say it with: what to run is chosen at the prompt.
    assert not any(flag in shown for flag in ("--flow", "--agent", "--config"))
    # And nothing humanize spawns for itself: a listing offering the supervisor a turn is
    # run under would be offering a way to run something that is not humanize.
    assert not any(spawned in shown for spawned in cli._SPAWNED)


@pytest.mark.parametrize("spawned", ["anchor", "cred", "hook", "tools"])
def test_what_humanize_spawns_for_itself_is_carried_out_but_not_listed(
    spawned: str,
) -> None:
    """A turn taken as an account is spawned as one of these; nobody types one."""
    assert spawned not in cli.COMMANDS
    # Still a line that runs: it is a command line because a process is started by one.
    with pytest.raises(SystemExit) as stopped:
        cli.main([spawned, "--help"])

    assert stopped.value.code == 0


def test_what_is_spawned_carries_out_what_it_was_given() -> None:
    """The supervisor a turn under an account runs in, reached the way humanize reaches it."""
    assert cli.main(["cred", "--map=/house/x=/store/y", "--", "true"]) in (0, 1)

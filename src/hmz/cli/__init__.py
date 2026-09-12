"""``hmz`` -- the whole command line, over layers that have none of their own.

    hmz
    hmz exec -f ralph_loop -a claude/MODEL:high "$(cat TASK.md)"

There is one command anybody types, and everything else humanize keeps is walked at the
prompt: a listing with a noun in it for every store would be a second interface to learn, and
the one with the sheets in it is the interface.

A command imports what it needs when it is the one asked for, and no earlier. Two things turn
on that: `hmz exec` must not pay for the terminal interface it is not opening, and
`hmz anchor serve` is what the zipapp bootstrapped onto a target runs, where coganchor is the
only layer present and the architecture is whatever the target happens to be.

A command whose line takes a parser of its own has a module of its own here, so that reaching
one of them costs nothing for the others -- which is what `anchor.py`, `cred.py` and
`tools.py`, the three humanize spawns for itself, are. `exec` has none: the line it takes is
read by :func:`hmz.runner.flow_and_agents`, since the terminal interface starts a flow from
that same line.

:mod:`hmz.cli.output` is the one module every command may reach: who is reading -- somebody at
a terminal, or a program -- is one question rather than one per command, and it costs nothing
to ask.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from argparse import ArgumentParser
    from collections.abc import MutableMapping

    from pydantic import BaseModel

    from hmz.daemon import Held
    from hmz.kept import Runs

__all__ = ["APART", "COMMANDS", "apart", "main", "many", "opens"]

#: What says whether a run may be held apart from the terminal at all, for a machine that
#: would rather it went with the window. `off`, `0` or `no`; anything else is silence, and
#: silence is a run that is held wherever there is a terminal to hand over to.
APART = "HUMANIZE_DAEMON"


def many(count: int | str, thing: str) -> str:
    """How many of something there are, said as English says it.

    Here rather than beside either line that prints one: a listing that says `1 sessions` is
    a line that reads as a template nobody finished, and there is one rule about that.

    Args:
      count: How many, as a number or as whatever counted them.
      thing: What they are, in the singular.

    Returns:
      The two words -- `1 session`, `3 sessions`.
    """
    return f"{count} {thing}" if str(count) == "1" else f"{count} {thing}s"


def _prepare_textual_terminal(
    environ: MutableMapping[str, str] | None = None,
) -> None:
    """Keeps Textual's extended keys off a direct iTerm2 session.

    iTerm2 loses IME-composed text when Textual asks it to report every key with associated
    text. A tmux between them handles that protocol correctly, so only the direct path needs
    Textual's own opt-out. An explicit setting belongs to whoever launched the process.

    Args:
      environ: The process environment, or another mapping for a caller testing the choice.
    """
    import os

    target = os.environ if environ is None else environ
    direct_iterm = not target.get("TMUX") and (
        target.get("TERM_PROGRAM") == "iTerm.app"
        or target.get("LC_TERMINAL") == "iTerm2"
    )
    if direct_iterm:
        target.setdefault("TEXTUAL_DISABLE_KITTY_KEY", "1")


def _exec(argv: list[str]) -> int:
    """Drives the flow named on the command line, on the agents it names.

    What the run looks like while it happens is settled here rather than by each backend
    teeing its own progress: watching the agents is what makes one run read as one run,
    whichever CLIs it was given, and registering a watcher is what stops those tees.

    Args:
      argv: What followed the command name.

    Returns:
      Zero, once the flow has returned.
    """
    from hmz import telemetry
    from hmz.flows import NotAFlow
    from hmz.sdk import Hmz

    from .output import Out, Shown

    hmz = Hmz()
    # If it has been answered yes, and never otherwise: a run with nobody at a terminal is a
    # run with nobody to ask, and silence is not an answer.
    hmz.reports()
    path, agents, task, config, as_json = hmz.read(argv)
    with Out(as_json=as_json) as out, Shown(out) as shown:
        # The agents the line named, and not whatever else the flow turns out to drive: a
        # flow whose other side is the person drives one more, and with nobody at a prompt
        # that one answers nothing to every turn it is given. Rows saying so would be the
        # only thing on the terminal that is about humanize rather than about the run.
        shown.watches(agents)
        try:
            running = hmz.run(path, agents, task, config)
        except NotAFlow as error:
            # A flow that is not there, or one that takes other agents than these, is a
            # command line that was wrong before anything ran, so it exits as argparse's own
            # rejections do. What the flow raises for itself is the flow's, and is left to
            # say so itself.
            print(f"hmz exec: error: {error}", file=sys.stderr)
            raise SystemExit(2) from error
        try:
            running.run()
        except (KeyboardInterrupt, SystemExit):
            # Somebody stopping a run is not a run that went wrong.
            raise
        except BaseException as why:
            # Reported and then raised on exactly as it was: what a flow does when it fails
            # is the flow's business and the person at the terminal's, and this is only
            # humanize finding out that it happened.
            telemetry.crash(why, doing="hmz exec")
            raise
    return 0


def _anchor(argv: list[str]) -> int:
    """Runs the agent named on the command line, with its work landing on another machine.

    Args:
      argv: What followed the command name.

    Returns:
      The agent's exit status, or one of our own if it never ran.
    """
    from .anchor import anchor

    return anchor(argv)


def _cred(argv: list[str]) -> int:
    """Runs a program whose credentials are kept somewhere other than where it looks.

    Args:
      argv: What followed the command name.

    Returns:
      The program's exit status, or one of our own if it never ran.
    """
    from .cred import cred

    return cred(argv)


def _tools(argv: list[str]) -> int:
    """Carries the tool protocol between a coding agent and the flow whose callbacks it is.

    Args:
      argv: What followed the command name.

    Returns:
      Zero once either end has gone, or one for a flow that is no longer there.
    """
    from .tools import tools

    return tools(argv)


def _line() -> ArgumentParser:
    """The line `hmz` itself takes, which is how the interface is opened.

    It takes nothing at all now: which flow runs and what drives it are chosen at the prompt,
    and whether the run is held apart from this terminal is read off the terminal rather than
    asked for -- a run nobody can walk away from is not a thing to want. What is left is a
    parser that names the program and refuses anything else, built here rather than where it
    is parsed because the help asks it what `hmz` takes.

    Returns:
      The parser, without the commands: whoever wants those adds them.
    """
    import argparse

    return argparse.ArgumentParser(
        prog="hmz",
        description="Orchestrate, execute, and observe agent flows. Naming no command opens "
        "the terminal interface, as this directory left it.",
        epilog="Run `hmz COMMAND --help` for what a command takes.",
    )


def _tui(argv: list[str]) -> int:
    """Opens the terminal interface, as this directory left it.

    The line says nothing about what to run: which flow, what drives it and what it is set up
    with are chosen at the prompt, and what was chosen there is what the next `hmz` opens on.
    Nothing is started either -- the interface opens ready, and what starts it is still the
    first thing said.

    Args:
      argv: The whole line, which names no command.

    Returns:
      Zero, once the interface has been closed, or two for a line to correct.
    """
    # Textual reads this once, while it is imported, so the terminal must be prepared before
    # reaching the lazily imported interface below.
    _prepare_textual_terminal()

    _line().parse_args(argv)
    return opens()


def opens() -> int:
    """Opens the interface, on this terminal or on one a run of its own is being held on.

    A run of a flow outlives the terminal it was started from, which is what makes `/detach`
    a thing there is: the interface goes on running where nothing is reading it, and `hmz` in
    this directory opens it again. So a line that opens the interface reads whichever run is
    already being held here, and starts one where none is.

    A terminal is what makes that worth doing. With nothing to attach -- output going to a
    file, a test driving the interface itself -- the interface is opened here, in this
    process, exactly as it always was.

    Returns:
      Zero, once the interface has been closed or this terminal has been let go of.
    """
    if not (_apart_is_wanted() and _at_a_terminal()):
        return _here()

    import functools

    from hmz import daemon

    found = daemon.running()
    if found is not None:
        if found.attach() == 0:
            return 0
        # It went between being found and being read, which is a directory with no run in it
        # after all rather than a reason to open nothing.
        print(
            "hmz: the run that was being held here has gone, so a new one is opened",
            file=sys.stderr,
        )
    # Opened on nothing in particular, which is what the interface then reads out of what
    # this directory was last left running.
    opening = functools.partial(apart, "", (), None)
    try:
        found = daemon.start(opening)
    except OSError as why:
        # A machine that will not fork, a home directory that cannot be written, a socket
        # that will not bind: none of those is a reason not to open the interface. What is
        # lost is being able to walk away from the run, which is said and then done without.
        print(
            f"hmz: this run cannot be held apart from the terminal ({why}), "
            "so it is opened here instead",
            file=sys.stderr,
        )
        return _here()
    return found.attach()


def _here() -> int:
    """Opens the interface in this process, on the terminal it was started from."""
    from hmz.tui import Humanize

    Humanize().run()
    return 0


def apart(
    flow: str,
    agents: tuple[Runs, ...],
    config: BaseModel | None,
    session: Held,
) -> None:
    """Opens the interface inside the process holding the run, and returns when it closes.

    Args:
      flow: The flow to open on.
      agents: What each of that flow's agents runs.
      config: What that flow is set up with.
      session: What is holding the run, which is what `/detach` lets go of and what draws
        the screen again for a terminal that has just arrived.
    """
    # Here rather than inside the line that opens the interface: this is the one function
    # that runs in the process holding a run, which is the other side of a fork and has none
    # of what `_tui` did before it. Textual reads the answer once, while it is imported, so
    # it has to be settled before the interface below is reached.
    _prepare_textual_terminal()

    from hmz.sdk import Hmz
    from hmz.tui import Humanize

    app = Humanize(flow=flow, agents=list(agents), config=config, session=session)
    # Each of these is called from a thread of whatever is holding the run, so each hands the
    # work to the interface's own thread and waits there rather than here.
    session.redrawn(lambda: app.call_from_thread(app.reattached))
    session.stopping(lambda: app.call_from_thread(app.action_quit))
    session.says(lambda: {"flows": [one.flow for one in Hmz().flows.running()]})
    app.run()


def _apart_is_wanted() -> bool:
    """Whether this machine wants a run held apart from the terminal at all.

    Answered for one process without writing anything down, the way the reporting question
    is: a scripted install, a machine somebody would rather have the run go with the window
    on, and this suite are all one variable rather than a line each of them has to remember
    to pass.

    Returns:
      Whether to hold one. False only where the variable says so outright.
    """
    import os

    return os.environ.get(APART, "").strip().lower() not in ("off", "0", "no")


def _at_a_terminal() -> bool:
    """Whether there is a terminal on both ends of this process to hand over to.

    A run held apart from the terminal is read by a terminal proxying to it, so there has to
    be one: output going to a file and input coming from a pipe are a run that is opened
    here, in this process, exactly as it always was.

    Returns:
      Whether there is one.
    """
    return sys.stdin.isatty() and sys.stdout.isatty()


#: Each command, as what carries it out and the line a listing shows it as. There is one:
#: running a flow in a directory is what a line is for, and everything else humanize keeps is
#: walked at the prompt rather than typed. There is no command for the terminal interface
#: either: naming nothing at all is how it opens.
COMMANDS = {
    "exec": (_exec, "run an agent flow in this directory"),
}

#: What humanize spawns for itself, carried out like any command and listed as none of them.
#: A turn taken as an account runs the CLI with the paths it keeps its credentials at pointed
#: into that account's directory, and the supervisor doing the pointing has to be a process of
#: its own -- it forks the program and takes the signal handling with it, which a flow pumping
#: turns from threads of its own has none to lend. A flow's own callbacks are the same shape
#: the other way round: a CLI takes a tool by starting a program, so there is a program, and it
#: does nothing but carry the protocol back to the process the callbacks are in. An anchored
#: turn is the third: `AnchorConfig.command()` renders one for every turn whose work lands on
#: another machine, and the zipapp bootstrapped onto a target answers it by running
#: `hmz anchor serve`. All three are a command line because there is no other way to start a
#: process, and none of them is a line anybody types.
_SPAWNED = {"anchor": _anchor, "cred": _cred, "tools": _tools}


def main(argv: list[str] | None = None) -> int:
    """Runs the command named on the command line, or opens the interface if none is.

    Args:
      argv: The arguments to parse, defaulting to this process's own.

    Returns:
      The command's exit status.
    """
    arguments = sys.argv[1:] if argv is None else argv
    if not arguments:
        return _tui([])
    # A line that names no command and starts with a flag is the interface being opened, and
    # what it may say about opening one is whatever `_line()` takes -- which is asked of the
    # parser rather than listed again here, so that a flag written as argparse would accept it
    # is one flag rather than two spellings to keep in step. Two flags on their own are not
    # that line: `--version` says the version, and `--help` lists the commands, which is what
    # somebody typing it wants.
    if arguments[0].startswith("-") and arguments not in (
        ["--version"],
        ["--help"],
        ["-h"],
    ):
        return _tui(arguments)
    if arguments[0] not in COMMANDS and arguments[0] not in _SPAWNED:
        if arguments == ["--version"]:
            # Read from the installed metadata, which costs more to reach than everything
            # else here put together -- so it is reached only when it is what was asked for.
            from importlib.metadata import version

            print(f"hmz {version('hmz')}")
            return 0
        # Anything else naming no command it knows: argparse says which was meant and exits,
        # so nothing below it runs. `--version` is handled above precisely because it is the
        # one flag this parser no longer carries, and would otherwise fall through to a
        # command lookup that has nothing to look up.

        # The same line `hmz` itself takes, with the commands added: one help, saying both
        # what may be opened and what may be run, since both are `hmz` and somebody typing
        # `hmz --help` is asking about the whole of it. It knows the commands by name and not
        # by what they take -- each one answers `hmz COMMAND --help` itself.
        parser = _line()
        commands = parser.add_subparsers(metavar="COMMAND", required=True)
        for name, (_, summary) in COMMANDS.items():
            commands.add_parser(name, help=summary, add_help=False)
        parser.parse_args(arguments)

    carries = _SPAWNED.get(arguments[0])
    return (carries or COMMANDS[arguments[0]][0])(arguments[1:])

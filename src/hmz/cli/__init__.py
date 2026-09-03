"""``hmz`` -- the whole command line, over layers that have none of their own.

    hmz
    hmz -f humanize1 -c setup.yaml -a claude/MODEL:max ...
    hmz exec -f ralph_loop -a claude/MODEL:high "$(cat TASK.md)"
    hmz trace collect
    hmz anchor --target ssh://build-box claude

A command imports what it needs when it is the one asked for, and no earlier. Two things turn
on that: `hmz exec` must not pay for a date parser it will not use, and `hmz anchor serve` is
what the zipapp bootstrapped onto a target runs, where coganchor is the only layer present
and the architecture is whatever the target happens to be.

A command whose line takes a parser of its own has a module of its own here, so that reaching
one of them costs nothing for the others. `exec` has none: the line it takes is read by
:func:`hmz.runner.flow_and_agents`, since the terminal interface starts a flow from that
same line.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from argparse import ArgumentParser
    from collections.abc import MutableMapping, Sequence

    from pydantic import BaseModel

    from hmz.daemon import Held
    from hmz.kept import Runs

__all__ = ["APART", "COMMANDS", "apart", "main", "many", "opens", "runs_of"]

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

    Args:
      argv: What followed the command name.

    Returns:
      Zero, once the flow has returned.
    """
    from hmz import telemetry
    from hmz.flows import NotAFlow
    from hmz.proctitle import named
    from hmz.sdk import Hmz

    hmz = Hmz()
    # If it has been answered yes, and never otherwise: a run with nobody at a terminal is a
    # run with nobody to ask, and silence is not an answer.
    hmz.reports()
    path, agents, task, config, container = hmz.read(argv)
    # The task is on this process's command line, and this is the one line that carries one:
    # renamed before an agent starts, so its ``pkill -f`` on a path the task names cannot
    # reach the run -- see ``hmz.proctitle``.
    named("exec")
    try:
        running = hmz.run(path, agents, task, config, container=container)
    except NotAFlow as error:
        # A flow that is not there, or one that takes other agents than these, is a command
        # line that was wrong before anything ran, so it exits as argparse's own rejections
        # do. What the flow raises for itself is the flow's, and is left to say so itself.
        print(f"hmz exec: error: {error}", file=sys.stderr)
        raise SystemExit(2) from error
    try:
        running.run()
    except (KeyboardInterrupt, SystemExit):
        # Somebody stopping a run is not a run that went wrong.
        raise
    except BaseException as why:
        # Reported and then raised on exactly as it was: what a flow does when it fails is
        # the flow's business and the person at the terminal's, and this is only humanize
        # finding out that it happened.
        telemetry.crash(why, doing="hmz exec")
        raise
    return 0


def _trace(argv: list[str]) -> int:
    """Gathers what a run left behind into one trace file.

    Args:
      argv: What followed the command name.

    Returns:
      Zero, once the trace has been written, or two for a line to correct.
    """
    from .trace import trace

    return trace(argv)


def _anchor(argv: list[str]) -> int:
    """Runs the agent named on the command line, with its work landing on another machine.

    Args:
      argv: What followed the command name.

    Returns:
      The agent's exit status, or one of our own if it never ran.
    """
    from .anchor import anchor

    return anchor(argv)


def _flowverses(argv: list[str]) -> int:
    """Lists, fetches and takes away the places flows come from.

    Args:
      argv: What followed the command name.

    Returns:
      Zero, or two for a line to correct.
    """
    from .flowverses import flowverses

    return flowverses(argv)


def _check(argv: list[str]) -> int:
    """Reads a flow for what will not run, before anything runs it.

    Args:
      argv: What followed the command name.

    Returns:
      Zero for a flow with nothing blocking, one for one with something, or two for a
      line to correct.
    """
    from .check import check

    return check(argv)


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


def _agents(argv: list[str]) -> int:
    """Lists, writes down and takes away the agents kept under a name.

    Args:
      argv: What followed the command name.

    Returns:
      Zero, or two for a line to correct.
    """
    from .agents import agents

    return agents(argv)


def _fallback(argv: list[str]) -> int:
    """Lists, writes down and takes away where one agent's turns go when it cannot run.

    Args:
      argv: The arguments after `hmz fallback`.

    Returns:
      Its exit status.
    """
    from .fallback import fallback

    return fallback(argv)


def _providers(argv: list[str]) -> int:
    """Lists, makes and takes away the accounts an agent may be run as.

    Args:
      argv: What followed the command name.

    Returns:
      Zero, or two for a line to correct.
    """
    from .providers import providers

    return providers(argv)


def _line() -> ArgumentParser:
    """The line `hmz` itself takes, which is how the interface is opened set up.

    Built here rather than where it is parsed because it is read in two places: the line that
    opens the interface is parsed with it, and the help asks it what `hmz` takes. A second
    copy of these three flags would be one to keep in step, and the one somebody typing
    `hmz --help` was shown would be the one that drifted.

    Returns:
      The parser, without the commands: whoever wants those adds them.
    """
    import argparse

    parser = argparse.ArgumentParser(
        prog="hmz",
        description="Orchestrate, execute, and observe agent flows. Naming no command opens "
        "the terminal interface, set up as the line says.",
        epilog="Run `hmz COMMAND --help` for what a command takes.",
    )
    parser.add_argument(
        "-f",
        "--flow",
        default="",
        metavar="FLOW",
        help="the flow to open on: one humanize ships or a flowverse holds, by name, or a "
        "file of your own",
    )
    parser.add_argument(
        "-a",
        "--agent",
        action="append",
        default=[],
        dest="agents",
        metavar="CLI/MODEL:EFFORT",
        help="what one of that flow's agents runs, repeated once for each it drives, in the "
        "order it takes them; the written-out form may include service_tier=SERVICE_TIER, "
        "permission=PERMISSION and web_search=on|off; needs -f",
    )
    parser.add_argument(
        "-c",
        "--config",
        metavar="PATH",
        help="a YAML file of what to set that flow up with, as choosing it would ask for it; "
        "needs -f",
    )
    parser.add_argument(
        "--no-daemon",
        dest="daemon",
        action="store_false",
        help="open the interface in this terminal rather than holding the run apart from it, "
        "which is what makes closing the terminal close the run",
    )
    return parser


def _tui(argv: list[str]) -> int:
    """Opens the terminal interface, set up the way the line says if it says anything.

    A line naming no command opens it as it was left; one naming a flow, what to run it on,
    or what to set it up with opens it that way instead -- so a run that is always the same
    run is one line rather than three walks through the sheets. Nothing is started: the
    interface opens ready, and what starts it is still the first thing said.

    Args:
      argv: The whole line, which names no command.

    Returns:
      Zero, once the interface has been closed, or two for a line to correct.
    """
    # Textual reads this once, while it is imported, so the terminal must be prepared before
    # reaching the lazily imported interface below.
    _prepare_textual_terminal()

    parser = _line()
    args = parser.parse_args(argv)
    flow = args.flow or ""
    # Each flag that says something about the flow, in the order they are written: a line
    # short of the flow they are about is a line to correct before either is read.
    if args.agents and not flow:
        parser.error("-a says what runs the flow, so it needs -f")
    if args.config is not None and not flow:
        parser.error("-c says how the flow runs, so it needs -f")
    agents = runs_of(parser, flow, args.agents)
    setting = None
    if args.config is not None:
        from hmz.sdk import Hmz

        flows = Hmz().flows
        try:
            model = flows.configures(flow)
        except Exception as why:  # noqa: BLE001 -- a flow that will not load is a line to fix
            parser.error(str(why))
        if model is None:
            parser.error(
                f"{flow} takes no setting up, so there is nothing for -c to say"
            )
        try:
            setting = model.model_validate(flows.set_up_from(args.config))
        except ValueError as refused:
            parser.error(f"{args.config}: {refused}")
    return opens(parser, flow=flow, agents=agents, config=setting, held=args.daemon)


def runs_of(parser: ArgumentParser, flow: str, agents: Sequence[str]) -> list[Runs]:
    """Reads what each of a flow's agents runs off the line that named them.

    Here rather than in either of the two lines that take it -- `hmz` and `hmz daemon start`
    -- because it is one rule: what `-a` means, how many of them a flow takes, and what an
    agent that named none of it does. Two readings of one line would be two ways of refusing
    the same mistake.

    Args:
      parser: The line, for reporting one to correct.
      flow: The flow they are to drive, or "" for a line that named none.
      agents: What each of them runs, as `-a` spells one.

    Returns:
      One apiece, in the order the flow takes them, and nothing at all for a line that named
      no agent.

    Raises:
      SystemExit: If the line names agents and no flow, an agent that is not one, or a
        different number of them than the flow drives -- each as argparse rejects a line.
    """
    from hmz.kept import Runs
    from hmz.sdk import Hmz

    if not agents:
        return []
    if not flow:
        parser.error("-a says what runs the flow, so it needs -f")
    hmz = Hmz()
    # What each line said about searching the web, kept beside the line itself: the rest of
    # what an agent is travels in the spec and is read again where the agent is made, and
    # this is a switch rather than a word of the spec by the time the interface holds it.
    searching: list[bool] = []
    for spec in agents:
        try:
            searching.append(hmz.agents.reads(spec)[6] is not False)
        except ValueError as bad:
            parser.error(f"bad agent {spec!r}: {bad}")
    try:
        places = hmz.flows.places(flow)
    except Exception as why:  # noqa: BLE001 -- a flow that will not load is a line to fix
        parser.error(str(why))
    if len(places) != len(agents):
        parser.error(f"{flow} drives {len(places)} agents, {len(agents)} given")
    return [
        Runs(spec, goals=places[at].goals_default, web_search=searching[at])
        for at, spec in enumerate(agents)
    ]


def opens(
    parser: ArgumentParser,
    *,
    flow: str = "",
    agents: Sequence[Runs] = (),
    config: BaseModel | None = None,
    held: bool = True,
) -> int:
    """Opens the interface, on this terminal or on one a run of its own is being held on.

    A run of a flow outlives the terminal it was started from, which is what makes `/detach`
    a thing there is: the interface goes on running where nothing is reading it, and `hmz` in
    this directory opens it again. So a line that opens the interface reads whichever run is
    already being held here, and starts one where none is.

    A terminal is what makes that worth doing. With nothing to attach -- output going to a
    file, a test driving the interface itself -- the interface is opened here, in this
    process, exactly as it always was.

    Args:
      parser: The line that asked, for reporting one to correct.
      flow: The flow to open on, which is what `-f` names.
      agents: What each of that flow's agents runs.
      config: What that flow is set up with.
      held: Whether the run may be held apart from this terminal at all.

    Returns:
      Zero, once the interface has been closed or this terminal has been let go of.
    """
    if not (held and _apart_is_wanted() and _at_a_terminal()):
        return _here(flow=flow, agents=agents, config=config)

    import functools

    from hmz import daemon

    found = daemon.running()
    if found is not None:
        if flow or agents or config is not None:
            # A run that is set up is set up. Saying how it is to be set up while one is
            # already being held is two answers to one question, and carrying on would be
            # one of them silently losing.
            parser.error(
                "a run is already being held here, and it is set up as it was set up; "
                "`hmz` reads it, and `hmz daemon stop` ends it"
            )
        if found.attach() == 0:
            return 0
        # It went between being found and being read, which is a directory with no run in it
        # after all rather than a reason to open nothing.
        print(
            "hmz: the run that was being held here has gone, so a new one is opened",
            file=sys.stderr,
        )
    opening = functools.partial(apart, flow, tuple(agents), config)
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
        return _here(flow=flow, agents=agents, config=config)
    return found.attach()


def _here(
    *,
    flow: str = "",
    agents: Sequence[Runs] = (),
    config: BaseModel | None = None,
) -> int:
    """Opens the interface in this process, on the terminal it was started from."""
    from hmz.tui import Humanize

    Humanize(flow=flow, agents=list(agents), config=config).run()
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
    # Here rather than only on the line that opens the interface: this is the one function
    # that runs inside the process holding a run, and `hmz daemon start` reaches it without
    # going past `_tui`. Textual reads the answer once, while it is imported, so it has to
    # be settled before the interface below is reached.
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


def _daemon(argv: list[str]) -> int:
    """Says what runs are being held apart from a terminal, and ends one.

    Args:
      argv: What followed the command name.

    Returns:
      Zero, or one for something that could not be done.
    """
    from .daemon import daemon

    return daemon(argv)


#: Each command, as what carries it out and the line a listing shows it as. There is no
#: command for the terminal interface: naming nothing at all is how it opens.
COMMANDS = {
    "exec": (_exec, "run an agent flow in this directory"),
    "trace": (
        _trace,
        "what a run left behind, gathered into a trace to read",
    ),
    "anchor": (_anchor, "run an agent here that acts on another machine"),
    "flowverses": (_flowverses, "the places flows come from"),
    "check": (_check, "check a flow before anything runs it"),
    "agents": (_agents, "the agents written down under a name"),
    "providers": (_providers, "the accounts an agent may be run as"),
    "fallback": (
        _fallback,
        "where a turn goes when the agent taking it cannot take it at all",
    ),
    "daemon": (_daemon, "the runs being held apart from a terminal"),
}

#: What humanize spawns for itself, carried out like any command and listed as none of them.
#: A turn taken as an account runs the CLI with the paths it keeps its credentials at pointed
#: into that account's directory, and the supervisor doing the pointing has to be a process of
#: its own -- it forks the program and takes the signal handling with it, which a flow pumping
#: turns from threads of its own has none to lend. A flow's own callbacks are the same shape
#: the other way round: a CLI takes a tool by starting a program, so there is a program, and it
#: does nothing but carry the protocol back to the process the callbacks are in. Both are a
#: command line because there is no other way to start a process, and neither is typed.
_SPAWNED = {"cred": _cred, "tools": _tools}


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
    # A line that names no command and starts with a flag is the interface being set up: what
    # flow, what runs it, how it is set up. Two flags on their own are not: `--version` says
    # the version, and `--help` lists the commands, which is what somebody typing it wants.
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

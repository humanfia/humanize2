"""``amflows`` -- the whole command line, over subpackages that have none of their own.

    amflows run -f ralph_loop -a claude/claude-opus-4-8/high "$(cat TASK.md)"
    amflows collect
    amflows anchor --target ssh://build-box claude
    amflows tui

A command imports the subpackage it needs when it is the one asked for, and no earlier. Two
things turn on that: `amflows run` must not pay for a date parser it will not use, and
`amflows anchor serve` is what the zipapp bootstrapped onto a target runs, where coganchor is the
only subpackage present and the architecture is whatever the target happens to be.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import argparse

    from amflows.janus import AgentBase

__all__ = ["COMMANDS", "anchor_parser", "flow_and_agents", "main"]

#: Addresses a target may be left listening on without a secret, because nothing off this
#: machine can reach them.
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})


def flow_and_agents(argv: list[str]) -> tuple[str, list[AgentBase], str]:
    """Reads an `amflows run` line into the flow to drive, the agents to drive it with, and
    what to have them do.

    A flow says how many agents it drives, and this is where they come from: one for each, in
    the order the flow takes them, at the model and effort each is to run at. Public because
    the terminal interface starts a flow the same way and then keeps the agents, which is what
    lets a line typed while the flow runs reach the one working.

    Args:
      argv: What followed the command name.

    Returns:
      The flow's path, the agents to drive it with, and the task.

    Raises:
      SystemExit: If the line does not name a flow and an agent apiece, as argparse rejects it.
    """
    import argparse

    backends = ("claude", "codex", "kimi")
    parser = argparse.ArgumentParser(
        prog="amflows run", description="Run an agent flow in this directory."
    )
    parser.add_argument(
        "-f",
        "--flow",
        required=True,
        metavar="PATH",
        help="the flow to drive: one that came with amflows, by name, or a file of your own",
    )
    parser.add_argument(
        "-a",
        "--agents",
        action="append",
        required=True,
        metavar="BACKEND/MODEL/EFFORT[,...]",
        help="the agents to drive the flow with, comma separated and repeatable, as many "
        f"as it declares; BACKEND is one of {', '.join(backends)}",
    )
    parser.add_argument(
        "task",
        help="what the flow is to have the agents do, after -- if it starts with a dash",
    )
    args = parser.parse_args(argv)

    # Only now that the line is known to name agents: `--help` has already exited, and it
    # should not have paid for three backends to say what it takes.
    from amflows.janus.agents import (
        ClaudeCodeAgent,
        ClaudeCodeAgentConfig,
        CodexAgent,
        CodexAgentConfig,
        KimiCodeCLIAgent,
        KimiCodeCLIAgentConfig,
    )
    from amflows.janus.flows import find

    built = {
        "claude": (ClaudeCodeAgent, ClaudeCodeAgentConfig),
        "codex": (CodexAgent, CodexAgentConfig),
        "kimi": (KimiCodeCLIAgent, KimiCodeCLIAgentConfig),
    }
    agents: list[AgentBase] = []
    for spec in ",".join(args.agents).split(","):
        # Read from both ends, because a model name may hold slashes of its own -- Kimi's
        # are `kimi-code/k3` -- while a backend and an effort never do.
        backend, _, rest = spec.strip().partition("/")
        model, _, effort = rest.rpartition("/")
        if backend not in backends or not model or not effort:
            parser.error(f"bad agent {spec!r}: expected BACKEND/MODEL/EFFORT")
        agent, config = built[backend]
        agents.append(agent(config(model=model, effort=effort)))
    return find(args.flow), agents, args.task


def _run(argv: list[str]) -> int:
    """Drives the flow named on the command line, on the agents it names.

    Args:
      argv: What followed the command name.

    Returns:
      Zero, once the flow has returned.
    """
    path, agents, task = flow_and_agents(argv)

    from amflows.janus.runner import NotAFlow, Runner

    try:
        runner = Runner(path, agents)
    except NotAFlow as error:
        # A flow that is not there, or one that takes other agents than these, is a command
        # line that was wrong before anything ran, so it exits as argparse's own rejections
        # do. What the flow raises for itself is the flow's, and is left to say so itself.
        print(f"amflows run: error: {error}", file=sys.stderr)
        raise SystemExit(2) from error
    runner.run(task)
    return 0


def _collect(argv: list[str]) -> int:
    """Writes the trajectories the agents left behind as one trace file.

    Args:
      argv: What followed the command name.

    Returns:
      Zero, once the trace has been written.
    """
    import argparse

    parser = argparse.ArgumentParser(
        prog="amflows collect",
        description="Aggregate agent trajectories into a Chrome trace.",
    )
    parser.add_argument(
        "workspace",
        nargs="?",
        help="Workspace directory, defaults to the current one unless sessions are named.",
    )
    parser.add_argument(
        "--session",
        action="append",
        dest="sessions",
        metavar="SESSION[,SESSION...]",
        help="Sessions to include, comma separated and repeatable, defaults to every session.",
    )
    parser.add_argument(
        "--output",
        help="Trace file to write, defaults to .amflows/<datetime>.trace.json.",
    )
    parser.add_argument(
        "--start", help="Earliest session time to include, e.g. '2 days ago'."
    )
    parser.add_argument(
        "--end", help="Latest session time to include, e.g. 'yesterday 18:00'."
    )
    args = parser.parse_args(argv)

    import datetime

    from amflows.oronyx.collector import collect

    # One trace per run, named after the moment it was taken, so collecting twice keeps both
    # rather than writing over the first.
    stamp = datetime.datetime.now(datetime.UTC).strftime("%Y%m%dT%H%M%SZ")
    output = args.output or f".amflows/{stamp}.trace.json"

    try:
        document = collect(
            args.workspace,
            sessions=args.sessions,
            output=output,
            start=args.start,
            end=args.end,
        )
    except ValueError as error:
        parser.error(str(error))
    summary = document["otherData"]
    print(
        f"{output}: {summary.get('sessions', '0')} sessions, "
        f"{summary.get('slices', '0')} slices"
    )
    return 0


def anchor_parser() -> argparse.ArgumentParser:
    """Builds the parser for `amflows anchor`, whose every option is a setting of the session.

    Public because :meth:`~amflows.coganchor.anchor.AnchorConfig.command` renders this same
    command line to run a turn in a process of its own, and nothing else could check that what
    it renders is what this reads back.

    Returns:
      A parser whose result is what :class:`~amflows.coganchor.anchor.AnchorConfig` takes.
    """
    import argparse
    import os

    parser = argparse.ArgumentParser(
        prog="amflows anchor",
        description="Run a coding agent on this machine that acts on another one.",
        epilog="Example: amflows anchor --target ssh://build-box claude --model opus",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--target",
        default=os.environ.get("AMFLOWS_TARGET", "local"),
        metavar="URL",
        help="ssh://HOST, docker://CONTAINER, tcp://HOST:PORT, or local[:DIR] "
        "(default: $AMFLOWS_TARGET)",
    )
    parser.add_argument(
        "--workspace",
        metavar="PATH",
        default=None,
        help="the project directory as it exists on the target (default: this directory)",
    )
    parser.add_argument(
        "--remote-path",
        metavar="PATH",
        default=None,
        help="where the workspace really lives on the target, if not --workspace",
    )
    parser.add_argument(
        "--shadow",
        metavar="PATH",
        default=None,
        help="local mirror directory (default: --workspace, so paths match exactly)",
    )
    parser.add_argument(
        "--local-path",
        metavar="PATH",
        action="append",
        default=[],
        help="keep this path on the local machine even inside the workspace",
    )
    parser.add_argument(
        "--local-exec",
        metavar="PATH",
        action="append",
        default=[],
        help="run programs under this path locally instead of on the target",
    )
    parser.add_argument(
        "--net",
        choices=["local", "remote"],
        default="local",
        help="where the agent's own TCP connections go (default: local, so its "
        "model provider stays reachable); commands always use the target's network",
    )
    parser.add_argument(
        "--net-allow",
        metavar="HOST[:PORT]",
        action="append",
        default=[],
        help="with --net remote, keep connections to this host local",
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("AMFLOWS_TOKEN"),
        help="shared secret expected by a tcp:// target (default: $AMFLOWS_TOKEN)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="use the mirror directory even if it already holds unrelated files",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="connect to the target, report what was found, and exit",
    )
    parser.add_argument(
        "--log-level",
        default=os.environ.get("AMFLOWS_LOG", "warning"),
        choices=["debug", "info", "warning", "error"],
        help="logging verbosity (default: warning)",
    )
    parser.add_argument(
        "command",
        nargs=argparse.REMAINDER,
        metavar="AGENT [ARGS...]",
        help="the agent to run, e.g. claude, codex or kimi, plus its own arguments",
    )
    return parser


def _tui(argv: list[str]) -> int:
    """Opens the terminal interface, which is every command at one prompt.

    Args:
      argv: What followed the command name, which is nothing it takes.

    Returns:
      Zero, once the interface has been closed.
    """
    import argparse

    argparse.ArgumentParser(
        prog="amflows tui", description="Open the terminal interface."
    ).parse_args(argv)

    from amflows.tui import Amflows

    Amflows().run()
    return 0


def _anchor(argv: list[str]) -> int:
    """Runs the agent named on the command line, with its work landing on another machine.

    Args:
      argv: What followed the command name.

    Returns:
      The agent's exit status, or one of our own if it never ran.
    """
    if argv and argv[0] == "serve":
        # The other half of the same session, routed before the agent half is reached: only
        # this end needs ptrace and an x86-64 register map, which is what lets the same
        # program -- the bundle shipped to the target -- serve a target of any architecture.
        return _serve(argv[1:])

    import logging

    parser = anchor_parser()
    args = parser.parse_args(argv)

    from amflows.coganchor.anchor import AnchorConfig, check, connect
    from amflows.coganchor.proto import ProtocolError

    # stderr, the one stream a session never speaks the protocol on.
    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s amflows %(levelname)s %(message)s",
        stream=sys.stderr,
    )
    if not args.command and not args.check:
        parser.error("no agent given; try `amflows anchor claude`")
    try:
        # Every option is a setting, and every setting is an option.
        config = AnchorConfig(
            target=args.target,
            workspace=args.workspace,
            remote_path=args.remote_path,
            shadow=args.shadow,
            local_paths=tuple(args.local_path),
            local_execs=tuple(args.local_exec),
            net=args.net,
            net_allow=tuple(args.net_allow),
            token=args.token,
            force=args.force,
        )
    except ValueError as exc:
        # Settings a session could not be run under are bad arguments, not failed sessions,
        # so they exit 2 the way argparse's own rejections do.
        parser.error(str(exc))

    try:
        if not args.check:
            return connect(args.command, config)
        found = check(config)
        print(f"target      {found['target']}")
        print(f"hostname    {found.get('hostname')}")
        print(f"python      {found.get('python')} (pid {found.get('pid')})")
        for export in found.get("exports", []):
            print(f"export      {export['virtual']} -> {export['real']}")
        print(f"workspace   {found['workspace']} ({found['entries']} entries)")
        return 0
    except KeyboardInterrupt:
        return 130
    except (ConnectionError, ProtocolError, OSError, ValueError) as exc:
        print(f"amflows: {exc}", file=sys.stderr)
        return 1


def _serve(argv: list[str]) -> int:
    """Replays on this machine what an `amflows anchor` elsewhere asks of it.

    Args:
      argv: What followed the command name.

    Returns:
      Zero once the session or the listener is done, or a status of our own if neither could
      be started.
    """
    import argparse
    import contextlib
    import logging
    import os

    parser = argparse.ArgumentParser(
        prog="amflows anchor serve",
        description="Replay an `amflows anchor` session's operations on this machine.",
    )
    parser.add_argument(
        "--export",
        metavar="VIRTUAL[:REAL]",
        action="append",
        default=[],
        required=True,
        help="expose a directory; VIRTUAL is the path the agent believes it uses",
    )
    where = parser.add_mutually_exclusive_group(required=True)
    where.add_argument(
        "--stdio", action="store_true", help="serve one session over stdin/stdout"
    )
    where.add_argument(
        "--listen", metavar="[HOST:]PORT", help="serve TCP connections on this address"
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("AMFLOWS_TOKEN"),
        help="shared secret required from clients (default: $AMFLOWS_TOKEN)",
    )
    parser.add_argument(
        "--log-level",
        default=os.environ.get("AMFLOWS_LOG", "warning"),
        choices=["debug", "info", "warning", "error"],
        help="logging verbosity (default: warning)",
    )
    args = parser.parse_args(argv)

    from amflows.coganchor.proto import Channel
    from amflows.coganchor.serve.exports import ExportTable
    from amflows.coganchor.serve.server import Server

    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s amflows %(levelname)s %(message)s",
        stream=sys.stderr,
    )
    try:
        table = ExportTable.parse(args.export)
    except ValueError as exc:
        print(f"amflows: {exc}", file=sys.stderr)
        return 2

    if args.stdio:
        # The real stdin/stdout are duplicated away and fds 0 and 1 pointed at /dev/null, so
        # a stray print from this process or any child it spawns cannot corrupt the protocol
        # stream. fd 2 keeps carrying the log.
        read_fd, write_fd = os.dup(0), os.dup(1)
        devnull = os.open(os.devnull, os.O_RDWR)
        os.dup2(devnull, 0)
        os.dup2(devnull, 1)
        os.close(devnull)
        channel = Channel(os.fdopen(read_fd, "rb"), os.fdopen(write_fd, "wb"))
        with contextlib.suppress(KeyboardInterrupt):
            Server(channel, table, args.token).serve()
        return 0

    host, sep, port = args.listen.rpartition(":")
    if not sep:
        host, port = "127.0.0.1", args.listen
    host = host.strip("[]") or "127.0.0.1"
    if not port.isdigit() or not 0 <= int(port) <= 65535:
        print(
            f"amflows: malformed listen address {args.listen!r}; expected [HOST:]PORT",
            file=sys.stderr,
        )
        return 2
    if host not in _LOOPBACK_HOSTS and not args.token:
        print(
            "amflows: refusing to listen on a non-loopback address without --token",
            file=sys.stderr,
        )
        return 2

    # Imported here rather than above: a session over a pipe is the one the bootstrapped
    # target runs, and it has no use for a listener that serves many.
    from amflows.coganchor.serve.listener import serve_forever

    try:
        serve_forever(host, int(port), table, args.token)
    except OSError as exc:
        print(
            f"amflows: cannot listen on {host}:{port}: {exc.strerror}", file=sys.stderr
        )
        return 1
    return 0


#: Each command, as what carries it out and the line a listing shows it as. Read by the
#: terminal interface too, which offers the same commands at its own prompt.
COMMANDS = {
    "run": (_run, "run an agent flow in this directory"),
    "collect": (
        _collect,
        "aggregate the trajectories agents left behind into a Chrome trace",
    ),
    "anchor": (_anchor, "run an agent here that acts on another machine"),
    "tui": (_tui, "open the terminal interface"),
}


def main(argv: list[str] | None = None) -> int:
    """Runs the command named on the command line, or the terminal interface if none is.

    Args:
      argv: The arguments to parse, defaulting to this process's own.

    Returns:
      The command's exit status.
    """
    arguments = sys.argv[1:] if argv is None else argv
    if not arguments or arguments[0] not in COMMANDS:
        import argparse

        if arguments[:1] == ["--version"]:
            # Read from the installed metadata, which costs more to reach than everything
            # else here put together -- so it is reached only when it is what was asked for.
            from importlib.metadata import version

            print(f"amflows {version('amflows')}")
            return 0
        # Anything else naming no command it knows: argparse says which was meant and exits,
        # so nothing below it runs. `--version` is handled above precisely because it is the
        # one flag this parser no longer carries, and would otherwise fall through to a
        # command lookup that has nothing to look up.

        # There is nothing to route to, so this parser only has to say so. It knows the
        # commands by name and not by what they take -- each one answers
        # `amflows COMMAND --help` itself -- and whether it lists them or names the one that
        # was meant, it exits rather than returning here.
        parser = argparse.ArgumentParser(
            prog="amflows",
            description="Orchestrate, execute, and observe agent flows.",
            epilog="Run `amflows COMMAND --help` for what a command takes.",
        )
        commands = parser.add_subparsers(metavar="COMMAND", required=True)
        for name, (_, summary) in COMMANDS.items():
            commands.add_parser(name, help=summary, add_help=False)
        parser.parse_args(arguments)

    return COMMANDS[arguments[0]][0](arguments[1:])

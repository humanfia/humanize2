"""``amflows moor`` -- run a coding agent here, have it act on another machine.

    amflows moor --target ssh://build-box claude
    amflows moor --target ssh://gpu-01 codex exec "run the test suite"
    amflows moor --target ssh://build-box kimi

Every option here is a field of :class:`~amflows.coganchor.anchor.AnchorConfig`,
so what this parses is what :func:`~amflows.coganchor.anchor.connect` takes.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

from amflows.coganchor.anchor import AnchorConfig, check, connect
from amflows.coganchor.proto import ProtocolError

__all__ = ["build_parser", "main"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="amflows moor",
        description="Run a coding agent on this machine that acts on another one.",
        epilog="Example: amflows moor --target ssh://build-box claude --model opus",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--target",
        default=os.environ.get("COGANCHOR_TARGET", "local"),
        metavar="URL",
        help="ssh://HOST, docker://CONTAINER, tcp://HOST:PORT, or local[:DIR] "
        "(default: $COGANCHOR_TARGET)",
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
        default=os.environ.get("COGANCHOR_TOKEN"),
        help="shared secret expected by a tcp:// target (default: $COGANCHOR_TOKEN)",
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
        default=os.environ.get("COGANCHOR_LOG", "warning"),
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


def main(argv: list[str] | None = None) -> int:
    """Runs the agent named on the command line, or serves a session for one elsewhere.

    Args:
      argv: The arguments to parse, defaulting to this process's own.

    Returns:
      The agent's exit status, or one of our own if it never ran.
    """
    arguments = sys.argv[1:] if argv is None else argv
    if arguments and arguments[0] == "serve":
        # `amflows anchor` under the name the target is started as, routed before the agent
        # half is reached: both ends of a session are this one program, but only this end
        # needs ptrace and an x86-64 register map, which is what lets the same program --
        # the bundle shipped to the target -- serve a target of any architecture.
        from amflows.coganchor.serve.cli import main as serve

        return serve(arguments[1:])

    parser = build_parser()
    args = parser.parse_args(arguments)
    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s amflows %(levelname)s %(message)s",
        stream=sys.stderr,
    )
    if not args.command and not args.check:
        parser.error("no agent given; try `amflows moor claude`")
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

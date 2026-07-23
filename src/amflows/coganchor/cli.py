"""``coganchor`` -- run a coding agent here, have it act on another machine.

    coganchor --target ssh://build-box claude
    coganchor --target ssh://gpu-01 codex exec "run the test suite"
    coganchor --target ssh://build-box kimi

The agent process runs locally, so its credentials, its state directory and
its connection to its model provider stay put.  Everything it *does* -- reading
and writing project files, running commands, reaching the network from those
commands -- happens on the target.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

from amflows.coganchor import __version__, agents
from amflows.coganchor.netproxy import NetProxy
from amflows.coganchor.policy import Layout, Router
from amflows.coganchor.proto import ProtocolError
from amflows.coganchor.remote import RemoteClient
from amflows.coganchor.shadow import ShadowTree, prepare_shadow_root
from amflows.coganchor.supervisor import Launch, Supervisor
from amflows.coganchor.transport import Target, Transport, connect

__all__ = ["main"]

log = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="coganchor",
        description="Run a coding agent on this machine that acts on another one.",
        epilog="Example: coganchor --target ssh://build-box claude --model opus",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--version", action="version", version=f"coganchor {__version__}"
    )
    parser.add_argument(
        "--target",
        default=os.environ.get("COGANCHOR_TARGET", "local"),
        metavar="URL",
        help="ssh://HOST, tcp://HOST:PORT, or local[:DIR] (default: $COGANCHOR_TARGET)",
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
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s coganchor %(levelname)s %(message)s",
        stream=sys.stderr,
    )
    try:
        return _run(args)
    except KeyboardInterrupt:
        return 130
    except (ConnectionError, ProtocolError, OSError, ValueError) as exc:
        print(f"coganchor: {exc}", file=sys.stderr)
        return 1


def _run(args: argparse.Namespace) -> int:
    try:
        target = Target.parse(args.target)
    except ValueError as exc:
        # A malformed argument exits 2, like argparse's own rejections.
        print(f"coganchor: {exc}", file=sys.stderr)
        return 2
    workspace = os.path.abspath(args.workspace or os.getcwd())
    shadow_root = os.path.abspath(args.shadow) if args.shadow else workspace
    remote_path = args.remote_path or target.path or None
    exports = [f"{workspace}:{remote_path}" if remote_path else workspace]

    if args.check:
        return _check(target, exports, args.token, workspace)

    if not args.command:
        print("coganchor: no agent given; try `coganchor claude`", file=sys.stderr)
        return 2
    agent = agents.resolve(args.command)

    layout = Layout.create(shadow_root, workspace)
    router = Router(
        layouts=(layout,),
        local_paths=tuple(
            agent.local_paths + [os.path.abspath(p) for p in args.local_path]
        ),
        local_programs=tuple(
            agent.local_programs + [os.path.abspath(p) for p in args.local_exec]
        ),
    )
    prepare_shadow_root(shadow_root, force=args.force, target=target.describe())

    transport = connect(target, exports, args.token)
    client = RemoteClient(transport.channel)
    netproxy = NetProxy(client, tuple(args.net_allow)) if args.net == "remote" else None
    supervisor = Supervisor(
        client,
        router,
        ShadowTree(client, router),
        Launch(
            program=agent.program,
            argv=agent.argv,
            env=_agent_env(target, workspace, shadow_root),
            cwd=shadow_root,
        ),
        netproxy=netproxy,
        token=args.token,
    )
    log.info("running %s against %s", agent.profile.name, target.describe())
    try:
        if netproxy is not None:
            netproxy.start()
        return supervisor.run()
    finally:
        if netproxy is not None:
            netproxy.close()
        client.close()
        transport.close()


def _check(
    target: Target, exports: list[str], token: str | None, workspace: str
) -> int:
    """Connect, describe what is on the other end, and disconnect."""
    transport: Transport | None = None
    try:
        transport = connect(target, exports, token)
        client = RemoteClient(transport.channel)
        info = client.start(token)
        listing = client.listdir(workspace)
        print(f"target      {target.describe()}")
        print(f"hostname    {info.get('hostname')}")
        print(f"python      {info.get('python')} (pid {info.get('pid')})")
        for export in info.get("exports", []):
            print(f"export      {export['virtual']} -> {export['real']}")
        print(f"workspace   {workspace} ({len(listing['entries'])} entries)")
        client.close()
        return 0
    finally:
        if transport is not None:
            transport.close()


def _agent_env(target: Target, workspace: str, shadow_root: str) -> dict[str, str]:
    env = dict(os.environ)
    env["COGANCHOR"] = __version__
    env["COGANCHOR_TARGET"] = target.describe()
    env["PWD"] = shadow_root
    # Agents surface this to the model; being explicit beats it guessing.
    env["COGANCHOR_WORKSPACE"] = workspace
    return env

"""The `hmz anchor` line, both ways round: read into settings, and written back out.

Here rather than in the command line, because the two directions have to agree and only one
of them is a command line. :meth:`~humanize.coganchor.anchor.AnchorConfig.command` renders a
turn as this same invocation for a process of its own, so a flag added to the parser and not
to the renderer is a setting a spawned turn silently loses. All three -- the flags, what they
become, and what they are written back as -- are in this one file, where that is visible.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from argparse import ArgumentParser, Namespace
    from collections.abc import Sequence

    from .anchor import AnchorConfig

__all__ = ["parser", "render", "settings"]


def parser() -> ArgumentParser:
    """Builds the parser for `hmz anchor`, whose every option is a setting of the session.

    Returns:
      A parser whose result is what :class:`~humanize.coganchor.anchor.AnchorConfig` takes.
    """
    import argparse
    import os

    built = argparse.ArgumentParser(
        prog="hmz anchor",
        description="Run a coding agent on this machine that acts on another one.",
        epilog="Example: hmz anchor --target ssh://build-box claude --model opus",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    built.add_argument(
        "--target",
        default=os.environ.get("HUMANIZE_TARGET", "local"),
        metavar="URL",
        help="ssh://HOST, docker://CONTAINER, tcp://HOST:PORT, or local[:DIR] "
        "(default: $HUMANIZE_TARGET)",
    )
    built.add_argument(
        "--workspace",
        metavar="PATH",
        default=None,
        help="the project directory as it exists on the target (default: this directory)",
    )
    built.add_argument(
        "--remote-path",
        metavar="PATH",
        default=None,
        help="where the workspace really lives on the target, if not --workspace",
    )
    built.add_argument(
        "--shadow",
        metavar="PATH",
        default=None,
        help="local mirror directory (default: --workspace, so paths match exactly)",
    )
    built.add_argument(
        "--local-path",
        metavar="PATH",
        action="append",
        default=[],
        help="keep this path on the local machine even inside the workspace",
    )
    built.add_argument(
        "--local-exec",
        metavar="PATH",
        action="append",
        default=[],
        help="run programs under this path locally instead of on the target",
    )
    built.add_argument(
        "--net",
        choices=["local", "remote"],
        default="local",
        help="where the agent's own TCP connections go (default: local, so its "
        "model provider stays reachable); commands always use the target's network",
    )
    built.add_argument(
        "--net-allow",
        metavar="HOST[:PORT]",
        action="append",
        default=[],
        help="with --net remote, keep connections to this host local",
    )
    built.add_argument(
        "--token",
        default=os.environ.get("HUMANIZE_TOKEN"),
        help="shared secret expected by a tcp:// target (default: $HUMANIZE_TOKEN)",
    )
    built.add_argument(
        "--force",
        action="store_true",
        help="use the mirror directory even if it already holds unrelated files",
    )
    built.add_argument(
        "--check",
        action="store_true",
        help="connect to the target, report what was found, and exit",
    )
    built.add_argument(
        "--log-level",
        default=os.environ.get("HUMANIZE_LOG", "warning"),
        choices=["debug", "info", "warning", "error"],
        help="logging verbosity (default: warning)",
    )
    built.add_argument(
        "command",
        nargs=argparse.REMAINDER,
        metavar="AGENT [ARGS...]",
        help="the agent to run, e.g. claude, codex or kimi, plus its own arguments",
    )
    return built


def settings(args: Namespace) -> AnchorConfig:
    """Reads what the parser answered with into the settings a session runs under.

    Args:
      args: What :func:`parser` parsed. Its `check`, `log_level` and `command` are the command
        line's own business rather than settings, and are not read here.

    Returns:
      The settings. Every option is one, and every one is an option.

    Raises:
      ValueError: If they are settings no session could run under, which a command line
        reports as the bad arguments they are.
    """
    from .anchor import AnchorConfig

    return AnchorConfig(
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


def render(config: AnchorConfig, argv: Sequence[str]) -> list[str]:
    """Writes the settings back out as the `hmz anchor` line that would read as them.

    The interpreter is named explicitly, so the child is the one humanize is installed in
    whether or not the console script is on PATH.

    Args:
      config: The settings to run the agent under.
      argv: The agent to run and its own arguments.

    Returns:
      The command to spawn, which exits with the agent's own status.
    """
    # Joined to their flag rather than following it, so that a setting reading as an option
    # of ours -- a token that happens to start with a dash -- is still its value.
    options = [f"--target={config.target}", f"--net={config.net}"]
    for flag, value in (
        ("--workspace", config.workspace),
        ("--remote-path", config.remote_path),
        ("--shadow", config.shadow),
        ("--token", config.token),
    ):
        if value is not None:
            options.append(f"{flag}={value}")
    for flag, values in (
        ("--local-path", config.local_paths),
        ("--local-exec", config.local_execs),
        ("--net-allow", config.net_allow),
    ):
        options += [f"{flag}={value}" for value in values]
    if config.force:
        options.append("--force")
    return [sys.executable, "-m", "humanize", "anchor", *options, *argv]

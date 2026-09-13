"""The `hmz internal anchor` line, both ways round: read into settings, and written back out.

Here rather than in the command line, because the two directions have to agree and only one
of them is a command line. :meth:`~hmz.coganchor.anchor.AnchorConfig.command` renders a
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
    """Builds the parser for `hmz internal anchor`, whose every option is a setting of the session.

    Returns:
      A parser whose result is what :class:`~hmz.coganchor.anchor.AnchorConfig` takes.
    """
    import argparse
    import os

    built = argparse.ArgumentParser(
        prog="hmz internal anchor",
        # Wrapped by hand: the raw formatter below keeps the epilog's own line breaks,
        # and pays for that by not re-wrapping the description either.
        description="Run a coding agent on this machine that acts on another one.\n"
        "humanize renders this line for every turn whose work lands\n"
        "elsewhere; it is not one to type by hand.",
        epilog="What humanize renders looks like this:\n"
        "  hmz internal anchor --target ssh://build-box claude --model opus",
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
        "--redirect",
        metavar="FROM=TO",
        action="append",
        default=[],
        help="answer this path with that one -- the file it names, or everything "
        "under the directory it names -- and keep what it is answered with local",
    )
    built.add_argument(
        "--chdir",
        metavar="PATH",
        help="where inside the workspace the agent starts, as the target names it "
        "(default: the workspace itself)",
    )
    built.add_argument(
        "--private",
        metavar="NAME",
        action="append",
        default=[],
        help="keep this variable out of what the agent's commands are run with on the "
        "target: a credential it was given to reach its model provider is its own",
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
        "--native",
        action="store_true",
        help="run the CLI already installed on the target rather than supervising one "
        "here: no mirror, nothing traced, and this process carries its streams",
    )
    built.add_argument(
        "--hush",
        metavar="NAME",
        action="append",
        default=[],
        help="with --native, run the CLI on the target without this variable, whoever "
        "left it there: a key in its shell profile would outrank the account it was given",
    )
    built.add_argument(
        "--project",
        metavar="NAME=DIR",
        action="append",
        default=[],
        help="with --native, put this directory of credentials on the target for the life "
        "of the session and set NAME to where it landed; removed when the turn is over",
    )
    built.add_argument(
        "--carry",
        metavar="DIR=PATH",
        action="append",
        default=[],
        help="with --native, put this directory into the target's copy of the workspace at "
        "PATH for the length of the turn -- which is how a flow's own skills get there",
    )
    built.add_argument(
        "--installs",
        metavar="LINE",
        default="",
        help="with --native, the line that installs this CLI, said where the target has "
        "nothing to run",
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
        chdir=args.chdir,
        remote_path=args.remote_path,
        shadow=args.shadow,
        local_paths=tuple(args.local_path),
        local_execs=tuple(args.local_exec),
        redirects=tuple(_pair(said) for said in args.redirect),
        private=tuple(args.private),
        net=args.net,
        net_allow=tuple(args.net_allow),
        token=args.token,
        force=args.force,
        native=args.native,
        hushes=tuple(args.hush),
        projects=tuple(_pair(said) for said in args.project),
        carries=tuple(_pair(said) for said in args.carry),
        installs=args.installs,
    )


def render(config: AnchorConfig, argv: Sequence[str]) -> list[str]:
    """Writes the settings back out as the `hmz internal anchor` line that would read as them.

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
        ("--chdir", config.chdir),
        ("--remote-path", config.remote_path),
        ("--shadow", config.shadow),
        ("--token", config.token),
        # Written only where there is one, unlike the two above: it defaults to "" rather
        # than to None, and an empty line would read as a CLI nothing installs.
        ("--installs", config.installs or None),
    ):
        if value is not None:
            options.append(f"{flag}={value}")
    for flag, values in (
        ("--local-path", config.local_paths),
        ("--local-exec", config.local_execs),
        ("--net-allow", config.net_allow),
        ("--hush", config.hushes),
    ):
        options += [f"{flag}={value}" for value in values]
    for flag, pairs in (
        ("--redirect", config.redirects),
        ("--project", config.projects),
        ("--carry", config.carries),
    ):
        options += [f"{flag}={one}={other}" for one, other in pairs]
    options += [f"--private={name}" for name in config.private]
    if config.force:
        options.append("--force")
    if config.native:
        options.append("--native")
    return [sys.executable, "-m", "hmz", "internal", "anchor", *options, *argv]


def _pair(said: str) -> tuple[str, str]:
    """Reads one `FROM=TO` as the two paths it names.

    Whether they are paths a session could answer anything with is
    :class:`~hmz.coganchor.anchor.AnchorConfig`'s to say, so one with no `=` in it comes
    back as half a pair and is refused there along with everything else it refuses.
    """
    named, _, instead = said.partition("=")
    return named, instead

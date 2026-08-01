"""Anchoring an agent that runs here to the machine its work lands on.

Where a session is said in Python: the settings, the call that runs one, and
the call that only asks the target what it is.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence

    from hmz.coganchor.transport import Target

__all__ = ["AnchorConfig", "check", "connect"]

log = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True, slots=True)
class AnchorConfig:
    """Where an agent's work lands, and what of it stays on this machine.

    Attributes:
      target: The machine the work lands on, as `ssh://HOST`, `docker://CONTAINER`,
        `tcp://HOST:PORT` or `local[:DIR]`, where a local target stands in for a remote one.
      chdir: Where inside that workspace the agent starts, as the target names it, or None
        for the workspace itself. What a session opened at a directory of its own comes to:
        the agent is put in this machine's mirror of it, and what it does there lands there.
      workspace: The project directory as it exists on the target, defaulting to this one.
      remote_path: Where that workspace really lives on the target, if not `workspace`.
      shadow: The local mirror directory, defaulting to `workspace` so that the paths the
        agent sees are the target's own.
      local_paths: Paths to keep on this machine even when they are inside the workspace.
      local_execs: Paths whose programs run here rather than on the target.
      private: Variables of the agent's own that must not cross to the target: a credential it
        was given to reach its model provider is the agent's business and not the target's, and
        everything else it exports reaches every command it runs there.
      redirects: Paths this session answers with others, as `(what the agent names, what it
        gets)`. A directory stands for everything inside it, and what a path is answered with
        is kept on this machine like any other state of the agent's own. This is how a turn
        runs as a provider's account: a process has one tracer, so an anchored session
        answers for the credentials itself rather than nesting a supervisor inside this one.
      net: Where the agent's own connections go: `local`, so that its model provider stays
        reachable, or `remote`. What it spawns always uses the target's network.
      net_allow: Hosts to keep local anyway when `net` is remote, as `HOST[:PORT]`.
      token: The shared secret a `tcp://` target expects. A spawned session falls back to
        `$HUMANIZE_TOKEN` when this is None, the way the command line does.
      force: Whether to use a mirror directory that already holds unrelated files.
    """

    target: str = "local"
    workspace: str | None = None
    chdir: str | None = None
    remote_path: str | None = None
    shadow: str | None = None
    local_paths: tuple[str, ...] = ()
    local_execs: tuple[str, ...] = ()
    private: tuple[str, ...] = ()
    redirects: tuple[tuple[str, str], ...] = ()
    net: str = "local"
    net_allow: tuple[str, ...] = ()
    token: str | None = None
    force: bool = False

    def __post_init__(self) -> None:
        """Refuses what the command line refuses, so both spellings mean the same thing.

        Where it is written, rather than where it is used: a flow that misspells a target
        hears about it as it configures its agents, not hours into the loop that drives them.

        Raises:
          ValueError: If the target cannot be read, the work's own connections are neither
            kept local nor sent to the target, or a path is answered with something that is
            not a path.
        """
        from hmz.coganchor.transport import Target

        Target.parse(self.target)
        if self.net not in ("local", "remote"):
            raise ValueError(f"unsupported net {self.net!r}; expected local or remote")
        for pair in self.redirects:
            # Absolute both ways: what the agent names is resolved before it is looked up,
            # and a relative answer would be read against wherever the turn happens to be.
            if not all(part.startswith("/") for part in pair):
                raise ValueError(
                    f"unsupported redirect {'='.join(pair)!r}; expected two absolute paths"
                )

    def command(
        self,
        argv: Sequence[str],
        *,
        swaps: Sequence[tuple[str, str]] = (),
        private: Sequence[str] = (),
        chdir: str = "",
    ) -> list[str]:
        """Renders the invocation that runs `argv` under this anchor in a process of its own.

        What :func:`connect` does in this one, for callers that cannot lend it theirs. A
        method rather than the function it calls, so that a caller holding a stand-in for
        these settings can answer for what a turn is spawned as.

        Args:
          argv: The agent to run and its own arguments.
          swaps: Paths this one turn answers with others, on top of :attr:`redirects`. Where a
            turn under a provider says which credentials it is taken with, rather than the
            settings saying it for every turn.
          private: Variables this one turn keeps to itself, on top of :attr:`private` -- the
            same thing said for the credentials a provider hands the agent as variables
            rather than as files.
          chdir: Where inside the workspace this one session works, as the target names it,
            in place of :attr:`chdir`. Where a session opened at a directory of its own says
            so, rather than the settings saying it for every session.

        Returns:
          The command to spawn, which exits with the agent's own status.

        Raises:
          ValueError: If a swap is not between two absolute paths.
        """
        from hmz.coganchor.argv import render

        answering = (
            replace(
                self,
                redirects=(*self.redirects, *swaps),
                private=(*self.private, *private),
                chdir=chdir or self.chdir,
            )
            if swaps or private or chdir
            else self
        )
        return render(answering, argv)

    def mount(self) -> tuple[Target, str, str]:
        """Reads the target, and works out where the workspace is on each side of it.

        Returns:
          The target as parsed, the workspace's absolute path on this machine, and the export
          that names it to the target, as `VIRTUAL[:REAL]`.

        Raises:
          ValueError: If the target cannot be read.
        """
        from hmz.coganchor.transport import Target

        target = Target.parse(self.target)
        workspace = os.path.abspath(self.workspace or os.getcwd())
        real = self.remote_path or target.path
        return target, workspace, f"{workspace}:{real}" if real else workspace


def check(config: AnchorConfig | None = None) -> dict[str, Any]:
    """Asks the target what it is, without running anything on it.

    Args:
      config: Where the work would land, defaulting to this directory on a local target.

    Returns:
      What the target says about itself -- its `hostname`, the `python` running it, its `pid`
      and the `exports` it opened -- along with the `target` it was reached at, the
      `workspace`, and how many `entries` that workspace holds.

    Raises:
      ValueError: If the target cannot be read.
      OSError: If the target cannot be reached, or the workspace is not there.
    """
    from hmz.coganchor import transport
    from hmz.coganchor.remote import RemoteClient

    config = config or AnchorConfig()
    target, workspace, export = config.mount()
    link = transport.connect(target, [export], config.token)
    client = RemoteClient(link.channel)
    try:
        return client.start(config.token) | {
            "target": target.describe(),
            "workspace": workspace,
            "entries": len(client.listdir(workspace)["entries"]),
        }
    finally:
        client.close()
        link.close()


def connect(command: Sequence[str], config: AnchorConfig | None = None) -> int:
    """Runs a coding agent on this machine that acts on another one.

    The agent process stays here, keeping its credentials, its state directory and its link
    to its model provider. Everything it *does* -- reading and writing project files, running
    commands, reaching the network from those commands -- happens on the target, and is
    undone by nothing: the call returns once the agent has exited and everything it wrote has
    been pushed.

    Args:
      command: The agent to run and its own arguments, e.g. `["claude", "--print"]`.
      config: Where its work lands, defaulting to this directory on a local target.

    Returns:
      The agent's own exit status.

    Raises:
      ValueError: If the target cannot be read, or no agent was named.
      FileNotFoundError: If the agent is not on PATH.
      OSError: If the mirror cannot be prepared or the target cannot be reached.
    """
    # Imported here rather than at the top: this half needs ptrace and an x86-64 register
    # map, which the machines reading the settings above are not required to have.
    from hmz.coganchor import __version__, statepaths, transport
    from hmz.coganchor.netproxy import NetProxy
    from hmz.coganchor.policy import Layout, Router
    from hmz.coganchor.remote import RemoteClient
    from hmz.coganchor.shadow import ShadowTree, prepare_shadow_root
    from hmz.coganchor.supervisor import Launch, Supervisor

    config = config or AnchorConfig()
    target, workspace, export = config.mount()
    agent = statepaths.resolve(list(command))
    shadow_root = os.path.abspath(config.shadow) if config.shadow else workspace
    # Where the agent itself starts: the mirror of the directory it was told to work in,
    # which is the workspace unless a session asked for one inside it.
    started_in = shadow_root
    if config.chdir:
        under = os.path.abspath(config.chdir)
        if under != workspace and not under.startswith(workspace + os.sep):
            raise ValueError(f"{under} is not inside {workspace}")
        started_in = os.path.join(shadow_root, os.path.relpath(under, workspace))
    redirects = tuple(
        (os.path.abspath(named), os.path.abspath(instead))
        for named, instead in config.redirects
    )
    router = Router(
        layouts=(Layout.create(shadow_root, workspace),),
        local_paths=tuple(
            agent.local_paths
            + [os.path.abspath(path) for path in config.local_paths]
            # What a path is answered with is this machine's business: mirroring a
            # provider's credentials onto the target would put them where the work lands.
            + [instead for _, instead in redirects]
        ),
        local_programs=tuple(
            agent.local_programs
            + [os.path.abspath(path) for path in config.local_execs]
        ),
        redirects=redirects,
    )
    prepare_shadow_root(shadow_root, force=config.force, target=target.describe())

    link = transport.connect(target, [export], config.token)
    client = RemoteClient(link.channel)
    netproxy = NetProxy(client, config.net_allow) if config.net == "remote" else None
    # The mirror fills itself in as the agent looks at things, and the one directory it
    # cannot be asked about first is the one the agent is started in: the `chdir` happens in
    # the forked child, before it has become the agent and before anything may talk to the
    # target -- a reader thread cannot exist across that fork. So the directory is made here
    # and left empty; the first thing the agent does in it is what fills it in, and a
    # directory the target does not have is emptied again by the same reconciliation.
    os.makedirs(started_in, exist_ok=True)
    supervisor = Supervisor(
        client,
        router,
        ShadowTree(client, router),
        Launch(
            program=agent.program,
            argv=agent.argv,
            env=dict(os.environ)
            | {
                "HUMANIZE": __version__,
                "HUMANIZE_TARGET": target.describe(),
                "PWD": started_in,
                # Agents surface this to the model; being explicit beats it guessing.
                "HUMANIZE_WORKSPACE": workspace,
            },
            cwd=started_in,
        ),
        netproxy=netproxy,
        token=config.token,
        private=config.private,
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
        link.close()

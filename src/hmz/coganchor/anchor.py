"""Anchoring an agent to the machine its work lands on, both ways round.

Where a session is said in Python: the settings, the two calls that run one, and the call
that only asks the target what it is.

The two are opposites and the settings are shared. :func:`connect` keeps the agent here and
answers everything it does from the target -- a mirror of the workspace, a supervisor, a
syscall at a time. :func:`drive` keeps nothing here: the CLI already installed on the target
is the one that runs, and this process carries its streams. Which to use is a fact about the
anchor rather than about the machine, so it is a setting and
:attr:`AnchorConfig.capabilities` is what says it out loud.
"""

from __future__ import annotations

import contextlib
import logging
import os
import sys
import uuid
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from hmz.coganchor.remote import RemoteClient
    from hmz.coganchor.transport import Target

__all__ = ["AnchorConfig", "NotInstalled", "check", "connect", "drive"]

log = logging.getLogger(__name__)


class NotInstalled(FileNotFoundError):  # noqa: N818 -- what it is, not what went wrong
    """The CLI a native turn was to run is not on the target.

    Its own kind rather than the bare `FileNotFoundError` it is one of, because what is done
    about it is particular: it is the one failure that means *install this there*, and the one
    a command line answers with the status a shell uses for a command it could not find.
    Every other missing file on the way to a turn -- a workspace the target has not got, an
    `ssh` this machine has not got -- is a different thing gone wrong and must not be read as
    this one.
    """


#: How long the short commands a native session settles itself with may take. Generous, since
#: each is a round trip to a machine that may be far away, and bounded, since a target that
#: has stopped answering must read as one that has rather than hang the turn forever.
_SETTLING = 120.0

#: What a status has added to it to say a signal ended the command, as every shell reports it.
_SIGNALLED = 128

#: This process's own input. Read from the descriptor rather than through :data:`sys.stdin`, so
#: that what crosses is bytes exactly as they arrived: the backends this exists for frame their
#: protocol themselves, and a reader that waited for a line would hold a request until the next
#: one arrived. How much at a time is the protocol's own chunk, read where it is declared.
_STDIN = 0

#: How long the thread carrying that input waits before looking again at whether the turn is
#: over. A number rather than a blocking read, so that the thread ends when the turn does
#: instead of sitting on this process's input after the call has returned.
_LOOKING = 0.2

#: Finding the CLI on the target, in POSIX sh. `command -v` rather than `which`, which is not
#: POSIX and which some shells answer for a name nothing would run. A path is answered with
#: itself where it is executable, which is what makes one lookup serve both spellings.
_FIND_PROGRAM = 'command -v -- "$1" 2>/dev/null || exit 127'

#: Making the directory a session's credentials live in on the target. `mktemp -d` makes one
#: only its owner may enter; the `umask` and the `chmod` say so again, because a target whose
#: `mktemp` is a shim for something laxer is not a target to take that on trust. The bare form
#: first and a template after it, the two spellings BSD and GNU `mktemp` agree on between them.
_MAKE_SESSION = (
    "umask 077; "
    "d=$(mktemp -d 2>/dev/null || mktemp -d -t humanize) || exit 1; "
    'chmod 700 "$d" || exit 1; '
    'printf %s "$d"'
)

#: Writing one of them, from what arrives on stdin. Anything already at the name goes first,
#: so a link left there is not a link this writes through; the file is made before anything is
#: in it and made unreadable by anyone else in the same breath, so there is no instant at which
#: a credential is on that machine under a mode somebody else could read it through.
_WRITE_PRIVATELY = (
    'umask 077; mkdir -p "$(dirname -- "$1")" || exit 1; rm -f -- "$1" || exit 1; '
    ': > "$1" || exit 1; chmod 600 "$1" || exit 1; cat > "$1"'
)

#: Taking one of them away again, whatever it turned out to be.
_SWEEP = 'rm -rf -- "$1"'

#: Where the turns using a carried directory write down that they are using it. Inside what
#: they are using, so that removing it removes them, and a dotted name so that a CLI reading a
#: directory of skills does not read this as one.
_CLAIMS = ".humanize-carried"

#: Claiming a directory this turn planted. The claims directory says a turn planted it, which
#: is what tells it apart from one the project owns.
_CLAIM = f'mkdir -p "$1/{_CLAIMS}" && : > "$1/{_CLAIMS}/$2"'

#: Taking a share of one that was already there -- and only of one some turn planted. A
#: directory with no claims in it is somebody's own, and this exits non-zero for it so that the
#: turn leaves it entirely alone rather than mounting over it and later removing it.
_SHARE = f'[ -d "$1/{_CLAIMS}" ] && : > "$1/{_CLAIMS}/$2"'

#: Giving that claim up, and taking the whole thing away with the last of them. `rmdir`
#: succeeds only on an empty directory, so it is the test and the removal at once -- another
#: turn still holding a claim leaves a file in there and the mount stays where it is.
_RELEASE = (
    f'rm -f "$1/{_CLAIMS}/$2"; '
    f'if rmdir "$1/{_CLAIMS}" 2>/dev/null; then rm -rf -- "$1"; fi; exit 0'
)


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
      native: Whether the agent's own CLI is the one already installed on the target, driven
        there. The other arrangement, and the opposite of everything above it: there is no
        mirror, no supervisor and no tracing, because there is no local process to trace --
        the CLI runs on the target, in the target's own copy of the workspace, and this
        machine carries its three streams and its exit status and nothing else. Which is why
        the settings above that describe the mirror -- `shadow`, `local_paths`, `local_execs`,
        `redirects`, `net`, `net_allow` -- say nothing here: each of them is an answer about a
        local process, and there is none.
      hushes: Variables the turn is run without on the target, whoever left them there. The
        other half of what `private` is under a supervisor: a key exported in the target's own
        shell profile outranks the account the turn was given, and a turn that ran -- and
        billed -- as that key would look like nothing was wrong.
      projects: Credentials to put on the target for the length of the turn, as
        `(variable, the directory on this machine holding it)`. Each is written into a
        directory only the target's own user may enter, taken away when the turn is over, and
        named to the CLI by setting that variable to where it landed. Never by argv: what is
        in a command line is in another user's `ps`.
      carries: Directories to put in the target's copy of the workspace for the length of the
        turn, as `(the directory on this machine, where it goes relative to the workspace)`.
        Which is how a flow's own skills reach a CLI that reads them on the target: a mirror
        is what pushes them under a supervisor, and there is no mirror here.
      installs: The one line that puts this CLI on the target, said when it is not there.
        Handed in rather than looked up: which line installs a backend is a fact about that
        backend, and coganchor is underneath the layer those are written down in.
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
    native: bool = False
    hushes: tuple[str, ...] = ()
    projects: tuple[tuple[str, str], ...] = ()
    carries: tuple[tuple[str, str], ...] = ()
    installs: str = ""

    def __post_init__(self) -> None:
        """Refuses what the command line refuses, so both spellings mean the same thing.

        Where it is written, rather than where it is used: a flow that misspells a target
        hears about it as it configures its agents, not hours into the loop that drives them.

        Raises:
          ValueError: If the target cannot be read, the work's own connections are neither
            kept local nor sent to the target, a path is answered with something that is not
            a path, a variable to run without is not a variable name, or a credential or a
            directory is to be put somewhere that is not a place.
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
        for name in self.hushes:
            # `env -u NAME` is what takes one off on the target, and `env` refuses a name
            # with an `=` in it -- so one written that way is a turn that would not start,
            # said here instead where the settings are read.
            if not name or "=" in name:
                raise ValueError(f"unsupported hush {name!r}; expected a variable name")
        for name, whence in self.projects:
            if not name or "=" in name or not whence.startswith("/"):
                raise ValueError(
                    f"unsupported projection {name}={whence!r}; expected a variable name "
                    "and an absolute path"
                )
        for whence, where in self.carries:
            # Relative on the target's side, and only downwards: what is carried goes inside
            # the workspace, and a `..` in it would be a flow writing outside the project.
            if not whence.startswith("/"):
                raise ValueError(
                    f"unsupported carry {whence}={where!r}; expected an absolute path"
                )
            if not where or where.startswith("/") or ".." in where.split("/"):
                raise ValueError(
                    f"unsupported carry {whence}={where!r}; expected a path inside "
                    "the workspace"
                )

    @property
    def capabilities(self) -> frozenset[str]:
        """What reaching a turn through this anchor comes to.

        The other half of what a place answers for. A machine's own settings say *where* the
        work lands -- somewhere else, somewhere isolated, somewhere started for the agent --
        and this says *how* a turn gets there, which is a fact about the anchor rather than
        about the machine: the same machine reached two ways is two different sets of things
        a turn may be asked to do.

        There are two ways and each is a function here. `anchor:supervised` is
        :func:`connect`: the agent runs on this machine under coganchor's supervisor, and
        every file it opens and every command it spawns is answered from the target.
        `anchor:native-cli` is :func:`drive`: the CLI already installed on the target is the
        one that runs, read off its own three streams, with nothing traced and nothing
        mirrored. Further ways name themselves here as they arrive, each under `anchor:` and
        its own name, so that a flow needing one asks for it by name instead of inferring it
        from a target.

        Returns:
          The names reaching this anchor answers to.
        """
        return frozenset({"anchor:native-cli" if self.native else "anchor:supervised"})

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
    config = config or AnchorConfig()
    # Answered before anything below is imported, and before a mirror is so much as looked
    # at: driving the CLI on the target needs no ptrace, no register map and no shadow, and a
    # machine that could not supervise a turn can still take one this way.
    if config.native:
        return drive(command, config)

    # Imported here rather than at the top: this half needs ptrace and an x86-64 register
    # map, which the machines reading the settings above are not required to have.
    from hmz.coganchor import __version__, statepaths, transport
    from hmz.coganchor.netproxy import NetProxy
    from hmz.coganchor.policy import Layout, Router
    from hmz.coganchor.remote import RemoteClient
    from hmz.coganchor.shadow import ShadowTree, prepare_shadow_root
    from hmz.coganchor.supervisor import Launch, Supervisor

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
    # How the target spells a path is the target's to say -- a Mac reaches `/tmp` through
    # `/private/tmp` and does not tell `A` from `a` -- and it says so at the handshake, which
    # happens once the agent is forked and stopped, after these settings are read. So the
    # router is given the question rather than the answer, and asks when a path needs routing.
    router.platform = lambda: str(client.info.get("platform", ""))
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


def drive(command: Sequence[str], config: AnchorConfig | None = None) -> int:
    """Runs the CLI already installed on the target, and carries its streams to this process.

    The other arrangement, and the simpler one. Nothing runs here: the CLI is started on the
    target, in the target's own copy of the workspace, and this process is a pipe -- what it
    is given on stdin reaches the CLI's stdin, what the CLI writes reaches these streams
    unchanged and unbuffered, a signal aimed here is aimed there, and the call returns with
    the CLI's own status. Which is what makes running a turn elsewhere an argv change for the
    backends that already speak a framed protocol to a process humanize spawns: the frames
    cross a machine boundary and neither end is told.

    Three things do not ride along on their own, and each is answered here. The environment is
    composed on the target, so what a provider hushes is taken off there with `env -u` rather
    than merely left out of what is sent. Credentials are written into a directory of the
    turn's own that only the target's user may enter, named to the CLI by variable and never by
    argv, and taken away whatever happens. And what the flow carries -- its own skills -- is
    put into the target's copy of the workspace and taken out of it again, since there is no
    mirror to push it.

    Args:
      command: The agent to run and its own arguments, e.g. `["claude", "--print"]`.
      config: Where it runs, defaulting to this directory on a local target.

    Returns:
      The CLI's own exit status, or 128 plus the signal that killed it.

    Raises:
      ValueError: If the target cannot be read, or no agent was named.
      NotInstalled: If the agent is not installed on the target.
      OSError: If the target cannot be reached, or a credential cannot be put on it.
    """
    from hmz.coganchor import __version__, transport
    from hmz.coganchor.remote import RemoteClient

    config = config or AnchorConfig()
    if not command:
        raise ValueError("no agent given")
    target, workspace, export = config.mount()
    started_in = config.chdir or workspace
    if started_in != workspace and not started_in.startswith(workspace + "/"):
        raise ValueError(f"{started_in} is not inside {workspace}")

    link = transport.connect(target, [export], config.token)
    client = RemoteClient(link.channel)
    kept: list[str] = []
    making: set[str] = set()
    session = ""
    # What this turn writes its claims on carried directories under. One per turn rather than
    # per session: a turn is what plants them and a turn is what gives them up.
    whose = uuid.uuid4().hex
    try:
        client.start(config.token)
        program = _installed(client, command[0], workspace, config, target.describe())
        said = {
            "HUMANIZE": __version__,
            "HUMANIZE_TARGET": target.describe(),
            # Agents surface this to the model; being explicit beats it guessing.
            "HUMANIZE_WORKSPACE": workspace,
        }
        if config.projects:
            session = _session(client, workspace)
            said |= _projected(client, config.projects, session, workspace)
        _carried(client, config.carries, workspace, whose, kept, making)
        log.info("driving %s on %s", program, target.describe())
        argv = [*_wrapping(config.hushes, said), program, *command[1:]]
        return _drives(client, argv, started_in, dict(os.environ))
    finally:
        _swept(client, session, kept, sorted(making, reverse=True), workspace, whose)
        client.close()
        link.close()


def _ran(
    client: RemoteClient, argv: list[str], cwd: str, feeding: bytes = b""
) -> tuple[int, str]:
    """Runs one short command on the target and waits for the whole of what it said.

    For the handful of things a session has to settle before the CLI starts -- is it there,
    where may a credential be put, what is to be swept up -- each of which is one command that
    answers in a line. The CLI itself is :func:`_drives`, which never waits for anything.

    Args:
      client: The open connection.
      argv: The command, whose paths may be the workspace's virtual ones: the target rewrites
        them to its own before it runs anything.
      cwd: Where to run it, as the target names it.
      feeding: What to write to its stdin, for a command whose input must not be in its argv.

    Returns:
      Its exit status, and what it wrote to stdout with the trailing newline taken off.

    Raises:
      OSError: If the target could not be asked at all.
    """
    import threading

    from hmz.coganchor.proto import CHUNK_SIZE, Stream

    said = bytearray()
    done = threading.Event()
    held: dict[str, Any] = {}

    def on_output(stream: Stream, data: bytes) -> None:
        if stream is Stream.STDOUT:
            said.extend(data)

    def on_exit(result: dict[str, Any] | None, error: OSError | None) -> None:
        held["result"], held["error"] = result, error
        done.set()

    import signal as signals

    handle = client.start_exec(argv, cwd, {}, on_output, on_exit)
    # A frame apiece, at the size the protocol carries one in: nothing here is ever that big,
    # and a file that was would otherwise be one frame nobody sized.
    for at in range(0, len(feeding), CHUNK_SIZE):
        handle.send_stdin(feeding[at : at + CHUNK_SIZE])
    handle.close_stdin()
    if not done.wait(timeout=_SETTLING):
        # Ended there as well as given up on here, best effort: these are one-line commands,
        # so one that has not answered in this long is stuck, and a stuck command left running
        # on the target is one nothing will ever come back for.
        with contextlib.suppress(OSError):
            handle.signal(signals.SIGKILL)
        raise TimeoutError(f"the target did not answer {argv[0]!r} in {_SETTLING:.0f}s")
    if (error := held.get("error")) is not None:
        raise error
    return _status(held.get("result")), said.decode("utf-8", "replace").strip()


def _status(result: dict[str, Any] | None) -> int:
    """What a command on the target exited with, as a shell would report it.

    Args:
      result: What the target answered the exchange with.

    Returns:
      Its own status, or 128 plus the signal that killed it -- and 1 for a command the target
      said nothing about, which is a command that did not succeed.
    """
    if result is None:
        return 1
    if (signalled := result.get("signal")) is not None:
        return _SIGNALLED + int(signalled)
    return int(result.get("exit_code", 1))


def _installed(
    client: RemoteClient,
    named: str,
    workspace: str,
    config: AnchorConfig,
    where: str,
) -> str:
    """Finds the CLI on the target, before anything is put there on its behalf.

    Asked first because a turn that cannot run must not leave a credential behind it, and
    because what is wrong is one sentence rather than whatever a CLI that is not there makes
    of its arguments. A name is looked up on the target's own `PATH`; a path is tried as it is
    and then by its last component, which is the same fallback a command spawned under a
    supervisor already gets -- an agent bundles helpers under its own install directory, and
    that directory is this machine's.

    Args:
      client: The open connection.
      named: The CLI, as the command line named it.
      workspace: Where to look from, as the target names it.
      config: The settings, for the line that installs it.
      where: The target, as it describes itself, for the sentence this fails with.

    Returns:
      Where it is on the target, as an absolute path.

    Raises:
      NotInstalled: If it is not installed there.
    """
    import errno
    import posixpath

    for candidate in dict.fromkeys((named, posixpath.basename(named))):
        status, found = _ran(
            client, ["/bin/sh", "-c", _FIND_PROGRAM, "humanize", candidate], workspace
        )
        if status == 0 and found:
            return found
    fix = f"; install it there with `{config.installs}`" if config.installs else ""
    raise NotInstalled(errno.ENOENT, f"{named} is not installed on {where}{fix}", named)


def _session(client: RemoteClient, workspace: str) -> str:
    """Makes the directory this session keeps its credentials in on the target.

    Made by `mktemp`, which every POSIX system has and which makes a directory only its owner
    may enter, and then told to be exactly that whatever the target's `umask` had to say.
    Under the target's own temporary directory rather than inside the workspace: what is in
    the workspace is the project's, and a credential written there would be a credential
    committed.

    Args:
      client: The open connection.
      workspace: Where to run the command from, as the target names it.

    Returns:
      Its absolute path on the target.

    Raises:
      OSError: If the target would not make one.
    """
    import errno

    status, made = _ran(client, ["/bin/sh", "-c", _MAKE_SESSION, "humanize"], workspace)
    if status != 0 or not made.startswith("/"):
        raise OSError(
            errno.EACCES,
            "could not make a private directory on the target",
            made or None,
        )
    return made


def _projected(
    client: RemoteClient,
    projects: Sequence[tuple[str, str]],
    session: str,
    workspace: str,
) -> dict[str, str]:
    """Puts this turn's credentials on the target, and says what to call each of them.

    One file at a time and each through the command that writes it, rather than through the
    filesystem calls: those are bounded by what the target exported, which is the workspace,
    and this deliberately lands outside it. The contents cross on the command's stdin, so no
    part of a credential is ever in an argument -- an argument being a line in every other
    user's `ps`.

    Args:
      client: The open connection.
      projects: What to put there, as `(variable, the directory on this machine)`.
      session: The directory on the target to put it under.
      workspace: Where to run the commands from, as the target names it.

    Returns:
      The variable to set for each, naming where it landed.

    Raises:
      OSError: If a credential could not be written to the target, which is a turn that must
        not run: a CLI that did not find the account it was given would sign in as whoever
        the target is.
    """
    import errno
    import posixpath
    from pathlib import Path

    named: dict[str, str] = {}
    for variable, whence in projects:
        root = Path(whence)
        landed = posixpath.join(session, variable.lower())
        for one in sorted(path for path in root.rglob("*") if path.is_file()):
            at = posixpath.join(landed, *one.relative_to(root).parts)
            status, said = _ran(
                client,
                ["/bin/sh", "-c", _WRITE_PRIVATELY, "humanize", at],
                workspace,
                feeding=one.read_bytes(),
            )
            if status != 0:
                raise OSError(
                    errno.EACCES, f"could not put {variable} on the target: {said}", at
                )
        named[variable] = landed
    return named


def _carried(
    client: RemoteClient,
    carries: Sequence[tuple[str, str]],
    workspace: str,
    whose: str,
    planted: list[str],
    making: set[str],
) -> None:
    """Puts what the flow brings into the target's copy of the workspace, for this turn.

    Inside the workspace, so these go through the filesystem calls the target already
    exports. Nothing is written over: a directory of that name already there is the project's
    own, and a flow does not get to replace what it finds -- the same rule a skill mounted on
    this machine is held to.

    Except one that another turn of the same flow put there, which this one shares rather than
    leaves: two turns landing in one workspace want the same skills in the same place, and the
    first to finish must not take them out from under the second. Each turn leaves a claim of
    its own inside what it is using, and what was planted goes when the last claim on it does.
    On the target rather than in a table here, because each turn is a process of its own and a
    table in this one would be a table of one.

    Args:
      client: The open connection.
      carries: What to put there, as `(the directory on this machine, where it goes)`.
      workspace: The workspace, as the target names it.
      whose: What this turn writes its claims under, which nothing else answers to.
      planted: Filled in with what this turn has a claim on, as each claim is taken. Given
        rather than answered with, because what has been planted has to be sweepable even
        when this does not return: a round trip that times out part way through would
        otherwise leave the directories it had already claimed in somebody's project with
        nobody left holding the note to take them away.
      making: Filled in the same way with the directories above those which had to be made
        to hold them. Kept apart because the two come away differently: a claim is given up
        and what it was on goes only with the last of them, and a directory goes only if it
        is empty -- one the project already had is the project's, and a turn ending is not a
        reason for it to disappear.
    """
    import posixpath
    from pathlib import Path

    for whence, where in carries:
        root = Path(whence)
        at = posixpath.join(workspace, where)
        if _there(client, at):
            # Somebody's own of that name, or another turn's. The claims directory is what
            # tells the two apart, and taking a share of one is refused for anything else.
            if _ran(
                client, ["/bin/sh", "-c", _SHARE, "humanize", at, whose], workspace
            )[0]:
                log.info("%s is already on the target; leaving it alone", at)
                continue
            planted.append(at)
            continue
        # Which directories above it do not exist yet, noted before any of them is made: those
        # are the ones this takes away again, and one that was already there was the
        # project's before this turn and is the project's after it.
        above = posixpath.dirname(at)
        while above.startswith(workspace + "/") and not _there(client, above):
            making.add(above)
            above = posixpath.dirname(above)
        planted.append(at)
        try:
            client.mkdir(at, mode=0o755, parents=True)
            for one in sorted(path for path in root.rglob("*") if path.is_file()):
                parts = one.relative_to(root).parts
                if len(parts) > 1:
                    client.mkdir(
                        posixpath.join(at, *parts[:-1]), mode=0o755, parents=True
                    )
                with one.open("rb") as reading:
                    client.write_file(posixpath.join(at, *parts), reading)
        except OSError as why:
            # A workspace that cannot be written is a skill the agent will not have, which is
            # a turn that runs without it rather than a run that will not start.
            log.warning("could not carry %s to %s: %s", whence, at, why)
        _ran(client, ["/bin/sh", "-c", _CLAIM, "humanize", at, whose], workspace)


def _there(client: RemoteClient, path: str) -> bool:
    """Whether the target has anything of that name.

    Args:
      client: The open connection.
      path: What to look for, as the target names it.

    Returns:
      Whether anything of that name is there. Asked of the name rather than of a directory
      listing, because a *file* of that name is something already there too -- and one taken
      for nothing there would be a file of the project's that this then removed.

      Only a plain "there is nothing there" answers False. A target that could not be asked --
      a directory above it nobody may read, a link that went quiet -- answers True, because
      what this guards is whether to write into a path and then delete it: the answer that is
      wrong in that direction destroys somebody's work, and the one that is wrong in this
      direction costs a flow its skills for one turn.
    """
    import errno

    from hmz.coganchor.proto import Op

    try:
        client.call(Op.STAT, path=path)
    except OSError as why:
        return why.errno not in (errno.ENOENT, errno.ENOTDIR)
    return True


def _swept(
    client: RemoteClient,
    session: str,
    held: Sequence[str],
    emptied: Sequence[str],
    workspace: str,
    whose: str,
) -> None:
    """Takes away everything this turn put on the target, whatever became of it.

    Never raises: this runs on the way out of a turn that may itself be on its way out badly,
    and a session that failed to tidy up must not turn into a session that failed.

    Args:
      client: The connection, which may already be broken.
      session: The private directory this turn's credentials went into, or "" for a turn that
        projected none. It is this turn's alone, so it goes whole and without asking.
      held: What this turn has a claim on, as the target names it. Each goes when the last
        claim on it does, which is this one only where no other turn is holding it too.
      emptied: Directories to remove only where nothing is left in them, deepest first --
        something still inside one is somebody else's, and it stays.
      workspace: Where to run the command from, as the target names it.
      whose: What this turn wrote its claims under.
    """
    for script, path, *rest in (
        *([(_SWEEP, session)] if session else []),
        *((_RELEASE, one, whose) for one in held),
    ):
        try:
            status, said = _ran(
                client, ["/bin/sh", "-c", script, "humanize", path, *rest], workspace
            )
        except (OSError, ValueError) as why:
            log.warning("could not clear %s from the target: %s", path, why)
            continue
        if status != 0:
            log.warning("could not clear %s from the target: %s", path, said)
    for empty in emptied:
        try:
            client.rmdir(empty)
        except OSError:
            continue  # something is still in it, which is somebody's or another turn's


def _wrapping(hushes: Sequence[str], said: Mapping[str, str]) -> list[str]:
    """The `env` the CLI is started behind on the target, for what its environment cannot say.

    Two things have to be said on the target's own command line rather than in what is sent to
    it. A variable is *taken away* here, because the environment a command runs in there is
    composed there -- this machine's is layered onto the target's own, so a key in the target's
    shell profile survives merely not being sent. And a variable is *set* here where the target
    would strike it out on the way in: the ones that move a program's home are exactly the ones
    it reads as describing the wrong machine, and so are humanize's own, and both are things a
    turn taken here would have had.

    Every one of them is a name or a path rather than a secret. What the account actually is
    travels in the environment, which is not a command line.

    Args:
      hushes: The variables to run without.
      said: The variables to run with, by name.

    Returns:
      The words to put in front of the CLI. Always some: a turn always has at least what
      humanize marks it with to say, so there is no case worth a branch.
    """
    return [
        "env",
        *(word for name in sorted(hushes) for word in ("-u", name)),
        *(f"{name}={value}" for name, value in sorted(said.items())),
    ]


def _drives(
    client: RemoteClient, argv: list[str], cwd: str, environ: Mapping[str, str]
) -> int:
    """Runs the CLI on the target with this process's own streams, and waits for it.

    Byte for byte and without waiting for a line: the backends this exists for speak a framed
    protocol over these streams, and a relay that buffered would be a turn that never answers.

    Args:
      client: The open connection.
      argv: The CLI and its arguments, as the target is to run them.
      cwd: Where it works, as the target names it.
      environ: What to run it with, on top of the target's own.

    Returns:
      Its exit status, or 128 plus the signal that killed it.
    """
    import selectors
    import signal as signals
    import threading

    from hmz.coganchor.proto import CHUNK_SIZE, Stream

    done = threading.Event()
    held: dict[str, Any] = {}

    def on_output(stream: Stream, data: bytes) -> None:
        sink = sys.stderr if stream is Stream.STDERR else sys.stdout
        sink.buffer.write(data)
        sink.buffer.flush()

    def on_exit(result: dict[str, Any] | None, error: OSError | None) -> None:
        held["result"], held["error"] = result, error
        done.set()

    handle = client.start_exec(argv, cwd, dict(environ), on_output, on_exit)

    def upward() -> None:
        """Carries what this process is given to the CLI, and says when there is no more.

        Watched for rather than read into, so that the thread ends when the turn does: a read
        that simply blocked would still be holding this process's input after the call had
        returned, and the next thing to read it would find its first bytes gone.
        """
        try:
            with selectors.DefaultSelector() as watching:
                watching.register(_STDIN, selectors.EVENT_READ)
                while not done.is_set():
                    if not watching.select(timeout=_LOOKING):
                        continue
                    if not (data := os.read(_STDIN, CHUNK_SIZE)):
                        return  # end of input, which the turn is told below
                    handle.send_stdin(data)
        except (OSError, ValueError):
            pass  # stdin closed under us, which is the end of the input either way
        finally:
            # Suppressed for the same reason the read above is: the far end may already be
            # gone, and a thread that raised on the way out would print a traceback over a
            # turn that had finished perfectly well.
            with contextlib.suppress(OSError, ValueError):
                handle.close_stdin()

    reading = threading.Thread(target=upward, name="hmz-anchor-stdin", daemon=True)
    reading.start()

    def onward(number: int, _frame: object) -> None:
        """Sends the signal on to the CLI, and steps out of the way if it is sent twice."""
        # The first is aimed at the CLI rather than swallowed here: a turn stopped by hand has
        # to stop the thing that is running, and one that stops is one whose own exit status
        # says so. The second is aimed at this process, because a CLI that did not stop for
        # the first is one somebody is now pressing the key at -- and a relay that answered
        # every one of them by forwarding would be a relay nobody can get out of.
        signals.signal(number, before.get(number) or signals.SIG_DFL)
        handle.signal(number)

    # Only from the main thread, which is the only one a handler may be installed from -- and
    # is where this runs, this process having been spawned to be exactly this.
    catching = (signals.SIGINT, signals.SIGTERM)
    main = threading.current_thread() is threading.main_thread()
    before: dict[int, Any] = {}
    if main:
        # `getsignal` answers None for a handler that was not installed from Python, and
        # `signal` will not take None back -- so what is remembered is the default instead,
        # which is what restoring one of those has to come to anyway.
        before = {
            number: signals.getsignal(number) or signals.SIG_DFL for number in catching
        }
        for number in catching:
            signals.signal(number, onward)
    try:
        done.wait()
    finally:
        for number, was in before.items():
            signals.signal(number, was)
        reading.join(timeout=_LOOKING * 2)
    if (error := held.get("error")) is not None:
        raise error
    return _status(held.get("result"))

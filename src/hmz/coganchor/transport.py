"""Getting a :class:`~hmz.coganchor.proto.Channel` to ``serve`` on the target.

Four ways in:

``ssh://[user@]host[:port]``
    Ship a self-contained zipapp of coganchor to the host and run its ``serve``
    side over the ssh pipe.  Nothing needs to be installed there beyond
    Python 3.
``docker://container``
    The same, into a running container, over ``docker exec``.  A container is a
    machine like any other here; it needs no port, no secret and no cooperation
    beyond a ``python3``.
``tcp://host:port``
    Attach to an ``hmz anchor serve --listen`` someone already started.
``local[:REAL]``
    Run ``serve`` as a child process on this machine.  Used for development and
    by the test suite, where ``REAL`` is the directory standing in for the
    target's copy of the workspace.
"""

from __future__ import annotations

import hashlib
import logging
import os
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import zipapp
from dataclasses import dataclass
from pathlib import Path

from hmz import coganchor
from hmz.coganchor.proto import Channel

__all__ = ["Target", "Transport", "build_bundle", "connect", "python_command"]

log = logging.getLogger(__name__)

#: Where the bootstrapped copy is cached on the target machine.
REMOTE_CACHE = "~/.cache/humanize"

#: Where a target may keep a Python, in the order they are tried.  ``python3`` first, which
#: answers on every Linux and on a Mac somebody has set up; then the versioned names, which is
#: what a Homebrew or a python.org install answers to when the bare one was never linked; then
#: the paths those two install at, for a target whose ``PATH`` is the short one a non-login
#: shell gets.  ``/usr/bin/python3`` last: on macOS it is the Command Line Tools shim, which is
#: either an interpreter too old for this or a prompt to install Xcode, and on Linux it is the
#: one ``PATH`` has already found.
PYTHON_CANDIDATES = (
    "python3",
    "python3.14",
    "python3.13",
    "python3.12",
    "/opt/homebrew/bin/python3",
    "/usr/local/bin/python3",
    "/Library/Frameworks/Python.framework/Versions/Current/bin/python3",
    "/usr/bin/python3",
)

#: The oldest Python the bundle runs on, which is this project's own floor.
MINIMUM_PYTHON = (3, 12)

#: Installing that copy, for a target reached by piping it there. Written under a name of its
#: own and moved into place, so a session finds the whole archive or none of it, and a copy
#: already there is left where it is: it is named by its digest, so it is the same archive, and
#: rewriting it would be rewriting a file a live session may still be importing from.
_INSTALL = (
    "if [ ! -s {file} ]; then cat > {file}.part && mv {file}.part {file}; "
    "else cat > /dev/null; fi"
)

_SSH_OPTIONS = ("-T", "-o", "BatchMode=no", "-o", "ServerAliveInterval=30")

#: Finding one, in POSIX sh, because this runs on the target before anything of humanize
#: exists there.  Each candidate is *run* rather than merely looked for: macOS's
#: ``/usr/bin/python3`` is a shim that is there whether or not an interpreter is behind it,
#: and answers with a prompt to install Xcode when none is.  What it is asked is its version,
#: so a target whose only Python is older than the bundle needs is passed over here rather
#: than failing on a syntax error a frame later.  A target with none at all is told what was
#: looked for, since what to do about it is to install one of them.
_FIND_PYTHON = (
    "for py in {candidates}; do "
    'command -v "$py" >/dev/null 2>&1 || continue; '
    '"$py" -c "import sys; sys.exit(sys.version_info < {minimum})" >/dev/null 2>&1 '
    "|| continue; "
    'exec "$py" "$@"; '
    "done; "
    'echo "humanize: no python {version} or newer on this machine; '
    'looked for: {candidates}" >&2; '
    "exit 127"
)


def python_command(args: list[str]) -> list[str]:
    """The command that runs ``args`` under the target's Python, wherever it keeps one.

    Argv, so that a path holding a space or a quote reaches the target as it is.  Called with
    nothing it is the part that does the finding, which is what whoever has to hand a target
    one string instead -- ``ssh`` does -- quotes before writing its own arguments after it.
    """
    script = _FIND_PYTHON.format(
        candidates=" ".join(PYTHON_CANDIDATES),
        minimum=f"({MINIMUM_PYTHON[0]}, {MINIMUM_PYTHON[1]})",
        version=".".join(str(part) for part in MINIMUM_PYTHON),
    )
    # ``/bin/sh`` by its path rather than its name, since the ``PATH`` this is reaching past
    # is the same one that would have to hold a shell.  ``$0`` is what sh prefixes its own
    # complaints with, so it is named for whose command this is.
    return ["/bin/sh", "-c", script, "humanize", *args]


@dataclass(frozen=True, slots=True)
class Target:
    """Where the target is."""

    scheme: str
    host: str = ""
    port: int = 0
    path: str = ""

    @classmethod
    def parse(cls, spec: str) -> Target:
        if spec == "local" or spec.startswith("local:"):
            _, _, path = spec.partition(":")
            return cls("local", path=path)
        if spec.startswith("ssh://"):
            authority = spec[len("ssh://") :]
            host, _, port = authority.rpartition(":")
            if host and port.isdigit():
                return cls("ssh", host=host, port=int(port))
            return cls("ssh", host=authority)
        if spec.startswith("docker://") and (container := spec[len("docker://") :]):
            return cls("docker", host=container)
        if spec.startswith("tcp://"):
            host, _, port = spec[len("tcp://") :].rpartition(":")
            if not host or not port.isdigit():
                raise ValueError(f"malformed target {spec!r}; expected tcp://HOST:PORT")
            return cls("tcp", host=host, port=int(port))
        raise ValueError(
            f"unsupported target {spec!r}; expected ssh://HOST, docker://CONTAINER, "
            "tcp://HOST:PORT or local[:PATH]"
        )

    def describe(self) -> str:
        if self.scheme == "ssh":
            return f"ssh://{self.host}" + (f":{self.port}" if self.port else "")
        if self.scheme == "docker":
            return f"docker://{self.host}"
        if self.scheme == "tcp":
            return f"tcp://{self.host}:{self.port}"
        return f"local{':' + self.path if self.path else ''}"


@dataclass(slots=True)
class Transport:
    """An open channel plus whatever process is keeping it alive."""

    channel: Channel
    process: subprocess.Popen[bytes] | None = None

    def close(self) -> None:
        self.channel.close()
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                # Reaped rather than left: a run that opens an anchor per agent would
                # otherwise gather a zombie for each one that would not go quietly.
                self.process.wait()


def connect(target: Target, exports: list[str], token: str | None = None) -> Transport:
    """Open a channel to the ``serve`` side described by ``target``."""
    if target.scheme == "tcp":
        return _connect_tcp(target)
    if target.scheme == "ssh":
        return _connect_ssh(target, exports, token)
    if target.scheme == "docker":
        return _connect_docker(target, exports)
    return _connect_local(target, exports, token)


def _connect_tcp(target: Target) -> Transport:
    sock = socket.create_connection((target.host, target.port), timeout=30.0)
    sock.settimeout(None)
    return Transport(Channel.from_socket(sock))


def _connect_local(target: Target, exports: list[str], token: str | None) -> Transport:  # noqa: ARG001
    command = [
        sys.executable,
        "-m",
        "hmz",
        "anchor",
        "serve",
        "--stdio",
        *_export_args(exports),
    ]
    return _spawn(command, token)


def _connect_ssh(target: Target, exports: list[str], token: str | None) -> Transport:
    payload = build_bundle().read_bytes()
    digest = hashlib.sha256(payload).hexdigest()[:16]
    remote_file = f"{REMOTE_CACHE}/humanize-{digest}.pyz"
    ssh = [
        "ssh",
        *_SSH_OPTIONS,
        *(["-p", str(target.port)] if target.port else []),
        target.host,
    ]

    upload = f"mkdir -p {REMOTE_CACHE} && " + _INSTALL.format(file=remote_file)
    result = subprocess.run(
        [*ssh, upload], input=payload, capture_output=True, check=False
    )
    if result.returncode != 0:
        raise ConnectionError(
            f"could not install humanize on {target.host}: "
            f"{result.stderr.decode(errors='replace').strip()}"
        )

    return _spawn([*ssh, _ssh_serve_line(remote_file, exports)], token)


def _connect_docker(target: Target, exports: list[str]) -> Transport:
    """Serve from inside a running container, over ``docker exec``.

    The bundle is pushed the way ``ssh://`` pushes it, into the container's ``/tmp`` rather than
    a home directory it may not have.  The exec inherits the container's own user and working
    directory, so a container is served as whoever it runs as.
    """
    payload = build_bundle().read_bytes()
    digest = hashlib.sha256(payload).hexdigest()[:16]
    # Inside the container rather than on this host, and named after what it holds, so two
    # pushes of the same bundle land on the same file instead of racing for one name.
    remote_file = f"/tmp/humanize-{digest}.pyz"  # noqa: S108
    exec_in = ["docker", "exec", "-i", target.host]

    result = subprocess.run(
        [*exec_in, "sh", "-c", _INSTALL.format(file=remote_file)],
        input=payload,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise ConnectionError(
            f"could not install humanize in {target.host}: "
            f"{result.stderr.decode(errors='replace').strip()}"
            f"{_docker_said(target.host)}"
        )

    # Unquoted, unlike ssh: docker is handed the command as argv and passes it on, so an export
    # holding a space or a quote needs nothing done to it to survive the trip.
    serve = [remote_file, "anchor", "serve", "--stdio", *_export_args(exports)]
    return _spawn([*exec_in, *python_command(serve)], None)


def _docker_said(container: str) -> str:
    """The tail of what the container printed, for an error that does not say enough.

    A container whose own process could not start is one docker then reports as merely not
    running; why it could not -- that there is no Python it can use, and where it was looked
    for -- was said on the way out and is in the log and nowhere else.
    """
    said = subprocess.run(
        ["docker", "logs", "--tail", "3", container], capture_output=True, check=False
    )
    if said.returncode != 0:
        # There is no container to have said anything, or no daemon to ask -- which is what
        # the error being written already says, and saying it twice says less.
        return ""
    # Both streams: what a container printed on its way out is on the one it chose.
    tail = (said.stdout + said.stderr).decode(errors="replace").strip()
    return f"; the container said: {tail}" if tail else ""


def _ssh_serve_line(remote_file: str, exports: list[str]) -> str:
    """The one string ssh carries, read by the login shell on the far side before it runs.

    Three things have to survive that reading.  The line that finds the interpreter is a
    shell script and is quoted whole, so the login shell hands it on rather than acts on it.
    The cache path is left bare, because the ``~`` in it is that shell's to expand -- quoted,
    it names a directory called ``~`` under wherever the session began -- which is the same
    expansion the upload was written against.  And an export is quoted as it is built, since
    a workspace path may hold a space.
    """
    return " ".join(
        [
            "exec",
            *(shlex.quote(word) for word in python_command([])),
            remote_file,
            "anchor",
            "serve",
            "--stdio",
            *_export_args(exports, quote=True),
        ]
    )


def _spawn(command: list[str], token: str | None) -> Transport:
    """Start a child that serves over its own stdin and stdout.

    The token travels in the environment the child inherits, which works for
    ``local``.  For ``ssh`` and ``docker`` the child is the client rather than
    the target and neither forwards the environment, so those sessions are
    authenticated by ssh and by the docker socket themselves and the token goes
    unused.
    """
    log.debug("starting the target: %s", " ".join(command))
    env = dict(os.environ)
    if token:
        env["HUMANIZE_TOKEN"] = token
    process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=None,
        env=env,
        close_fds=True,
    )
    assert process.stdin is not None  # noqa: S101
    assert process.stdout is not None  # noqa: S101
    return Transport(Channel(process.stdout, process.stdin), process)


def _export_args(exports: list[str], *, quote: bool = False) -> list[str]:
    """Build ``--export`` arguments, quoting them for a remote shell if needed.

    The ssh transport hands its command to the target's shell as one string, so
    a workspace path containing a quote or a space has to survive that; the
    local and docker transports pass argv straight through and must not be
    quoted.
    """
    args: list[str] = []
    for export in exports:
        args += ["--export", shlex.quote(export) if quote else export]
    return args


#: What the target has no use for, left out of the bundle by name. This package is two
#: things: the anchor -- the wire, the supervisor and the serving half, which is what a
#: target runs -- and everything humanize knows about driving a coding agent CLI, which a
#: target never does. The anchor half ships whole, ptrace layer and register maps included,
#: because pruning *that* would be a list to keep in step and nothing is lost by carrying
#: it: the target only ever runs ``anchor serve``, which reaches none of it. The driving
#: half is a different answer -- it is megabytes of drivers, it reaches the network to read
#: prices and catalogues, and no line the target runs can arrive at it. It is named here
#: rather than inferred, and ``test_the_bundle_carries_nothing_that_drives_an_agent`` is
#: what notices a new one.
DRIVING = ("agents", "providers", "machines", "backends.py", "models.py", "fallbacks.py",
           "prices.py")  # fmt: skip


def build_bundle(destination: Path | None = None) -> Path:
    """Package the anchor, and the command line reaching it, as a zipapp for the target.

    The anchor half of this package ships whole -- see :data:`DRIVING` for what does not and
    why.  Nothing is lost by carrying the tracer with it: the target only ever runs ``anchor
    serve``, which :func:`hmz.cli.main` reaches without importing the modules that need
    ptrace or an x86-64 register map -- nor any other subpackage, none of which is here -- so
    the bundle runs on a target of any architecture.  It is pure stdlib, so a host needs
    nothing but ``python3``.
    """
    if destination is None:
        destination = Path(tempfile.gettempdir()) / f"humanize-{os.getuid()}.pyz"
    with tempfile.TemporaryDirectory(prefix="humanize-bundle-") as staging:
        root = Path(staging)
        # Laid out under the package's own dotted name, so that moving the package moves the
        # bundle with it rather than breaking on the target, which is where it would surface.
        parts = coganchor.__name__.split(".")
        shutil.copytree(
            Path(coganchor.__file__).parent,
            root.joinpath(*parts),
            ignore=shutil.ignore_patterns("__pycache__", "*.md", *DRIVING),
        )
        for depth in range(1, len(parts)):
            # A namespace of its own rather than the installed ``hmz/__init__.py``: the
            # bundle stays pure stdlib however the rest of humanize grows, and a regular package
            # cannot be shadowed by an unrelated ``hmz`` already on the target's path.
            init = root.joinpath(*parts[:depth]) / "__init__.py"
            init.write_text(
                f'"""{".".join(parts[:depth])}, cut down to {parts[depth]}."""\n'
            )
        # The command line comes too, because it is the only one: what the target runs is the
        # same ``hmz anchor`` a user would run there, and each of its commands names the layers
        # it needs only from inside itself, none of which is this one.
        # Taken off disk rather than imported, so that the serving half still names nothing
        # above itself.
        package = Path(coganchor.__file__).parent.parent
        shutil.copytree(
            package / "cli",
            root.joinpath(*parts[:-1]) / "cli",
            ignore=shutil.ignore_patterns("__pycache__", "*.md"),
        )
        # Written by hand rather than via zipapp's ``main=`` shim, which calls
        # the entry point but throws its return value away -- a target that
        # failed to start would then look like a clean exit.
        (root / "__main__.py").write_text(
            "from hmz.cli import main\n\nraise SystemExit(main())\n"
        )
        # One timestamp for everything, so the archive is a function of the source alone: the
        # bundle is addressed on the target by its digest, and a build stamp would miss that
        # cache on every connect and leave another copy behind. A zip entry holds local
        # wall-clock time and cannot predate 1980, so the instant is the one reading as
        # 1980-01-02 here: a fixed instant would fall out of that range west of UTC, and would
        # still leave the digest following the machine's timezone.
        stamp = time.mktime((1980, 1, 2, 0, 0, 0, 0, 2, -1))
        for path in root.rglob("*"):
            # Modes for the same reason: the files written just above carry the builder's
            # umask, and a checkout's own bits vary with it too. Nothing on the target reads
            # them -- it runs the archive, and zipimport ignores the entries' modes.
            path.chmod(0o755 if path.is_dir() else 0o644)
            os.utime(path, (stamp, stamp))
        # Published by rename rather than written where it is read: two sessions starting at
        # once build the same bytes to the same path, and a reader must find the whole archive
        # or the last one, never a half-written file it would then ship to a target.
        handle, staged = tempfile.mkstemp(
            dir=destination.parent, prefix=f"{destination.name}."
        )
        os.close(handle)
        try:
            zipapp.create_archive(
                root, Path(staged), interpreter="/usr/bin/env python3"
            )
            os.replace(staged, destination)
        except BaseException:
            os.unlink(staged)  # a build that failed leaves nothing of itself behind
            raise
    return destination

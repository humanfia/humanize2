"""Getting a :class:`~amflows.coganchor.proto.Channel` to ``serve`` on the target.

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
    Attach to a ``coganchor serve --listen`` someone already started.
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

from amflows import coganchor
from amflows.coganchor.proto import Channel

__all__ = ["Target", "Transport", "build_bundle", "connect"]

log = logging.getLogger(__name__)

#: Where the bootstrapped copy is cached on the target machine.
REMOTE_CACHE = "~/.cache/coganchor"

#: Installing that copy, for a target reached by piping it there. Written under a name of its
#: own and moved into place, so a session finds the whole archive or none of it, and a copy
#: already there is left where it is: it is named by its digest, so it is the same archive, and
#: rewriting it would be rewriting a file a live session may still be importing from.
_INSTALL = (
    "if [ ! -s {file} ]; then cat > {file}.part && mv {file}.part {file}; "
    "else cat > /dev/null; fi"
)

_SSH_OPTIONS = ("-T", "-o", "BatchMode=no", "-o", "ServerAliveInterval=30")


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


def _connect_local(target: Target, exports: list[str], token: str | None) -> Transport:
    command = [
        sys.executable,
        "-m",
        coganchor.__name__,
        "serve",
        "--stdio",
        *_export_args(exports),
    ]
    return _spawn(command, token)


def _connect_ssh(target: Target, exports: list[str], token: str | None) -> Transport:
    payload = build_bundle().read_bytes()
    digest = hashlib.sha256(payload).hexdigest()[:16]
    remote_file = f"{REMOTE_CACHE}/coganchor-{digest}.pyz"
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
            f"could not install coganchor on {target.host}: "
            f"{result.stderr.decode(errors='replace').strip()}"
        )

    remote_command = " ".join(
        [
            "exec",
            "python3",
            remote_file,
            "serve",
            "--stdio",
            *_export_args(exports, quote=True),
        ]
    )
    return _spawn([*ssh, remote_command], token)


def _connect_docker(target: Target, exports: list[str]) -> Transport:
    """Serve from inside a running container, over ``docker exec``.

    The bundle is pushed the way ``ssh://`` pushes it, into the container's ``/tmp`` rather than
    a home directory it may not have.  The exec inherits the container's own user and working
    directory, so a container is served as whoever it runs as.
    """
    payload = build_bundle().read_bytes()
    digest = hashlib.sha256(payload).hexdigest()[:16]
    remote_file = f"/tmp/coganchor-{digest}.pyz"
    exec_in = ["docker", "exec", "-i", target.host]

    result = subprocess.run(
        [*exec_in, "sh", "-c", _INSTALL.format(file=remote_file)],
        input=payload,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise ConnectionError(
            f"could not install coganchor in {target.host}: "
            f"{result.stderr.decode(errors='replace').strip()}"
        )

    # Unquoted, unlike ssh: docker is handed the command as argv and passes it on, so an export
    # holding a space or a quote needs nothing done to it to survive the trip.
    command = [
        *exec_in,
        "python3",
        remote_file,
        "serve",
        "--stdio",
        *_export_args(exports),
    ]
    return _spawn(command, None)


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
        env["COGANCHOR_TOKEN"] = token
    process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=None,
        env=env,
        close_fds=True,
    )
    assert process.stdin is not None and process.stdout is not None
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


def build_bundle(destination: Path | None = None) -> Path:
    """Package coganchor as a runnable zipapp for the target.

    The whole package ships, tracer half included, because pruning it would be
    a list to keep in step with the source tree.  Nothing is lost by that: the
    target only ever runs ``serve``, which :func:`amflows.coganchor.cli.main`
    reaches without importing the modules that need ptrace or an x86-64 register
    map, so the bundle runs on a target of any architecture.  It is pure stdlib,
    so a host needs nothing but ``python3``.
    """
    if destination is None:
        destination = Path(tempfile.gettempdir()) / f"coganchor-{os.getuid()}.pyz"
    with tempfile.TemporaryDirectory(prefix="coganchor-bundle-") as staging:
        root = Path(staging)
        # Laid out under the package's own dotted name, so that moving the package moves the
        # bundle with it rather than breaking on the target, which is where it would surface.
        parts = coganchor.__name__.split(".")
        shutil.copytree(
            Path(coganchor.__file__).parent,
            root.joinpath(*parts),
            ignore=shutil.ignore_patterns("__pycache__", "*.md"),
        )
        for depth in range(1, len(parts)):
            # A namespace of its own rather than the installed ``amflows/__init__.py``: the
            # bundle stays pure stdlib however the rest of amflows grows, and a regular package
            # cannot be shadowed by an unrelated ``amflows`` already on the target's path.
            init = root.joinpath(*parts[:depth]) / "__init__.py"
            init.write_text(
                f'"""{".".join(parts[:depth])}, cut down to {parts[depth]}."""\n'
            )
        # Written by hand rather than via zipapp's ``main=`` shim, which calls
        # the entry point but throws its return value away -- a target that
        # failed to start would then look like a clean exit.
        (root / "__main__.py").write_text(
            f"from {coganchor.__name__}.cli import main\n\nraise SystemExit(main())\n"
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

"""Where one workspace's daemon keeps its socket, and what is written down beside it.

One daemon per workspace, under humanize's own home: a directory named for the project it is
holding, with the socket terminals reach it through and a note of what is running there. The
note is what tells a daemon that is running from one whose machine went down without it -- a
socket file outlives the process that bound it, and a stale one is a terminal that hangs.
"""

from __future__ import annotations

import contextlib
import errno
import hashlib
import json
import os
import re
import traceback
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from hmz import home

if TYPE_CHECKING:
    from collections.abc import Generator

__all__ = [
    "LOCK",
    "LOG",
    "RECORD",
    "SOCKET",
    "alive",
    "at",
    "held",
    "holds",
    "reached",
    "under",
    "wrote",
]

#: The socket a terminal reaches a run through, inside that run's own directory.
SOCKET = "daemon.sock"

#: What is written down about the daemon there: which process, which workspace, since when.
RECORD = "daemon.json"

#: Where whatever the daemon itself could not say through a terminal goes -- a crash before
#: the interface was up, after the last terminal let go, or a directory that went away under
#: whoever was reaching for the socket.
LOG = "daemon.log"

#: What the one daemon of a workspace holds for as long as it is running. A lock rather than
#: a file that is looked at: the kernel drops it when the process goes, however it goes, so
#: there is no such thing as one left behind by a machine that was turned off.
LOCK = "daemon.lock"

#: What a directory may be called after: everything else in a path is flattened, the way a
#: cycle flattens the workspace it was run in.
_PLAIN = re.compile(r"[^A-Za-z0-9]+")

#: How much of the workspace's own name is kept in front of the digest of the whole path. A
#: directory of these is read by people, and `humanize2-a1b2c3d4e5f6` says which project.
_KEPT = 24

#: The longest a socket may be reached by its whole path. What a Unix socket address holds is
#: about a hundred bytes -- 108 on Linux, 104 on macOS -- and the shorter of the two is what
#: is measured against, so that a humanize which works here works there. A path longer than
#: this is reached by standing in its directory and naming the socket alone.
_LONGEST = 100


def under() -> Path:
    """Where every workspace's daemon is kept, which is one directory under humanize's home."""
    return home() / "daemons"


def at(workspace: str | os.PathLike[str] | None = None) -> Path:
    """The directory one workspace's daemon keeps its socket in.

    Args:
      workspace: The project directory, or None for wherever humanize is being run.

    Returns:
      The directory. It is not made here: it is made by the daemon that binds the socket.

    Note:
      Named for the project and then for the whole path it is at, since two checkouts of one
      repository are two workspaces and would otherwise be one daemon.
    """
    where = Path(workspace or Path.cwd()).resolve()
    named = _PLAIN.sub("-", where.name).strip("-")[:_KEPT] or "workspace"
    digest = hashlib.sha256(str(where).encode()).hexdigest()[:12]
    return under() / f"{named}-{digest}"


@contextlib.contextmanager
def reached(where: Path) -> Generator[str]:
    """The socket in one daemon's directory, spelled short enough to be a socket address.

    A Unix socket is reached by a path of about a hundred bytes, whole, and a project under a
    deep home directory is longer than that. Standing in the directory and naming the socket
    alone is what makes the name short enough, and is what every program that meets this does.

    Args:
      where: The daemon's own directory.

    Yields:
      The socket, as it is to be bound or connected -- the whole path where that fits, and
      the name alone where it does not.

    Note:
      Where it does not fit, this changes the directory of the whole process for as long as
      the socket is being reached. It is done where a process has one thread -- opening the
      interface, and answering a line about a run -- and never while a flow is running, which
      is a flow that may be standing somewhere of its own.

      Where the directory it set out from has gone by the time it is over, that is written
      down beside the socket rather than raised. This is a `finally`: raising here would put
      a directory that went away in place of whatever the socket itself had to say, and every
      caller reads an `OSError` from this as the socket being unreachable -- which would turn
      a daemon that bound perfectly well into one that never came up. What must not happen is
      the quiet version, a run left standing somewhere it was never asked to run and no line
      anywhere saying so.
    """
    whole = where / SOCKET
    if len(str(whole).encode()) <= _LONGEST:
        yield str(whole)
        return
    was = Path.cwd()
    try:
        # The move is under the same `try` as what undoes it, so that a signal arriving in
        # the breath between the two cannot be the thing that leaves the process here. The
        # cost is putting a process back where it already is when the move itself failed,
        # which is one syscall and never wrong.
        os.chdir(where)
        yield SOCKET
    finally:
        try:
            os.chdir(was)
        except OSError:
            _logged(where, f"a run reaching for its socket could not go back to {was}")


def _logged(where: Path, about: str) -> None:
    """Writes down beside the socket what there was no terminal to say.

    The daemon's own log, written here rather than through :func:`hmz.daemon.serve.logged`:
    every other module of this package reaches for this one, so this one reaches for none of
    them.

    Args:
      where: The daemon's own directory.
      about: What was being done, since whatever is being handled is what raised.
    """
    with (
        contextlib.suppress(OSError),
        (where / LOG).open("a", encoding="utf-8") as writing,
    ):
        writing.write(f"{about}\n{traceback.format_exc()}\n")


def holds(where: Path) -> int:
    """Takes the one daemon of this workspace, for as long as this process lives.

    One daemon per workspace: two runs of one project in one directory are two flows writing
    over each other's cycle. A lock rather than a file somebody looks at, because looking is
    what leaves a window between the look and the socket -- two `hmz` started in the same
    second would both find nothing and both bind.

    Args:
      where: The daemon's own directory, which must already be there.

    Returns:
      The descriptor holding it, which is to be kept open for as long as the daemon runs and
      is dropped by the kernel however the process ends.

    Raises:
      OSError: If another process is already holding it, or the file cannot be made.
    """
    import fcntl

    taking = os.open(str(where / LOCK), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(taking, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(taking)
        raise
    return taking


def wrote(where: Path, said: dict[str, Any]) -> None:
    """Writes down what is running here, whole and then moved into place.

    Args:
      where: The daemon's own directory.
      said: What to write.
    """
    beside = where / f".{RECORD}.new"
    beside.write_text(json.dumps(said, indent=2) + "\n", encoding="utf-8")
    beside.replace(where / RECORD)


def held(where: Path) -> dict[str, Any]:
    """What is written down about the daemon there, and nothing at all where nothing is.

    Args:
      where: The daemon's own directory.

    Returns:
      What it says about itself, or an empty mapping for a directory holding no daemon, one
      whose note cannot be read, and one whose process is no longer there.
    """
    try:
        said: object = json.loads((where / RECORD).read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return {}
    if not isinstance(said, dict):
        return {}
    held = cast("dict[str, Any]", said)
    pid = held.get("pid")
    if not isinstance(pid, int) or not alive(pid):
        return {}
    return held


def alive(pid: int) -> bool:
    """Whether a process of that number is still there.

    Args:
      pid: The process.

    Returns:
      Whether it exists. A process somebody else owns still counts as running: this asks
      whether the daemon is there, not whether it could be signalled.
    """
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError as why:
        return why.errno == errno.EPERM
    return True

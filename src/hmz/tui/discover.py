"""Which agents are installed here, what each one runs, and where their turns could land.

Installed backends are found here, and optional backends somebody can add are named separately
so the picker can teach them how. An effort a model does not take is not offered against it.
What each backend runs is what that backend last said it runs, which :mod:`hmz.models` keeps --
read off the disk here, because asking means starting a coding agent and a prompt cannot wait
on one.

Nothing is asked of the backends either. Measured on the machine this was written on,
`claude --help` took over thirty seconds, `codex app-server` seventy-six, and `kimi web` about
a minute. So a catalogue is filled where there is time for it -- when an account is made, and
on the key that says to ask again -- and read here.
"""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from hmz import models
from hmz.backends import PROFILES

if TYPE_CHECKING:
    from hmz.backends import Model

__all__ = ["installable", "installed", "machines"]

#: How long the machines around here are given to name themselves before the list goes up
#: without them. A docker daemon that is not answering is not a reason to sit at a sheet.
_LOOKING_SECONDS = 2.0


def installed() -> dict[str, tuple[Model, ...]]:
    """The backends on this machine, and what each last said it runs.

    Costs a `which` apiece and one file read, so it can be asked for at a prompt.

    Returns:
      One entry per backend that is on this machine, as the models it last said it runs for
      the account nobody chose. Empty for one that has never been asked, which is a catalogue
      to fill rather than a backend with nothing in it.
    """
    return {
        profile.name: models.offered(profile.name)
        for profile in PROFILES
        if _is_installed(profile.name)
    }


def installable() -> dict[str, tuple[Model, ...]]:
    """Optional backends that can be added to this humanize installation.

    These are kept apart from :func:`installed`: they belong in the agent picker so that
    somebody can discover and install them, but they must not make an unopened prompt look
    ready to run or be asked for models in the background.

    Returns:
      One entry per supported optional backend missing from this Python environment, with
      the models it will offer once installed.
    """
    return {"dsh": models.offered("dsh")} if not _is_installed("dsh") else {}


def _is_installed(backend: str) -> bool:
    """Whether a backend's executable or Python SDK is installed here."""
    if backend == "dsh":
        return importlib.util.find_spec("deepseek_harness") is not None
    return shutil.which(backend) is not None


def machines() -> list[tuple[str, str]]:
    """Where an agent's turns could land, besides this machine.

    Found rather than typed, for the same reason the models are: a container that is not
    running and a host with no entry in your ssh config are not places work can go, and a
    list of what is actually there is shorter than the one you would have to remember. What
    is not found is still typed -- a target is a string, and any string that reads as one is
    taken.

    Returns:
      One `(target, where it came from)` pair apiece, containers first and then hosts, in the
      order each source gave them. Empty where there is no docker and no ssh config, which is
      a machine that only runs its own turns.
    """
    found: list[tuple[str, str]] = [
        (f"docker://{named}", "container") for named in _containers()
    ]
    found.extend((f"ssh://{host}", "ssh config") for host in _hosts())
    return found


def _containers() -> list[str]:
    """The containers running here, which are the ones a turn could be run in."""
    try:
        listed = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            timeout=_LOOKING_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []  # no docker here, or none that answered: no containers to offer
    return [named for named in listed.stdout.split() if named]


def _hosts() -> list[str]:
    """The hosts named in this user's ssh config, in the order they are written there.

    A pattern is not a host: `Host *` is what the settings under it apply to rather than
    somewhere to send a turn, and choosing it would send one nowhere.
    """
    named: list[str] = []
    try:
        written = (Path.home() / ".ssh" / "config").read_text(encoding="utf-8")
    except OSError:
        return []
    for line in written.splitlines():
        said = line.strip()
        if said.lower().startswith("host ") and not said.startswith("#"):
            named.extend(
                host
                for host in said.split()[1:]
                if not set(host) & set("*?!") and host not in named
            )
    return named

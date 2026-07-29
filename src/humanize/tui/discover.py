"""Which agents are installed here, what each one runs, and where their turns could land.

Nothing is typed in: a backend that is not on this machine is not offered, and an effort a
model does not take is not offered against it. What each backend runs is written down in
:mod:`humanize.backends`, which is where every other reader of it looks too.

Nothing is asked of the backends either. Asking means starting one, and starting one costs
what it costs -- measured on the machine this was written on, `claude --help` took over
thirty seconds, `codex app-server` seventy-six, and `kimi web` about a minute. A prompt
cannot wait on that. Claude's own cache is read as well, because which models an account may
run is the one part of this that is not the same for everyone.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from humanize.backends import PROFILES, Model

if TYPE_CHECKING:
    from humanize.backends import Profile

__all__ = ["installed", "machines"]

#: How long the machines around here are given to name themselves before the list goes up
#: without them. A docker daemon that is not answering is not a reason to sit at a sheet.
_LOOKING_SECONDS = 2.0

#: Where Claude Code keeps the models this account may run.
_CLAUDE_CACHE = Path.home() / ".claude.json"

#: What a context window is written as on the end of a model Claude Code offers. It is a way
#: of running the model rather than a model, and a backend asked for one answers that there is
#: no such model.
_WINDOW = re.compile(r"\[[^\]]*\]$")


def installed() -> dict[str, tuple[Model, ...]]:
    """The backends on this machine, and what each runs.

    Costs a `which` apiece and one file read, so it can be asked for at a prompt.

    Returns:
      One entry per backend that is on this machine, as its models.
    """
    return {
        profile.name: _claude(profile) if profile.name == "claude" else profile.models
        for profile in PROFILES
        if shutil.which(profile.name) is not None
    }


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


def _claude(profile: Profile) -> tuple[Model, ...]:
    """Claude's models: the ones it documents, plus the ones this account may run.

    Args:
      profile: Claude's own, whose models are the documented ones.

    Returns:
      Every model this account can name, newest first among the ones written down there and
      the rest after them, each at every effort Claude documents.
    """
    known = [model.name for model in profile.models]
    # Every model Claude runs takes the same efforts, so an account's own are offered at the
    # ones the documented models are.
    efforts = profile.models[0].efforts
    try:
        held: Any = json.loads(_CLAUDE_CACHE.read_text())
    except (OSError, ValueError):
        held = {}
    # `claude-fable-5[1m]` is that model at its largest window, which is a setting and not a
    # model: the id is what the backend answers to, and the window rides along with it.
    account = sorted(
        {
            _WINDOW.sub("", str(cast("dict[str, Any]", option)["value"]))
            for option in cast(
                "list[Any]", held.get("additionalModelOptionsCache") or []
            )
            if isinstance(option, dict) and cast("dict[str, Any]", option).get("value")
        }
    )
    named = known + [name for name in account if name not in known]
    return tuple(Model(name, efforts) for name in named)

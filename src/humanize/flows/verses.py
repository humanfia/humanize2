"""Where flows come from, when they come from somewhere else.

A flowverse is a git repository of flows: `.py` files, one flow apiece or several where a file
says so, and whatever they import beside them under names that start with an underscore. It is
cloned into `~/.humanize/flowverses/<name>/`, and every flow in it is offered under that name.

Two are always there. `builtin` is the handful humanize itself ships -- one agent talking, and
the two shapes a loop over one agent takes -- and cannot be added or taken away because it is
not fetched from anywhere. `official` is humanize's own repository of the rest, and is there
whether or not it has been fetched yet: a list that only mentioned it once somebody had thought
to add it would be a list that hid what there is.

Nothing here runs a flow, and nothing here reads one. It is the answer to "which flows are
there, and where did each come from" -- and to the three things that can happen to a flowverse:
added, fetched again, taken away.
"""

from __future__ import annotations

import configparser
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from humanize import home

__all__ = [
    "BUILTIN",
    "OFFICIAL",
    "Flowverse",
    "add",
    "fetch",
    "flowverses",
    "remove",
    "under",
]

#: What the flows humanize itself ships are listed under. Not a repository and not fetched
#: from anywhere: they are in the package, and a name here means one file in it.
BUILTIN = "builtin"

#: What humanize's own repository of flows is called, and where it is. Always listed, whether
#: or not it has been fetched: what there is to run is not the same question as what has been
#: downloaded, and somebody who has never fetched it should still be able to see it and say so.
OFFICIAL = "official"
OFFICIAL_URL = "https://github.com/humanfia/flowverse"

#: What a flowverse may be called: one directory name, and one that cannot climb out of the
#: directory they are kept in.
_NAMED = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")

#: How long a fetch is given before it is called off. A clone of a repository of text files is
#: seconds; a minute is the difference between slow and not answering.
_PATIENCE = 60.0


@dataclass(frozen=True, slots=True)
class Flowverse:
    """One place flows come from.

    Attributes:
      name: What it is called, which is the directory it is kept in and the name its flows are
        offered under.
      url: Where it is fetched from, or "" for one that is not fetched from anywhere -- which
        is `builtin`, and is what makes it the one nobody can take away.
      at: The directory its flows are read from.
      fetched: Whether it is there to be read. False for one named but never fetched, which
        `official` is until somebody asks for it.
      fixed: Whether it is always listed and cannot be removed: humanize's own two.
    """

    name: str
    url: str
    at: Path
    fetched: bool
    fixed: bool


def under() -> Path:
    """Where every fetched flowverse is kept, which is one directory under humanize's home."""
    return home() / "flowverses"


def where(name: str) -> Path:
    """The directory one flowverse is kept in.

    Args:
      name: What it is called.

    Returns:
      The path, whether or not anything has been fetched into it.

    Raises:
      ValueError: If the name is not one a flowverse may have -- a name is a directory, and
        one that climbs out of this one is not a name.
    """
    if not _NAMED.match(name):
        raise ValueError(
            f"{name!r} is not a flowverse name: letters, digits, dot, dash and underscore, "
            "starting with a letter or a digit"
        )
    return under() / name


def flowverses() -> list[Flowverse]:
    """Every place flows come from, in the order they are offered.

    Returns:
      humanize's own two first -- the flows it ships, then its own repository of the rest --
      and then whatever else has been added, alphabetically. Both of the first two are always
      here: one is not fetched from anywhere, and the other is what there is to fetch.
    """
    from . import BUILTIN_AT

    held = [
        Flowverse(name=BUILTIN, url="", at=BUILTIN_AT, fetched=True, fixed=True),
        Flowverse(
            name=OFFICIAL,
            url=OFFICIAL_URL,
            at=where(OFFICIAL),
            fetched=_cloned(where(OFFICIAL)),
            fixed=True,
        ),
    ]
    for at in sorted(_directories(under())):
        if at.name in (BUILTIN, OFFICIAL) or not _NAMED.match(at.name):
            continue
        held.append(
            Flowverse(
                name=at.name,
                url=_url(at),
                at=at,
                fetched=_cloned(at),
                fixed=False,
            )
        )
    return held


def named(name: str) -> Flowverse | None:
    """The flowverse called this, or None for a name none answers to."""
    return next((one for one in flowverses() if one.name == name), None)


def add(url: str, name: str = "") -> Flowverse:
    """Fetches a flowverse, and answers with what was fetched.

    Args:
      url: Where it is, as git takes it: a URL, or `owner/repo` for one on GitHub.
      name: What to call it, defaulting to the repository's own name. It is the directory it
        is kept in and the name its flows are offered under.

    Returns:
      The flowverse, fetched.

    Raises:
      ValueError: If the name is not one a flowverse may have, or one is already called that.
      OSError: If git is not there, or the fetch failed. What git said is attached.
    """
    said = url.strip()
    if not said:
        raise ValueError("no repository to fetch a flowverse from")
    called = name or _called(said)
    at = where(called)
    if at.exists():
        raise ValueError(f"there is already a flowverse called {called!r}")
    at.parent.mkdir(parents=True, exist_ok=True)
    _git("clone", "--depth", "1", _url_of(said), str(at))
    return Flowverse(
        name=called, url=_url(at), at=at, fetched=_cloned(at), fixed=called == OFFICIAL
    )


def fetch(name: str) -> Flowverse:
    """Fetches a flowverse again, or for the first time.

    The first time is what `official` is usually having done to it: it is listed from the
    start and fetched when somebody wants what is in it.

    Args:
      name: What it is called.

    Returns:
      The flowverse, as it is now.

    Raises:
      ValueError: If there is no such flowverse, or it is one that is not fetched from
        anywhere -- the flows humanize ships are in the package, and there is nowhere to
        fetch them from.
      OSError: If git is not there, or the fetch failed. What git said is attached.
    """
    one = named(name)
    if one is None:
        raise ValueError(f"no flowverse called {name!r}")
    if not one.url:
        raise ValueError(
            f"{name} is the flows humanize came with; there is nothing to fetch"
        )
    if not one.fetched:
        one.at.parent.mkdir(parents=True, exist_ok=True)
        _git("clone", "--depth", "1", _url_of(one.url), str(one.at))
    else:
        # Fetched and reset rather than pulled: a flowverse is a copy of somebody else's
        # repository, not a branch of your own, and a merge nobody asked for is a fetch that
        # fails the next time it is run.
        _git("-C", str(one.at), "fetch", "--depth", "1", "origin", "HEAD")
        _git("-C", str(one.at), "reset", "--hard", "FETCH_HEAD")
    return Flowverse(
        name=one.name,
        url=one.url,
        at=one.at,
        fetched=_cloned(one.at),
        fixed=one.fixed,
    )


def remove(name: str) -> bool:
    """Takes a flowverse away, flows and all.

    Args:
      name: What it is called.

    Returns:
      Whether there was one to take away.

    Raises:
      ValueError: If it is one of humanize's own two, which are always there: one is the
        flows in the package and the other is where the rest of them come from.
    """
    import shutil

    one = named(name)
    if one is None:
        return False
    if one.fixed:
        raise ValueError(f"{name} is always here; it is not one to take away")
    if not one.at.is_dir():
        return False
    shutil.rmtree(one.at)
    return True


def flows(one: Flowverse) -> list[str]:
    """The flow files in one flowverse, by the name each is offered under.

    Args:
      one: The flowverse.

    Returns:
      One name per file, alphabetically. A file whose name starts with an underscore is not a
      flow but something the flows beside it import, and is not among them.
    """
    if not one.at.is_dir():
        return []
    return sorted(
        path.name.removesuffix(".py")
        for path in one.at.glob("*.py")
        if not path.name.startswith("_") and path.is_file()
    )


def _git(*said: str) -> None:
    """Runs one git command, and says what it said if it would not.

    Args:
      said: The arguments, after `git` itself.

    Raises:
      OSError: If git is not there, or the command failed.
    """
    try:
        done = subprocess.run(
            ["git", *said],
            capture_output=True,
            text=True,
            check=False,
            timeout=_PATIENCE,
        )
    except FileNotFoundError as gone:
        raise OSError(
            "git is not installed here, and a flowverse is a git repository"
        ) from gone
    except subprocess.TimeoutExpired as slow:
        raise OSError(f"git {said[0]} took longer than {_PATIENCE:.0f}s") from slow
    if done.returncode != 0:
        raise OSError(done.stderr.strip() or f"git {said[0]} failed")


#: What `owner/repo` looks like, which is the one spelling that is not already something git
#: can clone: two names and one slash between them, and nothing that could be a path.
_OWNED = re.compile(r"[A-Za-z0-9][\w.-]*/[A-Za-z0-9][\w.-]*\Z")


def _url_of(said: str) -> str:
    """The URL to clone, from what somebody wrote.

    Args:
      said: A URL, a path to a repository on this machine, or `owner/repo` for one on GitHub
        -- which is how these are usually named, and how the one humanize ships is written
        down.

    Returns:
      Something git can clone.
    """
    if _OWNED.match(said) and not Path(said).expanduser().exists():
        return f"https://github.com/{said}"
    return said


def _called(url: str) -> str:
    """What a flowverse fetched from this URL is called, which is the repository's own name.

    Read as a posix path whatever this machine's separator is: it is a URL or an `owner/repo`,
    which are written with slashes wherever they are typed.
    """
    return PurePosixPath(url.rstrip("/")).name.removesuffix(".git") or "flowverse"


def _cloned(at: Path) -> bool:
    """Whether there is a fetched flowverse at this path."""
    return (at / ".git").exists()


def _url(at: Path) -> str:
    """Where a fetched flowverse came from, as its own clone says.

    Read out of the clone's own config rather than asked of git: this is answered every time
    the flowverses are listed, which is every time a list of flows is drawn, and a subprocess
    apiece per keystroke is a list that lags.

    Args:
      at: Its directory.

    Returns:
      The URL, or "" for one that cannot be read -- which is one that is not there.
    """
    held = configparser.ConfigParser(strict=False)
    try:
        held.read(at / ".git" / "config")
    except (OSError, configparser.Error):
        return ""
    return held.get('remote "origin"', "url", fallback="").strip()


def _directories(at: Path) -> list[Path]:
    """Every directory directly inside one, and nothing at all where there is no such place."""
    try:
        return [path for path in at.iterdir() if path.is_dir()]
    except OSError:
        return []

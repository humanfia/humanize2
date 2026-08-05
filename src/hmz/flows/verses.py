"""Where flows come from, when they come from somewhere else.

A flowverse is a git repository with a `flows/` directory in it: one directory per flow, each
with the `__init__.py` that is the flow, whatever it imports beside it and the `skills/` it
brings. It is cloned into `~/.humanize/flowverses/<name>/`, and every flow in it is offered
under that name. Only that directory is read, so a repository is free to be a repository
around it -- a README, a pyproject, a test suite -- without any of it being taken for a flow
and run to find out. `builtin` is the one that has no repository around it, being the
package's own, and is read where it stands.

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

from hmz import home

__all__ = [
    "BUILTIN",
    "FLOWS",
    "OFFICIAL",
    "Flowverse",
    "add",
    "clone",
    "fetch",
    "flowverses",
    "holds",
    "plain",
    "refresh",
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

#: The directory a fetched flowverse keeps its flows in, and the only one read for them. A
#: flowverse is a repository, and a repository has a README, a pyproject and a test suite in it:
#: reading a flow means running it, so the ones to run are the ones somebody put here and
#: nothing else. `builtin` has no repository around it and so has no need of this.
FLOWS = "flows"

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
      at: The directory it is kept in, which for a fetched one is the repository rather than
        the flows: what its flows are read from is :func:`holds`.
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


def holds(one: Flowverse) -> Path:
    """The directory one flowverse's flows are read from, and the one place that is worked out.

    The `flows/` inside it, except for the flows humanize ships: those are a directory of
    flows in the package with no repository around them -- no README, no pyproject, no test
    suite to be kept out of the way -- and so are read where they stand.

    Args:
      one: The flowverse.

    Returns:
      The path, whether or not there is anything there -- a repository with no `flows/` in it
      is a flowverse holding nothing, which is a thing to say rather than a thing to raise.
    """
    return one.at if one.name == BUILTIN else one.at / FLOWS


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
      ValueError: If the name is not one a flowverse may have, one is already called that, or
        it is one of the two that are always listed -- those two are humanize's own, and a
        repository cloned into either slot is one nobody could reach.
      OSError: If git is not there, or the fetch failed. What git said is attached, and
        whatever it had written before it failed is taken away again.
    """
    said = url.strip()
    if not said:
        raise ValueError("no repository to fetch a flowverse from")
    called = name or _called(said)
    if called == BUILTIN:
        # Cloned there, it would be in nobody's list: the flows humanize ships are the package's
        # and this name is spoken for, so the directory would sit there offering nothing and
        # refusing to be taken away again.
        raise ValueError(
            f"{BUILTIN} is what the flows humanize ships are called; pick another name"
        )
    if called == OFFICIAL:
        # This one is listed from the start with humanize's own URL against it, so a stranger's
        # repository here would be shown as humanize's own.
        raise ValueError(
            f"{OFFICIAL} is humanize's own repository of flows; "
            f"`fetch {OFFICIAL}` gets it, and another name holds another one"
        )
    at = where(called)
    if at.exists():
        raise ValueError(f"there is already a flowverse called {called!r}")
    at.parent.mkdir(parents=True, exist_ok=True)
    clone(said, at)
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
        clone(one.url, one.at)
    else:
        refresh(one.at)
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
    """The flows in one flowverse, by the name each is offered under.

    Args:
      one: The flowverse.

    Returns:
      One name per flow in the directory it holds them in, alphabetically -- a directory with
      an `__init__.py` in it, or a single `.py` file, both of which are a module. A directory
      without an entry point is what the flows beside it import rather than a flow, and
      neither is a name that starts with an underscore. Nothing at all where there is no such
      directory: a repository somebody added that keeps its flows somewhere else holds none of
      them, which is what the list says.
    """
    from . import offered

    return offered(holds(one))


def plain(url: str) -> str:
    """One URL with whatever was signed into it taken out.

    A flowverse is cloned from wherever somebody said, and a private one in CI is normally
    said as `https://x-access-token:$TOKEN@github.com/org/flows` -- which git writes into the
    clone's config verbatim and is read back out of it here. Where a flowverse came from is
    shown every time they are listed, at a prompt and on a command line both, so a token
    printed once is a token in a scrollback and in the log of every job that ran it.

    Here rather than beside either of the two things that print it: one place a thing is
    scrubbed is one place it is scrubbed, whichever way somebody reached it.

    Args:
      url: Where it was fetched from, as its clone records it.

    Returns:
      The same URL with any user and password between `//` and `@` replaced, and the URL
      untouched where there is none -- which is nearly always.
    """
    return re.sub(r"(?<=//)[^/@]+@", "***@", url, count=1)


def refresh(at: Path) -> None:
    """Takes what a fetched repository says now, whatever is in the clone of it.

    Fetched and reset rather than pulled: what humanize keeps is a copy of somebody else's
    repository, not a branch of your own, and a merge nobody asked for is a fetch that fails
    the next time it is run.

    Args:
      at: The clone.

    Raises:
      OSError: If git is not there, or the fetch failed. What git said is attached.
    """
    _git("-C", str(at), "fetch", "--depth", "1", "origin", "HEAD")
    _git("-C", str(at), "reset", "--hard", "FETCH_HEAD")


def clone(url: str, at: Path) -> None:
    """Clones a repository, and leaves nothing behind where it could not.

    git tidies up after its own failures, but not after being killed: a clone called off for
    taking too long is stopped where it stood, and what it had written so far stays. That is a
    name taken by a flowverse that is not there -- and since a name already taken is refused,
    it is a name that cannot be used again until somebody finds the directory and removes it.

    Args:
      url: Where the repository is, as somebody wrote it.
      at: The directory to clone into, which must not already be there.

    Raises:
      OSError: If git is not there, or the clone failed. What git said is attached.
    """
    import shutil

    try:
        _git("clone", "--depth", "1", _url_of(url), str(at))
    except OSError:
        shutil.rmtree(at, ignore_errors=True)
        raise


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
    # No interpolation: a `%` in a URL is ordinary -- a percent-encoded password, or a path
    # with one in it -- and configparser's default would read it as the start of a substitution
    # and raise. Lazily, too: it raises where the value is read rather than where the file is,
    # so the read is inside the try along with it.
    held = configparser.ConfigParser(strict=False, interpolation=None)
    try:
        held.read(at / ".git" / "config")
        return held.get('remote "origin"', "url", fallback="").strip()
    except (OSError, configparser.Error):
        return ""


def _directories(at: Path) -> list[Path]:
    """Every directory directly inside one, and nothing at all where there is no such place."""
    try:
        return [path for path in at.iterdir() if path.is_dir()]
    except OSError:
        return []

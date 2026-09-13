"""Where flows come from: every place there is one, and what each of them is called.

A flowverse is a git repository with a `flows/` directory in it: one directory per flow, each
with the `__init__.py` that is the flow, whatever it imports beside it and the `skills/` it
brings. It is cloned into `~/.humanize/flowverses/<name>/`, and every flow in it is offered
under that name. Only that directory is read, so a repository is free to be a repository
around it -- a README, a pyproject, a test suite -- without any of it being taken for a flow
and run to find out.

Three are always there, and none of them can be added or taken away. `official` is humanize's
own, and is there whether or not it has been fetched yet: a list that only mentioned it once
somebody had thought to add it would be a list that hid what there is. And `local` and `user`
are the flows of your own: `.humanize/flows` here, and the one in your home directory.

`official` is the one that is read from two places at once. `chat` is in the package, because
an interface that has never reached a network still has to have something to open talking to;
everything else humanize offers is in the repository, where it can change without a release.
Which of the two a flow is in is humanize's business rather than anybody else's, so both are
offered under the one name: `chat` and `rlar` are each one of humanize's flows, said the same
way, and `official/chat` resolves the same as `official/rlar`. The package's own wins a name
they both hold -- the one that is always there beats the one a fetch could take away.

Those last two are places rather than repositories -- nothing fetches them, and what is in one
is whatever you put there -- but they are flowverses all the same, because everything that goes
looking for a flow has one question to ask and one list to ask it of. A flow of yours is read
where it stands the way the package's own is, offered under the name of the place it is in the
way a flowverse's are, and looked in first: `local/chat` says which one it is, and a bare
`chat` finds yours before humanize's.

Nothing here runs a flow, and nothing here reads one. It is the answer to "which flows are
there, and where did each come from" -- and to the three things that can happen to a flowverse:
added, fetched again, taken away.
"""

from __future__ import annotations

import configparser
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from hmz import home

__all__ = [
    "FLOWS",
    "LOCAL",
    "MINE",
    "OFFICIAL",
    "USER",
    "Flowverse",
    "add",
    "clone",
    "edited",
    "fetch",
    "flowverses",
    "holds",
    "nearest",
    "plain",
    "refresh",
    "remove",
    "under",
]

#: What humanize's own flows are listed under, and where the repository of them is. Always
#: listed, whether or not it has been fetched: what there is to run is not the same question as
#: what has been downloaded, and somebody who has never fetched it should still be able to see
#: it and say so. The handful in the package are listed under this name too -- one name for
#: humanize's flows, whichever of the two places a given one happens to be kept in.
OFFICIAL = "official"
OFFICIAL_URL = "https://github.com/humanfia/flowverse"

#: What the flows of your own are listed under: this project's, and the ones in your home
#: directory. Flowverses like any other, except that nothing fetches them.
LOCAL = "local"
USER = "user"

#: And where those two are, nearest first. Kept unresolved: the project one is relative to
#: wherever humanize is being run, and `~` is whoever is running it, neither of which is
#: settled when this is imported.
MINE = {
    LOCAL: ".humanize/flows",
    USER: "~/.humanize/flows",
}

#: The names a flowverse cannot be added under, being the three that are always listed. One is
#: humanize's own and two are yours, and a repository cloned into any of their slots would be
#: one nobody could reach.
_ALWAYS = (OFFICIAL, LOCAL, USER)

#: The places whose flows are read where they stand rather than out of a `flows/` inside them.
#: A fetched flowverse needs that directory to tell its flows from the repository around them;
#: these have no repository around them, and a directory of flows has nothing to tell them from.
_AS_THEY_STAND = (LOCAL, USER)

#: The directory a fetched flowverse keeps its flows in, and the only one read for them. A
#: flowverse is a repository, and a repository has a README, a pyproject and a test suite in it:
#: reading a flow means running it, so the ones to run are the ones somebody put here and
#: nothing else. The flows in the package have no repository around them and so have no need
#: of this.
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
      url: Where it is fetched from, or "" for one that is not fetched from anywhere -- the
        two directories your own flows live in.
      at: The directory it is kept in, which for a fetched one is the repository rather than
        the flows: what its flows are read from is :func:`holds`.
      fetched: Whether the repository has been cloned. False for one named but never fetched,
        which `official` is until somebody asks for it, and true for the ones fetched from
        nowhere: a directory that is not there holds no flows, which is what its list of them
        says rather than a download somebody is waiting for. Not the same question as whether
        it offers anything -- `official` offers the flows in the package either way.
      fixed: Whether it is always listed and cannot be removed: humanize's own, and the two
        your own flows live in.
    """

    name: str
    url: str
    at: Path
    fetched: bool
    fixed: bool


def under() -> Path:
    """Where every fetched flowverse is kept, which is one directory under humanize's home."""
    return home() / "flowverses"


def holds(one: Flowverse) -> tuple[Path, ...]:
    """The directories one flowverse's flows are read from, and the one place that is worked out.

    The `flows/` inside it, except for the two places that are a directory of flows and nothing
    else -- yours -- which have no repository around them, no README, no pyproject and no test
    suite to be kept out of the way, and so are read where they stand.

    More than one only for `official`, which is humanize's own flows and is kept in two places:
    the handful in the package, read where they stand, and the repository of the rest. The
    package's own come first, so that a name both hold is the one that is always there rather
    than the one a fetch could take away.

    Args:
      one: The flowverse.

    Returns:
      The paths, in the order a name is looked for in them, whether or not there is anything
      at any of them -- a repository with no `flows/` in it is a flowverse holding nothing,
      which is a thing to say rather than a thing to raise.
    """
    from . import BUILTIN_AT

    if one.name in _AS_THEY_STAND:
        return (one.at,)
    if one.name == OFFICIAL:
        return (BUILTIN_AT, one.at / FLOWS)
    return (one.at / FLOWS,)


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
      humanize's own first, then whatever else has been added, alphabetically, and last the
      flows of your own: this project's, then the ones in your home directory. Three of them
      are always here: humanize's, which is the one there is anything to fetch, and two
      directories of yours that are read wherever they are.
    """
    held = [
        Flowverse(
            name=OFFICIAL,
            url=OFFICIAL_URL,
            at=where(OFFICIAL),
            fetched=_cloned(where(OFFICIAL)),
            fixed=True,
        ),
    ]
    for at in sorted(_directories(under())):
        if at.name in _ALWAYS or not _NAMED.match(at.name):
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
    # Last, because that is the order they are read in and not the order they are looked in:
    # a menu of flows opens on the ones there are to run rather than on a directory that is
    # empty in most projects. Which one wins a name is :func:`nearest`.
    held.extend(_own(name) for name in MINE)
    return held


def nearest() -> list[Flowverse]:
    """Every place flows come from, nearest first, which is the order a name is looked up in.

    The same places :func:`flowverses` lists, in the other of the two orders they have: that
    one is the order they are offered in, and this is the order they are searched in. Both are
    written down here, since a place missing from either is a flow that is offered and cannot
    be run, or one that runs and is nowhere to be seen.

    Returns:
      This project's flows, then yours, then the rest as they are listed -- so that a flow of
      your own may stand in for one of humanize's by taking its name, and a project may mean
      its own `chat` by `chat`.
    """
    held = flowverses()
    return [one for one in held if one.name in MINE] + [
        one for one in held if one.name not in MINE
    ]


def _own(name: str) -> Flowverse:
    """One of the two places flows of your own live, as a flowverse like any other.

    Args:
      name: Which of them, as :data:`MINE` names it.

    Returns:
      The flowverse. Fetched, whether or not the directory is there: there is nowhere to fetch
      it from, and a directory that is not there is a place holding no flows rather than one
      with a download outstanding. Fixed, since a place that is wherever you are cannot be
      taken away.

    Note:
      Expanded with `os.path` rather than `Path.expanduser`, which raises where there is no
      home behind the `~`: a machine with no home directory is a machine with no flows of
      yours on it, which is a thing to say rather than the reason a flow humanize itself came
      with could not be found.
    """
    return Flowverse(
        name=name,
        url="",
        at=Path(os.path.expanduser(MINE[name])),
        fetched=True,
        fixed=True,
    )


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
        it is one of the three that are always listed -- humanize's own and the two your own
        flows live in -- since a repository cloned into any of those slots is one nobody could
        reach.
      OSError: If git is not there, or the fetch failed. What git said is attached, and
        whatever it had written before it failed is taken away again.
    """
    said = url.strip()
    if not said:
        raise ValueError("no repository to fetch a flowverse from")
    called = name or _called(said)
    if called == OFFICIAL:
        # This one is listed from the start with humanize's own URL against it, so a stranger's
        # repository here would be shown as humanize's own.
        raise ValueError(
            f"{OFFICIAL} is humanize's own repository of flows; "
            f"`fetch {OFFICIAL}` gets it, and another name holds another one"
        )
    if called in MINE:
        # Same again: these two are the flows of your own, read out of a directory rather than
        # a clone, so a repository under the name would be listed and never looked at.
        raise ValueError(
            f"{called} is what your own flows in {MINE[called]} are listed under; "
            "pick another name"
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
        anywhere -- your own flows are a directory you keep, which is not somewhere to fetch
        from.
      OSError: If git is not there, or the fetch failed. What git said is attached.
    """
    one = named(name)
    if one is None:
        raise ValueError(f"no flowverse called {name!r}")
    if not one.url:
        # Two ways to have no URL now that the package's own flows are under `official`:
        # a directory of yours, which is not fetched from anywhere, and a directory under the
        # flowverses home that is not a clone -- what a clone killed partway leaves behind.
        # Telling somebody the second is their own flows directory is telling them to look in
        # a place their problem is not in.
        said = (
            f"a directory of flows of your own, {MINE[name]}"
            if name in MINE
            else "a directory here that is not a clone of anything; take it away and add it "
            "again"
        )
        raise ValueError(f"{name} is {said}; there is nothing to fetch")
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
      ValueError: If it is one of the three that are always there: humanize's own, and the
        two directories your own flows live in, which are wherever you are.
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
      One name per flow in the directories it holds them in, alphabetically -- a directory with
      an `__init__.py` in it, or a single `.py` file, both of which are a module. A directory
      without an entry point is what the flows beside it import rather than a flow, and
      neither is a name that starts with an underscore. Nothing at all where there is no such
      directory: a repository somebody added that keeps its flows somewhere else holds none of
      them, which is what the list says.

      One name apiece for `official`, which is kept in two places: a flow the package and the
      repository both hold is one name here, and which of the two it resolves to is the order
      :func:`holds` puts them in.
    """
    from . import offered

    found_: list[str] = []
    for under_ in holds(one):
        found_.extend(name for name in offered(under_) if name not in found_)
    return sorted(found_)


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


def edited(at: Path) -> bool:
    """Whether a clone has anything written into it that fetching it again would undo.

    A flowverse is a copy of somebody else's repository and a fetch resets the clone to what
    that repository says now, so anything written into a flow there goes. That is a fair thing
    to do on a key somebody pressed, and not a fair thing to do behind them: a weaver who has
    added their own repository and is editing a flow in it would lose the morning to a fetch
    nobody asked for. Whoever fetches without being asked asks this first.

    Tracked files only, which is exactly what `reset --hard` takes back: a file somebody added
    and never committed survives a fetch, and the `__pycache__` that reading a flow leaves
    behind would otherwise make every repository without a `.gitignore` look edited forever.

    Args:
      at: The clone.

    Returns:
      Whether git has anything to report about it, and False where git cannot be asked -- a
      directory that is not a clone has nothing in it that a fetch could take away, there
      being no fetch.
    """
    try:
        done = subprocess.run(
            ["git", "-C", str(at), "status", "--porcelain", "--untracked-files=no"],
            capture_output=True,
            text=True,
            check=False,
            timeout=_PATIENCE,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return done.returncode == 0 and bool(done.stdout.strip())


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

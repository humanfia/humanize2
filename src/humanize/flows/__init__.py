"""Where a flow is found, and what there is to find.

Named rather than pathed: `hmz exec -f ralph_loop` is a name, and anything with a slash or
an extension in it is a file taken as given. A name is looked for in this project first, then
in yours, then among the ones humanize came with -- so a flow of your own may stand in for one
of humanize' by taking its name, and a project may stand in for both.

That is what `-f` takes. What a flow is *called* is another question, and only the ones
humanize came with are called by a bare name: a flow of yours is called by its path, short
enough to read -- `.humanize/flows/rlar.py`, `~/.humanize/flows/rlar.py`. So one of yours that
shares a name with one of humanize's is listed beside it rather than instead of it, and what
each of them was set up to run is remembered apart.
"""

from __future__ import annotations

import os
from glob import glob
from pathlib import Path

__all__ = ["BUILTIN", "find", "found", "where"]

#: What the flows humanize came with are called on the list, and the one place whose flows
#: are named rather than pathed: a name here is humanize's own and means one file.
BUILTIN = "builtin"

#: Where flows live, nearest first, and what to call each place on screen. Kept unresolved:
#: the project one is relative to wherever humanize is being run, and `~` is whoever is
#: running it, neither of which is settled when this is imported.
#:
#: Looked in with `os.path` and `glob` rather than `pathlib`: a place that cannot be read, or
#: a `~` with no home behind it, is a place with no flows in it. The os functions say that;
#: the pathlib ones raise, which would make an unreadable `.humanize/flows` in this directory
#: the reason a flow humanize itself came with could not be found.
where = (
    ("local", ".humanize/flows"),
    ("user", "~/.humanize/flows"),
    (BUILTIN, str(Path(__file__).parent)),
)


def found() -> list[tuple[str, str]]:
    """Every flow there is to run, and where each came from.

    Returns:
      One `(where it came from, what to call it)` pair apiece, nearest first and alphabetical
      within each place. Only the flows humanize came with are called by a bare name: those
      names are humanize's own and mean one file each. A flow of yours is called by its path
      -- `.humanize/flows/rlar.py`, `~/.humanize/flows/rlar.py` -- so that one of yours which
      happens to share a name with one of humanize's is a different flow here rather than the
      same one, and is written down, offered and remembered under a name of its own.
    """
    listed: list[tuple[str, str]] = []
    for whose, folder in where:
        for path in sorted(glob(os.path.join(os.path.expanduser(folder), "*.py"))):
            base = os.path.basename(path)
            # The same test `find` applies, or the two disagree: a directory or a broken link
            # named like a flow would be listed as one and then not be there when it was
            # picked.
            if base.startswith("_") or not os.path.isfile(path):
                continue
            listed.append((whose, _called(whose, folder, base)))
    return listed


def _called(whose: str, folder: str, base: str) -> str:
    """What one flow is called everywhere: on a command line, on screen, in the settings.

    Args:
      whose: Where it came from.
      folder: The directory it was found in, as `where` writes it -- unexpanded, so that a
        `~` stays a `~` and a path in this project stays relative to it.
      base: The file.

    Returns:
      The bare name for one humanize came with, and the path for anything else, written the
      short way: `.humanize/flows/mine.py` here, `~/.humanize/flows/mine.py` in your home.
    """
    if whose == BUILTIN:
        return base.removesuffix(".py")
    return os.path.join(folder, base)


def find(named: str) -> str:
    """Where the flow called this is.

    Args:
      named: A flow's name, or the path to a file taken as given -- which is what a flow of
        your own is called, `~` and all.

    Returns:
      The path to run: the nearest flow of that name, the file the path names, or `named`
      itself if nothing answers to it, so that whatever named it hears about it. Resolved,
      since a flow is free to change the working directory the name was resolved against.
    """
    for _, folder in where:
        beside = os.path.join(os.path.expanduser(folder), f"{named}.py")
        if os.path.isfile(beside):
            return os.path.realpath(beside)
    said = os.path.expanduser(named)
    return os.path.realpath(said) if os.path.isfile(said) else named

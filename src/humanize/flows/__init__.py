"""Where a flow is found, and what there is to find.

Named rather than pathed: `hmz exec -f ralph_loop` is a name, and anything with a slash or
an extension in it is a file taken as given. A name is looked for in this project first, then
in yours, then among the ones humanize came with -- so a flow of your own may stand in for one
of humanize' by taking its name, and a project may stand in for both.
"""

from __future__ import annotations

import os
from glob import glob
from pathlib import Path

__all__ = ["find", "found", "where"]

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
    ("builtin", str(Path(__file__).parent)),
)


def found() -> list[tuple[str, str]]:
    """Every flow there is to run, and where each came from.

    Returns:
      One `(where it came from, its name)` pair apiece, nearest first and alphabetical
      within each place. A name appears once: the nearest flow answering to it is the one
      that runs, so the ones it stands in for are not offered as if they still did.
    """
    listed: list[tuple[str, str]] = []
    taken: set[str] = set()
    for whose, folder in where:
        for path in sorted(glob(os.path.join(os.path.expanduser(folder), "*.py"))):
            named = os.path.basename(path).removesuffix(".py")
            # The same test `find` applies, or the two disagree: a directory or a broken link
            # named like a flow would be listed as one, take the name from the flow that
            # really answers to it, and then not be there when it was picked.
            if named.startswith("_") or named in taken or not os.path.isfile(path):
                continue
            taken.add(named)
            listed.append((whose, named))
    return listed


def find(named: str) -> str:
    """Where the flow called this is.

    Args:
      named: A flow's name, or the path to a file taken as given.

    Returns:
      The path to run: the nearest flow of that name, or `named` itself if nothing answers
      to it -- which is what makes a path work wherever a name does. Resolved, since a flow
      is free to change the working directory the name was resolved against.
    """
    for _, folder in where:
        beside = os.path.join(os.path.expanduser(folder), f"{named}.py")
        if os.path.isfile(beside):
            return os.path.realpath(beside)
    return named

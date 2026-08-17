"""``hmz flowverses`` -- where flows come from, from a command line.

The same directories the interface's `/flowverses` keeps, said as arguments instead:
what places there are, what one of them holds, and the three things that can happen to a
flowverse -- added, fetched again, taken away.

It is here because the moment you find out you need one is not always a moment you are sitting
in the interface: a machine being set up, a CI job that runs a flow somebody else wrote, a
line in a script. Nothing here reads a flow, and nothing here runs one -- listing what a
flowverse holds is its filenames, which costs no import and starts nothing.

The store itself is reached through :class:`hmz.sdk.Hmz`, which is the same object the
interface's own `/flowverses` asks: one place a thing is kept is one place it is kept,
whichever way somebody reached it.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hmz.flows.verses import Flowverse

__all__ = ["flowverses"]


def flowverses(argv: list[str]) -> int:
    """Carries out one `hmz flowverses` line.

    Args:
      argv: What followed the command name.

    Returns:
      Zero, or two for a line to correct, or one for something that could not be done.
    """
    import argparse

    parser = argparse.ArgumentParser(
        prog="hmz flowverses",
        description="Where flows come from: a git repository with a `flows/` directory apiece, "
        "cloned under humanize's home, and the flows of your own read where they lie. Each is "
        "offered under the name it is listed here under.",
    )
    doing = parser.add_subparsers(dest="doing", metavar="COMMAND")

    listing = doing.add_parser("list", help="what places flows come from")
    listing.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="just the names, one a line, for a script to read",
    )

    showing = doing.add_parser("show", help="what one holds")
    showing.add_argument("name", metavar="NAME")

    making = doing.add_parser("add", help="fetch one, and offer its flows")
    making.add_argument(
        "url", metavar="URL", help="a URL, a path, or `owner/repo` for one on GitHub"
    )
    making.add_argument(
        "name",
        metavar="NAME",
        nargs="?",
        default="",
        help="what to keep it under, defaulting to the repository's own name",
    )

    again = doing.add_parser("fetch", help="fetch one again, or for the first time")
    again.add_argument("name", metavar="NAME")

    dropping = doing.add_parser("remove", help="take one away, flows and all")
    dropping.add_argument("name", metavar="NAME")

    args = parser.parse_args(argv)
    if args.doing in (None, "list"):
        return _list(quiet=getattr(args, "quiet", False))
    if args.doing == "show":
        return _show(args.name)
    if args.doing == "add":
        return _add(args.url, args.name)
    if args.doing == "fetch":
        return _fetch(args.name)
    return _remove(args.name)


def _list(*, quiet: bool) -> int:
    """Prints every place flows come from, in the order they are offered.

    Says which places there are and not what any of them holds, and so reads none of them.
    Finding out what a flowverse holds means importing every file in its `flows/`, which is a
    great deal of somebody else's code to run for a line that only asked which places there
    are. `show` is the line that asks what is in one, and is where that is paid for.
    """
    from hmz.sdk import Hmz

    verses = Hmz().verses
    for one in verses.all():
        if quiet:
            print(one.name)
            continue
        # What has been downloaded is not the same question as what there is to run, so one
        # that has not been fetched says that rather than being left off the list.
        state = "fetched" if one.fetched else "not fetched"
        print(f"{one.name:14} {state:12} {verses.whence(one)}")
    return 0


def _show(name: str) -> int:
    """Prints what one flowverse is, and the name each flow in it is offered under.

    This is the line that reads them. What a file holds is not a fact its name carries -- one
    file may hold several flows and the next may hold none at all -- so the only way to say
    what `-f` would take is to import them, which is what the interface does for the same
    question. It is asked of one flowverse rather than of all of them: somebody asking about
    theirs has not asked to run everybody else's.
    """
    from hmz.sdk import Hmz

    verses = Hmz().verses
    one = verses.find(name)
    if one is None:
        print(f"hmz: no flowverse called {name!r}", file=sys.stderr)
        return 1
    print(f"flowverse   {one.name}")
    print(f"from        {verses.whence(one)}")
    print(f"kept in     {one.at}")
    print(f"fetched     {'yes' if one.fetched else 'no'}")
    if one.fixed:
        from hmz.flows.verses import MINE

        why = "a directory of your own" if one.name in MINE else "humanize's own"
        print(f"always here {why}; not one to take away")
    if not one.fetched:
        print(f"\nnothing of it is here yet; `hmz flowverses fetch {one.name}` gets it")
        return 0
    held = verses.holds(one)
    for flow in held:
        # The name `-f` takes, worked out the one place that rule lives, and what the flow says
        # about itself beside it -- which is what somebody choosing between them is reading.
        print(f"holds       {flow.name:28} {flow.about}".rstrip())
    if not held:
        print("holds       nothing that is a flow")
    return 0


def _add(url: str, name: str) -> int:
    """Fetches a flowverse, and says what it is called here and where it landed."""
    from hmz.sdk import Hmz

    try:
        one = Hmz().verses.add(url, name)
    except (ValueError, OSError) as why:
        print(f"hmz: {why}", file=sys.stderr)
        return 1
    print(f"{one.name} is fetched into {one.at}")
    return _ask(one)


def _fetch(name: str) -> int:
    """Fetches a flowverse again, or for the first time."""
    from hmz.sdk import Hmz

    verses = Hmz().verses
    try:
        one = verses.fetch(name)
    except (ValueError, OSError) as why:
        print(f"hmz: {why}", file=sys.stderr)
        return 1
    print(f"{one.name} is fetched from {verses.plain(one.url)}")
    return _ask(one)


def _remove(name: str) -> int:
    """Takes a flowverse away, flows and all."""
    from hmz.sdk import Hmz

    try:
        gone = Hmz().verses.remove(name)
    except (ValueError, OSError) as why:
        # OSError too: taking one away is an rmtree, and a directory that will not go -- a
        # parent that cannot be written, a symlink, a file still held open -- is a line that
        # could not be carried out rather than a traceback to read.
        print(f"hmz: {why}", file=sys.stderr)
        return 1
    if not gone:
        print(f"hmz: no flowverse called {name!r}", file=sys.stderr)
        return 1
    print(f"{name} is gone, flows and all")
    return 0


def _ask(one: Flowverse) -> int:
    """Points at the line that says what a flowverse holds, without reading it to find out.

    A repository that has just been cloned off the internet is the last thing to import
    unasked: whoever ran this has said they trust it enough to fetch, which is not the same as
    having said to run it this second. `show` is one more line, and it is theirs to type.

    Args:
      one: The flowverse, as it is now.

    Returns:
      Zero.
    """
    print(f"`hmz flowverses show {one.name}` says what it holds")
    return 0

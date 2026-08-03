"""``hmz flowverses`` -- where flows come from, from a command line.

The same directories the interface's `/flow` walks a tab at a time, said as arguments instead:
what places there are, what one of them holds, and the three things that can happen to a
flowverse -- added, fetched again, taken away.

It is here because the moment you find out you need one is not always a moment you are sitting
in the interface: a machine being set up, a CI job that runs a flow somebody else wrote, a
line in a script. Nothing here reads a flow, and nothing here runs one -- listing what a
flowverse holds is its filenames, which costs no import and starts nothing.
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
        description="Where flows come from: a git repository of flows apiece, cloned under "
        "humanize's home and offered under the name it is kept there.",
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
    Finding out what a flowverse holds means importing every file in it, which is a great deal
    of somebody else's code to run for a line that only asked which places there are. `show` is
    the line that asks what is in one, and is where that is paid for.
    """
    from hmz.flows import verses as store

    for one in store.flowverses():
        if quiet:
            print(one.name)
            continue
        # What has been downloaded is not the same question as what there is to run, so one
        # that has not been fetched says that rather than being left off the list.
        state = "fetched" if one.fetched else "not fetched"
        print(f"{one.name:14} {state:12} {_from(one)}")
    return 0


def _show(name: str) -> int:
    """Prints what one flowverse is, and the name each flow in it is offered under.

    This is the line that reads them. What a file holds is not a fact its name carries -- one
    file may hold several flows and the next may hold none at all -- so the only way to say
    what `-f` would take is to import them, which is what the interface does for the same
    question. It is asked of one flowverse rather than of all of them: somebody asking about
    theirs has not asked to run everybody else's.
    """
    from hmz.flows import offers
    from hmz.flows import verses as store

    one = store.named(name)
    if one is None:
        print(f"hmz: no flowverse called {name!r}", file=sys.stderr)
        return 1
    print(f"flowverse   {one.name}")
    print(f"from        {_from(one)}")
    print(f"kept in     {one.at}")
    print(f"fetched     {'yes' if one.fetched else 'no'}")
    if one.fixed:
        print("always here humanize's own; not one to take away")
    if not one.fetched:
        print(f"\nnothing of it is here yet; `hmz flowverses fetch {one.name}` gets it")
        return 0
    held = offers(one)
    for flow in held:
        # The name `-f` takes, worked out the one place that rule lives, and what the flow says
        # about itself beside it -- which is what somebody choosing between them is reading.
        print(f"holds       {flow.name:28} {flow.about}".rstrip())
    if not held:
        print("holds       nothing that is a flow")
    return 0


def _add(url: str, name: str) -> int:
    """Fetches a flowverse, and says what it is called here and where it landed."""
    from hmz.flows import verses as store

    try:
        one = store.add(url, name)
    except (ValueError, OSError) as why:
        print(f"hmz: {why}", file=sys.stderr)
        return 1
    print(f"{one.name} is fetched into {one.at}")
    return _ask(one)


def _fetch(name: str) -> int:
    """Fetches a flowverse again, or for the first time."""
    from hmz.flows import verses as store

    try:
        one = store.fetch(name)
    except (ValueError, OSError) as why:
        print(f"hmz: {why}", file=sys.stderr)
        return 1
    print(f"{one.name} is fetched from {_plain(one.url)}")
    return _ask(one)


def _remove(name: str) -> int:
    """Takes a flowverse away, flows and all."""
    from hmz.flows import verses as store

    try:
        gone = store.remove(name)
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


def _from(one: Flowverse) -> str:
    """Where a flowverse came from, as it may be printed where a person can read it.

    Asked of the name rather than of the URL. An empty URL means two different things -- the
    flows humanize ships, which are fetched from nowhere, and a directory whose origin could
    not be read -- and answering both with the first would put humanize's name on somebody
    else's flows.

    Args:
      one: The flowverse.

    Returns:
      The URL with anything secret in it taken out, or a phrase for the two that have none.
    """
    from hmz.flows.verses import BUILTIN

    if one.name == BUILTIN:
        return _PACKAGE
    return _plain(one.url) if one.url else _NOWHERE


def _plain(url: str) -> str:
    """One URL with whatever was signed into it taken out.

    A flowverse is cloned from wherever somebody said, and a private one in CI is normally
    said as `https://x-access-token:$TOKEN@github.com/org/flows` -- which git writes into the
    clone's config verbatim and would be read back out of it here. This line is printed every
    time the flowverses are listed, and a token printed once is a token in a scrollback and in
    the log of every job that ran it. The sibling `hmz providers` never prints a secret; nor
    does this.

    Args:
      url: Where it was fetched from, as its clone records it.

    Returns:
      The same URL with any user and password between `//` and `@` replaced, and the URL
      untouched where there is none -- which is nearly always.
    """
    import re

    return re.sub(r"(?<=//)[^/@]+@", "***@", url, count=1)


#: What is printed where the other flowverses print where they were fetched from. The flows
#: humanize ships are not fetched from anywhere: they are in the package.
_PACKAGE = "the flows humanize ships"

#: For a directory under the flowverses home that is not a clone of anything, or is one whose
#: origin cannot be read. Its flows are still offered, so it is still listed -- but where it
#: came from is a question it has no answer to, which is not the same as having come from here.
_NOWHERE = "-"

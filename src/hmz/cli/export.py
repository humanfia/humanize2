"""``hmz export`` -- one whole run, packaged up to send to somebody who was not there.

A run is written down as it happens, and it is written down to be read on the machine it ran
on: the record of what happened, and beside it a link per file each backend logged a session
to. Which is the one thing that cannot be sent anywhere -- a directory of symlinks into
somebody's home is an archive with nothing in it once it leaves their machine.

So this is that same run with the links followed and everything behind them carried whole,
plus a manifest saying what humanize and each backend were: enough for whoever reads the
report to see what actually happened rather than to ask what happened next.

Credentials never ride along, whatever the run's own logs happen to hold. That is
:mod:`hmz.exporting`, which is also what the interface's `/export` asks -- one archive, made
one way, whichever way somebody reached it.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from argparse import ArgumentParser

__all__ = ["export"]


def export(argv: list[str]) -> int:
    """Carries out one `hmz export` line.

    Args:
      argv: What followed the command name.

    Returns:
      Zero, or two for a line to correct.
    """
    import argparse

    parser = argparse.ArgumentParser(
        prog="hmz export",
        description="One whole run, packaged up: what it did, what every session of every "
        "agent was logged as, and what this machine was running -- with every credential "
        "taken out.",
    )
    parser.add_argument(
        "epic",
        nargs="?",
        help="Which run, by the name of its directory or a leading part of it, or by the "
        "path to it. Defaults to the last run of this directory.",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Where to write it: a file, or a directory to write it into under its own "
        "name. Defaults to .humanize/<run>.epic.tar.gz here.",
    )
    args = parser.parse_args(argv)
    return _bundle(args.epic, args.output, parser)


def _bundle(named: str | None, output: str | None, parser: ArgumentParser) -> int:
    """Writes one run out as one archive, and says where it landed and how big it is.

    Args:
      named: Which run, or None for the last of this directory.
      output: Where to write it, or None for `.humanize/` here.
      parser: The line itself, for reporting one to correct.

    Returns:
      Zero, once the bundle has been written.
    """
    from hmz.cli import many
    from hmz.exporting import sized
    from hmz.sdk import Hmz

    runs = Hmz().epics
    found = runs.all()
    epic = _which(named, found, parser) if named else _last(found, parser)
    try:
        # A directory that holds no run is refused here rather than checked first: writing
        # one is what reads it, and a second reading to say the same thing is a second
        # reading.
        at, manifest = runs.bundled(epic, output=output)
    except (OSError, ValueError) as why:
        parser.error(str(why))
    # Counted off the manifest rather than off the run: what is being said is what went in
    # the archive, and a second reading of the links would describe the run as it is now --
    # which for a run that is still going is a different answer.
    held = [one["logs"] for one in manifest["sessions"]]
    quiet = sum(1 for each in held if not each)
    said = f", {quiet} logged nothing" if quiet else ""
    print(
        f"{at} of {manifest['epic']}: {many(len(held), 'session')}, "
        f"{many(sum(len(each) for each in held), 'log')}{said}, "
        f"{sized(at.stat().st_size)}"
    )
    return 0


def _which(named: str, found: list[Path], parser: ArgumentParser) -> Path:
    """The run one name means: a path to one, or a run of this directory called that.

    A path first, since a run of another workspace has no name here to answer to and its
    directory is the whole of what somebody has to point at it with.

    Args:
      named: What was typed.
      found: Every run of this directory, oldest first.
      parser: The line itself, for reporting one to correct.

    Returns:
      The run's directory.
    """
    at = Path(named)
    if at.is_dir():
        return at
    matched = [one for one in found if one.name.startswith(named)]
    if not matched:
        parser.error(
            f"no run of this directory is called {named!r}, and it is not a path"
        )
    return matched[-1]


def _last(found: list[Path], parser: ArgumentParser) -> Path:
    """The run to export where the line named none, which is the last one here.

    Args:
      found: Every run of this directory, oldest first.
      parser: The line itself, for reporting one to correct.

    Returns:
      The newest.
    """
    if not found:
        parser.error(
            "no flow has been run in this directory, so there is none to export"
        )
    return found[-1]

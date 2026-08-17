"""The flows there are, and the places they come from, as two objects rather than two modules.

What a flow is and how one is loaded is :mod:`hmz.flows`; where the fetched ones are kept is
:mod:`hmz.flows.verses`. Both are reached from here so that a command line, an interface and a
daemon ask the one object rather than three modules apiece -- and so that the handful of
answers all three of them need spelled the same way, such as where a flowverse came from, are
spelled once.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import os
    from pathlib import Path
    from typing import Any

    from pydantic import BaseModel

    from hmz.flows import Flowverse, Offer, Place, Running

__all__ = ["Flows", "Flowverses"]

#: What is printed where the other flowverses print where they were fetched from. The flows
#: humanize ships are not fetched from anywhere: they are in the package.
_PACKAGE = "the flows humanize ships"

#: For a directory under the flowverses home that is not a clone of anything, or is one whose
#: origin cannot be read. Its flows are still offered, so it is still listed -- but where it
#: came from is a question it has no answer to, which is not the same as having come from here.
_NOWHERE = "-"


class Flowverses:
    """Where flows come from: what places there are, and the three things that happen to one.

    The same directories every way in walks, so that a flowverse added from a command line is
    one the interface offers a moment later.
    """

    def all(self) -> list[Flowverse]:
        """Every place there is, in the order their flows are offered."""
        from hmz.flows import verses

        return verses.flowverses()

    def nearest(self) -> list[Flowverse]:
        """The same places, in the order a flow's name is looked up in."""
        from hmz.flows import verses

        return verses.nearest()

    def find(self, name: str) -> Flowverse | None:
        """The place called this, or None for a name none answers to."""
        from hmz.flows import verses

        return verses.named(name)

    def add(self, url: str, name: str = "") -> Flowverse:
        """Fetches a place and offers its flows under a name.

        Args:
          url: A URL, a path, or `owner/repo` for one on GitHub.
          name: What to keep it under, defaulting to the repository's own name.

        Returns:
          The flowverse, fetched.

        Raises:
          ValueError: If the name is taken, is one of the ones always there, or is not one a
            directory may be called.
          OSError: If it cannot be cloned or kept.
        """
        from hmz.flows import verses

        return verses.add(url, name)

    def fetch(self, name: str) -> Flowverse:
        """Fetches one again, or for the first time.

        Args:
          name: What it is listed under.

        Returns:
          The flowverse, as it now stands.

        Raises:
          ValueError: If no place answers to that name, or it is one nothing fetches.
          OSError: If git refused.
        """
        from hmz.flows import verses

        return verses.fetch(name)

    def remove(self, name: str) -> bool:
        """Takes one away, flows and all.

        Args:
          name: What it is listed under.

        Returns:
          Whether there was one to take away.

        Raises:
          ValueError: If it is one of the ones that are always there.
          OSError: If the directory will not go.
        """
        from hmz.flows import verses

        return verses.remove(name)

    def holds(self, one: Flowverse) -> list[Offer]:
        """What one place holds, by the name each flow is offered under.

        Reading a flow means running it, so this is the one question about a place with no
        cheap answer -- and it is asked of the place named rather than of all of them.

        Args:
          one: The flowverse.

        Returns:
          One offer per flow in it, and nothing at all for one that has not been fetched.
        """
        from hmz.flows import offers

        return offers(one)

    def where(self, name: str) -> Path:
        """The directory one place is kept in, whether or not anything has been fetched into it."""
        from hmz.flows import verses

        return verses.where(name)

    def plain(self, url: str) -> str:
        """A URL with whatever was signed into it taken out, as it may be printed."""
        from hmz.flows import verses

        return verses.plain(url)

    def whence(self, one: Flowverse, nowhere: str = _NOWHERE) -> str:
        """Where a place came from, as it may be shown to somebody.

        Asked of which flowverse it is rather than of whether its URL is empty. An empty URL
        means several different things -- the flows humanize ships, the two directories your
        own live in, and a directory whose origin could not be read -- and answering all of
        them with the first would put humanize's name on somebody else's flows.

        Args:
          one: The flowverse.
          nowhere: What to say for a directory that is not a clone of anything, or is one
            whose origin cannot be read. Whoever is showing it says it: a listing has a
            column of them and a sheet has a sentence.

        Returns:
          The URL with anything secret in it taken out, or what it is instead for the ones
          that have none. Scrubbed here rather than at each of the places that shows it: this
          line is printed every time the places are listed, and a token printed once is a
          token in the log of every job that ran it.
        """
        from hmz.flows.verses import BUILTIN, MINE, plain

        if one.name == BUILTIN:
            return _PACKAGE
        if one.name in MINE:
            return f"your own flows in {MINE[one.name]}"
        return plain(one.url) if one.url else nowhere


class Flows:
    """The flows there are: what is offered, what one of them takes, and what one says it is."""

    def __init__(self) -> None:
        self._verses = Flowverses()

    @property
    def verses(self) -> Flowverses:
        """Where the flows come from."""
        return self._verses

    def all(self) -> list[Offer]:
        """Every flow there is to run, by the name `-f` takes."""
        from hmz.flows import found

        return found()

    def find(self, named: str) -> str:
        """The file one flow is written in.

        Args:
          named: The flow, by the name it is offered under or by a path to a file.

        Returns:
          The path, as a string.

        Raises:
          NotAFlow: If nothing of that name is a flow.
        """
        from hmz.flows import find

        return find(named)

    def about(self, named: str) -> str:
        """The line a flow says about itself, and "" for one that says nothing."""
        from hmz.flows import about

        return about(named)

    def places(self, named: str | os.PathLike[str]) -> tuple[Place, ...]:
        """Every agent a flow needs chosen for it, in the order it takes them."""
        from hmz.flows import wanted

        return wanted(named)

    def configures(self, named: str | os.PathLike[str]) -> type[BaseModel] | None:
        """What a flow can be set up with, or None for one that takes no setting up."""
        from hmz.flows import configures

        return configures(named)

    def resumes(self, named: str | os.PathLike[str]) -> bool:
        """Whether a flow says it can be picked up where the last run of it left off."""
        from hmz.flows import resumes

        return resumes(named)

    def fork(self, named: str, into: str | os.PathLike[str] | None = None) -> str:
        """Copies a flow into this project's own flows, whole -- what it imports and all.

        Args:
          named: The flow, by the name it is offered under.
          into: Where to put it, defaulting to this project's own flows.

        Returns:
          The name it is offered under from now on, which is the one it already had.

        Raises:
          NotAFlow: If nothing of that name is a flow.
          OSError: If it cannot be copied.
        """
        from hmz.flows import fork

        return fork(named, into)

    def running(self) -> tuple[Running, ...]:
        """Every flow running in this process now, the one started first and what it called."""
        from hmz.flows import running

        return running()

    def set_up_from(self, said: str | os.PathLike[str]) -> dict[str, Any]:
        """Reads what a flow is to be set up with out of a YAML file of it.

        Args:
          said: The path to the file.

        Returns:
          What it holds, field by field, and nothing at all for a file that is empty.

        Raises:
          ValueError: If the file cannot be read, or holds something that is not a mapping.
        """
        from hmz.runner import set_up_from

        return set_up_from(said)

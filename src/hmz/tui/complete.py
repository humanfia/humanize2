"""What the editor offers to finish, which is the only way anything is typed here.

A command line is typed, never filled in on a form: `/` offers the commands, and `/flow`
offers the flows there are -- the ones humanize ships, the ones every flowverse fetched here
holds, and the ones under `.humanize/flows` here or in your home directory. So does `$`, which
is the flow said outright rather than chosen from a menu: the same list, under the sigil that
starts one. A flow anywhere else is a path, and a path is typed: looking for one would mean
reading every Python file below here to see which declare a flow, which is a guess, and far
too slow to make between keystrokes.

`hmz internal anchor` is not offered: it is not something to do to a flow while it runs, and
it takes a command line of its own. What a run left behind is `/epics`, which is where the runs are.
"""

from __future__ import annotations

import functools
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hmz.flows import Offer

__all__ = ["about", "hinted", "offered"]

#: What each command does, shown beside its name.
_ABOUT = {
    "flow": "Switch flow",
    "btw": "Ask a side question",
    "flowverses": "Manage the places flows come from",
    "providers": "Manage the accounts agents run as",
    "fallback": "Where a turn goes when the place taking it cannot take it at all",
    "epics": "The runs of this directory, and what to do with one",
    "resume": "Carry the last run here on from where it stopped",
    "settings": "What humanize remembers, here and everywhere",
    "monitor": "Watch the run: the flow drawn, and the board",
    "clear": "Clear the screen",
    "details": "Toggle tool calls and thinking",
    "afk": "Toggle whether an agent may ask you",
    "export": "Package this whole run up to send",
    "detach": "Let go of this terminal, leaving the flow running",
    "exit": "Exit humanize",
}


#: What a command takes after its name, shown beside it so that the list says what may be
#: written and not only what may be started. A switch takes `on` or `off` as well as being
#: flipped, and nothing says so unless the list does.
_TAKES = {
    "afk": "[on|off]",
    "btw": "<question>",
    "details": "[on|off]",
    "flow": "[flow]",
}

#: `/flow` and the name being typed after it. A third word is a line that has moved on.
_FLOW_AND_NAME = 2


def takes(name: str) -> str:
    """What a command takes after its name.

    Args:
      name: The command, without its slash.

    Returns:
      How its arguments are written, or "" for a command that takes none.
    """
    return _TAKES.get(name, "")


def about(name: str) -> str:
    """What a command is for.

    Args:
      name: The command, without its slash.

    Returns:
      The one line said about it, or "" if it is not one to offer.
    """
    return _ABOUT.get(name, "")


def offered(typed: str, commands: tuple[str, ...]) -> list[str]:
    """What the line being typed could be finished with.

    Args:
      typed: The line as it stands.
      commands: The commands there are, without their slashes.

    Returns:
      Everything the last word could become, in full, so that taking one replaces what was
      typed rather than being appended to it, and in alphabetical order -- the only order a
      list of commands has that a reader can predict. Never the word itself, and nothing at
      all for a word that has been written out already, whether it is a command or a flow: it
      is finished, and enter over an open list takes what is under the cursor rather than
      sending the line -- so `/flow`, with `/flowverses` beside it in the list, would be a
      command nobody could send, and `$rlar`, with `$rlar2` beside it, a flow nobody could
      start.
    """
    words = typed.split(" ")
    tail = words[-1]
    # A `$` names a flow to start, so it offers the flows and nothing else -- and only while
    # that first word is the one being typed: everything after it is the prompt, which is
    # prose and has nothing to finish it with.
    if typed.startswith("$"):
        if len(words) > 1:
            return []
        offers = [f"${one.name}" for one in _flows()]
    elif not typed.startswith("/"):
        return []
    elif len(words) == 1:  # still naming the command
        if tail.removeprefix("/") in commands:
            return []
        offers = sorted(f"/{name}" for name in commands if name in _ABOUT)
    # The flow is the one thing `/flow` takes, so it is offered while that word is the one
    # being typed and not after it: a line that already names a flow is a finished line.
    elif words[0] == "/flow" and len(words) == _FLOW_AND_NAME:
        offers = [one.name for one in _flows()]
    else:
        return []
    if tail in offers:
        return []  # written out in full, so enter over the list still sends the line
    return [offer for offer in offers if offer.startswith(tail) and offer != tail]


#: How long one reading of the flows stands for. Reading them means importing and running
#: every flow file there is, and a `$` asks for them on every keystroke of the name after it
#: -- twice, since the offers are reconsidered when the cursor moves as well as when the text
#: does. A moment's cache is the difference between a list that keeps up with typing and one
#: that does not, and the flows there are change when a flowverse is fetched or a file is
#: written, neither of which happens between two keystrokes.
_FOR = 2.0


def _flows() -> tuple[Offer, ...]:
    """Every flow there is to run, read where it is offered rather than kept here.

    Returns:
      One per flow, as `hmz.flows` lists them -- which is the one place that works out what
      each is called, since a name that drifted is a name nothing would take. As it was up to
      a moment ago, rather than as it is this instant.
    """
    return _found(int(time.monotonic() / _FOR), str(Path.cwd()))


@functools.lru_cache(maxsize=1)
def _found(_moment: int, _where: str) -> tuple[Offer, ...]:
    """One reading of the flows, kept under the moment and the directory it was read in.

    The arguments are the cache rather than the question: one bucket of `_FOR` seconds and one
    working directory is one answer, and the next bucket evicts it. Kept by directory as well,
    since `local` flows are this project's and a process that changed directory changed the
    list.

    Args:
      _moment: Which bucket of time this is.
      _where: The directory the flows were looked for from.

    Returns:
      One per flow.
    """
    from hmz.flows import found

    return tuple(found())


def hinted(typed: str, commands: tuple[str, ...]) -> str:
    """The command a line is writing, for as long as it is still being written.

    Args:
      typed: The line as it stands.
      commands: The commands there are, without their slashes.

    Returns:
      The command the line names, without its slash, or "" if it names none. Shown rather
      than offered: the line about a command says what it takes after its name, which is the
      half of it that matters most while that part is being typed -- and a list that empties
      the moment the name is finished takes it away exactly then. Nothing about it is taken,
      so enter over one sends the line as it always did.
    """
    if not typed.startswith("/"):
        return ""
    named = typed[1:].partition(" ")[0]
    return named if named in commands and about(named) else ""

"""What the editor offers to finish, which is the only way anything is typed here.

A command line is typed, never filled in on a form: `/` offers the commands, and `/flow`
offers the flows there are -- the ones humanize ships, the ones every flowverse fetched here
holds, and the ones under `.humanize/flows` here or in your home directory. A flow anywhere
else is a path, and a path is typed: looking for one would mean reading every Python file below
here to see which declare a flow, which is a guess, and far too slow to make between
keystrokes.

`hmz anchor` is not offered: it is not something to do to a flow while it runs, and it takes
a command line of its own. What a run left behind is `/cycles`, which is where the runs are.
"""

from __future__ import annotations

__all__ = ["about", "hinted", "offered"]

#: What each command does, shown beside its name.
_ABOUT = {
    "flow": "Switch flow",
    "btw": "Ask a side question",
    "flowverses": "Manage the places flows come from",
    "agents": "Set what each agent runs",
    "providers": "Manage the accounts agents run as",
    "fallback": "Where a turn goes when an agent or an account cannot take it",
    "cycles": "The runs of this directory, and what to do with one",
    "settings": "What humanize remembers, here and everywhere",
    "status": "Show how the run is going",
    "clear": "Clear the screen",
    "details": "Toggle tool calls and thinking",
    "afk": "Toggle whether an agent may ask you",
    "export": "Write the transcript out",
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
      all for a word that is already a command: a command that has been written out is
      finished, and enter over an open list takes what is under the cursor rather than
      sending the line -- so `/flow`, with `/flowverses` beside it in the list, would be a
      command nobody could send.
    """
    if not typed.startswith("/"):
        return []
    words = typed.split(" ")
    tail = words[-1]
    if len(words) == 1:  # still naming the command
        if tail.removeprefix("/") in commands:
            return []
        offers = sorted(f"/{name}" for name in commands if name in _ABOUT)
    # The flow is the one thing `/flow` takes, so it is offered while that word is the one
    # being typed and not after it: a line that already names a flow is a finished line.
    elif words[0] == "/flow" and len(words) == _FLOW_AND_NAME:
        from hmz.flows import found

        offers = [one.name for one in found()]
    else:
        return []
    return [offer for offer in offers if offer.startswith(tail) and offer != tail]


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

"""What the editor offers to finish, which is the only way anything is typed here.

A command line is typed, never filled in on a form: `/` offers the commands, and `/flow`
offers the flows there are -- the ones humanize came with and the ones under `.humanize/flows`
here or in your home directory. A flow anywhere else is a path, and a path is typed: looking
for one would mean reading every Python file below here to see which declare a flow, which is
a guess, and far too slow to make between keystrokes.

`hmz collect` and `hmz anchor` are not offered. Neither is something to do to a flow while it
runs, and both take a command line of their own.
"""

from __future__ import annotations

__all__ = ["about", "offered"]

#: What each command does, shown beside its name.
_ABOUT = {
    "flow": "Switch flow",
    "agents": "Set what each agent runs",
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
    "details": "[on|off]",
    "flow": "[path]",
}


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
      list of commands has that a reader can predict. Never the word itself: a word that is
      already what it would become is finished, and enter over an open list takes what is
      under the cursor rather than sending the line.
    """
    if not typed.startswith("/"):
        return []
    words = typed.split(" ")
    tail = words[-1]
    if len(words) == 1:  # still naming the command
        offers = sorted(f"/{name}" for name in commands if name in _ABOUT)
    # The flow is the one thing `/flow` takes, so it is offered while that word is the one
    # being typed and not after it: a line that already names a flow is a finished line.
    elif words[0] == "/flow" and len(words) == 2:
        from humanize.janus.flows import found

        offers = [name for _, name in found()]
    else:
        return []
    return [offer for offer in offers if offer.startswith(tail) and offer != tail]

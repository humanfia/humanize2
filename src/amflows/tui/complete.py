"""What the editor offers to finish, which is the only way anything is typed here.

A command line is typed, never filled in on a form: `/` offers the commands, and `/agents`
offers the flows there are -- the ones amflows came with and the ones under `.amflows/flows`
here or in your home directory. A flow anywhere else is a path, and a path is typed: looking
for one would mean reading every Python file below here to see which declare a flow, which is
a guess, and far too slow to make between keystrokes.
"""

from __future__ import annotations

__all__ = ["about", "offered"]

#: What each command does, shown beside its name. A command with nothing said about it is
#: not offered: `run` is what the first thing you say already does, and `tui` is this.
_ABOUT = {
    "agents": "Switch flow",
    "models": "Set what each agent runs",
    "new": "New session",
    "details": "Toggle tool calls",
    "thinking": "Toggle reasoning",
    "export": "Write the transcript out",
    "collect": "Collect a session",
    "anchor": "Run under the anchor",
    "help": "Help",
    "exit": "Exit amflows",
}


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
      typed rather than being appended to it.
    """
    if not typed.startswith("/"):
        return []
    words = typed.split(" ")
    tail = words[-1]
    if len(words) == 1:  # still naming the command
        return [
            f"/{name}"
            for name in commands
            if f"/{name}".startswith(tail) and name in _ABOUT
        ]
    if words[0] == "/agents":
        from amflows.janus.flows import found

        return [name for _, name in found() if name.startswith(tail)]
    return []

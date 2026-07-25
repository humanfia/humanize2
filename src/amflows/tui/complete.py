"""What the editor offers to finish, which is the only way anything is chosen here.

A command line is typed, never filled in on a form: `/` offers the commands, and the flags a
command takes offer whatever they are for -- the flows in this directory, the backends an
agent can run on. So there is one way to say a thing, and it is the way it is written down.
"""

from __future__ import annotations

import os
import shlex
from pathlib import Path

__all__ = ["flows", "offered"]

#: The backends an agent can be asked for, and an effort apiece worth starting from.
_AGENTS = (
    "claude/claude-opus-4-8/high",
    "claude/claude-opus-4-8/max",
    "claude/claude-haiku-4-5/low",
    "codex/gpt-5.6-sol/high",
    "codex/gpt-5.6-sol/xhigh",
    "kimi/kimi-code/k3/high",
    "kimi/kimi-code/k3/swarmmax",
)

#: The flows found under each directory this has looked in. Finding them means reading every
#: Python file below it, which is far too slow to do between keystrokes -- so it is done once
#: per directory and kept.
_FOUND: dict[str, list[str]] = {}


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
        return [f"/{name}" for name in commands if f"/{name}".startswith(tail)]
    if words[0] == "/run":
        # A flow is a file and an agent is a backend at a model at an effort. Both are what
        # the flag before them is for, so the flag is what says which to offer.
        if words[-2] in ("-f", "--flow"):
            return [path for path in flows() if path.startswith(tail)]
        if words[-2] in ("-a", "--agents"):
            return [spec for spec in _AGENTS if spec.startswith(tail)]
    return []


def flows(where: str | None = None) -> list[str]:
    """Every file below a directory that looks like a flow, found once and kept.

    Args:
      where: The directory to look in, defaulting to this one.

    Returns:
      The path of each file declaring a `run(agents` of its own, nearest first.
    """
    here = os.path.abspath(where or os.getcwd())
    if here in _FOUND:
        return _FOUND[here]
    found: list[str] = []
    for root, folders, files in os.walk(here):
        # Pruned as it descends rather than filtered afterwards: a checkout with a virtualenv
        # in it holds thousands of Python files, and none of them is a flow.
        folders[:] = [
            folder
            for folder in folders
            if not folder.startswith(".") and folder != "__pycache__"
        ]
        for name in sorted(files):
            if not name.endswith(".py"):
                continue
            path = Path(root, name)
            try:
                if "def run(agents" in path.read_text(errors="ignore"):
                    found.append(shlex.quote(os.path.relpath(path, here)))
            except OSError:
                continue
    _FOUND[here] = found
    return found

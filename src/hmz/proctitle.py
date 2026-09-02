"""What this process is called, as every other process sees it.

``pkill -f PATTERN`` matches the pattern against the command line of every process the user
owns -- not the ones in a session, not the ones in a group, all of them. And ``hmz``'s own
command line carries whatever was typed after the command: the flow, the agents, and the
prompt in full. ``hmz exec -f rlar "... run pytest tests/x.py ..."`` is a process whose
command line says ``pytest tests/x.py``, so an agent tidying up after itself with
``pkill -f "pytest tests/x.py"`` reached the process holding its own run, and the run went
with it -- SIGTERM, exit 143. The agent's own CLI was never exposed: it reads its turns from
stdin. Only the supervisor was.

So ``hmz exec`` -- the one line that carries a task; ``hmz`` and ``hmz daemon start`` take a
flow and its agents and nothing more -- renames itself once it has read its line and before the
first agent starts: ``hmz exec``, the command and nothing typed after it. ``sys.argv`` is
untouched (argparse has already read it); what changes is the memory the operating system shows
other processes, and the short name ``ps`` and ``pkill NAME`` go by. A wrapper that stays as
the parent, ``uv run hmz``, keeps its own command line, and that is beyond this module.

A rename must never cost a run. The library that does it is a compiled extension with a
platform of its own under every call, so a machine it cannot serve gets the old name and
nothing else.
"""

from __future__ import annotations

import contextlib

#: What every title begins with, so that ``ps`` still says what a process is and
#: ``hmz daemon stop`` still has something to be told about. The threat is the text
#: typed after the command, not the command's own name.
PROGRAM = "hmz"


def named(command: str = "") -> None:
    """Renames this process to ``hmz COMMAND``, keeping nothing typed after the command.

    Args:
      command: The command being run -- ``exec`` -- as it should read in ``ps``. Never
        anything the user typed after it.
    """
    title = f"{PROGRAM} {command}".strip()
    with contextlib.suppress(
        Exception
    ):  # a name is a courtesy; a run is not spent on one
        import setproctitle

        setproctitle.setproctitle(title)

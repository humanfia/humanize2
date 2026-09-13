"""The SDK: how a tool that is not humanize reaches humanize.

    from hmz.sdk import Hmz

    hmz = Hmz()
    hmz.run("chat", [], "say hello").run()

There are two ways to reach a run from out here, and both are offered.

:class:`Hmz` is the runtime, straight at it, in the process that asked: a workspace and
everything that can be done in it. It is the same object the command line holds -- so a tool
that wants what `hmz exec` does, or what a sheet of the interface does, writes the call rather
than the command line, and a tool with something better in mind than either has what it would
need to write its own.

:class:`Daemons` is a run held where a terminal closing cannot end it -- a process of its own,
per workspace, reached over its socket. That is what a tool looking after a run somebody else
started asks: what is being held here, what it is running, letting go of the terminals on it,
stopping it. A run held that way outlives the program that asked for it.

Nothing under this names it. What is here is not a layer humanize is built out of -- every
answer is written where it is carried out, in :mod:`hmz.runtime` and :mod:`hmz.daemon`, and
this restates none of it. That is the whole of the difference between this and the seam every
way in used to pass through: a seam somebody outside reaches in through is a different job,
and doing both at once was doing this one badly.

Everything here is fetched when it is named, for the reason a workspace's own layers are: a
tool that only lists the places flows come from must not pay for the runs, the accounts and
the traces to do it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hmz.daemon import Daemon, Held, Session
    from hmz.runtime import Accounts, Epics, Fallbacks, Flows, Flowverses, Hmz, Run
    from hmz.sdk.daemons import Daemons

__all__ = [
    "Accounts",
    "Daemon",
    "Daemons",
    "Epics",
    "Fallbacks",
    "Flows",
    "Flowverses",
    "Held",
    "Hmz",
    "Run",
    "Session",
]

#: Which front door each of them is behind: the runtime, reached straight, and the daemon
#: holding a run apart from a terminal. The name of the layer rather than the module inside it
#: that happens to hold the class, so that what is offered out here follows what is done in
#: there -- and one entry apiece, so that `from hmz.sdk import Hmz` costs the one module `Hmz`
#: is in rather than every layer humanize has.
_WRITTEN = {
    "Accounts": "hmz.runtime",
    "Daemon": "hmz.daemon",
    "Daemons": "hmz.sdk.daemons",
    "Epics": "hmz.runtime",
    "Fallbacks": "hmz.runtime",
    "Flows": "hmz.runtime",
    "Flowverses": "hmz.runtime",
    "Held": "hmz.daemon",
    "Hmz": "hmz.runtime",
    "Run": "hmz.runtime",
    "Session": "hmz.daemon",
}


def __getattr__(name: str) -> object:
    """Hands through what this package offers, out of the layer it is written in.

    Args:
      name: What was asked for.

    Returns:
      The same object that layer holds, so that there is one of each however it was reached --
      a tool that named this and humanize itself are holding one class, not two that agree.

    Raises:
      AttributeError: If nothing here is called that, as for any other module.
    """
    from importlib import import_module

    where_ = _WRITTEN.get(name)
    if where_ is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return getattr(import_module(where_), name)

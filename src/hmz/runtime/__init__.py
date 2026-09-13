"""What a run is, here: driving one, writing it down, and reading it back afterwards.

    from hmz.runtime import Hmz

    hmz = Hmz()
    hmz.run("chat", [], "say hello").run()

The layer between what a flow says and the agents that do it. It finds the flow, hands it
the agents it declared, opens the epic a run is written into as it happens, remembers what
this workspace was set up with, and reads the whole of it back again -- as a trace, or as
one archive to send somewhere.

:class:`Hmz` is the front door: one workspace and everything that can be done in it, composed
out of the modules beside it in :mod:`hmz.runtime.doing`. A command line names it, and so does
the daemon that holds a run apart from any terminal -- what humanize can do is one list rather
than one per way in, and a thing that can be done one way can be done every way.

Nothing here drives a coding agent. That is :mod:`hmz.coganchor`, which this is written
against and which names nothing here.

Everything but the front door's own name is fetched when it is named, for the reason the
layers under it are: a command line that only lists the places flows come from must not pay
for the runs, the accounts and the traces to do it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hmz.runtime.doing.accounts import Accounts
    from hmz.runtime.doing.core import Hmz
    from hmz.runtime.doing.epics import Epics
    from hmz.runtime.doing.fallbacks import Fallbacks
    from hmz.runtime.doing.flows import Flows, Flowverses
    from hmz.runtime.doing.running import Run

__all__ = [
    "Accounts",
    "Epics",
    "Fallbacks",
    "Flows",
    "Flowverses",
    "Hmz",
    "Run",
]

#: Which module each of them is written in. One entry per name this package offers, so that
#: `from hmz.runtime import Hmz` costs the one module `Hmz` is in rather than all of them.
_WRITTEN = {
    "Accounts": "hmz.runtime.doing.accounts",
    "Epics": "hmz.runtime.doing.epics",
    "Fallbacks": "hmz.runtime.doing.fallbacks",
    "Flows": "hmz.runtime.doing.flows",
    "Flowverses": "hmz.runtime.doing.flows",
    "Hmz": "hmz.runtime.doing.core",
    "Run": "hmz.runtime.doing.running",
}


def __getattr__(name: str) -> object:
    """Hands through what the front door offers, out of the module it is written in.

    Args:
      name: What was asked for.

    Returns:
      The same object that module holds, so that there is one of each however it was reached.

    Raises:
      AttributeError: If nothing here is called that, as for any other module. It is also
        what sends Python looking for a module of that name beside this one, which is how
        `from hmz.runtime import telemetry` goes on being the reporter rather than this.
    """
    from importlib import import_module

    where_ = _WRITTEN.get(name)
    if where_ is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return getattr(import_module(where_), name)

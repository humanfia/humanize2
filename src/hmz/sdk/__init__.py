"""The SDK: humanize as one object, which every other way in is a way of reaching.

    from hmz.sdk import Hmz

    hmz = Hmz()
    hmz.run("chat", [], "say hello").run()

One class rather than a dozen modules. :class:`Hmz` is a workspace and everything that can be
done in it: what is remembered about it, the flows there are to run, the agents and accounts
those run as, the runs that have already happened, and the run happening now. The layers under
it stay where they are and go on being what they were; this is the one place they are composed.

The command line calls it, the daemon calls it, and the terminal interface reaches it through
the daemon holding the run -- so that what humanize can do is one list rather than four.

Everything but :class:`Hmz` itself is fetched when it is named, for the reason a workspace's
own layers are: a command line that only lists the agents kept under a name must not pay for
the runs, the accounts and the traces to do it, and naming this package is how every command
begins.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hmz.sdk.accounts import Accounts
    from hmz.sdk.agents import Agents, Taken
    from hmz.sdk.core import Hmz
    from hmz.sdk.epics import Epics
    from hmz.sdk.fallbacks import Fallbacks
    from hmz.sdk.flows import Flows, Flowverses
    from hmz.sdk.running import Run
    from hmz.sdk.session import Session

__all__ = [
    "Accounts",
    "Agents",
    "Epics",
    "Fallbacks",
    "Flows",
    "Flowverses",
    "Hmz",
    "Run",
    "Session",
    "Taken",
]

#: Which module each of them is written in. One entry per name this package offers, so that
#: `from hmz.sdk import Hmz` costs the one module `Hmz` is in rather than all eight.
_WRITTEN = {
    "Accounts": "hmz.sdk.accounts",
    "Agents": "hmz.sdk.agents",
    "Epics": "hmz.sdk.epics",
    "Fallbacks": "hmz.sdk.fallbacks",
    "Flows": "hmz.sdk.flows",
    "Flowverses": "hmz.sdk.flows",
    "Hmz": "hmz.sdk.core",
    "Run": "hmz.sdk.running",
    "Session": "hmz.sdk.session",
    "Taken": "hmz.sdk.agents",
}


def __getattr__(name: str) -> object:
    """Hands through what this package offers, out of the module it is written in.

    Args:
      name: What was asked for.

    Returns:
      The same object that module holds, so that there is one of each however it was reached.

    Raises:
      AttributeError: If nothing here is called that, as for any other module.
    """
    from importlib import import_module

    where_ = _WRITTEN.get(name)
    if where_ is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return getattr(import_module(where_), name)

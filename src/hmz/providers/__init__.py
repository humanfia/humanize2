"""Which account a coding agent runs as, kept apart from which CLI it is.

A provider is a named set of credentials for one backend: a subscription signed into, a key,
an endpoint of somebody else's speaking that vendor's protocol. Each is kept in a directory of
its own under `~/.humanize/providers/<cli>/<name>/`, and an agent configured with one runs its
turns under it -- with that provider's variables, and reading its credentials out of that
directory rather than out of the one the CLI keeps its own in.

Which is what lets one flow drive two agents of the same CLI as two different accounts at the
same time: two Claude Codes, one on an Anthropic subscription and one on somebody's gateway,
each refreshing its own token and neither able to see the other's.

An account also says what happens when it is the one that goes down: how many times a turn
under it is tried again and how long to wait between tries, and which account to carry on
under once those are spent. Each naming the next is a chain -- subscription, then key, then
gateway -- walked inside the session that was running, so a run does not end on the minute one
vendor did.
"""

from __future__ import annotations

from . import retry
from .store import (
    ENV,
    Provider,
    add,
    chain,
    env_of,
    environ,
    filled,
    find,
    points,
    providers,
    ready,
    remove,
    retrying,
    ways,
    where,
)

__all__ = [
    "ENV",
    "Provider",
    "add",
    "chain",
    "env_of",
    "environ",
    "filled",
    "find",
    "points",
    "providers",
    "ready",
    "remove",
    "retry",
    "retrying",
    "ways",
    "where",
]

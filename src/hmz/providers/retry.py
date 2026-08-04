"""How long a turn waits before it is tried again, and how many times it is.

A turn fails for two kinds of reason, and only one of them is worth trying again. A prompt the
model refused is the same refusal every time; a gateway that answered 503, a subscription that
said "too many requests", a socket that closed mid-stream are the same call away from working.
So an account says how a turn under it is retried -- how long to wait between tries, how many
tries there are, and how long the whole of it may go on for -- and a run that would have ended
on a bad minute goes on instead.

The waits are the ones everybody uses, under the names everybody uses them by, and nothing
here invents one. What each of them is for is written beside it: the shape of the failure
decides the shape of the wait, and a queue of agents retrying in lockstep is what jitter is
for.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

__all__ = ["POLICIES", "Policy", "waits"]

#: The first wait, which every policy is written in terms of. A second is short enough that a
#: turn nobody is watching is not held up by it and long enough that a service which has just
#: refused one call is not immediately asked again.
BASE = 1.0

#: The longest any single wait may be, however far the backoff has climbed. A turn is minutes
#: long, and a wait longer than the turn it is waiting for is a run that looks hung.
CEILING = 60.0


@dataclass(frozen=True, slots=True)
class Policy:
    """One way of waiting between tries.

    Attributes:
      name: What it is called, which is what an account is written down with.
      about: One line saying what it is and when to reach for it.
    """

    name: str
    about: str


#: Every way a turn may be waited over, in the order they are offered: the plainest first, and
#: the one to reach for when several agents are failing at once marked as such. `none` is here
#: because "try again at once" is a real answer for a transport that dropped a connection.
POLICIES = (
    Policy("none", "try again at once, with no wait at all"),
    Policy("constant", "the same wait every time: 1s, 1s, 1s"),
    Policy("linear", "one second longer each time: 1s, 2s, 3s"),
    Policy("exponential", "twice as long each time: 1s, 2s, 4s, 8s"),
    Policy(
        "exponential-jitter",
        "exponential, each wait anywhere up to it -- for agents failing at once",
    ),
    Policy("fibonacci", "the Fibonacci sequence: 1s, 1s, 2s, 3s, 5s"),
)

#: What an account is retried by where it says nothing, and what the interface starts a new one
#: on: exponential backoff with full jitter is what every one of these services documents, and
#: the jitter is what keeps a flow's agents from retrying in lockstep.
DEFAULT = "exponential-jitter"


def named(policy: str) -> Policy | None:
    """The policy of that name, or None for a name none answers to."""
    return next((one for one in POLICIES if one.name == policy), None)


def waits(policy: str, attempt: int, base: float = BASE) -> float:
    """How long to wait before one try, given how many have already failed.

    Args:
      policy: The policy, as :data:`POLICIES` names them. One that is not among them waits
        the way the default does: a name nobody recognises is a setting to correct, and
        waiting nothing at all because of it would hammer whatever has just failed.
      attempt: Which try this is going to be, counting the first as 1 -- so the wait before
        the second try is `waits(policy, 2)`.
      base: The first wait, which every policy is written in terms of.

    Returns:
      The seconds to wait, never negative and never longer than :data:`CEILING`.
    """
    over = max(attempt - 1, 0)  # how many waits have already been taken
    if not over:
        return 0.0
    if policy == "none":
        return 0.0
    if policy == "constant":
        held = base
    elif policy == "linear":
        held = base * over
    elif policy == "fibonacci":
        held = base * _fibonacci(over)
    elif policy == "exponential":
        held = base * 2 ** (over - 1)
    else:
        # Full jitter, which is what "exponential backoff with jitter" means everywhere it is
        # documented: anywhere between nothing and the exponential wait. Two agents that
        # failed on the same second do not come back on the same second.
        held = random.uniform(0.0, base * 2 ** (over - 1))  # noqa: S311 -- a wait, not a key
    return min(held, CEILING)


def _fibonacci(over: int) -> int:
    """The nth Fibonacci number, counting 1, 1, 2, 3, 5 from n = 1."""
    before, held = 0, 1
    for _ in range(over - 1):
        before, held = held, before + held
    return held

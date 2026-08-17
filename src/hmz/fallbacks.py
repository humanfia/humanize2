"""Where a turn goes when the place taking it cannot take it at all.

The layer between an agent and an account, and it is neither of them. An account has a chain
of its own -- `hmz.providers` -- and it is the right one for what it is for: a subscription
that ran out falls to a key of the same backend, the conversation carries on because the
conversation is the backend's and is named by an id, and the same agent goes on running.

This is the other half. A model that has been retired, a CLI that will not start, a region
that has gone dark, a rate limit on the whole of an account rather than one request: none of
those is answered by another account of the same backend. What answers it is another place to
run -- another CLI, another account, another model -- and the turn is taken there.

A place is three things and no more: the CLI, the account it runs as, and the model it runs.
`claude@work/claude-opus-5` to `codex@key/gpt-5.6-sol`, which is a step from one to another.
It is not a step between agents. How hard an agent thinks, what it may reach for, which of a
flow's skills it carries and what it is called are what that agent *is*, settled where it was
made, and they come across the step unchanged: what failed was the place, so the place is what
moves.

Trying again is written down here too, for the same reason. A turn fails for two kinds of
reason and only one of them is worth another go -- a gateway that answered 503, a socket that
closed mid-stream, a service that said `too many requests` are each the same call away from
working -- and how many goes it gets is a thing about the place rather than about the agent
standing in it. One place says both: how often a turn under it is tried again, and where it
goes once those tries are spent.

What is lost across such a step is the conversation, and nothing here pretends otherwise: no
backend can be handed another backend's session id, so the turn that moves is taken in a new
session at the place it moved to. Which is why this is the second thing tried and not the
first: the account chain is walked to its end inside the conversation that was running, and
only a turn with nowhere left to go under its own backend leaves it.
"""

from __future__ import annotations

import json
import os
import random
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from hmz import backends, home

if TYPE_CHECKING:
    from collections.abc import Iterable

__all__ = [
    "BASE",
    "CEILING",
    "DEFAULT",
    "POLICIES",
    "Falls",
    "Policy",
    "chain",
    "clear",
    "falls",
    "named",
    "points",
    "reads",
    "retrying",
    "spec",
    "tried",
    "waits",
]

#: What the file every step is written down in is called. One file rather than one per step:
#: a chain is read whole every time it is read at all -- a turn that failed asks where it
#: goes, and the answer is the walk rather than the step -- and a directory of one-line files
#: would be a directory to walk to answer it.
_HELD = "fallbacks.json"

#: The first wait, which every policy is written in terms of. A second is short enough that a
#: turn nobody is watching is not held up by it and long enough that a service which has just
#: refused one call is not immediately asked again.
BASE = 1.0

#: The longest any single wait may be, however far the backoff has climbed. A turn is minutes
#: long, and a wait longer than the turn it is waiting for is a run that looks hung.
CEILING = 60.0

#: How far a backoff is worked out before the answer is the ceiling anyway. Doubling a second
#: passes a minute at the seventh, and Fibonacci at the eleventh; anything past this is a
#: number to stop computing rather than one to compute.
_CLIMBED = 64


@dataclass(frozen=True, slots=True)
class Policy:
    """One way of waiting between tries.

    Attributes:
      name: What it is called, which is what a step is written down with.
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

#: What a place is retried by where it says nothing, and what a menu starts a new one on:
#: exponential backoff with full jitter is what every one of these services documents, and the
#: jitter is what keeps a flow's agents from retrying in lockstep.
DEFAULT = "exponential-jitter"


@dataclass(frozen=True, slots=True)
class Falls:
    """One place: how a turn under it is tried again, and where it goes once they are spent.

    Attributes:
      spec: The place, as `CLI[@ACCOUNT]/MODEL` -- three things and no more, because those
        are what a turn can fail for having named. How hard the agent thinks and what it may
        reach for are what that agent is rather than where it runs.
      to: The place that takes the turn instead, in the same spelling, or "" for one that
        falls back nowhere -- which is a turn that fails as a turn has always failed.
      tries: How many times over a failed turn is tried again here before the step is taken.
        Zero is the first try and no more, which is what a turn has always had.
      policy: How long to wait between those tries, as :data:`POLICIES` names them.
      timeout: The longest the trying again may go on for, in seconds, or 0.0 for no limit.
    """

    spec: str
    to: str = ""
    tries: int = 0
    policy: str = DEFAULT
    timeout: float = 0.0

    def says(self) -> bool:
        """Whether this says anything at all, which is what keeps it written down.

        A place that falls back nowhere and is tried once is a place nobody has said anything
        about, and a file holding a row of those is a file that grows for nothing.

        Returns:
          True if it names somewhere to go or asks for a turn to be tried again.
        """
        return bool(self.to) or self.tries > 0


def spec(backend: str, model: str, provider: str = "") -> str:
    """One place as a step names it, which is three things and no more.

    Written down once, here, because two places spelling a place is two places to drift: an
    agent asks where it falls back to by this name, and a person writes one down by it.

    Args:
      backend: The CLI, by the name a command line calls it.
      model: The model it runs.
      provider: The account its turns run as, or "" for the one this machine is signed into.

    Returns:
      The spec, with the account in it only where there is one to name.
    """
    return f"{backend}{'@' + provider if provider else ''}/{model}"


def reads(said: str) -> str:
    """One place as it is written down, or "" for one that is not a place at all.

    Read through `hmz.backends` for the CLI rather than pattern-matched here, so that a name
    no backend answers to is refused where it is written rather than found by the turn that
    needed it. A model may hold slashes of its own -- Kimi Code's and opencode's are
    `provider/id` -- and a CLI never does, so the first slash is the one that separates them.

    An effort after a colon is dropped rather than refused: a step written down before effort
    left this spelling is a step somebody still means, and how hard an agent thinks is that
    agent's rather than the place's.

    Args:
      said: What was written.

    Returns:
      The spec as this module spells it, or "" where it cannot be read as one.
    """
    backend, slash, model = said.strip().partition("/")
    if not slash:
        return ""
    backend, at, account = backend.partition("@")
    if at and not account.strip():
        return ""
    profile = backends.named(backend.strip())
    model = _bare(profile, model.strip())
    if profile is None or not model:
        return ""
    return spec(profile.name, model, account.strip())


def _bare(profile: backends.Profile | None, model: str) -> str:
    """One model with the effort a step used to be written with taken off it.

    Args:
      profile: The CLI it is a model of, or None for one nothing answers to.
      model: The model as it was written, which may carry `:EFFORT` behind it.

    Returns:
      The model alone. A colon that is part of the model's own name is left where it is: only
      a rung this backend actually has is read as one.
    """
    before, colon, rung = model.rpartition(":")
    if not colon or profile is None:
        return model
    if rung in profile.efforts or rung in profile.beyond:
        return before
    return model


def falls() -> list[Falls]:
    """Every place written down, in the order they were written.

    Returns:
      One apiece. Empty where nothing has been written down, where the file has gone, and
      where what is there cannot be read -- a file somebody edited by hand into something
      else is a file to correct rather than the end of every run on this machine.
    """
    at = home() / _HELD
    try:
        held = json.loads(at.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(held, list):
        return []
    found: list[Falls] = []
    seen: set[str] = set()
    for said_ in cast("list[object]", held):
        if not isinstance(said_, dict):
            continue
        one = cast("dict[str, Any]", said_)
        # Read back through the same reading that wrote them: a file edited by hand holds
        # whatever somebody typed, and a step naming a CLI there is none of is a step that
        # could only fail the turn it was asked about.
        said, at_ = reads(str(one.get("spec") or "")), reads(str(one.get("to") or ""))
        if not said or said == at_ or said in seen:
            continue
        step = Falls(
            said,
            at_,
            tries=_counted(one.get("tries")),
            policy=str(one.get("policy") or DEFAULT),
            timeout=_seconds(one.get("timeout")),
        )
        if not step.says():
            continue
        seen.add(said)
        found.append(step)
    return found


def tried(said: str) -> Falls:
    """What is written down about one place, which is nothing at all for most of them.

    Args:
      said: The place, as `-a` or a step would name it.

    Returns:
      Its step, or one that falls back nowhere and is tried once -- so that whoever is
      walking a chain reads a step rather than a step and a special case.
    """
    from_ = reads(said) or said.strip()
    return next((one for one in falls() if one.spec == from_), Falls(from_))


def points(said: str, at: str) -> Falls:
    """Says where one place's turns go when it cannot take them, and writes it down.

    Args:
      said: The place that fails, as `CLI[@ACCOUNT]/MODEL`.
      at: The place that takes the turn instead, or "" to say it falls back nowhere -- which
        is a turn that fails as a turn has always failed.

    Returns:
      The step as it now stands, whose `to` is "" for one that was taken away.

    Raises:
      ValueError: If either cannot be read as a place, or if the two are the same one. A step
        that pointed at itself would be a turn that could never run out of places to go, and
        it is refused where it is written rather than found by the turn that needed it.
    """
    from_ = reads(said)
    if not from_:
        raise ValueError(f"{said!r} is not a place: expected CLI[@ACCOUNT]/MODEL")
    to = reads(at) if at.strip() else ""
    if at.strip() and not to:
        raise ValueError(f"{at!r} is not a place: expected CLI[@ACCOUNT]/MODEL")
    if to == from_:
        raise ValueError(f"{from_} cannot fall back to itself")
    return _keeps(replace(tried(from_), spec=from_, to=to))


def retrying(said: str, tries: int, policy: str, timeout: float) -> Falls:
    """Says how many times over a failed turn at one place is taken again, and how.

    Written down beside where that place falls back to, both being answers to the one thing
    that happened: the turn did not land. The tries come first -- the same call may yet
    work -- and the step is what is left when they are spent.

    Args:
      said: The place, as `CLI[@ACCOUNT]/MODEL`.
      tries: How many goes beyond the first.
      policy: How long to wait between them, as :data:`POLICIES` names them.
      timeout: The longest the trying again may go on for, in seconds, or 0.0 for no limit.

    Returns:
      The step as it now stands.

    Raises:
      ValueError: If the place cannot be read, the policy is not one there is, or either
        number is negative. All three are a line to correct rather than something for the
        turn that needed it to find out about.
    """
    from_ = reads(said)
    if not from_:
        raise ValueError(f"{said!r} is not a place: expected CLI[@ACCOUNT]/MODEL")
    if named(policy) is None:
        raise ValueError(
            f"{policy!r} is not a retry policy: "
            f"{', '.join(one.name for one in POLICIES)}"
        )
    if tries < 0 or timeout < 0:
        raise ValueError("tries and seconds are counts, not debts")
    return _keeps(
        replace(
            tried(from_), spec=from_, tries=tries, policy=policy, timeout=float(timeout)
        )
    )


def clear(said: str) -> bool:
    """Takes one place's whole step away, tries and destination alike.

    Args:
      said: The place it was written down against.

    Returns:
      Whether there was one to take away.
    """
    from_ = reads(said)
    kept = [one for one in falls() if one.spec != from_]
    if not from_ or len(kept) == len(falls()):
        return False
    _writes(kept)
    return True


def chain(said: str) -> list[str]:
    """The places one turn walks, this one first and each falling back to the next.

    Args:
      said: The place the turn is being taken at.

    Returns:
      The specs, in the order they are tried. The first is always this place, whether or not
      anything was written down about it, so that whoever is walking one walks a list rather
      than a list and a special case.

    Note:
      A chain that comes round on itself ends at the second sight of a place, and one whose
      next step names a place nothing answers to ends there: either would otherwise be a run
      that never stopped. Read whole rather than a step at a time, because a step at a time
      is what a loop is made of.
    """
    from_ = reads(said) or said.strip()
    walked = [from_]
    seen = {from_}
    steps = {one.spec: one.to for one in falls()}
    while (nowhere := steps.get(walked[-1], "")) and nowhere not in seen:
        seen.add(nowhere)
        walked.append(nowhere)
    return walked


def named(policy: str) -> Policy | None:
    """The policy of that name, or None for a name none answers to."""
    return next((one for one in POLICIES if one.name == policy), None)


def waits(policy: str, attempt: int, base: float = BASE) -> float:
    """How long to wait before one try, given how many have already failed.

    The waits are the ones everybody uses, under the names everybody uses them by, and nothing
    here invents one. What each of them is for is written beside it: the shape of the failure
    decides the shape of the wait, and a queue of agents retrying in lockstep is what jitter
    is for.

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
    # Held to where the ceiling has long since been reached: `2 ** 4000` is a number Python
    # is happy to build and `float` will not take, and a retry count is somebody's to set.
    over = min(over, _CLIMBED)
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


def _counted(said: object) -> int:
    """One count as it was written down, and none at all for anything that is not one."""
    try:
        held = int(cast("int", said))
    except (TypeError, ValueError):
        return 0
    return max(held, 0)


def _seconds(said: object) -> float:
    """One length of time as it was written down, and none at all for anything that is not."""
    try:
        held = float(cast("float", said))
    except (TypeError, ValueError):
        return 0.0
    return max(held, 0.0)


def _keeps(step: Falls) -> Falls:
    """Writes one step down in place of whatever was written against that place.

    Args:
      step: The step as it now stands.

    Returns:
      It, so that whoever asked for the change is holding what was written.
    """
    kept = [one for one in falls() if one.spec != step.spec]
    if step.says():
        kept.append(step)
    _writes(kept)
    return step


def _writes(steps: Iterable[Falls]) -> None:
    """Writes every step out whole, so that a file read while it is written is one of the two.

    Args:
      steps: What to write down.
    """
    at = home() / _HELD
    at.parent.mkdir(parents=True, exist_ok=True)
    said = (
        json.dumps(
            [
                {
                    "spec": one.spec,
                    "to": one.to,
                    "tries": one.tries,
                    "policy": one.policy,
                    "timeout": one.timeout,
                }
                for one in steps
            ],
            indent=2,
        )
        + "\n"
    )
    handle, beside = tempfile.mkstemp(
        dir=at.parent, prefix=f".{at.name}.", suffix=".new"
    )
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as writing:
            writing.write(said)
        Path(beside).replace(at)
    except OSError:
        Path(beside).unlink(missing_ok=True)
        raise

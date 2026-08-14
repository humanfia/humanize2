"""Where a turn goes when the agent taking it cannot take it at all.

An account has a chain of its own -- `hmz.providers` -- and it is the right one for what it
is for: a subscription that ran out falls to a key, the conversation carries on under the next
account because the conversation is the backend's and is named by an id, and the agent is the
same agent at the same model throughout.

This is the other half. A model that has been retired, a CLI that will not start, a region
that has gone dark, a rate limit on the whole of an account rather than one request: none of
those is answered by another account of the same backend, and what a run needs then is another
agent. So a whole agent falls back to a whole agent -- `claude@work/claude-opus-5:high` to
`codex@key/gpt-5.6-sol:high` -- and the turn is taken there.

What is lost across such a step is the conversation, and nothing here pretends otherwise: no
backend can be handed another backend's session id, so the turn that moves is taken in a new
session of the agent it moved to. Which is why this is the second thing tried and not the
first: the account chain is walked to its end inside the conversation that was running, and
only a turn with nowhere left to go under its own backend leaves it.

A step is written down between two agents rather than on either of them, because it is about
neither on its own: it is what to do when this one, at this model, at this effort, as this
account, cannot run. Two agents of one CLI on one account at two models are two things to say,
and an answer written on the account could only say one.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from hmz import backends, home

if TYPE_CHECKING:
    from collections.abc import Iterable

__all__ = [
    "Falls",
    "chain",
    "clear",
    "falls",
    "points",
    "reads",
    "spec",
]

#: What the file every step is written down in is called. One file rather than one per step:
#: a chain is read whole every time it is read at all -- a turn that failed asks where it
#: goes, and the answer is the walk rather than the step -- and a directory of one-line files
#: would be a directory to walk to answer it.
_HELD = "fallbacks.json"


@dataclass(frozen=True, slots=True)
class Falls:
    """One step: the agent that cannot run, and the agent that takes the turn instead.

    Attributes:
      spec: What fails, as `CLI[@ACCOUNT]/MODEL:EFFORT` -- the same word `-a` takes, so that
        a fallback is written the way the thing it is about is written.
      to: What takes the turn, in the same spelling.
    """

    spec: str
    to: str


def spec(backend: str, model: str, effort: str, provider: str = "") -> str:
    """One agent as a step names it, which is how `-a` names it.

    Written down once, here, because two places spelling an agent is two places to drift: an
    agent asks where it falls back to by this name, and a person writes one down by it.

    Args:
      backend: The CLI, by the name a command line calls it.
      model: The model it runs.
      effort: How hard it thinks, in that backend's own word.
      provider: The account its turns run as, or "" for the one this machine is signed into.

    Returns:
      The spec, with the account in it only where there is one to name.
    """
    return f"{backend}{'@' + provider if provider else ''}/{model}:{effort}"


def reads(said: str) -> str:
    """One spec as it is written down, or "" for one that is not a spec at all.

    Read through `hmz.backends` rather than pattern-matched here, so that what may be written
    down is exactly what `-a` takes -- a CLI by any of its spellings, a model with slashes of
    its own, an account after an `@` -- and what is written down is the one spelling of it.
    A name no backend answers to is refused where it is written rather than found by the turn
    that needed it.

    Args:
      said: What was written.

    Returns:
      The spec as this module spells it, or "" where it cannot be read as one.
    """
    try:
        profile, model, effort, _tier, provider, _may, _searches, _held = backends.read(
            said.strip()
        )
    except ValueError:
        return ""
    return spec(profile.name, model, effort, provider)


def falls() -> list[Falls]:
    """Every step written down, in the order they were written.

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
        if not said or not at_ or said == at_ or said in seen:
            continue
        seen.add(said)
        found.append(Falls(said, at_))
    return found


def points(said: str, at: str) -> Falls:
    """Says where one agent's turns go when it cannot take them, and writes it down.

    Args:
      said: The agent that fails, as `-a` would name it.
      at: The agent that takes the turn instead, or "" to say it falls back nowhere -- which
        is a turn that fails as a turn has always failed.

    Returns:
      The step as it now stands, whose `to` is "" for one that was taken away.

    Raises:
      ValueError: If either cannot be read as an agent, or if the two are the same one. A
        step that pointed at itself would be a turn that could never run out of places to go,
        and it is refused where it is written rather than found by the turn that needed it.
    """
    from_ = reads(said)
    if not from_:
        raise ValueError(
            f"{said!r} is not an agent: expected CLI[@ACCOUNT]/MODEL:EFFORT"
        )
    to = reads(at) if at.strip() else ""
    if at.strip() and not to:
        raise ValueError(f"{at!r} is not an agent: expected CLI[@ACCOUNT]/MODEL:EFFORT")
    if to == from_:
        raise ValueError(f"{from_} cannot fall back to itself")
    kept = [one for one in falls() if one.spec != from_]
    step = Falls(from_, to)
    if to:
        kept.append(step)
    _writes(kept)
    return step


def clear(said: str) -> bool:
    """Takes one step away, which is an agent that falls back nowhere again.

    Args:
      said: The agent it was written down against.

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
    """The agents one turn walks, this one first and each falling back to the next.

    Args:
      said: The agent the turn is being taken by.

    Returns:
      The specs, in the order they are tried. The first is always this agent, whether or not
      anything was written down about it, so that whoever is walking one walks a list rather
      than a list and a special case.

    Note:
      A chain that comes round on itself ends at the second sight of an agent, and one whose
      next step names an agent nothing answers to ends there: either would otherwise be a
      run that never stopped. Read whole rather than a step at a time, because a step at a
      time is what a loop is made of.
    """
    from_ = reads(said) or said.strip()
    walked = [from_]
    seen = {from_}
    steps = {one.spec: one.to for one in falls()}
    while (nowhere := steps.get(walked[-1], "")) and nowhere not in seen:
        seen.add(nowhere)
        walked.append(nowhere)
    return walked


def _writes(steps: Iterable[Falls]) -> None:
    """Writes every step out whole, so that a file read while it is written is one of the two.

    Args:
      steps: What to write down.
    """
    at = home() / _HELD
    at.parent.mkdir(parents=True, exist_ok=True)
    said = (
        json.dumps(
            [{"spec": one.spec, "to": one.to} for one in steps],
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

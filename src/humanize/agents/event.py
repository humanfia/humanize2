"""What a turn says while it runs, and what it asks -- the values, with no behaviour on them.

Separate from the classes that produce them because every backend needs these and none of
them needs the base classes to say one: a reader of somebody else's stream format turns lines
into `Event`s, and that is all it has to import to do it.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from typing import IO, TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = ["Event", "Question", "Stopped", "say"]


class Stopped(Exception):  # noqa: N818  -- not an error: an agent asked to stop has stopped
    """Raised in place of a turn, once the agent has been told to stop.

    A flow is a loop, and a loop that catches a failed turn goes round again -- so stopping
    one cannot be a failed turn. This is not a `CalledProcessError`, so the loops that carry
    on past a turn that failed do not carry on past this.
    """


@dataclass(frozen=True, slots=True)
class Event:
    """One thing an agent said while a turn was still running.

    What a turn returns is its last word; this is the rest of them, in the order they were
    said, so that a turn can be watched and talked to rather than only waited on.

    Attributes:
      kind: What was said. `text` is the agent talking, `reasoning` is it thinking aloud,
        `tool` is it using one, and `result` is the answer the turn ends on -- exactly one
        of which closes a turn. `failed` closes it the other way, carrying what went wrong
        in place of an answer. A watcher sees three more: `begins` and `ends`, which bracket
        the turn itself, and `asks`, which is the agent stopping to ask its user something.
      text: The words themselves, ready to be shown.
      tokens: What the turn cost, as tokens spent per model. Only a `result` carries it, and
        only from a backend that says.
    """

    kind: str
    text: str
    tokens: Mapping[str, int] = field(default_factory=dict[str, int])


@dataclass(frozen=True, slots=True)
class Question:
    """Something an agent stopped mid-turn to ask its user.

    Attributes:
      text: What is being asked, ready to be shown.
      options: The answers it offered, if it offered any. An answer is not held to them --
        every backend that offers options takes something else too -- but they are what the
        agent expects, and what an interface has to show for the question to read as one.
    """

    text: str
    options: tuple[str, ...] = ()


def say(text: str, sink: IO[str], *, end: str = "\n") -> None:
    """Puts something an agent said where the flow driving it can be watched.

    A sink that has gone away -- a flow piped into something that has exited -- takes nothing
    more rather than taking the turn down with it, whichever backend the turn was run through.

    Args:
      text: What the agent said.
      sink: The stream to put it on.
      end: What to follow it with, which is nothing for words arriving a fragment at a time.
    """
    with contextlib.suppress(OSError):
        sink.write(text + end)
        sink.flush()

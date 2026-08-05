"""What a turn says while it runs, and what it asks -- the values, with no behaviour on them.

Separate from the classes that produce them because every backend needs these and none of
them needs the base classes to say one: a reader of somebody else's stream format turns lines
into `Event`s, and that is all it has to import to do it.
"""

from __future__ import annotations

import contextlib
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import IO, TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator

__all__ = ["Event", "Failed", "Question", "Stopped", "Usage", "say"]

#: The kinds every backend here counts, and which of them each also counts beside those. A
#: kind is named the same thing wherever it is counted, so that one flow reading two backends
#: reads one word for one thing.
COMMON = ("input", "output")


class Usage(Mapping[str, float]):
    """Tokens, by the kind each of them went on.

    A mapping, because what a backend counts is what a backend counts: `input` and `output`
    are the two every one of them has, and the rest -- a cache read, a cache write, the
    reasoning one counts beside the output rather than inside it -- differ from CLI to CLI. A
    kind that is not in one of these is one this backend does not report, which is not the
    same as one it reports as nothing, so `usage.get("cache_read", 0)` is how an optional kind
    is asked for.

    The same shape says what has been spent and how fast it is being spent: a rate is tokens a
    second, kind by kind, which is the same reckoning divided by the seconds it happened over.
    """

    __slots__ = ("_kinds",)

    def __init__(
        self, kinds: Mapping[str, float] | None = None, /, **named: float
    ) -> None:
        """Initializes a reckoning of tokens.

        Args:
          kinds: What was spent, by kind.
          named: The same, for the kinds that can be written as words.
        """
        self._kinds: dict[str, float] = {**(kinds or {}), **named}

    @property
    def input(self) -> float:
        """What went in, which every backend counts."""
        return self._kinds.get("input", 0.0)

    @property
    def output(self) -> float:
        """What came out, which every backend counts."""
        return self._kinds.get("output", 0.0)

    @property
    def total(self) -> float:
        """Every kind together, which is the whole of what crossed the wire.

        The kinds are counted so that adding them up says that: a backend that counts its
        reasoning inside the output does not also carry it beside it, and one that counts a
        cached read inside the input does not carry that twice either.
        """
        return sum(self._kinds.values())

    def __getitem__(self, kind: str) -> float:
        return self._kinds[kind]

    def __iter__(self) -> Iterator[str]:
        return iter(self._kinds)

    def __len__(self) -> int:
        return len(self._kinds)

    def __add__(self, other: Mapping[str, float]) -> Usage:
        """Two reckonings as one, kind by kind."""
        added = dict(self._kinds)
        for kind, tokens in other.items():
            added[kind] = added.get(kind, 0.0) + tokens
        return Usage(added)

    def __truediv__(self, over: float) -> Usage:
        """The same reckoning as a rate, which is what it came to over that many seconds."""
        if over <= 0:
            return Usage(dict.fromkeys(self._kinds, 0.0))
        return Usage({kind: tokens / over for kind, tokens in self._kinds.items()})

    def __repr__(self) -> str:
        said = ", ".join(f"{kind}={tokens:g}" for kind, tokens in self._kinds.items())
        return f"Usage({said})"


class Failed(subprocess.CalledProcessError):
    """A turn that failed, saying why where whoever it happened to can read it.

    A `CalledProcessError` says `Command X returned non-zero exit status 1` and keeps what
    actually went wrong in an attribute nothing prints. What actually went wrong is the whole
    of what a person needs: `the model is not supported when using a ChatGPT account`, `the
    free service has ended`, `no credential`. Those are the lines that tell somebody their
    account needs attention rather than that humanize is broken -- and until this they were
    a field on an exception whose message said nothing.

    A `CalledProcessError` still, so that a flow catches turns rather than transports and
    every loop written against one goes on working.
    """

    def __str__(self) -> str:
        """What the process was, and then what it said about why it stopped.

        Both of what it said, where the two are different things: a CLI that warns on one
        stream and fails on the other -- pi says `no project session found` on stderr and
        `the requested model is not available for your geography` on stdout -- would
        otherwise be reported by the half that does not matter.
        """
        said = [super().__str__(), _words(self.stderr), _plainly(self.output)]
        return " ".join(one for one in said if one)


#: How much of what a failed turn said is worth putting in the message. Enough for the
#: sentence a CLI fails with, and not the transcript it failed part way through.
_ENOUGH = 400


def _words(said: str | bytes | None) -> str:
    """One stream of a failed turn, as one line of a message.

    Args:
      said: What it wrote, however the driver kept it.

    Returns:
      It on one line, clipped, and "" for a stream that said nothing.
    """
    held = said.decode("utf-8", "replace") if isinstance(said, bytes) else said
    if not isinstance(held, str) or not held.strip():
        return ""
    line = " ".join(held.split())
    return line if len(line) <= _ENOUGH else f"{line[: _ENOUGH - 1]}…"


def _plainly(said: str | bytes | None) -> str:
    """The last thing a failed turn said in words rather than in its protocol.

    What a backend writes to stdout is its event stream, which is a wall of JSON nobody wants
    in an error message -- except for the line it writes in plain words when it is about to
    stop, which is exactly the line worth reading.

    Args:
      said: The whole of what it wrote there.

    Returns:
      That line, clipped, and "" where everything it said was protocol.
    """
    held = said.decode("utf-8", "replace") if isinstance(said, bytes) else said
    if not isinstance(held, str):
        return ""
    for line in reversed(held.splitlines()):
        one = line.strip()
        if one and not one.startswith(("{", "[")):
            return _words(one)
    return ""


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
        in place of an answer. A watcher sees four more: `begins` and `ends`, which bracket
        the turn itself, `asks`, which is the agent stopping to ask its user something, and
        `took`, which is the agent saying that a word put into the turn is now in front of
        it -- carrying that word, so that whoever said it knows which one landed.
      text: The words themselves, ready to be shown.
      tokens: What the turn cost, as tokens spent per model. Only a `result` carries it, and
        only from a backend that says.
      spent: The same cost, by the kind of token it went on rather than by model -- what a
        rate is read off. Only a `result` carries it, and its `total` is what `tokens` comes
        to: the two are the same spending counted two ways.
    """

    kind: str
    text: str
    tokens: Mapping[str, int] = field(default_factory=dict[str, int])
    spent: Usage = field(default_factory=Usage)


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

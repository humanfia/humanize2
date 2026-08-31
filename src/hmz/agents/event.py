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
    from collections.abc import Iterator, Sequence

__all__ = [
    "Event",
    "Failed",
    "Question",
    "Saying",
    "Stopped",
    "Unrecoverable",
    "Usage",
    "say",
]


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

    It also says which *kind* of failure it was, where somebody has worked that out. A kind
    rather than a sentence, because the answer to each kind is a different answer: a rate
    limit is waited out and then taken to another account, a refused credential is not waited
    out at all, a retired model is answered by another place and by nothing else. Before that
    there were two kinds -- a turn that failed and a turn no other try could change -- so a
    401 was retried five times on a schedule and a `database is locked` waited a minute.

    Which kind it was is worked out where the backend, the exit status and the CLI's own log
    are all to hand, which is `hmz.backends.trouble` reached from the session -- not here: a
    value carries what it was told, and reading a message to guess at one is somebody else's
    job. What is written down here is what was decided.

    A `CalledProcessError` still, so that a flow catches turns rather than transports and
    every loop written against one goes on working.

    Attributes:
      fault: Which kind of failure this was, as `hmz.backends.FAULTS` names them, or "" for
        one nobody has classified -- which is a turn tried again exactly as it always was.
      fix: What a person does about it, in a few words, or "" where there is nothing to say
        beyond what the CLI already said.
    """

    def __init__(
        self,
        returncode: int,
        cmd: Sequence[str],
        output: str | bytes | None = None,
        stderr: str | bytes | None = None,
        *,
        fault: str = "",
        fix: str = "",
    ) -> None:
        """Initializes a failed turn.

        Args:
          returncode: How the process exited.
          cmd: What was run.
          output: What it wrote on stdout.
          stderr: What it wrote on stderr.
          fault: Which kind of failure it was, where the backend already knows.
          fix: What a person does about it, where the backend already knows that too.
        """
        super().__init__(returncode, cmd, output, stderr)
        self.fault = fault
        self.fix = fix

    def __str__(self) -> str:
        """What the process was, then what it said about why it stopped, then which kind.

        Both of what it said, where the two are different things: a CLI that warns on one
        stream and fails on the other -- pi says `no project session found` on stderr and
        `the requested model is not available for your geography` on stdout -- would
        otherwise be reported by the half that does not matter.

        And the kind last, because it is the reading rather than the evidence: whoever is
        looking at this wants what the CLI actually said first, and what to do about it after.
        """
        said = [
            super().__str__(),
            _words(self.stderr),
            _plainly(self.output),
            self.reads(),
        ]
        return " ".join(one for one in said if one)

    def reads(self) -> str:
        """Which kind of failure this was and what to do about it, as one clause.

        Returns:
          It in parentheses, and "" for a failure nobody has classified -- which reads exactly
          as a failed turn has always read.
        """
        if not self.fault:
            return ""
        return f"({self.fault}: {self.fix})" if self.fix else f"({self.fault})"


class Unrecoverable(Failed):
    """A turn that failed for a reason no other try could come out differently on.

    Most of what goes wrong in a turn is worth another go: a gateway that answered 503, a
    subscription that said `too many requests`, a socket that closed mid-stream are each the
    same call away from working, which is what an account's retries and the chain behind it
    are for -- and `fault` says which of those it was, so that each gets the go that suits it
    rather than all of them getting the same one. Some of it is not. A prompt the model
    refused for being longer than its context window is that long again on the next try; a
    conversation whose backend can no longer be reached under the id it was opened with is
    not reachable under it a second later either.

    Tried again, those become a loop: the same failure, at whatever interval the account was
    given, for as long as anybody leaves it running. So they are said once, as this, and
    whatever is trying a turn again MUST let this through rather than count it as an attempt.

    A `Failed` still, and so a `CalledProcessError`: a flow catches turns rather than the
    reasons they went wrong, and every loop written against one goes on working.
    """


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
        in place of an answer. A watcher sees five more: `begins` and `ends`, which bracket
        the turn itself, `asks`, which is the agent stopping to ask its user something,
        `took`, which is the agent saying that a word put into the turn is now in front of
        it -- carrying that word, so that whoever said it knows which one landed -- and
        `subagent` and `subagent-ends`, which bracket an agent this one started of its own.
      text: The words themselves, ready to be shown. For a `subagent` it is what the agent
        under this one is called and what it was asked to do.
      whose: Which of a turn's several things this is about, where a turn has several going
        at once: the backend's own id for a subagent, so that the one that started and the
        one that ended read as one agent. Empty for everything else, a turn having one of
        each of those.
      tokens: What the turn cost, as tokens spent per model. Only a `result` carries it, and
        only from a backend that says.
      spent: The same cost, by the kind of token it went on rather than by model -- what a
        rate is read off. Only a `result` carries it, and its `total` is what `tokens` comes
        to: the two are the same spending counted two ways.
    """

    kind: str
    text: str
    whose: str = ""
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


class Saying:
    """The fragments of an answer, gathered into the utterances they are pieces of.

    Every backend that streams sends its words a fragment at a time, and a fragment is not a
    thing to show. Said one at a time they are a line per token on a terminal and a bulleted
    block per token in a transcript -- one paragraph broken into fifty rows of one word each,
    which is not what the agent said and is not readable as it. So the fragments are gathered
    here and said whole: at the moment the agent reaches for something, since what it said
    before reaching is what says why it reached, and again when the answer ends.

    How much of each has already gone out is remembered, so a backend that repeats the whole
    message once it is finished says only the part nobody has seen -- and one that streams
    nothing at all says the whole of it, the two arriving here the same way.

    Several answers may be in flight at once, and a backend with more than one numbers them:
    by message id, or by the step of the turn each belongs to. Each is gathered under whatever
    the backend calls it. A backend with one at a time names none, and so does the event that
    ends a message on a backend that names the rest -- what has just come back is what the
    fragments before it were fragments of -- so an unnamed answer means the one last written
    to.
    """

    __slots__ = ("_latest", "_said", "_shown")

    def __init__(self) -> None:
        """Initializes a reading in which nothing has been said yet."""
        #: What has arrived, by the answer it belongs to and the kind of thing it is.
        self._said: dict[tuple[str, str], str] = {}
        #: How much of each of those has been passed on already.
        self._shown: dict[tuple[str, str], int] = {}
        #: Which answer is being streamed, for the events that name none.
        self._latest = ""

    def delta(self, kind: str, text: str, whose: str = "") -> None:
        """Takes one fragment of an answer, which is nothing to show on its own.

        Args:
          kind: What the fragment is a piece of -- `text` or `reasoning`.
          text: The fragment, as it arrived, with its spacing left alone: what makes the
            pieces one paragraph again is that nothing was put between them.
          whose: Which answer it belongs to, or "" for the one being streamed.
        """
        at = self._at(kind, whose)
        self._said[at] = self._said.get(at, "") + text

    def whole(self, kind: str, text: str, whose: str = "") -> None:
        """Takes one kind of an answer entire, as the backend has it.

        The deltas put back together, which is what a backend hands over when a message ends
        -- and what one that streamed nothing hands over instead. It replaces what arrived
        rather than adding to it, since it is the same words and the backend's copy is the
        one to trust.

        Args:
          kind: What it is -- `text` or `reasoning`.
          text: The whole of that kind of it.
          whose: Which answer it is, or "" for the one being streamed.
        """
        at = self._at(kind, whose)
        if (
            self._said.get(at, "")[: self._shown.get(at, 0)]
            != text[: self._shown.get(at, 0)]
        ):
            # Not the pieces after all: a backend that trimmed them, or squared up their
            # spacing, hands back a message that says the same thing at different offsets --
            # and how far into the old one had been shown then means nothing about this one.
            # Said from the start rather than cut at a place that now lands mid-word.
            self._shown[at] = 0
        self._said[at] = text

    def upto(self, whose: str = "") -> list[Event]:
        """Says one answer as far as it has got, and remembers how far that was.

        Args:
          whose: Which answer, or "" for the one being streamed.

        Returns:
          What it has thought and said beyond whatever has been shown, one event per kind,
          and nothing at all where everything of it has been shown already.
        """
        return self._saying(whose or self._latest, forget=False)

    def ended(self, whose: str = "") -> list[Event]:
        """The same, and then lets the answer go: it has now been said in full.

        Args:
          whose: Which answer, or "" for the one being streamed.

        Returns:
          Whatever of it nobody has seen.
        """
        return self._saying(whose or self._latest, forget=True)

    def rest(self) -> list[Event]:
        """Everything gathered and not yet said, whichever answer it belongs to.

        What a turn ends on, for a backend whose stream stops rather than closing each answer:
        words held back for a boundary that never came are words the turn would swallow.

        Returns:
          All of it, oldest answer first.
        """
        said: list[Event] = []
        for marked in list(dict.fromkeys(marked for marked, _ in self._said)):
            said += self._saying(marked, forget=True)
        return said

    def _at(self, kind: str, whose: str) -> tuple[str, str]:
        """Where one piece of one answer is gathered, taking note of which answer that is.

        Args:
          kind: What the piece is.
          whose: Which answer it is of, or "" for the one being streamed.

        Returns:
          The key it is held under.
        """
        if whose:
            self._latest = whose
        return (whose or self._latest, kind)

    def _saying(self, whose: str, *, forget: bool) -> list[Event]:
        """One answer as far as it has got, and how far that was written down.

        Args:
          whose: Which answer.
          forget: Whether to let go of it afterwards.

        Returns:
          What of it has not been shown, one event per kind, stripped -- the spacing between
          the fragments is what made them a paragraph, and the spacing around them is not.
        """
        said: list[Event] = []
        # Thinking before talking, whichever arrived first: what a model thought is what says
        # why it then said what it said, and an order that moved with the stream would put
        # the two round the other way as often as not.
        keys = sorted(
            (key for key in self._said if key[0] == whose),
            key=lambda key: key[1] != "reasoning",
        )
        for at in keys:
            rest = self._said[at][self._shown.get(at, 0) :]
            self._shown[at] = len(self._said[at])
            if forget:
                del self._said[at]
                del self._shown[at]
            if words := rest.strip():
                said.append(Event(kind=at[1], text=words))
        if forget and self._latest == whose:
            self._latest = ""
        return said


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

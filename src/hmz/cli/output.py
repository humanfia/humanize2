"""Who is reading a command line, and which of the two languages the answer is written in.

A command line is read twice over. Somebody at a terminal wants a run laid out -- which agent
is taking a turn, in which conversation, what it said, what it ran, and something moving while
it thinks, because a turn thinks for minutes and says nothing for most of them. A program
wants the same facts and none of the layout. This is the one place that answers which of the
two is there, so that no command has to guess.

Whether escapes are wanted is a question about the stream rather than about the command, and
three variables answer it before the stream does: `NO_COLOR` says never, `TERM=dumb` says the
terminal could not read them, and `FORCE_COLOR` says yes to something that is not a terminal
at all -- which is what a CI log wants, and what this project's own CI sets. Under none of
them, a run that is piped or redirected is written plainly, so that it stays exactly as
scriptable as it was before anything here existed.

`--json` is the other reading: NDJSON, one object a line, flushed as it happens, so that a
program tailing a run that will take an hour is told each thing as it is said rather than
handed a document at the end. While it is on, nothing else may reach stdout -- whatever a flow
prints goes to stderr instead, since one stray line is a stream that will not parse.

`rich` is reached only where escapes are actually wanted. A run written plainly, a `--json`
run and every listing pay nothing for it, which is what keeps `hmz` cheap to start.
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
import threading
import time
from typing import TYPE_CHECKING, Any, Self

from . import many

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable
    from types import TracebackType
    from typing import IO

    from rich.console import Console, ConsoleOptions, RenderResult
    from rich.live import Live

    from hmz.coganchor.agents import AgentBase, Event
    from hmz.coganchor.agents.base import SessionBase

__all__ = ["Out", "Shown", "colours", "terminal"]


#: The bullet a thing an agent said is set on, and the star a turn is closed with. The same
#: two the interface draws, since the two readings of one run should not look like two runs.
_SAID = "⏺" if sys.platform == "darwin" else "●"
_WORKED = "✻"
_DOT = " · "

#: Where the numbers in a token footer turn into a `k` and an `M`.
_THOUSAND = 1000
_MILLION = 1000 * 1000

#: How often the clock at the foot of a run is redrawn. The spinner steps every 80ms, so this
#: is roughly one step a frame: enough to read as moving, and few enough writes that a run
#: watched over ssh is not a run being drawn over ssh.
_FRAMES = 10


def terminal(stream: IO[str] | None = None) -> bool:
    """Whether a terminal is reading a stream.

    Asked apart from :func:`colours` on purpose: `FORCE_COLOR` says to write escapes into
    something that is not a terminal, and it must not also make a piped run believe somebody
    is watching it.

    Args:
      stream: The stream, or None for this process's own stdout.

    Returns:
      Whether it is a terminal. A stream that has been closed under us is not.
    """
    where = sys.stdout if stream is None else stream
    try:
        return where.isatty()
    except (AttributeError, ValueError):
        return False


def colours(stream: IO[str] | None = None) -> bool:
    """Whether escapes may be written to a stream.

    The three conventions, in the order they settle it: `NO_COLOR` is unconditional and wins
    over everything, `TERM=dumb` is a terminal saying it could not read them, and
    `FORCE_COLOR` is somebody saying to write them anyway -- a CI log is not a terminal and
    still renders them.

    Args:
      stream: The stream, or None for this process's own stdout.

    Returns:
      Whether to write them.
    """
    if os.environ.get("NO_COLOR", ""):
        return False
    if os.environ.get("TERM", "") == "dumb":
        return False
    forced = os.environ.get("FORCE_COLOR", "")
    if forced and forced != "0":
        return True
    return terminal(stream)


def _counted(tokens: float) -> str:
    """A number of tokens, narrow enough to sit in a footer."""
    if tokens < _THOUSAND:
        return f"{tokens:.0f}"
    if tokens < _MILLION:
        return f"{tokens / _THOUSAND:.1f}k"
    return f"{tokens / _MILLION:.2f}M"


class _Working:
    """The clock at the foot of a run, redrawn on every frame rather than on every event.

    A turn takes minutes and says nothing for most of them, so what says a run is alive cannot
    be a line printed when something happens. It is asked what to say each time it is drawn,
    which is how the seconds go up while nothing at all is being said.
    """

    def __init__(self, says: Callable[[], str]) -> None:
        """Holds what to ask, and the spinner it is written beside.

        Args:
          says: What the foot of the run should say now, or "" for a run with no turn open.
        """
        from rich.spinner import Spinner

        self._says = says
        # One spinner for the whole run: it steps off the time between the frame it was first
        # drawn on and this one, so a new one every frame would be a spinner that never moved.
        self._spinner = Spinner("dots", "")

    def __rich_console__(
        self, console: Console, options: ConsoleOptions
    ) -> RenderResult:
        """Draws the clock, or nothing at all between turns."""
        from rich.text import Text

        said = self._says()
        if not said:
            return
        self._spinner.update(text=Text(said, style="dim"))
        yield self._spinner


class Out:
    """One console for the whole command line: where it writes, and in which language.

    Held open around whatever the command does, because that is what makes `--json` a promise
    rather than a hope: while it is held, stdout belongs to the objects, and everything a flow
    or a layer under it prints goes to stderr instead.
    """

    def __init__(self, *, as_json: bool = False) -> None:
        """Answers who is reading before anything has been written.

        Args:
          as_json: Whether a program is reading, rather than a person.
        """
        self._json = as_json
        # Taken now, before `__enter__` puts anything else in its place: this is the stream
        # the objects go on, whatever `sys.stdout` is by the time one is written.
        self._machine: IO[str] = sys.stdout
        self._lock = threading.RLock()
        self._console: Console | None = None
        self._region: Live | None = None
        self._held: contextlib.ExitStack | None = None

    @property
    def as_json(self) -> bool:
        """Whether a program is reading this, rather than a person."""
        return self._json

    def __enter__(self) -> Self:
        """Takes stdout for the objects, where a program is reading."""
        self._held = contextlib.ExitStack()
        if self._json:
            # A flow prints, and so does a layer under one. Under `--json` a single such line
            # is a stream that will not parse, so there is nowhere for one to land but stderr.
            self._held.enter_context(contextlib.redirect_stdout(sys.stderr))
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        why: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Gives stdout back, and takes down whatever was being drawn on stderr."""
        self.spins(None)
        held, self._held = self._held, None
        if held is not None:
            held.close()
        with contextlib.suppress(OSError):
            self._machine.flush()

    def record(self, **fields: Any) -> None:
        """Puts one object on the stream a program is reading.

        Args:
          fields: The object. Every key it is written with is written every time: a schema a
            program has to guess at is not one it can read.
        """
        line = json.dumps(fields, default=str, ensure_ascii=False)
        with self._lock, contextlib.suppress(OSError):
            self._machine.write(line + "\n")
            # As it happens rather than when the process ends: a run that will take an hour
            # is watched by whatever is tailing it.
            self._machine.flush()

    def row(self, said: str, /, **fields: Any) -> None:
        """One row of a listing, as a line for a person or an object for a program.

        Args:
          said: The line, already laid out.
          fields: The same row's facts, for the program.
        """
        if self._json:
            self.record(**fields)
        else:
            print(said)

    def note(self, said: str) -> None:
        """Something only a person needs: a heading, a count, the line to type next.

        Args:
          said: The line. Nothing at all is written where a program is reading -- an empty
            list is already the answer, and a hint is not a row of it.
        """
        if not self._json:
            print(said)

    @property
    def console(self) -> Console:
        """The console a run is drawn on, which is stderr and is built when it is first used.

        On stderr because stdout is the answer: a run whose progress went there would be a run
        no script could read. Built lazily so that a plainly written run, a `--json` run and
        every listing pay nothing for `rich`.
        """
        if self._console is None:
            from rich.console import Console

            self._console = Console(
                file=sys.stderr,
                force_terminal=terminal(sys.stderr) or None,
                no_color=not colours(sys.stderr),
                # A run is prose and paths, not a table of literals to paint, and a bullet
                # is not an emoji shortcode somebody typed.
                highlight=False,
                emoji=False,
            )
        return self._console

    def line(self, *parts: tuple[str, str]) -> None:
        """One line of a run: the pieces of it, and the style each piece is in.

        Pieces rather than markup, so that the plain reading is the same call. A person at a
        terminal gets it styled; a run being piped gets exactly the characters, which is what
        makes a redirected run readable rather than a file of escapes.

        Args:
          parts: Each piece and its style, in the order they are written.
        """
        if not colours(sys.stderr):
            said = "".join(text for text, _ in parts)
            with self._lock, contextlib.suppress(OSError):
                sys.stderr.write(said + "\n")
                sys.stderr.flush()
            return
        from rich.text import Text

        with self._lock, contextlib.suppress(OSError):
            # Printed through the console the clock is drawn on, which is what lifts the
            # clock out of the way and puts it back under the new line.
            self.console.print(Text.assemble(*parts), soft_wrap=True)

    def answer(self, said: str) -> None:
        """Puts what a turn answered where a script reading this run will find it.

        Args:
          said: The answer itself, as the agent wrote it.
        """
        with self._lock:
            region = self._region
            if region is not None:
                # The clock is drawn on stderr and this is stdout, so nothing coordinates the
                # two: it is taken down for the write and put back after, rather than left to
                # be written through.
                region.stop()
            try:
                with contextlib.suppress(OSError):
                    self._machine.write(said + "\n")
                    self._machine.flush()
            finally:
                if region is not None:
                    region.start(refresh=True)

    def spins(self, says: Callable[[], str] | None) -> None:
        """Starts or stops the clock at the foot of a run.

        Args:
          says: What it should say each time it is drawn, or None to take it down. Nothing is
            drawn where no terminal is reading -- control codes in a log file are not a clock
            -- and nothing is drawn where escapes are not wanted either: a clock is written in
            them, cursor and all, so `NO_COLOR` and `TERM=dumb` mean no clock. What the run is
            doing is still said, a line at a time, as it is for anything that is not a
            terminal.
        """
        with self._lock:
            if says is None:
                region, self._region = self._region, None
                if region is not None:
                    with contextlib.suppress(Exception):
                        region.stop()
                return
            if self._region is not None or not (
                terminal(sys.stderr) and colours(sys.stderr)
            ):
                return
            from rich.live import Live

            region = Live(
                _Working(says),
                console=self.console,
                refresh_per_second=_FRAMES,
                # Gone the moment the run is: a clock left behind on the last line would be
                # the one thing on the terminal that is no longer true.
                transient=True,
            )
            region.start(refresh=True)
            self._region = region


class Shown:
    """A run of a flow as it happens, laid out for whoever is reading it.

    Built on `AgentBase.watch`, which is the same stream the interface draws from -- so the
    two readings of one run say the same things in the same order. Registering a watcher is
    also what stops every driver teeing its own raw progress to stderr, so this replaces that
    tee rather than being printed beside it.
    """

    def __init__(self, out: Out) -> None:
        """Holds where to write, and works out whether the answer needs writing twice.

        Args:
          out: The console for this command line.
        """
        self._out = out
        # When each turn started, filed under the conversation it is being taken in rather
        # than under the agent: an agent runs several at once, and one key apiece would have
        # the second turn's start time write over the first's -- so the first would be timed
        # against the wrong moment, the second against nothing at all, and the clock at the
        # foot would go out while a turn was still thinking.
        self._began: dict[tuple[str, int], float] = {}
        self._lock = threading.Lock()
        # A run nobody watched used to tee its progress to stderr and put each turn's answer
        # on stdout, and a script reading one reads that stdout -- so it goes on going there.
        # Except where both streams are the one terminal, where the turn has already said it
        # in front of the person and putting it there again would be the same words twice.
        self._echoes = not (terminal(sys.stdout) and terminal(sys.stderr))

    def __enter__(self) -> Self:
        """Puts the clock at the foot of the run."""
        if not self._out.as_json:
            self._out.spins(self._working)
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        why: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Takes it down again, however the run ended."""
        self._out.spins(None)

    def watches(self, agents: Iterable[AgentBase]) -> None:
        """Has everything these agents' turns say reach this.

        Args:
          agents: The agents the flow is being driven with.
        """
        for agent in agents:
            agent.watch(self.heard)

    def heard(
        self, agent: AgentBase, session: SessionBase | None, event: Event
    ) -> None:
        """Shows one thing a turn said, in whichever language is being read.

        Called from the turn's own thread, which is not the one the run was started on.

        Args:
          agent: Whose turn said it.
          session: The conversation it was said in, or None for something the agent said
            rather than one of them.
          event: What was said.
        """
        if self._out.as_json:
            self._object(agent, session, event)
            return
        self._row(agent, session, event)

    def _object(
        self, agent: AgentBase, session: SessionBase | None, event: Event
    ) -> None:
        """Puts one event on the stream a program is reading, as one object."""
        self._out.record(
            at=time.time(),
            agent=agent.id,
            cli=agent.backend,
            model=agent.config.model,
            # `named` rather than `id`: a session is named by the backend as its first turn
            # starts, and asking for the id before that raises.
            session=(session.named or "") if session is not None else "",
            kind=event.kind,
            text=event.text,
            whose=event.whose,
            # A cost in money goes here, for whoever is holding the prices.
            tokens=dict(event.tokens),
            spent=dict(event.spent),
        )

    def _row(self, agent: AgentBase, session: SessionBase | None, event: Event) -> None:
        """Shows one event as a line, or as several for something said in several."""
        whose = agent.id
        if event.kind == "begins":
            with self._lock:
                self._began[whose, id(session)] = time.monotonic()
            self._out.line(
                (f"{_SAID} ", "dim"),
                (f"{whose} is working{_where(agent, session)}", "dim"),
            )
        elif event.kind == "ends":
            with self._lock:
                started = self._began.pop((whose, id(session)), time.monotonic())
            took = time.monotonic() - started
            self._out.line(
                (f"{_WORKED} ", "dim"), (f"Worked for {took:.0f}s{_DOT}{whose}", "dim")
            )
        elif event.kind == "text":
            self._says(event.text)
        elif event.kind == "reasoning":
            for line in event.text.splitlines():
                self._out.line((line, "dim italic"))
        elif event.kind == "tool":
            named, _, about = event.text.partition(" ")
            self._out.line((f"{_SAID} ", "green"), (named, ""), (f"({about})", "dim"))
        elif event.kind == "notice":
            # humanize saying what it is doing about the turn rather than the agent working:
            # a rate limit being waited out, another account being carried on as, a turn being
            # cut off. Said in its own colour so it does not read as a tool call.
            self._out.line((f"{_SAID} ", "yellow"), (event.text, "dim"))
        elif event.kind in ("subagent", "subagent-ends"):
            named, _, about = event.text.partition(" ")
            done = "started" if event.kind == "subagent" else "done"
            self._out.line(
                (f"{_SAID} ", "cyan"), (named, ""), (f"({about}) {done}", "dim")
            )
        elif event.kind == "asks":
            self._out.line((f"{_SAID} ", "yellow"), (event.text, "yellow"))
        elif event.kind == "failed":
            self._out.line(("hmz: ", "red"), (event.text, "red"))
        elif event.kind == "result":
            self._footer(agent, event)
            if self._echoes and event.text:
                # Where the backend's own command line would have put it, and where every
                # script written against `hmz exec` before this reads it. Nothing for a turn
                # that answered nothing: a blank line is not an answer, and a script reading
                # this stream would have to know to drop it.
                self._out.answer(event.text)

    def _says(self, text: str) -> None:
        """What the agent said, on the bullet, with the rest of it set under."""
        said = text.splitlines() or [""]
        self._out.line((f"{_SAID} ", "green"), (said[0], ""))
        for line in said[1:]:
            self._out.line((f"  {line}", ""))

    def _footer(self, agent: AgentBase, event: Event) -> None:
        """What the turn cost, under the turn, for a backend that says.

        In money as well as in tokens, since nobody is watching a token count for its own
        sake. Blank rather than nought where the model is one nobody lists -- which is the
        ordinary case, the list being a few dozen models and humanize driving whatever CLI is
        installed: `$0.00` beside a turn that cost something would be a claim about a bill,
        and a wrong one.
        """
        from hmz.coganchor.agents import KINDS
        from hmz.coganchor.prices import cost, money

        if not event.spent:
            return
        # In the one order every reader of these is shown them: what went in, what came out,
        # then the cache kinds and the reasoning. A footer whose columns came out in whatever
        # order the backend happened to write them is one nobody can read two turns of.
        counted = _DOT.join(
            f"{kind} {_counted(event.spent[kind])}"
            for kind in sorted(
                event.spent,
                key=lambda kind: (
                    KINDS.index(kind) if kind in KINDS else len(KINDS),
                    kind,
                ),
            )
        )
        bill = cost(event.spent, agent.config.model)
        priced = f"{money(bill)}{_DOT}" if bill is not None else ""
        self._out.line(
            (f"{_WORKED} ", "dim"),
            (
                f"{counted}{_DOT}{priced}{agent.config.model}{_DOT}{agent.id}",
                "dim",
            ),
        )

    def _working(self) -> str:
        """What the clock at the foot of the run says now, or "" between turns.

        Counted in turns rather than in agents: an agent that has three conversations open is
        one agent and three things being waited on, and the number worth reading is how many
        are still going.
        """
        with self._lock:
            began = dict(self._began)
        if not began:
            return ""
        # The oldest of them, which is how long the run has been waiting on anything at all.
        took = time.monotonic() - min(began.values())
        if len(began) == 1:
            whose, _ = next(iter(began))
            return f"{whose} is working{_DOT}{took:.0f}s"
        return f"{many(len(began), 'turn')} working{_DOT}{took:.0f}s"


def _where(agent: AgentBase, session: SessionBase | None) -> str:
    """Which of an agent's conversations a turn is being taken in, where it has several.

    Args:
      agent: Whose turn it is.
      session: The conversation it is in, or None where the agent itself said it.

    Returns:
      Which one, counting from one, and nothing at all for an agent holding one -- there
      being nothing to tell it apart from.
    """
    held = agent.sessions
    if session is None or len(held) < 2:  # noqa: PLR2004 -- one is none to tell apart
        return ""
    at = next((one for one, other in enumerate(held) if other is session), None)
    return "" if at is None else f"{_DOT}conversation {at + 1} of {len(held)}"

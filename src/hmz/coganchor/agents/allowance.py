"""What a whole run may spend before it is stopped, and the reckoning that holds it to one.

Not :class:`hmz.coganchor.agents.Budget`, which is the cap on **one turn**. That one shortens
an answer; this one ends a run. They are two different questions and they are deliberately two
different types with two different vocabularies, because the confusion between them is a
factor of a million: ``Budget(output=2)`` is two output tokens and :class:`Allowance` counts
its tokens in millions, so a field called `output` on both would be a run stopped after two
tokens or one that ran a million times too long, and neither reads wrong at a glance.

Every flow runs under one of these whether or not the flow says anything about it. A flow
MUST NOT hold itself to a budget of its own: a cap a flow implements is a cap that only that
flow has, that reads only the tokens that flow happened to count, that no other flow's author
thought to copy, and that a person cannot set from the menu they set everything else from.
So it is held to here, off the meters every backend already feeds, at the edges of every
session of every agent of the run -- which is one place rather than one per flow.

The reckoning is polled rather than pushed. A run is read when a session starts work, when it
stops working and when it closes, which is a handful of readings a minute and costs one
`spent()` per agent apiece; pushing would mean a hook in the hot path every backend's meter
runs through, for a figure nobody reads between turns.
"""

from __future__ import annotations

import threading
import time
import weakref
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from hmz.coganchor import prices

if TYPE_CHECKING:
    from collections.abc import Iterable

    from .base import AgentBase

__all__ = [
    "DEFAULT",
    "FIELDS",
    "KEY",
    "MILLION",
    "Allowance",
    "Ledger",
    "Reading",
    "allowed",
    "unreadable",
    "unwatched",
    "written",
]

#: What :attr:`Allowance.tokens` is counted in. Millions, because a run is a day of turns and
#: a number with six zeros on it is one nobody can type without counting the zeros twice.
MILLION = 1_000_000.0

#: Which dimensions are named in :attr:`Reading.blind` and in what a person is told about
#: them. The word is the field's own, so that a message naming one is a message naming
#: something the person set.
_UNREADABLE = {
    "tokens": "no agent of this run reports what it writes",
    "dollars": "no agent of this run is running a model anybody prices",
}


@dataclass(frozen=True, slots=True, kw_only=True)
class Allowance:
    """What a whole run may spend before every session of it is stopped.

    Per run rather than per turn, which is the other half of :class:`Budget`: a cap on one
    turn shortens an answer and can be reached a thousand times in an afternoon, and what a
    person means by "this may cost me fifty dollars" is the afternoon.

    Three dimensions, because a run ends in three ways that are worth naming separately. Time
    is the only one that moves whether or not anything is being spent, and so is the only one
    that stops a flow whose turns are all failing. Output tokens are what the work itself is,
    and are the one figure every backend that counts anything counts. Money is what the person
    actually pays, and is the one of the three that cannot always be read -- a model nobody
    lists has a price of `None` and never `$0.00`.

    Nothing is capped unless it is named::

        Allowance(hours=6, dollars=50)   # six hours or fifty dollars, whichever comes first
        Allowance()                      # a run under nothing at all

    A dataclass rather than three arguments, for the reason `Budget` is one: a fourth
    dimension is a field here and a line in :meth:`over`, and written as arguments it would be
    a signature change in every place a run can be started from.

    Attributes:
      hours: Wall clock the run may take, or 0 for as long as it takes. On the clock rather
        than on the models: a run waiting on a sandbox, a rate limit or a tool is a run taking
        that long, and it is the wall clock a person is out of pocket for.
      tokens: **Millions** of output tokens the run may come out with, or 0 for as many as it
        takes. Millions because a run is counted in them, and output alone because what a run
        spends its time and most of its money on is what it writes -- its input is the
        conversation so far, sent again every request and mostly served from a cache.
      dollars: US dollars the run may cost, or 0 for whatever it costs. Never held against a
        bill of `None`: a model nobody prices is a run whose money cannot be read, which is
        said out loud rather than treated as nothing spent.

    Raises:
      ValueError: If any dimension is less than nothing, said where the allowance is written
        rather than hours into the run it was meant to hold.
    """

    hours: float = 0.0
    tokens: float = 0.0
    dollars: float = 0.0

    def __post_init__(self) -> None:
        # A negative cap would read as spent from the first reading, which is a run that stops
        # before it starts and says it ran out -- so it is refused where it is written.
        if self.hours < 0 or self.tokens < 0 or self.dollars < 0:
            raise ValueError("an allowance cannot be less than nothing")

    @property
    def bounded(self) -> bool:
        """Whether this allowance stops the run at anything at all.

        An allowance with nothing named in it is a run under none, and it costs nothing to be
        given one: nothing is added up and no meter is read for a run that cannot reach the
        end of it.
        """
        return self.hours > 0 or self.tokens > 0 or self.dollars > 0

    def over(
        self,
        *,
        seconds: float = 0.0,
        output: float = 0.0,
        dollars: float | None = None,
    ) -> str:
        """Which dimension this run has reached the end of, said the way a person reads it.

        The one place a reading is compared with an allowance, so that a dimension added is a
        field above and a line here rather than a change wherever a run is started.

        Args:
          seconds: How long the run has been going, on the clock.
          output: Output tokens it has come out with so far, counted one by one rather than
            in millions -- what a meter says is what is handed in, and the millions are this
            one's own spelling of its cap.
          dollars: What it has cost, or None where nothing in it can be priced. None never
            reaches the cap: a bill nobody can read is not a bill of nothing, and stopping a
            run on one would be stopping it for a figure that was never measured.

        Returns:
          Why the run is over its allowance -- `6h`, `2M output tokens`, `$50` -- or "" while
          it is inside every dimension it was given.
        """
        if self.hours > 0 and seconds >= self.hours * 3600:
            return f"{self.hours:g}h"
        if self.tokens > 0 and output >= self.tokens * MILLION:
            return f"{self.tokens:g}M output tokens"
        if self.dollars > 0 and dollars is not None and dollars >= self.dollars:
            return f"${self.dollars:g}"
        return ""


@dataclass(frozen=True, slots=True, kw_only=True)
class Reading:
    """What a run has spent so far, as one reckoning over every agent in it.

    Attributes:
      seconds: How long the run has been going, on the clock.
      output: Output tokens every agent of it has come out with, added up.
      dollars: What that came to, or None where nothing in the run can be priced -- never
        0.00, which would say the run had been free.
      floor: Whether the money is short of the truth, because some of the run is priced and
        some of it is not. A figure marked as a floor is one a reader can act on; one quietly
        missing an agent's bill is worse than no figure.
      blind: The dimensions this allowance names that nothing in this run can read, so that a
        cap which is never going to bite says so instead of silently never biting.
    """

    seconds: float
    output: float
    dollars: float | None
    floor: bool
    blind: frozenset[str]


class Ledger:
    """One run's spending, read off the agents driving it and held to its allowance.

    Made by whatever starts the run and hung on every agent of it, so that the reckoning is
    the run's rather than any one agent's: two agents under one allowance spend one allowance,
    which is what a person setting one means.

    Clones count. An agent cloned mid-flow "has spent nothing, is being written down nowhere"
    -- it is another agent, for tracing, and a trace is about identity. An allowance is about
    the run's money, and a clone spends the run's, so a clone is enrolled here as it is made.
    A flow that does all of its work through clones would otherwise read as having spent
    nothing at all.

    Read per agent off that agent's own meter rather than per model off a tally, which is what
    keeps one run behind a gateway from being counted twice: the same turns can be reported
    under two spellings of one model -- `claude-haiku-4-5-20251001` from the log and
    `azure/anthropic/claude-haiku-4-5` from the backend -- and anything adding up by model name
    can double them. There is one meter per agent and every agent is counted once.
    """

    def __init__(self, allowance: Allowance, agents: Iterable[AgentBase] = ()) -> None:
        """Starts the reckoning, with the clock running from here.

        Args:
          allowance: What the run may spend.
          agents: The agents it is driving, which a clone of any of them joins later.
        """
        self._allowance = allowance
        self._began = time.monotonic()
        self._lock = threading.RLock()
        #: Weakly held, so that a flow which opens ten thousand clones and drops them is a
        #: ledger of what they spent rather than ten thousand agents nobody can collect.
        #: What a dropped agent spent goes with it, which is the same answer `spent()` gives
        #: for an agent nobody holds.
        self._agents: weakref.WeakSet[AgentBase] = weakref.WeakSet(agents)
        self._why = ""
        self._stopping = False

    @property
    def allowance(self) -> Allowance:
        """What this run may spend, as it was set."""
        return self._allowance

    @property
    def began(self) -> float:
        """The monotonic clock this run's hours are counted from."""
        return self._began

    def enrol(self, agent: AgentBase) -> None:
        """Counts an agent's spending toward this run from here on.

        Args:
          agent: The agent, which is one the run was started with or one cloned from it.
        """
        with self._lock:
            self._agents.add(agent)

    def agents(self) -> tuple[AgentBase, ...]:
        """Every agent still enrolled, as a tuple nothing else can change under a reader."""
        with self._lock:
            return tuple(self._agents)

    def reads(self) -> Reading:
        """What the run has spent up to this moment.

        Returns:
          The reckoning, with the money left as None rather than added up as zero where
          nothing in the run is priced.
        """
        enrolled = self.agents()
        output = 0.0
        billed: list[float] = []
        priced = 0
        counted = 0
        for agent in enrolled:
            usage = agent.spent()
            output += usage.output
            if "output" in type(agent).counts:
                counted += 1
            if prices.price(agent.config.model) is not None:
                priced += 1
                money = prices.cost(usage, agent.config.model)
                if money is not None:
                    billed.append(money)
        blind: set[str] = set()
        if self._allowance.tokens > 0 and enrolled and not counted:
            blind.add("tokens")
        if self._allowance.dollars > 0 and enrolled and not priced:
            blind.add("dollars")
        return Reading(
            seconds=time.monotonic() - self._began,
            output=output,
            # None rather than 0.00 where nothing could be priced, which is a bill nobody can
            # read and not a run that was free.
            dollars=sum(billed) if billed else None,
            floor=bool(billed) and priced < len(enrolled),
            blind=frozenset(blind),
        )

    def over(self) -> str:
        """Why this run is over its allowance, or "" while it is still inside it.

        Held once it is true: an allowance only ever runs out -- time and tokens rise and
        never fall -- so the first reading that says so is the answer from then on, and a
        second reading that happened to come back short would be a run that unstopped itself.

        Returns:
          The dimension it ran out of, in words, or "".
        """
        with self._lock:
            if self._why or not self._allowance.bounded:
                return self._why
        read = self.reads()
        why = self._allowance.over(
            seconds=read.seconds, output=read.output, dollars=read.dollars
        )
        with self._lock:
            if why and not self._why:
                self._why = why
            return self._why

    @property
    def spent(self) -> bool:
        """Whether this run has already been found to be over its allowance.

        Read rather than reckoned: this asks what the last reading said, so that whatever is
        writing the run down can say how it ended without taking a reading of its own.
        """
        with self._lock:
            return bool(self._why)

    def stops(self) -> None:
        """Stops every agent of the run, once, because the allowance is spent.

        The allowance is the run's, so the moment one session reads it full it is full for
        every session at once -- there is no set of blocked sessions to wait for. What this
        does is the waiting, all at once: every agent is stopped, which closes every session
        it holds, so a turn running elsewhere ends too rather than going on spending money the
        run has not got.

        Once and once only, and the flag is set before anything is stopped: stopping an agent
        closes its sessions, and a session closing reads the ledger, so a second pass through
        here is the ordinary way in rather than an unlikely one.
        """
        with self._lock:
            if self._stopping:
                return
            self._stopping = True
            enrolled = tuple(self._agents)
        for agent in enrolled:
            agent.stop()


#: What a flow runs under when neither it nor the person running it said anything: no cap at
#: all. A shipped non-zero default would cut off `chat`, and every flow written before there
#: was such a thing, in the middle of its first run -- which is a cap nobody chose taking work
#: away. What catches an unbounded run instead is being asked about it: :func:`unwatched`.
DEFAULT = Allowance()

#: What an allowance written down is filed under, in a YAML file of a flow's settings and in
#: what a workspace remembers. One word, and it is the word the person set it under.
KEY = "budget"

#: The three fields, as a file spells them. Named here rather than read off the dataclass so
#: that a file naming a fourth is refused with the three there are.
FIELDS = ("hours", "tokens", "dollars")


def written(said: object, where_: str = "") -> Allowance:
    """Reads a run's allowance out of what a file or a settings entry says.

    Refuses a bare number outright, and says both things it could have meant. Every flowverse
    loop used to take `budget: 25` meaning twenty-five million output tokens for that flow,
    and the same line now would have to mean one of three quantities. Read as any of them it
    would be a run held to something nobody asked for, so it is refused and named.

    Args:
      said: What was written: an allowance already, or a mapping of the three fields.
      where_: The file it was written in, for saying which one to correct.

    Returns:
      The allowance.

    Raises:
      ValueError: If it is not a mapping of the fields there are, or if any of them is not a
        non-negative number.
    """
    if isinstance(said, Allowance):
        return said
    at = f"{where_}: " if where_ else ""
    if not isinstance(said, Mapping):
        # One number could be any of the three, and a run held to the wrong one stops a
        # thousand times too early or never. So it is refused, with all three said.
        raise ValueError(  # noqa: TRY004 -- a file to correct, not a caller's type error
            f"{at}{KEY} is {', '.join(FIELDS)} rather than one number -- "
            f"`{KEY}: {{tokens: 25}}` for 25 million output tokens, "
            f"`{KEY}: {{hours: 25}}` for a day of it, `{KEY}: {{dollars: 25}}` for the money"
        )
    held = cast("Mapping[str, object]", said)
    if unknown := [name for name in held if name not in FIELDS]:
        raise ValueError(
            f"{at}{KEY} takes {', '.join(FIELDS)}, not {', '.join(sorted(unknown))}"
        )
    read: dict[str, float] = {}
    for name in FIELDS:
        if (value := held.get(name)) is None:
            continue
        # `bool` first, because a `True` is an `int` in Python and `hours: true` is a file to
        # correct rather than a run of one hour.
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(  # noqa: TRY004 -- a file to correct, not a caller's type error
                f"{at}{KEY}.{name} is a number, not {value!r}"
            )
        read[name] = float(value)
    try:
        return Allowance(**read)
    except ValueError as why:
        raise ValueError(f"{at}{KEY}: {why}") from why


def allowed(
    given: Allowance | Mapping[str, object] | None, declared: Allowance | None
) -> Allowance:
    """What a run is actually held to, out of what was asked for and what the flow said.

    The one place the three sources are ranked, so that a run started from a command line, a
    run started from the menu and a run started from another flow all land on one answer:
    whoever started it wins, else the flow's own default, else nothing at all.

    Args:
      given: What the line, the file or the menu said, or None for neither.
      declared: What the flow said where it was marked, or None for a flow with no opinion.

    Returns:
      The allowance the run is held to.

    Raises:
      ValueError: If what was given cannot be read as one.
    """
    if given is not None:
        return written(given)
    return declared if declared is not None else DEFAULT


def unreadable(blind: Iterable[str]) -> str:
    """What to tell somebody about a cap nothing in their run can read.

    Said rather than left silent, because a cap that will never bite reads exactly like a cap
    that has not bitten yet: a person who set a fifty-dollar limit on a model nobody prices
    has a run with no limit on it and no way of knowing.

    Args:
      blind: The dimensions nothing can read, as :attr:`Reading.blind` names them.

    Returns:
      One line about them, or "" where every cap that was set can be read.
    """
    said = [f"{name} ({_UNREADABLE[name]})" for name in FIELDS if name in set(blind)]
    return f"nothing here can read {' or '.join(said)}" if said else ""


def unwatched(effective: Allowance, declared: Allowance | None) -> bool:
    """Whether a run under this allowance would have nothing at all to stop it.

    The one place the question is asked, so that the menu asking somebody to confirm and the
    command line saying so on its way past are asking the same thing. A flow is exempt by
    declaring `@flow(budget=Allowance())` -- saying in its own file that it is meant to run
    unbounded, which is what `chat` is -- rather than by being named in a table here, in the
    menu and in the command line, where three copies of one list is three places to forget.

    Args:
      effective: What the run will actually be held to.
      declared: What the flow itself said, or None for a flow with no opinion.

    Returns:
      Whether nothing will stop this run and nobody has said that is what they meant.
    """
    return not effective.bounded and declared is None

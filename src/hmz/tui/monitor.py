"""What a flow is doing, kept as it happens: who is working, who handed to whom, and cost.

None of this is asked of the agents. A flow drives them and they answer; what is watched here
is the turns going past, which is the only place the order of a flow is ever visible -- the
flow itself is a Python file that could branch any way it likes.
"""

from __future__ import annotations

import threading
import time
from collections import Counter, deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from hmz.coganchor import prices

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = ["Monitor", "Shape", "Spend", "Under", "lasting", "short", "thousands"]

#: How far back the rate is measured. Five minutes is long enough to carry across the gaps a
#: flow leaves -- a turn that thinks, a round it sleeps off, a commit it makes -- and short
#: enough that a run which has gone quiet reads as quiet.
_WINDOW = 300.0

#: Where a count stops fitting and starts being abbreviated.
_THOUSAND = 1000
_MILLION = 1_000_000

#: What a clock is read in, in the units the seconds it is given are.
_MINUTE = 60.0
_HOUR = 3600.0


def thousands(count: int) -> str:
    """Renders a token count short enough for a status line.

    Args:
      count: How many tokens.

    Returns:
      The count, abbreviated once it stops fitting.
    """
    if count < _THOUSAND:
        return str(count)
    if count < _MILLION:
        return f"{count / _THOUSAND:.1f}k"
    return f"{count / _MILLION:.2f}M"


def lasting(seconds: float) -> str:
    """How long something has been going, as a box on the diagram says it.

    Args:
      seconds: How long, in seconds.

    Returns:
      Seconds under a minute, minutes and seconds under an hour, and hours and minutes above
      it -- the second figure always two digits, so that a box does not shuffle its contents
      sideways every time a clock in it ticks past ten.
    """
    if seconds < _MINUTE:
        # Cut rather than rounded: a clock that read 60s for the half-second before it read
        # 1m00s would be a box counting past the unit it is in.
        return f"{int(seconds)}s"
    if seconds < _HOUR:
        return f"{int(seconds // _MINUTE)}m{int(seconds % _MINUTE):02d}s"
    return f"{int(seconds // _HOUR)}h{int(seconds % _HOUR // _MINUTE):02d}m"


def short(agent: str) -> str:
    """An agent's name, cut down to what fits beside a transcript.

    Args:
      agent: The agent id, which is a Chrysos Heir's codename unless it was named.

    Returns:
      Something recognisable and narrow.
    """
    kind, _, tail = agent.partition("#")
    if not tail:  # a flow that named its agents said what it wanted them called
        return agent[:16]
    backend = kind.removesuffix("Agent").removesuffix("CLI").removesuffix("Code")
    return f"{backend.lower()}#{tail[:4]}"


@dataclass(frozen=True, slots=True)
class Under:
    """One agent a flow's own agent started of its own, which is what a subagent is.

    Not an agent of the flow. Nobody chose what it runs, nothing can be said to it and it has
    no transcript of its own -- it is a thing the agent above it is doing, and it is drawn as
    one. What is known of it is what its backend said on the way past.

    Attributes:
      whose: The backend's own id for it, which is what pairs the one that started with the
        one that ended.
      about: What it was asked to do, as its backend said it.
      working: Whether it is still going.
    """

    whose: str
    about: str
    working: bool = True


@dataclass(frozen=True, slots=True)
class Shape:
    """The directed graph of a run so far, taken whole so a reader never sees it mid-change.

    Which is the shape of the flow, and the only place it is ever visible: a flow is a Python
    file that may branch any way it likes, so what it did is read off the turns going past
    rather than asked of it.

    Attributes:
      turns: How many turns each agent that has worked has taken.
      working: Which of them have a turn open right now.
      handovers: How often each agent handed on to each other agent, as the flow went from
        one to the next.
      under: The agents each of them has started of its own, oldest first -- the ones still
        going and the ones that have finished, since a fleet that vanished as it landed would
        be a turn nobody could see the shape of afterwards.
      since: How long each of them has been at what it is doing, in seconds: the turn it has
        open, or the wait since its last turn ended for one that has stopped. Worked out
        where the rest of the graph is taken, so that a diagram is one moment of the run
        rather than a clock per box read at a different one.
      latest: The handover the flow took most recently, or None before it has taken one. It
        is what the eye wants first with six boxes on the page -- where the run just went --
        and nothing else on a still picture says it.
    """

    turns: Mapping[str, int]
    working: frozenset[str]
    handovers: Mapping[tuple[str, str], int]
    under: Mapping[str, tuple[Under, ...]] = field(
        default_factory=dict[str, tuple[Under, ...]]
    )
    since: Mapping[str, float] = field(default_factory=dict[str, float])
    latest: tuple[str, str] | None = None


@dataclass(frozen=True, slots=True)
class Spend:
    """What one model has cost so far, in tokens and in money, and how fast.

    Attributes:
      model: The model the tokens were spent on.
      tokens: Every token spent on it, in and out alike.
      rate: Tokens a second over the last five minutes, or over the whole run while the run
        is younger than that. Seconds on the clock, not seconds an agent was talking: a flow
        sleeps between rounds, commits, reads what the last turn wrote, and that time is time
        the tokens were spent over.
      dollars: What those tokens came to, or None where nobody prices this model or the
        source that counted them did not say which kind each was. None is not nothing spent:
        a reader MUST show the tokens alone rather than a bill of zero.
    """

    model: str
    tokens: int
    rate: float
    dollars: float | None = None


@dataclass
class Monitor:
    """The running state of one flow, written from the turns and read by the interface."""

    #: Who is working right now, counted rather than listed: an agent may hold two sessions,
    #: and one of them ending does not mean the agent has stopped.
    working: Counter[str] = field(default_factory=Counter[str])
    #: How many turns each agent has taken.
    turns: Counter[str] = field(default_factory=Counter[str])
    #: Which agent handed to which, and how often, as the flow went from one to the next.
    handovers: Counter[tuple[str, str]] = field(
        default_factory=Counter[tuple[str, str]]
    )
    #: The model each agent runs at, so that spending can be named by model.
    models: dict[str, str] = field(default_factory=dict[str, str])
    #: The agents each of them has started of its own, in the order they started, by the
    #: backend's own id for each. A dict rather than a list: one ends by name, and a fleet of
    #: forty would be a list searched forty times.
    fleets: dict[str, dict[str, Under]] = field(
        default_factory=dict[str, dict[str, Under]]
    )
    #: When the turn each working agent has open began, by agent. Only the ones working are
    #: in it: a turn that is over is not a clock anybody is reading.
    opened: dict[str, float] = field(default_factory=dict[str, float])
    #: And when each one's last turn ended, which is what the clock on a stopped agent counts
    #: from -- an agent that has been quiet four minutes is the one a reader is looking for.
    rested: dict[str, float] = field(default_factory=dict[str, float])
    #: The handover taken most recently, so the arrow it went along can be drawn lit.
    handed: tuple[str, str] | None = None
    #: Tokens spent per model, all told.
    spent: Counter[str] = field(default_factory=Counter[str])
    #: What each source says has been spent on each model so far. Two of them say: the
    #: backends, as each turn ends, and the logs those backends keep, as they write them. They
    #: are counting the same tokens, so what was spent is the higher of the two rather than
    #: the sum -- and whichever has seen further is the one that is right.
    totals: dict[tuple[str, str], int] = field(
        default_factory=dict[tuple[str, str], int]
    )
    #: And what each of those totals was made of, by kind of token, for the sources that say.
    #: Money needs the kinds: an input token and an output token of one model differ in price
    #: by five or ten times, so a lump of tokens is a lump nobody can put a figure on.
    kinds: dict[tuple[str, str], dict[str, float]] = field(
        default_factory=dict[tuple[str, str], dict[str, float]]
    )
    #: Recent spending as (when, model, tokens), which is what the rate is measured over.
    #: Bounded by the window rather than by the length of the run: a flow going for days
    #: keeps five minutes of it.
    recent: deque[tuple[float, str, int]] = field(
        default_factory=deque[tuple[float, str, int]]
    )
    #: The rate per model as it was last worked out, and what it was worked out from: the rate
    #: is worked out again when something it is made of moves, and not on any clock of its own.
    rates: dict[str, float] = field(default_factory=dict[str, float])
    #: And the money, worked out at the same moment and from the same tokens.
    money: dict[str, float | None] = field(default_factory=dict[str, float | None])
    figured: int | None = None
    #: How many times what has been spent has changed, which is what `figured` is against.
    changed: int = 0
    #: When the run began, which is when this was made: one of these is made for one flow.
    began: float = field(default_factory=time.monotonic)
    #: When it ended, or None while it is still going -- so that a run that is over reads as
    #: what it was doing when it ended rather than as a rate decaying to nothing after it.
    until: float | None = None
    #: The agent whose turn ended last, which is who the next one was handed from.
    _last: str | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def begins(self, agent: str, model: str, now: float | None = None) -> None:
        """Notes that an agent has started a turn.

        Args:
          agent: Whose turn it is.
          model: The model that agent runs at.
          now: When, defaulting to this moment. Given only so a test can say.
        """
        with self._lock:
            self.models[agent] = model
            # The clock starts on the first turn an agent has open and not on the second: an
            # agent driving two sessions at once has been working since the earlier of them
            # began, and starting it again there would read as a turn that keeps beginning.
            if not self.working[agent]:
                self.opened[agent] = time.monotonic() if now is None else now
            self.working[agent] += 1
            self.turns[agent] += 1
            if self._last is not None and self._last != agent:
                self.handovers[self._last, agent] += 1
                self.handed = (self._last, agent)

    def ends(self, agent: str, now: float | None = None) -> None:
        """Notes that an agent's turn is over, and that it is the one to hand on from.

        Args:
          agent: Whose turn ended.
          now: When, defaulting to this moment. Given only so a test can say.
        """
        with self._lock:
            if self.working[agent] <= 1:
                del self.working[agent]
                self.opened.pop(agent, None)
                self.rested[agent] = time.monotonic() if now is None else now
            else:
                self.working[agent] -= 1
            self._last = agent

    def started(self, agent: str, whose: str, about: str) -> None:
        """Notes that an agent has started an agent of its own.

        Args:
          agent: Whose fleet it is.
          whose: The backend's own id for the one that started.
          about: What it was asked to do.
        """
        with self._lock:
            self.fleets.setdefault(agent, {})[whose] = Under(whose, about)

    def finished(self, agent: str, whose: str, about: str = "") -> None:
        """Notes that one of those has come back.

        Kept rather than forgotten: a fleet that vanished as it landed would be a turn nobody
        could see the shape of afterwards. One that ended without ever being seen to start --
        a backend that says only the one half, a turn watched from part way through -- is
        written down as having ended, since it did.

        Args:
          agent: Whose fleet it is.
          whose: The backend's own id for the one that ended.
          about: What it was asked to do, for one nothing saw start.
        """
        with self._lock:
            held = self.fleets.setdefault(agent, {})
            was = held.get(whose)
            held[whose] = Under(
                whose, was.about if was is not None else about, working=False
            )

    def stops(self) -> None:
        """Notes that the run is over, which is what stops the clock the rate is read at."""
        with self._lock:
            self.until = time.monotonic()
            self.figured = None  # so the last rate shown is the one it ended on

    def spend(
        self,
        agent: str,
        tokens: int,
        model: str | None = None,
        now: float | None = None,
        kinds: Mapping[str, float] | None = None,
    ) -> None:
        """Notes tokens an agent's backend has just reported spending.

        Args:
          agent: Who spent them.
          tokens: How many, in and out together.
          model: What they were spent on, if the backend said. What it says beats what the
            agent was configured with: a turn that reached for a sub-agent spent it there.
          now: When, defaulting to this moment. Given only so a test can say.
          kinds: What those same tokens were, kind by kind, where the backend said. Only the
            kinds put a price on them, an input token and an output token of one model
            differing in price several times over.
        """
        if tokens <= 0:
            return
        if model is not None:
            self.models[agent] = model
        model = self.models.get(agent, agent)
        # The whole read-modify-write under the lock: two turns of one model land on two
        # threads, and a total each of them read before either wrote is a turn lost.
        with self._lock:
            # Added up here rather than there, so that what a backend reports a turn at a
            # time arrives as the same kind of thing a log read from the top does: a total.
            running = self.totals.get(("told", model), 0) + tokens
            broken = dict(self.kinds.get(("told", model), {}))
            for kind, spent in (kinds or {}).items():
                broken[kind] = broken.get(kind, 0.0) + spent
            # Whatever the kinds did not account for still cost something, and is put under
            # no kind at all rather than guessed at as one: what is priced is then a floor.
            if (rest := tokens - sum((kinds or {}).values())) > 0:
                broken[""] = broken.get("", 0.0) + rest
            self._counted("told", model, running, now, broken or None)

    def counted(
        self,
        source: str,
        model: str,
        total: int,
        now: float | None = None,
        kinds: Mapping[str, float] | None = None,
    ) -> None:
        """Notes what one source has now seen spent on one model, all told.

        A total rather than an addition, because a log is read again and again: what it says
        the second time is what it said the first time and more, and adding that would count
        the first of it twice.

        Args:
          source: Who says so, which is either the backends or their logs.
          model: What the tokens were spent on.
          total: Every token that source has seen spent on it.
          now: When, defaulting to this moment. Given only so a test can say.
          kinds: The same total broken into the kinds of token it went on, where this source
            says which. A total rather than an addition, for the reason `total` is one.
        """
        with self._lock:
            self._counted(source, model, total, now, kinds)

    def _counted(
        self,
        source: str,
        model: str,
        total: int,
        now: float | None,
        kinds: Mapping[str, float] | None,
    ) -> None:
        """The whole of `counted`, with the lock already held by whoever called."""
        was = self.totals.get((source, model), 0)
        broken = dict(kinds) if kinds else None
        # A breakdown that has changed is worth having even where the total has not moved:
        # one source may say a lump where another says what the lump was made of, and the
        # money is worked out from whichever of them said.
        moved = broken != self.kinds.get((source, model))
        if total <= was and not moved:
            return
        # Written even where it has not risen, and even where it is nought: what is spent is
        # the most any source has seen, and a source with no entry at all is one there is no
        # max to take. A log read again from the top says less than it did, and keeps what
        # it said.
        self.totals[(source, model)] = max(total, was)
        if moved:
            # Replaced rather than merged, and dropped where a source has stopped saying:
            # a breakdown outliving the total it described would price a bigger total
            # against a smaller reckoning of what went into it.
            if broken is None:
                self.kinds.pop((source, model), None)
            else:
                self.kinds[(source, model)] = broken
            self.changed += 1  # so that what it is worth is worked out again
        # The most any source has seen, which is what has been spent: two sources counting
        # the same tokens are not two lots of tokens.
        seen = max(held for (_, named), held in self.totals.items() if named == model)
        if (risen := seen - self.spent[model]) <= 0:
            return
        self.spent[model] = seen
        self.recent.append((time.monotonic() if now is None else now, model, risen))
        self.changed += 1

    def spending(self, now: float | None = None) -> list[Spend]:
        """What each model has cost, and how fast, biggest spender first.

        Args:
          now: The moment to measure the rate at, defaulting to this one.

        Returns:
          One entry per model anything has been spent on. How fast is worked out again when
          something it is made of has moved -- tokens counted, or old ones falling out of the
          window -- and stands the rest of the time, rather than being worked out on a clock.
        """
        moment = time.monotonic() if now is None else now
        if self.until is not None:
            moment = min(
                moment, self.until
            )  # a run that is over is read at its own end
        with self._lock:
            aged = False
            while self.recent and self.recent[0][0] < moment - _WINDOW:
                self.recent.popleft()
                aged = True
            if aged or self.figured != self.changed:
                # Seconds on the clock: the window holds the turns and the flow's own code
                # alike, so what a flow spent between two turns -- sleeping off a round,
                # committing, reading what the last turn wrote -- is time it is measured over.
                # Under five minutes old, the run itself is the window it has had.
                over = min(_WINDOW, moment - self.began)
                lately: Counter[str] = Counter()
                for _, model, tokens in self.recent:
                    lately[model] += tokens
                self.rates = {
                    model: lately[model] / over if over > 0 else 0.0
                    for model in self.spent
                }
                # Priced here rather than as it is drawn: the prices are read off the disk,
                # and a screen redrawn twice a second must not pay for that twice a second.
                self.money = {model: self._priced(model) for model in self.spent}
                self.figured = self.changed
            return [
                Spend(
                    model=model,
                    tokens=tokens,
                    rate=self.rates.get(model, 0.0),
                    dollars=self.money.get(model),
                )
                for model, tokens in self.spent.most_common()
            ]

    def _priced(self, model: str) -> float | None:
        """What has been spent on one model, in money. Held under the lock by its callers.

        The kinds come from whichever source said the kind of the most tokens, and where two
        said as much, from the one that has seen the most: two sources counting the same
        tokens are one bill, so the fullest reckoning that can be priced is the one to price
        -- and a total nobody broke down is no reckoning at all rather than the biggest one.

        Args:
          model: The model.

        Returns:
          Dollars, or None where nobody lists this model or no source said which kind each
          token was -- which a reader shows as tokens alone rather than as nothing spent.
          What comes back is a floor: tokens no source said the kind of are left out of it.
        """
        fullest: Mapping[str, float] | None = None
        best = (-1.0, -1.0)
        for (source, named), held in self.totals.items():
            if named != model:
                continue
            broken = self.kinds.get((source, model))
            if broken is None:
                continue
            # How much of its total that source actually said the kind of, which is what
            # ranks a log against the backend that keeps it: the fullest *priceable*
            # reckoning wins, since a source whose whole total is tokens of no named kind
            # can be priced at nothing at all however many of them it has seen.
            told = sum(count for kind, count in broken.items() if kind)
            if (told, held) > best:
                best, fullest = (told, held), broken
        return prices.cost(fullest, model) if fullest else None

    def now_working(self) -> list[str]:
        """Who has a turn open, taken whole so that a reader never sees it mid-change.

        Returns:
          The agents working, in a settled order.
        """
        with self._lock:
            return sorted(self.working)

    def shape(self) -> Shape:
        """The run as a graph: who has worked, who is working, who handed to whom.

        Taken under the lock and copied out of it, so that whatever draws it is drawing one
        moment of the run rather than three moments of three counters.

        Returns:
          The graph, which is what the diagram on `/monitor` is drawn from.
        """
        # A run that is over is read at its own end, as the rate is: a diagram whose clocks
        # went on counting after the last turn would say the flow was still doing something.
        moment = time.monotonic() if self.until is None else self.until
        with self._lock:
            return Shape(
                turns=dict(self.turns),
                working=frozenset(self.working),
                handovers=dict(self.handovers),
                under={
                    agent: tuple(held.values())
                    for agent, held in self.fleets.items()
                    if held
                },
                since={
                    agent: max(0.0, moment - self._counting_from(agent))
                    for agent in self.turns
                },
                latest=self.handed,
            )

    def _counting_from(self, agent: str) -> float:
        """When one agent's clock started, which is what makes its box say a length of time.

        Read under the caller's lock, since it is taken where the rest of the graph is.

        Args:
          agent: The agent.

        Returns:
          When its open turn began, or when its last turn ended for one that has stopped --
          and when the run began for one that has neither, which is an agent whose turns were
          already going when this started watching.
        """
        if (opened := self.opened.get(agent)) is not None:
            return opened
        return self.rested.get(agent, self.began)

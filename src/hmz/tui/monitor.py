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

__all__ = ["Monitor", "Spend", "short", "thousands"]

#: How far back the rate is measured. Five minutes is long enough to carry across the gaps a
#: flow leaves -- a turn that thinks, a round it sleeps off, a commit it makes -- and short
#: enough that a run which has gone quiet reads as quiet.
_WINDOW = 300.0

#: Where a count stops fitting and starts being abbreviated.
_THOUSAND = 1000
_MILLION = 1_000_000


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


def short(agent: str) -> str:
    """An agent's name, cut down to what fits beside a transcript.

    Args:
      agent: The agent id, which is its class and a hex tail unless it was named.

    Returns:
      Something recognisable and narrow.
    """
    kind, _, tail = agent.partition("#")
    if not tail:  # a flow that named its agents said what it wanted them called
        return agent[:16]
    backend = kind.removesuffix("Agent").removesuffix("CLI").removesuffix("Code")
    return f"{backend.lower()}#{tail[:4]}"


@dataclass(frozen=True, slots=True)
class Spend:
    """What one model has cost so far, and how fast it is costing it.

    Attributes:
      model: The model the tokens were spent on.
      tokens: Every token spent on it, in and out alike.
      rate: Tokens a second over the last five minutes, or over the whole run while the run
        is younger than that. Seconds on the clock, not seconds an agent was talking: a flow
        sleeps between rounds, commits, reads what the last turn wrote, and that time is time
        the tokens were spent over.
    """

    model: str
    tokens: int
    rate: float


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
    #: Tokens spent per model, all told.
    spent: Counter[str] = field(default_factory=Counter[str])
    #: What each source says has been spent on each model so far. Two of them say: the
    #: backends, as each turn ends, and the logs those backends keep, as they write them. They
    #: are counting the same tokens, so what was spent is the higher of the two rather than
    #: the sum -- and whichever has seen further is the one that is right.
    totals: dict[tuple[str, str], int] = field(
        default_factory=dict[tuple[str, str], int]
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

    def begins(self, agent: str, model: str) -> None:
        """Notes that an agent has started a turn.

        Args:
          agent: Whose turn it is.
          model: The model that agent runs at.
        """
        with self._lock:
            self.models[agent] = model
            self.working[agent] += 1
            self.turns[agent] += 1
            if self._last is not None and self._last != agent:
                self.handovers[self._last, agent] += 1

    def ends(self, agent: str) -> None:
        """Notes that an agent's turn is over, and that it is the one to hand on from.

        Args:
          agent: Whose turn ended.
        """
        with self._lock:
            if self.working[agent] <= 1:
                del self.working[agent]
            else:
                self.working[agent] -= 1
            self._last = agent

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
    ) -> None:
        """Notes tokens an agent's backend has just reported spending.

        Args:
          agent: Who spent them.
          tokens: How many, in and out together.
          model: What they were spent on, if the backend said. What it says beats what the
            agent was configured with: a turn that reached for a sub-agent spent it there.
          now: When, defaulting to this moment. Given only so a test can say.
        """
        if tokens <= 0:
            return
        if model is not None:
            self.models[agent] = model
        model = self.models.get(agent, agent)
        # Added up here rather than there, so that what a backend reports a turn at a time
        # arrives as the same kind of thing a log read from the top does: a total.
        self.counted("told", model, self.totals.get(("told", model), 0) + tokens, now)

    def counted(
        self, source: str, model: str, total: int, now: float | None = None
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
        """
        with self._lock:
            if total <= self.totals.get((source, model), 0):
                return
            self.totals[(source, model)] = total
            # The most any source has seen, which is what has been spent: two sources counting
            # the same tokens are not two lots of tokens.
            seen = max(
                held for (_, named), held in self.totals.items() if named == model
            )
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
                self.figured = self.changed
            return [
                Spend(model=model, tokens=tokens, rate=self.rates.get(model, 0.0))
                for model, tokens in self.spent.most_common()
            ]

    def now_working(self) -> list[str]:
        """Who has a turn open, taken whole so that a reader never sees it mid-change.

        Returns:
          The agents working, in a settled order.
        """
        with self._lock:
            return sorted(self.working)

    def graph(self) -> list[str]:
        """The agents this flow has run, and what handed to what, as lines to show.

        Returns:
          One line per agent, marked if it is working, then one per handover -- which together
          are the directed graph of the run so far, drawn as an adjacency list because that is
          what stays readable in a corner of a screen.
        """
        with self._lock:
            lines = [
                f"{'▶' if agent in self.working else '·'} {short(agent)}"
                f"  [dim]×{taken}[/dim]"
                for agent, taken in self.turns.most_common()
            ]
            lines += [
                f"  [dim]{short(sender)} → {short(taker)} ×{often}[/dim]"
                for (sender, taker), often in self.handovers.most_common()
            ]
            return lines

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

__all__ = ["Monitor", "Spend", "short"]

#: How far back the rate is measured. Long enough to survive the gap between two turns, short
#: enough that a flow which has stopped reads as stopped.
_WINDOW = 30.0


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
      rate: Tokens a second over the last window, which is zero once it falls quiet.
    """

    model: str
    tokens: int
    rate: float


@dataclass
class Monitor:
    """The running state of one flow, written from the turns and read by the interface."""

    #: Who is working right now, counted rather than listed: an agent may hold two sessions,
    #: and one of them ending does not mean the agent has stopped.
    working: Counter[str] = field(default_factory=Counter)
    #: How many turns each agent has taken.
    turns: Counter[str] = field(default_factory=Counter)
    #: Which agent handed to which, and how often, as the flow went from one to the next.
    handovers: Counter[tuple[str, str]] = field(default_factory=Counter)
    #: The model each agent runs at, so that spending can be named by model.
    models: dict[str, str] = field(default_factory=dict)
    #: Tokens spent per model, all told.
    spent: Counter[str] = field(default_factory=Counter)
    #: Recent spending as (when, model, tokens), for the rate. Bounded by the window, not by
    #: the length of the run: a flow going for days keeps a few seconds of history.
    recent: deque[tuple[float, str, int]] = field(default_factory=deque)
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

    def spend(
        self,
        agent: str,
        tokens: int,
        model: str | None = None,
        now: float | None = None,
    ) -> None:
        """Notes tokens spent by an agent, on whichever model it ran them on.

        Args:
          agent: Who spent them.
          tokens: How many, in and out together.
          model: What they were spent on, if the backend said. What it says beats what the
            agent was configured with: a turn that reached for a sub-agent spent it there.
          now: When, defaulting to this moment. Given only so a test can say.
        """
        if tokens <= 0:
            return
        with self._lock:
            if model is not None:
                self.models[agent] = model
            model = self.models.get(agent, agent)
            self.spent[model] += tokens
            self.recent.append(
                (time.monotonic() if now is None else now, model, tokens)
            )

    def spending(self, now: float | None = None) -> list[Spend]:
        """What each model has cost, and how fast, biggest spender first.

        Args:
          now: The moment to measure the rate at, defaulting to this one.

        Returns:
          One entry per model anything has been spent on.
        """
        moment = time.monotonic() if now is None else now
        with self._lock:
            while self.recent and self.recent[0][0] < moment - _WINDOW:
                self.recent.popleft()
            lately: Counter[str] = Counter()
            for _, model, tokens in self.recent:
                lately[model] += tokens
            return [
                Spend(model=model, tokens=tokens, rate=lately[model] / _WINDOW)
                for model, tokens in self.spent.most_common()
            ]

    def now_working(self) -> list[str]:
        """Who has a turn open, taken whole so that a reader never sees it mid-change.

        Returns:
          The agents working, in a settled order.
        """
        with self._lock:
            return sorted(self.working)

    def has_run(self) -> bool:
        """Whether this flow has run anything at all.

        Returns:
          Whether there is anything to show beside the transcript.
        """
        with self._lock:
            return bool(self.turns)

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

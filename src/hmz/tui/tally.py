"""What a run has cost, read from the logs the agents keep for themselves.

A backend says what a turn cost when the turn ends, and a turn is minutes long -- so a number
taken from that alone stands still for most of a run, and moves in one jump at the end of it.
The CLIs write their own usage down as they go, a row per request to the model, and this reads
it there instead: the same tokens, as they are spent rather than once they are done being spent.

Reading is not being told. What is read is what the session has spent all told, so it is
reported as a total rather than as an addition, and a log read twice cannot count a token
twice -- which is also what lets the backends' own reports stand beside it: the two are
counting the same tokens, and whichever has seen more is what has been spent.
"""

from __future__ import annotations

import json
import threading
from collections import Counter
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, cast

from hmz.coganchor import backends

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from hmz.coganchor.agents import AgentBase

    from .monitor import Monitor

__all__ = ["Tally"]

#: How often the logs are looked at. Often enough that a turn's spending shows while the turn
#: is still running, and cheap because only what has been appended since is ever read.
_EVERY = 1.0


#: What each backend's log calls each kind of token. A kind is named the same thing wherever
#: it is counted, so that one flow reading two backends reads one word for one thing -- and
#: so that the prices, which are per kind, can be put against any of them. Codex's rollout is
#: the odd one out: its `input_tokens` has the cached reads inside it, so the read is taken
#: back out rather than paid for twice.
_KINDS: dict[str, tuple[tuple[str, str], ...]] = {
    "claude": (
        ("input", "input_tokens"),
        ("output", "output_tokens"),
        ("cache_read", "cache_read_input_tokens"),
        ("cache_write", "cache_creation_input_tokens"),
    ),
    "dsh": (
        ("input", "inputTokens"),
        ("output", "outputTokens"),
        ("cache_read", "cacheReadTokens"),
        ("cache_write", "cacheWriteTokens"),
    ),
    "zcode": (("input", "inputTokens"), ("output", "outputTokens")),
    "codex": (
        ("input", "input_tokens"),
        ("output", "output_tokens"),
        ("cache_read", "cached_input_tokens"),
    ),
    "kimi": (
        ("input", "inputOther"),
        ("output", "output"),
        ("cache_read", "inputCacheRead"),
        ("cache_write", "inputCacheCreation"),
    ),
}


def _kinds(backend: str, usage: dict[str, Any]) -> dict[str, float]:
    """One row's usage, under the names every kind is counted by here.

    Args:
      backend: Whose log the row came out of.
      usage: The usage as that backend wrote it.

    Returns:
      Tokens by kind, holding only the kinds this backend actually reported -- a kind that is
      not here is one it does not report, which is not the same as one it reports as nothing.
    """
    broken = {
        kind: float(usage.get(named) or 0)
        for kind, named in _KINDS.get(backend, ())
        if usage.get(named)
    }
    if backend == "codex" and "cache_read" in broken:
        # Codex counts its cached reads inside the input rather than beside it, and a token
        # priced as an input and again as a cached read is a token billed twice. A prompt
        # that was wholly cached leaves no plain input at all, and is written down as having
        # none rather than as having nought of it.
        rest = broken.get("input", 0.0) - broken["cache_read"]
        if rest > 0:
            broken["input"] = rest
        else:
            broken.pop("input", None)
    return broken


def _spent(
    backend: str, row: dict[str, Any]
) -> tuple[str | None, int, dict[str, float]]:
    """What one row of a log says was spent, read as that backend writes it.

    Every one of them is per request rather than a running total, so a session's spending is
    what its rows come to. Claude writes an assistant message with the usage of the request
    that produced it, and names the model on it -- which is how a sub-agent's cheaper model is
    counted as itself. Codex writes a `token_count` event whose `last_token_usage` is the
    request that just came back, the `total_token_usage` beside it being the thread so far.
    Kimi writes a `turn.step.completed` whose usage is that step's. ZCode writes one row per
    model request, holding what was sent, what came back and what that one cost.

    Args:
      backend: Whose log this row came out of.
      row: The row, as read.

    Returns:
      The model it names, or None to leave that to whoever asked; how many tokens the request
      cost -- zero for a row that is not one of these -- and what those tokens were, kind by
      kind, which is the only reckoning a price can be put against.
    """
    if backend == "claude":
        message: dict[str, Any] = row.get("message") or {}
        usage: dict[str, Any] = message.get("usage") or {}
        broken = _kinds(backend, usage)
        return (
            str(message.get("model") or "") or None,
            int(sum(broken.values())),
            broken,
        )
    if backend == "dsh":
        if row.get("type") != "assistant/message":
            return None, 0, {}
        data: dict[str, Any] = row.get("data") or {}
        message = data.get("message") or {}
        source: dict[str, Any] = message.get("source") or {}
        usage = data.get("usage") or {}
        broken = _kinds(backend, usage)
        return (
            str(source.get("model") or "") or None,
            int(sum(broken.values())),
            broken,
        )
    if backend == "zcode":
        # One row per request the turn made, the whole of what was sent and what came back.
        # Its `usage` is that request's, and the model beside it is the one it ran on -- which
        # is how a title or a sub-agent on the lite model is counted as itself.
        answered: dict[str, Any] = row.get("response") or {}
        counting: dict[str, Any] = answered.get("usage") or {}
        ran: dict[str, Any] = row.get("model") or {}
        named = f"{ran.get('providerId', '')}/{ran.get('modelId', '')}".strip("/")
        broken = _kinds(backend, counting)
        return named or None, int(sum(broken.values())), broken
    envelope: dict[str, Any] = row.get("envelope") or {}
    payload: dict[str, Any] = row.get("payload") or envelope.get("payload") or {}
    if backend == "codex":
        info: dict[str, Any] = payload.get("info") or {}
        counted: dict[str, Any] = info.get("last_token_usage") or {}
        # The total is Codex's own rather than what the kinds add up to: a rollout row naming
        # only the total still says what that request cost, and that is what is counted.
        return None, int(counted.get("total_tokens") or 0), _kinds(backend, counted)
    spent: dict[str, Any] = payload.get("usage") or {}
    broken = _kinds("kimi", spent)
    return None, int(sum(broken.values())), broken


@dataclass
class _Reading:
    """One log being read: how far into it we are, and what it has come to so far.

    Kept by model and then by kind, a bill needing the kinds and a sub-agent on a cheaper
    model being its own line. The kind called `` is what a row counted without saying what
    kind of token it was, which is the one part of a total that cannot be priced.
    """

    at: int = 0
    spent: dict[str, Counter[str]] = field(default_factory=dict[str, Counter[str]])


class Tally:
    """The logs of the sessions a flow has open, read as the agents write them."""

    def __init__(self, agents: Sequence[AgentBase], monitor: Monitor) -> None:
        """Initializes a tally that has read nothing yet.

        Args:
          agents: The agents of the flow, whose sessions are the logs to read.
          monitor: What to tell, as the total each model has cost.
        """
        self._agents = list(agents)
        self._monitor = monitor
        self._read: dict[Path, _Reading] = {}
        self._stop = threading.Event()

    def watch(self) -> None:
        """Reads the logs for as long as the flow runs, on a thread of its own.

        Its own, because this reads files: a log a turn has just written a tool's whole
        output to is not something to parse on the thread drawing the screen.
        """

        def reading() -> None:
            while not self._stop.wait(_EVERY):
                self.read()
            self.read()  # once more, for what the last turn wrote on its way out

        threading.Thread(target=reading, daemon=True).start()

    def stops(self) -> None:
        """Stops reading, once the run this was watching is over."""
        self._stop.set()

    def read(self) -> None:
        """Reads whatever has been appended since the last read, and says what it comes to.

        Every failure here is somebody else's: a log that is not there yet, one this has no
        business reading, a row half written. What a run costs is worth nothing at the price
        of the run, so anything that goes wrong is left for the next read to find gone.
        """
        for agent in self._agents:
            profile = backends.named(agent.backend)
            if profile is None:
                continue
            home = profile.directory()
            # Every session this agent has going, named as the backend names it -- which it
            # does as the turn starts rather than when the turn lands -- and every one it has
            # let go of, whose last rows are still worth reading.
            idents = {
                session.named for session in agent.sessions if session.named is not None
            } | set(agent.opened)
            for ident in sorted(idents):
                for pattern in profile.logs:
                    for path in sorted(home.glob(pattern.format(ident=ident))):
                        self._take(path, profile.name, agent.config.model)
        totals: dict[str, Counter[str]] = {}
        for reading in self._read.values():
            for model, broken in reading.spent.items():
                totals.setdefault(model, Counter()).update(broken)
        for model, broken in totals.items():
            # The kind with no name goes along with the rest: it is what a row counted
            # without saying what it went on, and leaving it out here would price the whole
            # of a total against the part of it somebody did break down.
            kinds = {kind: float(count) for kind, count in broken.items()}
            self._monitor.counted(
                "read", model, sum(broken.values()), kinds=kinds or None
            )

    def _take(self, path: Path, backend: str, model: str) -> None:
        """Reads one log on from wherever this last left it.

        Args:
          path: The log.
          backend: Whose it is, which is how its rows are read.
          model: What to count a row against when the row does not say for itself.
        """
        reading = self._read.setdefault(path, _Reading())
        try:
            with path.open("rb") as stream:
                stream.seek(reading.at)
                written = stream.read()
        except OSError:
            return  # not there yet, or not ours to read
        # To the last full line: a row being written is a row to read next time round.
        written = written[: written.rfind(b"\n") + 1]
        reading.at += len(written)
        for line in written.splitlines():
            try:
                loaded: object = json.loads(line)
            except ValueError:
                continue
            if not isinstance(loaded, dict):
                continue
            named, tokens, broken = _spent(backend, cast("dict[str, Any]", loaded))
            if tokens > 0:
                counted = reading.spent.setdefault(named or model, Counter())
                counted.update({kind: int(count) for kind, count in broken.items()})
                # Whatever the kinds did not account for still cost something, and is put
                # under no kind at all rather than guessed at as one.
                if (rest := tokens - int(sum(broken.values()))) > 0:
                    counted[""] += rest

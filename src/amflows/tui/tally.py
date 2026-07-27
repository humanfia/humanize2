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
import os
import threading
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence

    from amflows.janus import AgentBase

    from .monitor import Monitor

__all__ = ["Tally"]

#: Where each backend keeps the log of one session: the variable that moves its home, where
#: that home is by default, and the logs one session id is written to under it. Claude gets two
#: -- a sub-agent it starts writes its own transcript, and the tokens it spends are the run's.
_LOGS: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "claude": (
        "CLAUDE_CONFIG_DIR",
        ".claude",
        ("projects/*/{ident}.jsonl", "projects/*/{ident}/subagents/**/*.jsonl"),
    ),
    "codex": ("CODEX_HOME", ".codex", ("sessions/**/rollout-*{ident}.jsonl",)),
    "kimi": ("KIMI_CODE_HOME", ".kimi-code", ("server/events/{ident}.jsonl",)),
}

#: How often the logs are looked at. Often enough that a turn's spending shows while the turn
#: is still running, and cheap because only what has been appended since is ever read.
_EVERY = 1.0


def _spent(backend: str, row: dict[str, Any]) -> tuple[str | None, int]:
    """What one row of a log says was spent, read as that backend writes it.

    Every one of them is per request rather than a running total, so a session's spending is
    what its rows come to. Claude writes an assistant message with the usage of the request
    that produced it, and names the model on it -- which is how a sub-agent's cheaper model is
    counted as itself. Codex writes a `token_count` event whose `last_token_usage` is the
    request that just came back, the `total_token_usage` beside it being the thread so far.
    Kimi writes a `turn.step.completed` whose usage is that step's.

    Args:
      backend: Whose log this row came out of.
      row: The row, as read.

    Returns:
      The model it names, or None to leave that to whoever asked, and how many tokens the
      request cost -- zero for a row that is not one of these.
    """
    if backend == "claude":
        message = row.get("message") or {}
        usage = message.get("usage") or {}
        return str(message.get("model") or "") or None, sum(
            int(usage.get(name) or 0)
            for name in (
                "input_tokens",
                "output_tokens",
                "cache_read_input_tokens",
                "cache_creation_input_tokens",
            )
        )
    payload = row.get("payload") or (row.get("envelope") or {}).get("payload") or {}
    if backend == "codex":
        counted = (payload.get("info") or {}).get("last_token_usage") or {}
        return None, int(counted.get("total_tokens") or 0)
    usage = payload.get("usage") or {}
    return None, sum(
        int(usage.get(name) or 0)
        for name in ("inputOther", "output", "inputCacheRead", "inputCacheCreation")
    )


@dataclass
class _Reading:
    """One log being read: how far into it we are, and what it has come to so far."""

    at: int = 0
    spent: Counter[str] = field(default_factory=Counter)


class Tally:
    """The logs of the sessions a flow has open, read as the agents write them."""

    def __init__(self, agents: Sequence[AgentBase], monitor: Monitor):
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
            backend = agent.backend
            if backend not in _LOGS:
                continue
            variable, under, patterns = _LOGS[backend]
            home = Path(os.environ.get(variable) or Path.home() / under)
            # Every session this agent has going, named as the backend names it -- which it
            # does as the turn starts rather than when the turn lands -- and every one it has
            # let go of, whose last rows are still worth reading.
            idents = {session.named for session in agent.sessions} | set(agent.opened)
            for ident in sorted(idents - {None}):
                for pattern in patterns:
                    for path in sorted(home.glob(pattern.format(ident=ident))):
                        self._take(path, backend, agent.config.model)
        totals: Counter[str] = Counter()
        for reading in self._read.values():
            totals.update(reading.spent)
        for model, total in totals.items():
            self._monitor.counted("read", model, total)

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
                row = json.loads(line)
            except ValueError:
                continue
            if not isinstance(row, dict):
                continue
            named, tokens = _spent(backend, row)
            if tokens > 0:
                reading.spent[named or model] += tokens

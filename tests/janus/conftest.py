"""What both halves of the janus suite need: a shell-backed agent, and an anchor that stays here."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from humanize.coganchor import AnchorConfig
from humanize.janus import AgentBase, CommandSessionBase


@dataclass(frozen=True, kw_only=True, slots=True)
class HereAnchor(AnchorConfig):
    """An anchor that runs the turn here after all, and keeps what it was handed.

    A real one would spawn coganchor, which needs a target and a machine to intercept on;
    what janus owes it is the whole call the backend built, which is what this records.
    """

    seen: list[list[str]] = field(default_factory=list)

    def command(self, argv: Sequence[str]) -> list[str]:
        self.seen.append(list(argv))
        return list(argv)


class ShellSession(CommandSessionBase):
    """Runs the prompt as a shell script, so each test spells the agent it stands in for."""

    def __init__(self, agent: AgentBase):
        super().__init__(agent)
        self.reads = 0

    def _turn(self, prompt: str) -> tuple[list[str], str | None]:
        return (["sh", "-c", prompt], None)

    def _read_session_id(self, transcript: str) -> str:
        self.reads += 1
        return transcript.strip()  # so a test can see exactly what the parser was given


class ShellAgent(AgentBase):
    def new(self) -> ShellSession:
        return ShellSession(self)

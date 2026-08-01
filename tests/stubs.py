"""What more than one suite needs: a shell-backed agent, and an anchor that stays here.

Here rather than in a conftest because these are imported by name, and a conftest is a pytest
plugin rather than a module to import from -- and because the agents, the cycles and the
machines are three suites now, all of which drive a stand-in agent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from humanize.agents import AgentBase, CommandSessionBase
from humanize.coganchor import AnchorConfig

if TYPE_CHECKING:
    import os
    from collections.abc import Sequence


@dataclass(frozen=True, kw_only=True, slots=True)
class HereAnchor(AnchorConfig):
    """An anchor that runs the turn here after all, and keeps what it was handed.

    A real one would spawn coganchor, which needs a target and a machine to intercept on;
    what an agent owes it is the whole call the backend built, which is what this records --
    and, for an agent that is also run under a provider, the paths that session is to answer
    with others, since a process has one tracer and the anchor is the one that has it -- and
    the directory each session works in, which is the target's to hold.
    """

    seen: list[list[str]] = field(default_factory=list[list[str]])
    answered: list[list[tuple[str, str]]] = field(
        default_factory=list[list[tuple[str, str]]]
    )
    kept: list[list[str]] = field(default_factory=list[list[str]])
    into: list[str] = field(default_factory=list[str])

    def command(
        self,
        argv: Sequence[str],
        *,
        swaps: Sequence[tuple[str, str]] = (),
        private: Sequence[str] = (),
        chdir: str = "",
    ) -> list[str]:
        self.seen.append(list(argv))
        self.answered.append(list(swaps))
        self.kept.append(list(private))
        self.into.append(chdir)
        return list(argv)


class ShellSession(CommandSessionBase):
    """Runs the prompt as a shell script, so each test spells the agent it stands in for."""

    def __init__(
        self, agent: AgentBase, cwd: str | os.PathLike[str] | None = None
    ) -> None:
        super().__init__(agent, cwd)
        self.reads = 0

    def _turn(self, prompt: str) -> tuple[list[str], str | None]:
        return (["sh", "-c", prompt], None)

    def _read_session_id(self, transcript: str) -> str:
        self.reads += 1
        return transcript.strip()  # so a test can see exactly what the parser was given


class ShellAgent(AgentBase):
    def new(self, cwd: str | os.PathLike[str] | None = None) -> ShellSession:
        return ShellSession(self, cwd)

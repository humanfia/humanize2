"""Claude Code: ``claude --print``, on a session id pinned before the turn that opens it."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from .base import AgentBase, CommandSessionBase
from .config import AgentConfig


@dataclass(frozen=True, kw_only=True)
class ClaudeCodeAgentConfig(AgentConfig):
    """What Claude Code is configured with: the common model and effort, and nothing else."""


class ClaudeCodeSession(CommandSessionBase):
    """A Claude Code conversation, addressed by an id chosen up front.

    Pinning beats ``--continue``, which resumes whichever session in this directory is newest:
    a second agent working alongside would steal the resume.
    """

    _pinned: (
        str  # the id this session is opened under, reserved by the turn that opens it
    )

    def _turn(self, prompt: str) -> tuple[list[str], str | None]:
        """Builds ``claude --print`` with the prompt on stdin, opening or resuming the session."""
        # A fresh id per attempt: an opening turn that failed may still have left Claude holding
        # the id it was given, and retrying under that one would collide forever.
        self._pinned = self._id or str(uuid.uuid4())
        return (
            [
                "claude",
                "--print",
                "--resume" if self._id else "--session-id",
                self._pinned,
                "--dangerously-skip-permissions",
                "--model",
                self._agent.config.model,
                "--effort",
                self._agent.config.effort,
            ],
            prompt,
        )

    def _read_session_id(self, transcript: str) -> str:
        """Returns the pinned id: Claude took it, so there is nothing to read back."""
        return self._pinned

    def pursue(self, objective: str) -> str:
        """Runs the turn as Claude Code's own ``/goal``, which print mode expands like any other.

        Claude keeps the session going itself, by refusing to stop while the objective is
        unmet, so the turn is over only once it has been reached or given up on.
        """
        return self.run(f"/goal {objective}")


class ClaudeCodeAgent(AgentBase):
    """Claude Code, which takes the prompt on stdin and the effort via ``--effort``."""

    def launch(self) -> ClaudeCodeSession:
        """Creates a new Claude Code session."""
        return ClaudeCodeSession(self)

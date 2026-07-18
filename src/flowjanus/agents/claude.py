"""Claude Code: ``claude --print``, on a session id pinned before the turn that opens it."""

from __future__ import annotations

import uuid

from .base import AgentBase, SessionBase


class ClaudeCodeSession(SessionBase):
    """A Claude Code conversation, addressed by an id chosen up front.

    Pinning beats ``--continue``, which resumes whichever session in this directory is newest:
    a second agent working alongside would steal the resume.
    """

    _id: str  # the id this session is opened under, reserved by the turn that opens it

    def _turn(self, prompt: str) -> tuple[list[str], str | None]:
        """Builds ``claude --print`` with the prompt on stdin, opening or resuming the session."""
        # A fresh id per attempt: an opening turn that failed may still have left Claude holding
        # the id it was given, and retrying under that one would collide forever.
        self._id = self.session_id or str(uuid.uuid4())
        return (
            [
                "claude",
                "--print",
                "--resume" if self.session_id else "--session-id",
                self._id,
                "--dangerously-skip-permissions",
                "--model",
                self.agent.model,
                "--effort",
                self.agent.effort,
            ],
            prompt,
        )

    def _read_session_id(self, transcript: str) -> str:
        """Returns the pinned id: Claude took it, so there is nothing to read back."""
        return self._id


class ClaudeCodeAgent(AgentBase):
    """Claude Code, which takes the prompt on stdin and the effort via ``--effort``."""

    def start(self) -> ClaudeCodeSession:
        """Creates a new Claude Code session."""
        return ClaudeCodeSession(self)

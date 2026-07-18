"""Codex: ``codex exec``, on the session id it prints in the header of every turn."""

from __future__ import annotations

import re

from .base import AgentBase, SessionBase

_SESSION_ID = re.compile(r"^session id: (\S+)$", re.MULTILINE)


class CodexSession(SessionBase):
    """A Codex conversation, addressed by the id ``codex exec`` announces before it starts work.

    Codex has no way to pin the id up front and ``resume --last`` takes whichever session in
    this directory is newest, so the id is read back from the first turn instead.
    """

    def _turn(self, prompt: str) -> tuple[list[str], str | None]:
        """Builds ``codex exec [resume <id>]`` with the prompt on stdin."""
        resume = ["resume", self.session_id] if self.session_id else []
        return (
            [
                "codex",
                "exec",
                *resume,
                "--dangerously-bypass-approvals-and-sandbox",
                "--skip-git-repo-check",
                "--model",
                self.agent.model,
                "-c",
                f'model_reasoning_effort="{self.agent.effort}"',
                "-c",
                'service_tier="default"',
                "-",  # take the prompt from stdin
            ],
            prompt,
        )

    def _read_session_id(self, transcript: str) -> str:
        """Reads ``session id: <uuid>`` out of the header Codex prints before it starts work.

        Raises:
          RuntimeError: If the header is missing, which means the id cannot be resumed.
        """
        match = _SESSION_ID.search(transcript)
        if match is None:
            raise RuntimeError("codex exec printed no session id")
        return match.group(1)


class CodexAgent(AgentBase):
    """Codex, which takes the prompt on stdin and the effort via ``model_reasoning_effort``."""

    def start(self) -> CodexSession:
        """Creates a new Codex session."""
        return CodexSession(self)

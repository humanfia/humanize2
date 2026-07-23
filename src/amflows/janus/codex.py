"""Codex: ``codex exec``, on the session id it prints in the header of every turn."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .base import AgentBase, SessionBase
from .config import AgentConfig

_SESSION_ID = re.compile(r"^session id: (\S+)$", re.MULTILINE)


@dataclass(frozen=True, kw_only=True)
class CodexAgentConfig(AgentConfig):
    """What Codex is configured with: the common model and effort, and nothing else."""


class CodexSession(SessionBase):
    """A Codex conversation, addressed by the id ``codex exec`` announces before it starts work.

    Codex has no way to pin the id up front and ``resume --last`` takes whichever session in
    this directory is newest, so the id is read back from the first turn instead.
    """

    def _turn(self, prompt: str) -> tuple[list[str], str | None]:
        """Builds ``codex exec [resume <id>]`` with the prompt on stdin."""
        resume = ["resume", self._id] if self._id else []
        return (
            [
                "codex",
                "exec",
                *resume,
                "--dangerously-bypass-approvals-and-sandbox",
                "--skip-git-repo-check",
                "--model",
                self._agent.config.model,
                "-c",
                f'model_reasoning_effort="{self._agent.config.effort}"',
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

    def launch(self) -> CodexSession:
        """Creates a new Codex session."""
        return CodexSession(self)

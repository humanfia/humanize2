"""Kimi Code: ``kimi --prompt``, on the session id it prints as a closing resume hint."""

from __future__ import annotations

import re

from .base import AgentBase, SessionBase

_SESSION_ID = re.compile(r"^To resume this session: kimi -r (\S+)$", re.MULTILINE)


class KimiCodeCLISession(SessionBase):
    """A Kimi Code conversation, addressed by the id in the resume hint each turn ends with.

    Kimi has no way to pin the id up front and ``--continue`` takes whichever session in this
    directory is newest, so the id is read back from the first turn instead.
    """

    def _turn(self, prompt: str) -> tuple[list[str], str | None]:
        """Builds ``kimi [--session <id>] --prompt`` with the prompt as an argument."""
        resume = ["--session", self.session_id] if self.session_id else []
        return (["kimi", *resume, "--prompt", prompt, "--model", self.agent.model], None)

    def _read_session_id(self, transcript: str) -> str:
        """Reads the id out of the ``To resume this session: kimi -r <id>`` line.

        Raises:
          RuntimeError: If the hint is missing, which means the id cannot be resumed.
        """
        match = _SESSION_ID.search(transcript)
        if match is None:
            raise RuntimeError("kimi printed no resume hint")
        return match.group(1)


class KimiCodeCLIAgent(AgentBase):
    """Kimi Code, which takes the prompt as a flag and has no effort knob, so effort is ignored."""

    def start(self) -> KimiCodeCLISession:
        """Creates a new Kimi Code session."""
        return KimiCodeCLISession(self)

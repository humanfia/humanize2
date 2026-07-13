"""Kimi Code as a one-shot agent: ``kimi --prompt`` with the prompt passed as an argument.

Kimi takes the prompt as a flag rather than on stdin and (in one-shot mode) has no effort knob, so
``effort`` is ignored here.
"""

from __future__ import annotations

from .base import AgentBase


class KimiCodeCLIAgent(AgentBase):
    def _command(self, prompt: str) -> tuple[list[str], str | None]:
        argv = ["kimi", "--prompt", prompt]
        if self.model:
            argv += ["--model", self.model]
        return argv, None

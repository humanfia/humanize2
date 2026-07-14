"""Kimi Code as a one-shot agent: ``kimi --prompt`` with the prompt passed as an argument."""

from __future__ import annotations

from .base import AgentBase


class KimiCodeCLIAgent(AgentBase):
    """Kimi Code, which takes the prompt as a flag and has no effort knob, so effort is ignored."""

    def run(self, prompt: str) -> str:
        """Runs ``kimi --prompt`` with the prompt as an argument and returns its output."""
        return self._run_cli(["kimi", "--prompt", prompt, "--model", self.model], None)

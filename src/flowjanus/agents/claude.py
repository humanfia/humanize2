"""Claude Code as a one-shot agent: ``claude --print`` with the prompt on stdin."""

from __future__ import annotations

from .base import AgentBase


class ClaudeCodeAgent(AgentBase):
    """Claude Code, which takes the prompt on stdin and the effort via ``--effort``."""

    def run(self, prompt: str) -> str:
        """Runs ``claude --print`` with the prompt on stdin and returns its output."""
        return self._run_cli(
            [
                "claude",
                "--print",
                "--dangerously-skip-permissions",
                "--model",
                self.model,
                "--effort",
                self.effort,
            ],
            prompt,
        )

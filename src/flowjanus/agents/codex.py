"""Codex as a one-shot agent: ``codex exec`` with the prompt on stdin."""

from __future__ import annotations

from .base import AgentBase


class CodexAgent(AgentBase):
    """Codex, which takes the prompt on stdin and the effort via ``model_reasoning_effort``."""

    def run(self, prompt: str) -> str:
        """Runs ``codex exec`` with the prompt on stdin and returns its output."""
        return self._run_cli(
            [
                "codex",
                "exec",
                "--dangerously-bypass-approvals-and-sandbox",
                "--skip-git-repo-check",
                "--model",
                self.model,
                "-c",
                f'model_reasoning_effort="{self.effort}"',
                "-c",
                'service_tier="default"',
            ],
            prompt,
        )

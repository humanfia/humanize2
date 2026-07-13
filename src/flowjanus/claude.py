"""Claude Code as a one-shot agent: ``claude --print`` with the prompt on stdin."""

from __future__ import annotations

from .base import AgentBase


class ClaudeCodeAgent(AgentBase):
    def _command(self, prompt: str) -> tuple[list[str], str | None]:
        argv = ["claude", "--print", "--dangerously-skip-permissions"]
        if self.model:
            argv += ["--model", self.model]
        if self.effort:
            argv += ["--effort", self.effort]
        return argv, prompt

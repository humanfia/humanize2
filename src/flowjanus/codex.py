"""Codex as a one-shot agent: ``codex exec`` with the prompt on stdin."""

from __future__ import annotations

from .base import AgentBase


class CodexAgent(AgentBase):
    def _command(self, prompt: str) -> tuple[list[str], str | None]:
        argv = [
            "codex",
            "exec",
            "--dangerously-bypass-approvals-and-sandbox",
            "--skip-git-repo-check",
        ]
        if self.model:
            argv += ["--model", self.model]
        if self.effort:
            argv += ["-c", f'model_reasoning_effort="{self.effort}"']
        argv += ["-c", 'service_tier="default"']
        return argv, prompt

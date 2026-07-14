"""Coding agents behind one interface, hiding which CLI actually runs.

from flowjanus.agents import ClaudeCodeAgent
agent = ClaudeCodeAgent(model="claude-opus-4-8", effort="high")
text = agent.run("Refactor foo.py")
"""

from __future__ import annotations

from .base import AgentBase
from .claude import ClaudeCodeAgent
from .codex import CodexAgent
from .kimi import KimiCodeCLIAgent

__all__ = [
    "AgentBase",
    "ClaudeCodeAgent",
    "CodexAgent",
    "KimiCodeCLIAgent",
]

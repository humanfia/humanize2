"""flowjanus: treat any coding agent as one interface, hiding which CLI actually runs.

from flowjanus import ClaudeCodeAgent
agent = ClaudeCodeAgent(model="claude-opus-4-8", effort="high")
text = agent.run("Refactor foo.py")
"""

from __future__ import annotations

from .base import AgentBase, AgentError
from .claude import ClaudeCodeAgent
from .codex import CodexAgent
from .kimi import KimiCodeCLIAgent

__all__ = [
    "AgentBase",
    "AgentError",
    "ClaudeCodeAgent",
    "CodexAgent",
    "KimiCodeCLIAgent",
]

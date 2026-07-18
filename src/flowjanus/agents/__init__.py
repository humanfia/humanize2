"""Coding agents behind one interface, hiding which CLI actually runs.

An agent is structure -- a model at an effort. A session is the conversation it runs on, so a
flow chooses whether turns share context:

from flowjanus.agents import ClaudeCodeAgent

agent = ClaudeCodeAgent(model="claude-opus-4-8", effort="high")
agent.run("Refactor foo.py")     # one turn in a throwaway session

session = agent.start()          # a conversation that remembers
session.run("Refactor foo.py")
session.run("Now write tests for it")
"""

from __future__ import annotations

from .base import AgentBase, SessionBase
from .claude import ClaudeCodeAgent, ClaudeCodeSession
from .codex import CodexAgent, CodexSession
from .kimi import KimiCodeCLIAgent, KimiCodeCLISession

__all__ = [
    "AgentBase",
    "ClaudeCodeAgent",
    "ClaudeCodeSession",
    "CodexAgent",
    "CodexSession",
    "KimiCodeCLIAgent",
    "KimiCodeCLISession",
    "SessionBase",
]

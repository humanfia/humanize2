"""Drive coding agent CLIs as agents and the sessions they hold."""

from __future__ import annotations

from .base import AgentBase, CommandSessionBase, SessionBase, StreamSessionBase
from .claude import ClaudeCodeAgent, ClaudeCodeAgentConfig, ClaudeCodeSession
from .codex import CodexAgent, CodexAgentConfig, CodexSession
from .config import AgentConfig, anchored
from .event import Event, Question, Stopped
from .hooks import EVERYWHERE, Hook, Hooks, Hung, Moment, Occasion, Unhooked, Verdict
from .human import HumanAgent, HumanSession
from .kimi import SWARM, KimiCodeCLIAgent, KimiCodeCLIAgentConfig, KimiCodeCLISession

#: What each coding agent CLI is driven by here, under the name a command line calls it.
#: One table rather than one apiece: whoever reads an `-a` builds an agent from it, and
#: whoever offers the backends at a prompt asks what each of them can do, and neither should
#: have to know that `kimi` is a `KimiCodeCLIAgent` for itself.
DRIVEN: dict[str, tuple[type[AgentBase], type[AgentConfig]]] = {
    "claude": (ClaudeCodeAgent, ClaudeCodeAgentConfig),
    "codex": (CodexAgent, CodexAgentConfig),
    "kimi": (KimiCodeCLIAgent, KimiCodeCLIAgentConfig),
}

__all__ = [
    "DRIVEN",
    "EVERYWHERE",
    "SWARM",
    "AgentBase",
    "AgentConfig",
    "ClaudeCodeAgent",
    "ClaudeCodeAgentConfig",
    "ClaudeCodeSession",
    "CodexAgent",
    "CodexAgentConfig",
    "CodexSession",
    "CommandSessionBase",
    "Event",
    "Hook",
    "Hooks",
    "HumanAgent",
    "HumanSession",
    "Hung",
    "KimiCodeCLIAgent",
    "KimiCodeCLIAgentConfig",
    "KimiCodeCLISession",
    "Moment",
    "Occasion",
    "Question",
    "SessionBase",
    "Stopped",
    "StreamSessionBase",
    "Unhooked",
    "Verdict",
    "anchored",
]

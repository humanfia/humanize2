"""Drive coding agent CLIs as agents and the sessions they hold."""

from __future__ import annotations

from .base import (
    WINDOW,
    AgentBase,
    CommandSessionBase,
    Meter,
    SessionBase,
    StreamSessionBase,
)
from .claude import ClaudeCodeAgent, ClaudeCodeAgentConfig, ClaudeCodeSession
from .codex import CodexAgent, CodexAgentConfig, CodexSession
from .config import (
    PERMISSIONS,
    AgentConfig,
    AgentDefaults,
    Goal,
    Isolated,
    Remote,
    anchored,
    isolated,
)
from .dsh import DshAgent, DshAgentConfig, DshSession
from .event import Event, Question, Stopped, Usage
from .grok import GrokBuildAgent, GrokBuildAgentConfig, GrokBuildSession
from .hooks import EVERYWHERE, Hook, Hooks, Hung, Moment, Occasion, Unhooked, Verdict
from .human import HumanAgent, HumanSession
from .kimi import SWARM, KimiCodeCLIAgent, KimiCodeCLIAgentConfig, KimiCodeCLISession
from .mimo import MimoCodeAgent, MimoCodeAgentConfig, MimoCodeSession
from .opencode import OpencodeAgent, OpencodeAgentConfig, OpencodeSession
from .pi import PiAgent, PiAgentConfig, PiSession
from .qwen import QwenCodeAgent, QwenCodeAgentConfig, QwenCodeSession

#: What each coding agent CLI is driven by here, under the name a command line calls it.
#: One table rather than one apiece: whoever reads an `-a` builds an agent from it, and
#: whoever offers the backends at a prompt asks what each of them can do, and neither should
#: have to know that `kimi` is a `KimiCodeCLIAgent` for itself.
DRIVEN: dict[str, tuple[type[AgentBase], type[AgentConfig]]] = {
    "claude": (ClaudeCodeAgent, ClaudeCodeAgentConfig),
    "codex": (CodexAgent, CodexAgentConfig),
    "dsh": (DshAgent, DshAgentConfig),
    "grok": (GrokBuildAgent, GrokBuildAgentConfig),
    "kimi": (KimiCodeCLIAgent, KimiCodeCLIAgentConfig),
    "mimo": (MimoCodeAgent, MimoCodeAgentConfig),
    "opencode": (OpencodeAgent, OpencodeAgentConfig),
    "pi": (PiAgent, PiAgentConfig),
    "qwen": (QwenCodeAgent, QwenCodeAgentConfig),
}

__all__ = [
    "DRIVEN",
    "EVERYWHERE",
    "PERMISSIONS",
    "SWARM",
    "WINDOW",
    "AgentBase",
    "AgentConfig",
    "AgentDefaults",
    "ClaudeCodeAgent",
    "ClaudeCodeAgentConfig",
    "ClaudeCodeSession",
    "CodexAgent",
    "CodexAgentConfig",
    "CodexSession",
    "CommandSessionBase",
    "DshAgent",
    "DshAgentConfig",
    "DshSession",
    "Event",
    "Goal",
    "GrokBuildAgent",
    "GrokBuildAgentConfig",
    "GrokBuildSession",
    "Hook",
    "Hooks",
    "HumanAgent",
    "HumanSession",
    "Hung",
    "Isolated",
    "KimiCodeCLIAgent",
    "KimiCodeCLIAgentConfig",
    "KimiCodeCLISession",
    "Meter",
    "MimoCodeAgent",
    "MimoCodeAgentConfig",
    "MimoCodeSession",
    "Moment",
    "Occasion",
    "OpencodeAgent",
    "OpencodeAgentConfig",
    "OpencodeSession",
    "PiAgent",
    "PiAgentConfig",
    "PiSession",
    "Question",
    "QwenCodeAgent",
    "QwenCodeAgentConfig",
    "QwenCodeSession",
    "Remote",
    "SessionBase",
    "Stopped",
    "StreamSessionBase",
    "Unhooked",
    "Usage",
    "Verdict",
    "anchored",
    "isolated",
]

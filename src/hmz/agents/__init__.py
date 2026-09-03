"""Drive coding agent CLIs as agents and the sessions they hold."""

from __future__ import annotations

from .acp import AcpAgent, AcpAgentConfig, AcpSession
from .agy import (
    AntigravityCLIAgent,
    AntigravityCLIAgentConfig,
    AntigravityCLISession,
)
from .base import (
    WINDOW,
    AgentBase,
    CommandSessionBase,
    ForkContext,
    Meter,
    SessionBase,
    StreamSessionBase,
)
from .board import ANYONE, FLOW, USER, WHOSE, Board, Item, Refused
from .claude import ClaudeCodeAgent, ClaudeCodeAgentConfig, ClaudeCodeSession
from .codex import CodexAgent, CodexAgentConfig, CodexSession
from .config import (
    PERMISSIONS,
    SERVICE_TIERS,
    AgentConfig,
    AgentDefaults,
    Forks,
    Goal,
    Isolated,
    Remote,
    anchored,
    isolated,
)
from .cursor import CursorAgent, CursorAgentConfig, CursorSession
from .dsh import DshAgent, DshAgentConfig, DshSession
from .event import Event, Failed, Question, Stopped, Unrecoverable, Usage
from .grok import GrokBuildAgent, GrokBuildAgentConfig, GrokBuildSession
from .hooks import (
    EVERYWHERE,
    SUBAGENTS,
    Hook,
    Hooks,
    Hung,
    Moment,
    Occasion,
    Unhooked,
    Verdict,
)
from .human import HumanAgent, HumanSession
from .kimi import SWARM, KimiCodeCLIAgent, KimiCodeCLIAgentConfig, KimiCodeCLISession
from .mimo import MimoCodeAgent, MimoCodeAgentConfig, MimoCodeSession
from .opencode import OpencodeAgent, OpencodeAgentConfig, OpencodeSession
from .pi import PiAgent, PiAgentConfig, PiSession
from .qwen import QwenCodeAgent, QwenCodeAgentConfig, QwenCodeSession
from .tools import Tool, Toolbox
from .zcode import ZcodeAgent, ZcodeAgentConfig, ZcodeSession

#: What each coding agent CLI is driven by here, under the name a command line calls it.
#: One table rather than one apiece: whoever reads an `-a` builds an agent from it, and
#: whoever offers the backends at a prompt asks what each of them can do, and neither should
#: have to know that `kimi` is a `KimiCodeCLIAgent` for itself.
DRIVEN: dict[str, tuple[type[AgentBase], type[AgentConfig]]] = {
    "agy": (AntigravityCLIAgent, AntigravityCLIAgentConfig),
    "claude": (ClaudeCodeAgent, ClaudeCodeAgentConfig),
    "codex": (CodexAgent, CodexAgentConfig),
    "cursor": (CursorAgent, CursorAgentConfig),
    "dsh": (DshAgent, DshAgentConfig),
    "grok": (GrokBuildAgent, GrokBuildAgentConfig),
    "kimi": (KimiCodeCLIAgent, KimiCodeCLIAgentConfig),
    "mimo": (MimoCodeAgent, MimoCodeAgentConfig),
    "opencode": (OpencodeAgent, OpencodeAgentConfig),
    "pi": (PiAgent, PiAgentConfig),
    "qwen": (QwenCodeAgent, QwenCodeAgentConfig),
    "zcode": (ZcodeAgent, ZcodeAgentConfig),
}


def driver(backend: str) -> tuple[type[AgentBase], type[AgentConfig]]:
    """What drives one backend, whether humanize wrote the driver or somebody added the CLI.

    Args:
      backend: The backend, by the name a command line calls it.

    Returns:
      The agent class and the config class to build it from. A CLI added by hand is driven by
      the one class that speaks the Agent Client Protocol, since the protocol is the whole of
      what is known about it.

    Raises:
      KeyError: If nothing here drives it and nobody has added it.
    """
    from hmz import backends

    held = DRIVEN.get(backend)
    if held is not None:
        return held
    if backend in backends.speaking():
        return (AcpAgent, AcpAgentConfig)
    raise KeyError(backend)


__all__ = [
    "ANYONE",
    "DRIVEN",
    "EVERYWHERE",
    "FLOW",
    "PERMISSIONS",
    "SERVICE_TIERS",
    "SUBAGENTS",
    "SWARM",
    "USER",
    "WHOSE",
    "WINDOW",
    "AcpAgent",
    "AcpAgentConfig",
    "AcpSession",
    "AgentBase",
    "AgentConfig",
    "AgentDefaults",
    "AntigravityCLIAgent",
    "AntigravityCLIAgentConfig",
    "AntigravityCLISession",
    "Board",
    "ClaudeCodeAgent",
    "ClaudeCodeAgentConfig",
    "ClaudeCodeSession",
    "CodexAgent",
    "CodexAgentConfig",
    "CodexSession",
    "CommandSessionBase",
    "CursorAgent",
    "CursorAgentConfig",
    "CursorSession",
    "DshAgent",
    "DshAgentConfig",
    "DshSession",
    "Event",
    "Failed",
    "ForkContext",
    "Forks",
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
    "Item",
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
    "Refused",
    "Remote",
    "SessionBase",
    "Stopped",
    "StreamSessionBase",
    "Tool",
    "Toolbox",
    "Unhooked",
    "Unrecoverable",
    "Usage",
    "Verdict",
    "ZcodeAgent",
    "ZcodeAgentConfig",
    "ZcodeSession",
    "anchored",
    "isolated",
]

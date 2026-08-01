"""mimocode: opencode under another name, and driven the same way.

The program is the same one, installed as `mimo` and serving models of its own, so what it is
driven by is opencode's driver with the command it answers to and the flags that differ. Here
rather than as a second name in `hmz.agents.opencode` because it is a second backend: it
has its own home, its own models and its own place at a prompt, and a reader looking for what
drives `mimo` should find a file called that.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import os

from dataclasses import dataclass
from typing import ClassVar

from .config import AgentConfig
from .opencode import OpencodeAgent, OpencodeSession


class MimoCodeSession(OpencodeSession):
    """A mimocode conversation, held and resumed exactly as an opencode one is."""

    command: ClassVar[str] = "mimo"
    permits: ClassVar[str] = "MIMOCODE_PERMISSION"

    def _unattended(self) -> list[str]:
        """What tells mimocode that nobody is there to answer it.

        Its own spelling of opencode's `--auto`: the same setting under the name this fork
        gives it.
        """
        return ["--dangerously-skip-permissions"]


@dataclass(frozen=True, kw_only=True)
class MimoCodeAgentConfig(AgentConfig):
    """What mimocode is configured with: the common model and effort, and nothing else.

    The model is written as mimocode writes it, `provider/id`, since a model here belongs to
    the provider that serves it and mimocode is asked for the pair.
    """


class MimoCodeAgent(OpencodeAgent):
    """mimocode, driven through its own command line, one run per turn."""

    def new(self, cwd: str | os.PathLike[str] | None = None) -> MimoCodeSession:
        """Opens a new mimocode session, in the directory it is given or in this one."""
        return MimoCodeSession(self, cwd)

"""A machine that is already running, named by the anchor that reaches it.

Nothing is brought up and nothing is taken down: the machine is somebody else's, and all
this says is that the agent's turns land there rather than here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .base import MachineBase, MachineConfig

if TYPE_CHECKING:
    from humanize.coganchor import AnchorConfig


@dataclass(frozen=True, kw_only=True)
class AnchoredConfig(MachineConfig):
    """The machine an anchor names.

    Attributes:
      anchor: Where the work lands, and what of it stays on this machine.
    """

    anchor: AnchorConfig

    def create(self) -> Anchored:
        """Builds the machine, which is one that is already up."""
        return Anchored(self)


class Anchored(MachineBase):
    """The machine an anchor reaches, which was running before this and stays after it."""

    _config: AnchoredConfig

    def start(self) -> AnchorConfig:
        """Answers with the anchor, there being nothing to bring up."""
        return self._config.anchor

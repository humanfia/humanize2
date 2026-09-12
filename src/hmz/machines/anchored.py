"""A machine that is already running, named by the anchor that reaches it.

Nothing is brought up and nothing is taken down: the machine is somebody else's, and all
this says is that the agent's turns land there rather than here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .base import MachineBase, MachineConfig

if TYPE_CHECKING:
    from hmz.coganchor import AnchorConfig


@dataclass(frozen=True, kw_only=True)
class AnchoredConfig(MachineConfig):
    """The machine an anchor names.

    Attributes:
      anchor: Where the work lands, and what of it stays on this machine.
    """

    anchor: AnchorConfig

    @property
    def capabilities(self) -> frozenset[str]:
        """`remote`, and nothing besides.

        Work that lands through an anchor rather than here is the whole of what naming one
        says, and it is said of every target: a `local:` one stands in for a machine of its
        own, and a turn reaches it down the same road as any other.

        Not `managed`, because nobody here brought it up, so nobody here may take it down and
        claiming it would be claiming the right to. Not `isolated`, because what a target does
        with the commands it is sent is the target's own business. And no platform, that being
        the one thing about somebody else's machine which cannot be known until it has been
        reached -- :meth:`~hmz.machines.MachineBase.observe` reads it from the handshake.
        """
        return frozenset({"remote"})

    def create(self) -> Anchored:
        """Builds the machine, which is one that is already up."""
        return Anchored(self)


class Anchored(MachineBase):
    """The machine an anchor reaches, which was running before this and stays after it."""

    _config: AnchoredConfig

    def start(self) -> AnchorConfig:
        """Answers with the anchor, there being nothing to bring up."""
        return self._config.anchor

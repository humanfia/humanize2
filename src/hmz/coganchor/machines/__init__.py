"""Where an agent's turns land: a machine that is already up, or one started for it.

And the workspace on it, as the flow's own code reaches it: an agent under an anchor is
answered for without being told, and the flow driving it is this process, so what it wants of
that machine it asks for.
"""

from __future__ import annotations

from .anchored import Anchored, AnchoredConfig
from .base import MachineBase, MachineConfig
from .docker import Docker, DockerConfig
from .mapped import Mapped, Ran

__all__ = [
    "Anchored",
    "AnchoredConfig",
    "Docker",
    "DockerConfig",
    "MachineBase",
    "MachineConfig",
    "Mapped",
    "Ran",
]

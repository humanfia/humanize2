"""Give an agent a machine of its own, and anchor its turns onto it."""

from __future__ import annotations

from .base import IsolationBase, IsolationConfig
from .docker import DockerIsolation, DockerIsolationConfig

__all__ = [
    "DockerIsolation",
    "DockerIsolationConfig",
    "IsolationBase",
    "IsolationConfig",
]

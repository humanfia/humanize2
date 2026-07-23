"""coganchor -- run a coding agent on one machine, have it act on another.

The agent process stays local, keeping its credentials, its state directory
and its link to its model provider.  A seccomp-filtered ptrace supervisor
intercepts the cold syscalls that name a path, spawn a process or open a
socket, and ``coganchor serve`` replays them on the target machine.
"""

from .anchor import AnchorConfig, check, connect

__version__ = "0.1.0"

__all__ = ["AnchorConfig", "__version__", "check", "connect"]

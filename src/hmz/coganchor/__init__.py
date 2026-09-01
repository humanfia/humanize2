"""coganchor -- run a coding agent on one machine, have it act on another.

Two arrangements, and a session says which it is.  Under :func:`connect` the agent process
stays local, keeping its credentials, its state directory and its link to its model provider:
a seccomp-filtered ptrace supervisor intercepts the cold syscalls that name a path, spawn a
process or open a socket, and ``hmz anchor`` replays them on the target machine.  Under
:func:`drive` nothing stays local at all -- the CLI already installed on the target is the one
that runs, and this side is a pipe carrying its streams.
"""

from .anchor import AnchorConfig, check, connect, drive

__version__ = "0.1.0"

__all__ = ["AnchorConfig", "__version__", "check", "connect", "drive"]

"""The runs humanize is holding apart from a terminal, as a tool outside reaches one.

A run of a flow outlives the program that asked for it: it is held in a process of its own,
one per workspace, and is reached over the socket beside it. That is the other way in --
:class:`hmz.runtime.doing.core.Hmz` runs a flow here, in the process that asked, and this
starts one somewhere a terminal closing cannot end it and reaches whichever are already
running.

:mod:`hmz.daemon` is where all of it is done; this is the one object it is asked through, so
that a tool holds one thing per way in rather than a module of functions apiece.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import os
    from collections.abc import Callable

    from hmz.daemon import Daemon, Held

__all__ = ["Daemons"]


class Daemons:
    """Every run being held apart from a terminal, and how one is put there."""

    def here(self, workspace: str | os.PathLike[str] | None = None) -> Daemon | None:
        """The run being held in one workspace, if one is.

        Args:
          workspace: The project directory, or None for wherever this is being run.

        Returns:
          It, or None where nothing is being held there -- which is what a directory left
          behind by a daemon whose process has gone reads as, a socket file outliving the
          process that bound it.
        """
        from hmz import daemon

        return daemon.running(workspace)

    def all(self) -> list[Daemon]:
        """Every run being held on this machine, oldest first."""
        from hmz import daemon

        return daemon.daemons()

    def hold(
        self,
        opens: Callable[[Held], object],
        workspace: str | os.PathLike[str] | None = None,
        *,
        columns: int = 0,
        rows: int = 0,
    ) -> Daemon:
        """Puts a run where a terminal closing cannot end it, and comes back once it is there.

        What is held is whatever `opens` does. It is called in the held process with the run
        being held, and returns when the run is over -- so a tool that wants a flow held is a
        tool whose `opens` runs one, and one that wants an interface of its own held draws
        one.

        Args:
          opens: What opens the run, called in the detached process.
          workspace: The project directory, or None for wherever this is being run.
          columns: How wide the terminal it draws for is until one arrives, or 0 for this
            one's.
          rows: How tall, or 0 for this one's.

        Returns:
          The daemon, listening.

        Raises:
          OSError: If it could not be started, or did not come up in the time it was given --
            which is what a workspace already holding a run answers with.
        """
        from hmz import daemon

        return daemon.start(opens, workspace, columns=columns, rows=rows)

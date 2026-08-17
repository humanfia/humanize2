"""A run being read from a terminal, as whatever is holding the run sees it.

The interface is opened on a terminal and the run it started outlives that terminal: a flow is
a loop, a turn thinks for minutes, and a day's work must not end because somebody closed a
laptop. What holds the run when no terminal is reading it is :mod:`hmz.daemon`, and this is
the little of it the interface has to know about -- how many terminals are reading, and how to
let go of them without stopping anything.

A protocol rather than the thing itself, so that the interface names no daemon: one running
under a daemon is handed one of these, and one run in the process somebody typed `hmz` in is
handed none and says so where the question is asked.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

__all__ = ["Session"]


@runtime_checkable
class Session(Protocol):
    """What a run that outlives its terminal offers whatever is drawing it."""

    @property
    def attached(self) -> int:
        """How many terminals are reading this run right now."""
        ...

    def detach(self) -> int:
        """Lets go of every terminal reading this, leaving the run itself running.

        Returns:
          How many were let go of, which is zero where nobody was reading.
        """
        ...

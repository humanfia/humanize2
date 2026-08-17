"""Where a turn goes when the place taking it cannot take it at all, as one object.

A place is a CLI, an account and a model, and a step is written between two of them. How many
times over a failed turn is taken again is written on the same row, both being answers to the
one thing that happened. The file is :mod:`hmz.fallbacks`; this is what every way in asks, so
that a step written from a command line is one the interface's own menu reads back.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hmz.fallbacks import Falls, Policy

__all__ = ["Fallbacks"]


class Fallbacks:
    """Every step written down, and the three things that can happen to one."""

    def all(self) -> list[Falls]:
        """Every step, in the order they were written down in."""
        from hmz import fallbacks

        return fallbacks.falls()

    @property
    def default(self) -> str:
        """How a failed turn waits unless somebody said otherwise."""
        from hmz import fallbacks

        return fallbacks.DEFAULT

    def policies(self) -> tuple[Policy, ...]:
        """How long a failed turn waits before it is taken again, hardest last."""
        from hmz import fallbacks

        return fallbacks.POLICIES

    def named(self, policy: str) -> Policy | None:
        """The wait one name means, or None for a name none of them goes by."""
        from hmz import fallbacks

        return fallbacks.named(policy)

    def reads(self, said: str) -> str:
        """One place as it is written down, and "" for a spelling no place answers to."""
        from hmz import fallbacks

        return fallbacks.reads(said)

    def spec(self, backend: str, model: str, provider: str = "") -> str:
        """One place, out of the three things a place is."""
        from hmz import fallbacks

        return fallbacks.spec(backend, model, provider)

    def tried(self, said: str) -> Falls:
        """What is written down against one place, which says nothing where nothing is."""
        from hmz import fallbacks

        return fallbacks.tried(said)

    def chain(self, said: str) -> list[str]:
        """The places one turn would walk, the one it starts at first."""
        from hmz import fallbacks

        return fallbacks.chain(said)

    def points(self, said: str, at: str) -> Falls:
        """Says where one place's turns go when it cannot run at all.

        Args:
          said: The place that cannot run.
          at: The place that takes the turn instead.

        Returns:
          The step, as it is now written down.

        Raises:
          ValueError: If either is not a place, or a step would point at itself.
        """
        from hmz import fallbacks

        return fallbacks.points(said, at)

    def retrying(self, said: str, tries: int, policy: str, timeout: float) -> Falls:
        """Says how a failed turn at one place is taken again before the step is taken.

        Args:
          said: The place it is about.
          tries: How many goes beyond the first, or 0 for none.
          policy: How long to wait between them.
          timeout: The longest the trying again may go on for, or 0 for no limit.

        Returns:
          The step, as it is now written down.

        Raises:
          ValueError: If it is not a place, or the numbers are not ones to try again by.
        """
        from hmz import fallbacks

        return fallbacks.retrying(said, tries, policy, timeout)

    def clear(self, said: str) -> bool:
        """Takes one step away, which is a place that falls back nowhere again.

        Args:
          said: The place it was written down against.

        Returns:
          Whether there was anything written down about it.
        """
        from hmz import fallbacks

        return fallbacks.clear(said)

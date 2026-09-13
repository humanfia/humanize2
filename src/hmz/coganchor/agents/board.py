"""The board a flow and the person at the prompt both write on, and neither waits at.

Asking somebody something stops the turn: the agent says what it wants, and nothing happens
until an answer comes back. That is right for a question, and wrong for everything a run needs
that is not a question -- what there is to do next, how far through it is, what somebody
thought of while it was running.

So this is the other shape. A handful of lines, each a name and what it says, kept beside the
run and shown where the run is shown. The flow reads and writes it whenever it likes; the
person changes it whenever they like; neither is ever waiting on the other. A flow that wants
work asks the board for it; somebody who thinks of more work puts it there and goes back to
what they were doing.

Which makes it an issue list without being one. `todo` holding three lines is three things to
do, `doing` is what is being done, `done` is what has been -- and none of that is written down
here, because it is the flow's to decide. What is here is the board: lines, who may change
each of them, and a way of being told when one moves.

Some lines are one side's alone. A flow writing down how far through it is does not want that
edited underneath it, and a person writing what they want next does not want it rewritten by
the thing that is meant to be reading it. So a line says whose it is, and the other side is
refused where it tries rather than quietly ignored.
"""

from __future__ import annotations

import contextlib
import threading
import time
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

__all__ = ["ANYONE", "FLOW", "USER", "WHOSE", "Board", "Item", "Refused"]

#: Who may change one line. `both` is the ordinary one: a line either of them may write is
#: how a flow and a person hand something back and forth. The other two are for the lines
#: that are one side's own -- a flow's note of how far through it is, a person's list of what
#: they want next -- which the other side may read and may not rewrite.
ANYONE, USER, FLOW = "both", "user", "flow"

#: Every answer to that, in the order a menu offers them.
WHOSE = (ANYONE, USER, FLOW)


class Refused(PermissionError):  # noqa: N818  -- what happened, not what went wrong
    """Raised where one side changes a line the other side's alone.

    A `PermissionError` because that is what it is, and raised rather than ignored because a
    write that quietly did nothing is a flow that quietly does not do what it says.
    """


@dataclass(frozen=True, slots=True)
class Item:
    """One line of the board.

    Attributes:
      key: What it is called, which is how both sides name it. A name rather than a number:
        a flow reads `todo` and a person reads `todo`, and a line that moved up the board
        would otherwise be a different line.
      value: What it says now. Text, because both sides read it and one of them is a person:
        a line a model has to parse is a line a person cannot write.
      about: What the line is for, said where it is shown. Empty for one that speaks for
        itself.
      whose: Who may change it, as one of :data:`WHOSE`.
      at: When it last changed, as a monotonic moment. What a flow watches to know something
        has: a value that came back the same is a value nobody touched.
      by: Which side wrote what it says now, so that a flow reading its own board can tell a
        line it wrote from one somebody answered it with.
    """

    key: str
    value: str = ""
    about: str = ""
    whose: str = ANYONE
    at: float = field(default_factory=time.monotonic)
    by: str = FLOW

    def writable(self, by: str) -> bool:
        """Whether that side may change this line.

        Args:
          by: Which side is asking, as :data:`USER` or :data:`FLOW`.

        Returns:
          True where the line is either side's, or is that side's own.
        """
        return self.whose in (ANYONE, by)


class Board:
    """Every line of one run's board, and whatever is watching it.

    Held by the person the flow talks to rather than by the flow: the flow is a function that
    returns, and the board outlives any one turn of it. Whatever is showing the run reads it
    as it draws, and is told when it moves so that it draws again.

    Everything here is written from whichever thread had something to say -- a flow's own, a
    turn's, the interface's -- so all of it is under one lock, and what is read out is a copy.
    """

    def __init__(self, items: Iterable[Item] = ()) -> None:
        """Initializes a board holding whatever it was started with.

        Args:
          items: The lines to start with, in the order to show them. A flow that wants the
            board to open on something puts it here.
        """
        self._held: dict[str, Item] = {one.key: one for one in items}
        self._lock = threading.RLock()
        self._watchers: list[Callable[[Board], None]] = []

    def items(self) -> tuple[Item, ...]:
        """Every line, in the order they were first written.

        Returns:
          A copy, taken whole, so that whatever is drawing the board is drawing one moment of
          it rather than four moments of four lines.
        """
        with self._lock:
            return tuple(self._held.values())

    def get(self, key: str, otherwise: str = "") -> str:
        """What one line says now.

        Args:
          key: Which line.
          otherwise: What to answer for a line that is not there.

        Returns:
          Its value, or `otherwise`.
        """
        with self._lock:
            one = self._held.get(key)
            return one.value if one is not None else otherwise

    def held(self, key: str) -> Item | None:
        """One whole line, or None for a name the board does not have."""
        with self._lock:
            return self._held.get(key)

    def put(
        self,
        key: str,
        value: str,
        *,
        about: str | None = None,
        whose: str | None = None,
        by: str = FLOW,
    ) -> Item:
        """Writes a line, making it where there is none of that name.

        Args:
          key: What it is called.
          value: What it is to say.
          about: What the line is for, or None to leave what it says now -- so that writing a
            value does not have to say again what the line was for.
          whose: Who may change it, or None to leave that as it is. A line made without
            saying is one either side may change.
          by: Which side is writing, as :data:`USER` or :data:`FLOW`.

        Returns:
          The line as this call wrote it under the lock, which is the same thing :meth:`moves`
          answers with and read the same way: something watching is told before this returns.

        Raises:
          Refused: If the line is the other side's own.
          ValueError: If `whose` is not one of :data:`WHOSE`, or the line is unnamed.
        """
        if whose is not None and whose not in WHOSE:
            raise ValueError(f"{whose!r} is not one of {', '.join(WHOSE)}")
        named = key.strip()
        if not named:
            raise ValueError("a line of the board is named")
        with self._lock:
            was = self._held.get(named)
            if was is not None and not was.writable(by):
                raise Refused(f"{named} is {was.whose}'s to change, not {by}'s")
            one = Item(
                key=named,
                value=value,
                about=was.about if about is None and was is not None else (about or ""),
                whose=whose
                if whose is not None
                else (was.whose if was is not None else ANYONE),
                by=by,
            )
            self._held[named] = one
        self._moved()
        return one

    def drop(self, key: str, *, by: str = FLOW) -> bool:
        """Takes a line away, which is a flow having done what it said or a person changing.

        Args:
          key: Which line.
          by: Which side is taking it away.

        Returns:
          Whether there was one to take away.

        Raises:
            Refused: If the line is the other side's own.
        """
        with self._lock:
            was = self._held.get(key)
            if was is None:
                return False
            if not was.writable(by):
                raise Refused(f"{key} is {was.whose}'s to change, not {by}'s")
            del self._held[key]
        self._moved()
        return True

    def moves(self, key: str, *, to: str, by: str = FLOW) -> Item:
        """Renames a line, keeping everything else it says.

        Args:
          key: Which line.
          to: What to call it now.
          by: Which side is renaming it.

        Returns:
          The line under its new name, as this call made it under the lock rather than as
          the board stands by the time the answer is back: something watching is told before
          this returns, and may already have moved the line again or taken it away.

        Raises:
          Refused: If the line is the other side's own.
          KeyError: If there is no line of that name.
          ValueError: If the new name is already taken, or is not a name.
        """
        named = to.strip()
        if not named:
            raise ValueError("a line of the board is named")
        with self._lock:
            was = self._held.get(key)
            if was is None:
                raise KeyError(key)
            if not was.writable(by):
                raise Refused(f"{key} is {was.whose}'s to change, not {by}'s")
            if named != key and named in self._held:
                raise ValueError(f"the board already has a line called {named}")
            now = replace(was, key=named, by=by, at=time.monotonic())
            self._held = {
                (named if one == key else one): (now if one == key else line)
                for one, line in self._held.items()
            }
        self._moved()
        return now

    def watch(self, listener: Callable[[Board], None]) -> None:
        """Has this board tell something whenever a line of it moves.

        Args:
          listener: What to tell, which is given the board. A listener that raises has said
            nothing, in the way a watcher of an agent has: a flow must not fail because
            something watching it did.
        """
        with self._lock:
            self._watchers.append(listener)

    def _moved(self) -> None:
        """Tells everything watching that a line has moved."""
        with self._lock:
            watching = list(self._watchers)
        for one in watching:
            # A watcher that raised has said nothing, the way a watcher of an agent has: a
            # flow must not fail because something looking at its board did.
            with contextlib.suppress(Exception):
                one(self)

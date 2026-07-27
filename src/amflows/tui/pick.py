"""The two things there are to choose: which flow, and what each of its agents runs.

They are the two opencode has. Its tab switches the agent -- Build, Plan -- and that is what
a flow is here, so the same key switches flows. Its `/models` sets what that agent runs, and
`/agents` is that here, except that a flow drives more than one agent, so it asks once apiece.

What one agent runs is three things, so it is asked as three columns rather than as one list
of every backend crossed with every model crossed with every effort. Each column holds what
the ones to its left have under the cursor, enter moves right, and esc moves left -- off the
leftmost column, back to the agent chosen before this one. Nothing is final until the last
agent is.

The flows listed are the ones amflows came with and the ones written down where flows live:
`.amflows/flows` in this project, and the same under your home directory. A flow anywhere
else is a path you type, rather than one picked out of a walk of the directory -- which would
be a guess about which files are flows, and slow to make.
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, ClassVar

from rich.markup import escape
from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Label, OptionList
from textual.widgets.option_list import Option, OptionDoesNotExist

if TYPE_CHECKING:
    from .discover import Model

__all__ = ["Flows", "Models", "Sheet"]

#: What a choice is drawn in: a panel, unbordered, the question on the left and how to leave
#: on the right, the keys along the bottom -- which is opencode's own dialog.
_SHEET = """
Screen { align: center middle; }
#sheet { width: 64; height: auto; padding: 1 2; background: $panel; }
#head { height: 1; }
#asked { width: 1fr; text-style: bold; }
#leave { width: auto; color: $text-muted; }
OptionList { border: none; background: $panel; max-height: 14; scrollbar-size: 0 0; }
#choices { margin-top: 1; }
#columns { height: auto; margin-top: 1; }
.column { height: auto; }
.column Label { color: $text-muted; padding: 0 1; }
#agents { width: 14; }
#models { width: 1fr; }
#efforts { width: 12; }
/* Not one line: what has been chosen so far is said here too, and a flow driving three
   agents says more than a line holds. */
#keys { width: 1fr; height: auto; margin-top: 1; color: $text-muted; }
"""


class Sheet(ModalScreen[list[str] | None]):
    """One question drawn the way opencode draws one, answered by picking a line."""

    CSS = _SHEET
    BINDINGS: ClassVar = [("escape", "back", "back")]

    def compose(self) -> ComposeResult:
        """The question, how to leave it, what there is to choose, and the keys."""
        with Vertical(id="sheet"):
            with Horizontal(id="head"):
                yield Label(id="asked")
                yield Label("esc", id="leave")
            yield from self._choices()
            yield Label(id="keys")

    def on_mount(self) -> None:
        """Asks the first question."""
        self._ask()

    def action_back(self) -> None:
        """Leaves, there being nothing before the one thing this sheet asks."""
        self.dismiss(None)

    def _choices(self) -> ComposeResult:
        """What the choosing happens in, which each sheet says for itself."""
        raise NotImplementedError

    def _ask(self) -> None:
        """Draws whatever is being asked for now, which each sheet says for itself."""
        raise NotImplementedError


class Flows(Sheet):
    """Which flow to run, which is what opencode's tab switches between agents for."""

    def __init__(self, current: str):
        """Initializes the switching.

        Args:
          current: The flow running now, or "" if none has been chosen.
        """
        super().__init__()
        self._current = current

    def _choices(self) -> ComposeResult:
        """One list, since a flow is one thing to choose."""
        yield OptionList(id="choices")

    def _ask(self) -> None:
        """Lists every flow there is, grouped under where each came from."""
        from amflows.janus.flows import found

        self.query_one("#asked", Label).update("Select flow")
        self.query_one("#keys", Label).update(
            "enter chooses  esc cancels  ·  a flow anywhere else is a path you type"
        )
        listing = self.query_one("#choices", OptionList)
        listing.clear_options()
        under = ""
        for group, choice in found():
            if group != under:
                listing.add_option(Option(f"[dim]{escape(group)}[/dim]", disabled=True))
                under = group
            # Escaped, since a flow may be named with brackets in it.
            mark = "[cyan]●[/cyan] " if choice == self._current else "  "
            listing.add_option(Option(f"{mark}{escape(choice)}", id=choice))
        # On the one in force, or on the first that can be chosen -- never on a heading,
        # which is what `action_first` is for.
        try:
            listing.highlighted = listing.get_option_index(self._current)
        except OptionDoesNotExist:
            listing.action_first()
        listing.focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Answers with the flow that was picked.

        Args:
          event: What was chosen.
        """
        self.dismiss([str(event.option.id)])


class Models(Sheet):
    """What each of the flow's agents runs, asked once apiece as `/agents` does."""

    #: The columns, left to right, which is the order the three parts are answered in.
    _PARTS: ClassVar[tuple[str, ...]] = ("agent", "model", "effort")

    def __init__(self, flow: str, wanted: int, agents: dict[str, tuple[Model, ...]]):
        """Initializes the configuring.

        Args:
          flow: The flow whose agents these are.
          wanted: How many agents it drives.
          agents: The backends installed here, and what each says it runs.
        """
        super().__init__()
        self._flow = flow
        self._wanted = wanted
        self._agents = agents
        self._chosen: list[str] = []

    def _choices(self) -> ComposeResult:
        """Three columns, each headed with the part of an agent it holds."""
        with Horizontal(id="columns"):
            for part in self._PARTS:
                with Vertical(id=f"{part}s", classes="column"):
                    yield Label(part)
                    yield OptionList(id=part)

    def _ask(self) -> None:
        """Asks for one more agent, from the backends leftwards."""
        self.query_one("#asked", Label).update(
            f"Select what agent {len(self._chosen) + 1} of {self._wanted} runs"
        )
        self.query_one("#keys", Label).update(
            f"{escape(self._flow)}  ·  enter goes right  ·  esc goes back"
            + (f"  ·  {escape(', '.join(self._chosen))}" if self._chosen else "")
        )
        self._fill("agent")
        self.query_one("#agent", OptionList).focus()

    def action_back(self) -> None:
        """Steps one column left, and off the leftmost back to the agent before this one.

        Which is what the columns are for: nothing chosen is chosen for good until the last
        agent is, so a backend taken by mistake is one esc away rather than a sheet to start
        over. Off the leftmost column of the first agent there is nothing left to step back
        to, and this leaves.
        """
        under = "" if self.focused is None else str(self.focused.id)
        at = self._PARTS.index(under) if under in self._PARTS else 0
        if at:
            self.query_one(f"#{self._PARTS[at - 1]}", OptionList).focus()
            return
        if not self._chosen:
            self.dismiss(None)
            return
        # Read from both ends, because a model name may hold slashes of its own -- Kimi's
        # are `kimi-code/k3` -- while a backend and an effort never do.
        backend, _, rest = self._chosen.pop().partition("/")
        model, _, effort = rest.rpartition("/")
        self._ask()
        # Put back the way it was left, a column at a time: what hangs off a column cannot
        # be put back before the column it hangs off has been.
        for part, was in zip(self._PARTS, (backend, model, effort), strict=True):
            listing = self.query_one(f"#{part}", OptionList)
            with contextlib.suppress(OptionDoesNotExist):
                listing.highlighted = listing.get_option_index(was)
            self._fill(part)
        self.query_one("#effort", OptionList).focus()

    @on(OptionList.OptionHighlighted)
    def _moved(self, event: OptionList.OptionHighlighted) -> None:
        """Refills whatever hangs off the column the cursor just moved in.

        Args:
          event: Where it moved.
        """
        self._fill(str(event.option_list.id))

    @on(OptionList.OptionSelected)
    def _took(self, event: OptionList.OptionSelected) -> None:
        """Moves one column right, and off the rightmost takes the agent whole.

        Args:
          event: What was chosen, in whichever column it was chosen in.
        """
        at = self._PARTS.index(str(event.option_list.id))
        if at + 1 < len(self._PARTS):
            self.query_one(f"#{self._PARTS[at + 1]}", OptionList).focus()
            return
        self._chosen.append(
            f"{self._picked('agent')}/{self._picked('model')}/{self._picked('effort')}"
        )
        if len(self._chosen) < self._wanted:
            self._ask()
            return
        self.dismiss(self._chosen)

    def _fill(self, part: str) -> None:
        """Puts up a column and every column hanging off it, from what is under the cursor.

        A column already holding the right things is left alone, cursor and all -- which is
        what makes a walk back land where it was left, and what stops the refilling of one
        column from refilling the rest of them for ever.

        Args:
          part: The leftmost column to fill.
        """
        for at in range(self._PARTS.index(part), len(self._PARTS)):
            models = self._agents.get(self._picked("agent"), ())
            named = self._picked("model")
            choices = (
                sorted(self._agents)
                if self._PARTS[at] == "agent"
                else [model.name for model in models]
                if self._PARTS[at] == "model"
                # An effort a model does not take is not offered against it.
                else [
                    effort
                    for model in models
                    if model.name == named
                    for effort in model.efforts
                ]
            )
            listing = self.query_one(f"#{self._PARTS[at]}", OptionList)
            if choices == [str(option.id) for option in listing.options]:
                continue
            # Escaped, since a model may be named with brackets in it.
            listing.set_options(Option(escape(choice), id=choice) for choice in choices)
            listing.highlighted = 0 if choices else None

    def _picked(self, part: str) -> str:
        """What a column has under its cursor.

        Args:
          part: Which column.

        Returns:
          The choice under the cursor, or "" if the column is empty.
        """
        under = self.query_one(f"#{part}", OptionList).highlighted_option
        return "" if under is None else str(under.id)

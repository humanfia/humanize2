"""The two things there are to choose: which flow, and what each of its agents runs.

They are the two opencode has. Its tab switches the agent -- Build, Plan -- and that is what
a flow is here, so the same key switches flows. Its `/models` sets what that agent runs, and
that is what `/models` does here, except that a flow drives more than one agent, so it asks
once apiece.

Only the flows amflows came with are listed. A flow of your own is a path, and a path is
typed rather than picked out of a walk of the directory -- which would be a guess about
which files are flows, and slow to make.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from rich.markup import escape
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
#choices { border: none; background: $panel; max-height: 14; scrollbar-size: 0 0;
           margin-top: 1; }
#keys { height: 1; margin-top: 1; color: $text-muted; }
"""


class Sheet(ModalScreen[list[str] | None]):
    """One question drawn the way opencode draws one, answered by picking a line."""

    CSS = _SHEET
    BINDINGS: ClassVar = [("escape", "dismiss_sheet", "cancel")]

    def compose(self) -> ComposeResult:
        """The question, how to leave it, the choices, and the keys."""
        with Vertical(id="sheet"):
            with Horizontal(id="head"):
                yield Label(id="asked")
                yield Label("esc", id="leave")
            yield OptionList(id="choices")
            yield Label(id="keys")

    def on_mount(self) -> None:
        """Asks the first question."""
        self._ask()

    def action_dismiss_sheet(self) -> None:
        """Leaves without choosing anything."""
        self.dismiss(None)

    def _ask(self) -> None:
        """Draws whatever is being asked for now, which each sheet says for itself."""
        raise NotImplementedError

    def _draw(
        self, asked: str, keys: str, choices: list[tuple[str, str]], current: str = ""
    ) -> None:
        """Puts a question and its choices on screen, grouped under where they came from.

        Args:
          asked: The question.
          keys: What to say along the bottom.
          choices: The `(group, choice)` pairs, in the order they should read.
          current: The one in force now, marked as opencode marks its own.
        """
        self.query_one("#asked", Label).update(asked)
        self.query_one("#keys", Label).update(keys)
        listing = self.query_one("#choices", OptionList)
        listing.clear_options()
        under = ""
        for group, choice in choices:
            if group != under:
                listing.add_option(Option(f"[dim]{escape(group)}[/dim]", disabled=True))
                under = group
            # Escaped, since a model may be named with brackets in it.
            mark = "[cyan]●[/cyan] " if choice == current else "  "
            listing.add_option(Option(f"{mark}{escape(choice)}", id=choice))
        # On the one in force, or on the first real choice -- never on a heading, which is
        # why this is asked of the list rather than counted out of `choices`.
        try:
            listing.highlighted = listing.get_option_index(current)
        except OptionDoesNotExist:
            listing.highlighted = 1 if choices else 0
        listing.focus()


class Flows(Sheet):
    """Which flow to run, which is what opencode's tab switches between agents for."""

    def __init__(self, current: str):
        """Initializes the switching.

        Args:
          current: The flow running now, or "" if none has been chosen.
        """
        super().__init__()
        self._current = current

    def _ask(self) -> None:
        """Lists the flows amflows came with, which are the ones there are to pick."""
        from amflows.janus.flows import prebuilt

        self._draw(
            "Select flow",
            "enter chooses  esc cancels  ·  a flow of your own is a path you type",
            [("amflows", name) for name in prebuilt()],
            self._current,
        )

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Answers with the flow that was picked.

        Args:
          event: What was chosen.
        """
        self.dismiss([str(event.option.id)])


class Models(Sheet):
    """What each of the flow's agents runs, asked once apiece as `/models` does."""

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

    def _ask(self) -> None:
        """Asks for one agent, grouped under the backend each would run on."""
        self._draw(
            f"Select model for agent {len(self._chosen) + 1} of {self._wanted}",
            f"{self._flow}  ·  backend, model, effort",
            [
                (backend, f"{backend}/{model.name}/{effort}")
                for backend, models in sorted(self._agents.items())
                for model in models
                # An effort a model does not take is not offered against it.
                for effort in model.efforts
            ],
        )

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Takes one agent, then asks for the next, or answers with all of them.

        Args:
          event: What was chosen.
        """
        self._chosen.append(str(event.option.id))
        if len(self._chosen) < self._wanted:
            self._ask()
            return
        self.dismiss(self._chosen)

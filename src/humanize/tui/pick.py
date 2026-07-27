"""The two things there are to choose: which flow, and what each of its agents runs.

Drawn as Claude Code draws its own `/model`, which is the same question one step along: a rule
of `▔` across the top, the question and a line about it indented three, the choices numbered
with `❯` against the one under the cursor and a `✔` against the one already in force, and
under them the one setting that is adjusted rather than chosen -- the effort -- on a line the
left and right arrows move along. The keys are said at the bottom and nowhere else.

What one agent runs is a CLI, a model and an effort. The first two are one choice here rather
than two, because they are one choice in fact: a model belongs to the CLI that runs it, and a
list of the pairs is shorter than a walk through two columns. The effort is the line with the
arrows on it, exactly as Claude Code's is.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from rich.markup import escape
from textual import on
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Label, OptionList
from textual.widgets.option_list import Option

if TYPE_CHECKING:
    from .discover import Model

__all__ = ["Flows", "Models", "Sheet"]

#: What Claude Code rules the top of a sheet with, and how far in everything under it sits.
_RULE = "▔"
_INDENT = "   "

#: The marker against the choice under the cursor, and against the one already in force.
_HERE = "❯"
_INFORCE = "✔"

#: How wide the column of names is before the line about each one starts.
_LABEL = 24

_SHEET = """
Flows, Models { align: center middle; background: $background; }
#sheet { width: 100%; height: auto; padding: 0; }
#rule { height: 1; color: $primary; }
#asked { padding: 0 0 0 3; text-style: bold; color: $primary; }
#about { padding: 0 3 1 3; color: $text-muted; width: 1fr; }
OptionList { border: none; background: $background; max-height: 14; scrollbar-size: 0 0;
             padding: 0; }
/* The marker says where the cursor is, so the row is not filled as well. */
#choices > .option-list--option-highlighted {
    background: $background; color: $foreground; text-style: none; }
#tuning { padding: 1 0 1 3; }
#keys { padding: 0 0 0 3; color: $text-muted; }
"""


class Sheet(ModalScreen[list[str] | None]):
    """One question drawn the way Claude Code draws one, answered by picking a line."""

    CSS = _SHEET
    BINDINGS: ClassVar = [("escape", "back", "back")]

    #: Which row the marker was last drawn against. Putting the rows up moves the cursor,
    #: which asks for them to be put up again -- and the message saying so is posted rather
    #: than called, so a flag set around the drawing is already clear by the time it arrives.
    #: What breaks the loop is having nothing to do: the marker is already where it goes.
    _drawn: int | None = None
    #: How many columns the numbering takes, so that every row starts in the same one.
    _counting = 1

    def compose(self) -> ComposeResult:
        """The rule, the question, what there is to choose, what is tuned, and the keys."""
        with Vertical(id="sheet"):
            yield Label(id="rule")
            yield Label(id="asked")
            yield Label(id="about")
            yield OptionList(id="choices")
            yield Label(id="tuning")
            yield Label(id="keys")

    def on_mount(self) -> None:
        """Rules the top of the sheet across, and asks."""
        self.query_one("#rule", Label).update(_RULE * self.size.width)
        self._ask()

    def action_back(self) -> None:
        """Leaves, there being nothing before the one thing this sheet asks."""
        self.dismiss(None)

    def _row(
        self, at: int, label: str, about: str, *, here: bool, inforce: bool
    ) -> str:
        """One numbered choice, laid out as Claude Code lays one out.

        Args:
          at: Which one it is, counting from zero.
          label: What it is called.
          about: The line about it, which is said quietly.
          here: Whether the cursor is on it.
          inforce: Whether it is the one already in force.

        Returns:
          The row, as markup.
        """
        mark = f"{_INDENT}[$primary]{_HERE}[/] " if here else f"{_INDENT}  "
        # Right-aligned, so that the tenth row starts where the ninth does.
        number = f"{at + 1:>{self._counting}}."
        named = escape(label) + (f" [$success]{_INFORCE}[/]" if inforce else "")
        # Padded on what is shown rather than on what is written: markup is not columns.
        pad = " " * max(1, _LABEL - len(label) - (2 if inforce else 0))
        return f"{mark}[$text-muted]{number}[/] {named}{pad}[$text-muted]{escape(about)}[/]"

    @on(OptionList.OptionHighlighted)
    def _moved(self, event: OptionList.OptionHighlighted) -> None:
        """Redraws, so the marker sits beside the row the cursor moved to.

        Only when it has moved somewhere the marker is not already: putting the rows up sets
        the cursor, which posts one of these, and redrawing on that would be one keypress and
        renders without end -- which is what a list that lags is.

        Args:
          event: Where the cursor is now.
        """
        if event.option_index == self._drawn:
            return
        self._drawn = event.option_index
        self._fill()

    def _fill(self) -> None:
        """Puts the choices up, which each sheet says for itself."""
        raise NotImplementedError

    def _ask(self) -> None:
        """Draws whatever is being asked for now, which each sheet says for itself."""
        raise NotImplementedError


class Flows(Sheet):
    """Which flow to run, which is what tab switches between."""

    def __init__(self, current: str):
        """Initializes the switching.

        Args:
          current: The flow running now, or "" if none has been chosen.
        """
        super().__init__()
        self._current = current
        self._named: list[tuple[str, str]] = []

    def _ask(self) -> None:
        """Lists every flow there is, saying where each one came from."""
        self.query_one("#asked", Label).update("Select flow")
        self.query_one("#about", Label).update(
            "Which flow the agents are driven through. The first thing you say once it is "
            "chosen is what it is to do. A flow anywhere else is a path you type."
        )
        self.query_one("#tuning", Label).update("")
        self.query_one("#keys", Label).update("Enter to choose · Esc to cancel")
        self._fill()

    def _fill(self) -> None:
        """Puts the flows up, with the marker beside the one the cursor is on."""
        from humanize.flows import found

        listing = self.query_one("#choices", OptionList)
        if not self._named:
            self._named = [(name, whose) for whose, name in found()]
            self._counting = len(str(len(self._named)))
        at = listing.highlighted or 0
        listing.set_options(
            Option(
                self._row(
                    seen, name, whose, here=seen == at, inforce=name == self._current
                ),
                id=name,
            )
            for seen, (name, whose) in enumerate(self._named)
        )
        listing.highlighted = at
        self._drawn = at

    @on(OptionList.OptionSelected)
    def _took(self, event: OptionList.OptionSelected) -> None:
        """Answers with the flow that was picked.

        Args:
          event: What was chosen.
        """
        self.dismiss([str(event.option.id)])


class Models(Sheet):
    """What each of the flow's agents runs, asked once apiece as `/agents` does."""

    BINDINGS: ClassVar = [
        ("escape", "back", "back"),
        ("left", "easier", "less effort"),
        ("right", "harder", "more effort"),
    ]

    def __init__(
        self, flow: str, wanted: tuple[str, ...], agents: dict[str, tuple[Model, ...]]
    ):
        """Initializes the configuring.

        Args:
          flow: The flow whose agents these are.
          wanted: What the flow calls each agent it drives, in the order it takes them, which
            is "" apiece for a flow that said how many it drives and nothing more.
          agents: The CLIs installed here, and what each says it runs.
        """
        super().__init__()
        self._flow = flow
        self._wanted = wanted
        # One choice rather than two: a model belongs to the CLI that runs it.
        self._runs = [
            (backend, model) for backend in sorted(agents) for model in agents[backend]
        ]
        self._chosen: list[str] = []
        self._effort = 0
        self._counting = len(str(len(self._runs)))

    def _ask(self) -> None:
        """Asks for one more agent, from the models down."""
        at = len(self._chosen)
        named = self._wanted[at] or f"agent {at + 1} of {len(self._wanted)}"
        self.query_one("#asked", Label).update(f"Select what {named} runs")
        self.query_one("#about", Label).update(
            f"Which coding agent takes this one's turns in {self._flow}, and the model it "
            "runs at. Two agents at one model are still two agents."
        )
        self._effort = 0
        self._fill()
        self.query_one("#choices", OptionList).focus()

    def _fill(self) -> None:
        """Puts the models up, and under them the effort the arrows move along."""
        listing = self.query_one("#choices", OptionList)
        at = listing.highlighted or 0
        listing.set_options(
            Option(
                self._row(seen, model.name, backend, here=seen == at, inforce=False),
                id=f"{backend}/{model.name}",
            )
            for seen, (backend, model) in enumerate(self._runs)
        )
        listing.highlighted = at
        self._drawn = at
        self._effort = min(self._effort, len(self._efforts()) - 1)
        self.query_one("#tuning", Label).update(
            f"[$secondary]◉[/] {self._efforts()[self._effort]} effort  "
            f"[$text-muted]←/→ to adjust[/]"
        )
        self.query_one("#keys", Label).update(
            "Enter to choose · Esc to cancel"
            + (f"  ·  {escape(' · '.join(self._chosen))}" if self._chosen else "")
        )

    def _efforts(self) -> tuple[str, ...]:
        """What the model under the cursor takes, hardest first."""
        listing = self.query_one("#choices", OptionList)
        _, model = self._runs[listing.highlighted or 0]
        return model.efforts

    def action_harder(self) -> None:
        """Moves one along the efforts, towards the one that thinks hardest."""
        self._effort = max(self._effort - 1, 0)
        self._fill()

    def action_easier(self) -> None:
        """Moves one along the efforts, towards the one that thinks least."""
        self._effort = min(self._effort + 1, len(self._efforts()) - 1)
        self._fill()

    @on(OptionList.OptionSelected)
    def _took(self, event: OptionList.OptionSelected) -> None:
        """Takes this agent whole, and asks for the next one the flow drives.

        Args:
          event: What was chosen.
        """
        self._chosen.append(f"{event.option.id}:{self._efforts()[self._effort]}")
        if len(self._chosen) < len(self._wanted):
            self._ask()
            return
        self.dismiss(self._chosen)

"""The sheets: which flow, what each of its agents runs, and how the run is going.

Drawn as Claude Code draws its own `/model`, which is the same question one step along: a rule
of `▔` across the top, the question and a line about it indented three, the choices numbered
with `❯` against the one under the cursor and a `✔` against the one already in force, and
under them the one setting that is adjusted rather than chosen -- the effort -- on a line the
left and right arrows move along. The keys are said at the bottom and nowhere else.

What one agent runs is a CLI, a model and an effort. The first two are one choice here rather
than two, because they are one choice in fact: a model belongs to the CLI that runs it, and a
list of the pairs is shorter than a walk through two columns. The effort is the line with the
arrows on it, exactly as Claude Code's is.

`/status` is the third of them, and is read rather than answered -- Claude Code's own, which
is a rule across, fields down the left and their values lined up beside them.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, ClassVar, NamedTuple, cast

from rich.markup import escape
from textual import events, on, work
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Label, OptionList
from textual.widgets.option_list import Option

from humanize.agents import DRIVEN, SWARM, Moment, anchored

from .discover import machines
from .monitor import short, thousands

if TYPE_CHECKING:
    from textual.app import App, ComposeResult

    from humanize.backends import Model
    from humanize.runner import Place

    from .monitor import Monitor

__all__ = ["Anchors", "Flows", "Models", "Runs", "Sheet", "Status", "reads"]


class Runs(NamedTuple):
    """What one agent of a flow was set up to run, and where its turns land.

    Attributes:
      spec: The agent itself, as `cli/model:effort` -- the same word a command line takes.
      anchor: The machine its work lands on, as a target, or "" to work on this one.
    """

    spec: str
    anchor: str = ""


#: What Claude Code rules the top of a sheet with, and how far in everything under it sits.
_RULE = "▔"
_INDENT = "   "

#: The dot Claude Code separates the parts of a line with.
_DOT = " · "

#: The marker against the choice under the cursor, and against the one already in force.
_HERE = "❯"
_INFORCE = "✔"

#: How wide the column of names is before the line about each one starts. A model id
#: may hold slashes of its own -- Kimi Code's are `kimi-code/k3` -- and is shown as the
#: CLI is given it, since a name shortened here is not the name of anything.
_LABEL = 26

#: How wide the column of field names on `/status` is, so their values line up beside them.
_FIELD = 18

#: How often `/status` is redrawn, in seconds. It is read while a flow is running, which is
#: the whole point of it: a sheet that froze what it said the moment it opened would be a
#: snapshot of a run, and the run is what is being watched.
_LIVE = 0.5


def reads(named: tuple[str, ...], runs: list[Runs]) -> list[str]:
    """One line per agent a flow drives: what it is called, what it runs, and where.

    In one place because it is read in two -- above the prompt while a flow runs, and on
    `/status` -- and an agent that read as two different things in them would be two.

    Args:
      named: What the flow calls each of them, "" apiece where it names none.
      runs: What each of them runs, and where its turns land.

    Returns:
      One line apiece, in the order the flow takes them.
    """
    return [
        _DOT.join(
            escape(part)
            for part in (
                named[at] if at < len(named) else "",
                one.spec,
                one.anchor,
            )
            if part
        )
        for at, one in enumerate(runs)
    ]


_SHEET = """
Anchors, Flows, Models, Status { align: center middle; background: $background; }
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
/* The fields carry their own indent, as the numbered rows above them do. */
#said { padding: 0 0 1 0; }
"""


class Sheet[T](ModalScreen[T | None]):
    """One question drawn the way Claude Code draws one, answered by picking a line.

    What answering it comes to is the sheet's own: a flow is a name, an agent is what it runs
    and where, and walking out without answering is None wherever it is asked.
    """

    CSS = _SHEET
    BINDINGS: ClassVar = [("escape", "back", "back")]

    #: Which row the marker was last drawn against. Putting the rows up moves the cursor,
    #: which asks for them to be put up again -- and the message saying so is posted rather
    #: than called, so a flag set around the drawing is already clear by the time it arrives.
    #: What breaks the loop is having nothing to do: the marker is already where it goes.
    _drawn: int | None = None
    #: How many columns the numbering takes, so that every row starts in the same one.
    _counting = 1
    #: What has been typed to narrow the list down. A list of every model of every CLI is
    #: longer than a screen, and a list you walk to the end of to find one thing is one you
    #: read rather than use -- so the letters go into it instead of nowhere.
    _typed = ""

    def fits(self, *fields: str) -> bool:
        """Whether a row is one of the ones still worth showing.

        Args:
          fields: Everything the row says, which is all of it that is searched: what a thing
            is called, and where it came from.

        Returns:
          True if what has been typed is spread through one of them in order -- `cop` finds
          `claude-opus-5`, since nobody types a model id out to narrow a list of them. One of
          them rather than all of them run together, or a search would run off the end of the
          name it was narrowing to and finish itself in the word beside it: `chat` would find
          `flame_chase builtin`, which is a match nobody typed.
        """
        if not self._typed:
            return True
        wanted = self._typed.lower()
        for field in fields:
            looking, at = field.lower(), 0
            for letter in wanted:
                at = looking.find(letter, at) + 1
                if not at:
                    break
            else:
                return True
        return False

    def searching(self) -> str:
        """What to say about the letters typed so far, which is nothing until some are."""
        return f"{_DOT}{escape(self._typed)}" if self._typed else ""

    def on_key(self, event: events.Key) -> None:
        """Takes a letter as something to narrow the list with.

        The arrows walk it, enter takes what is under the cursor, and everything else that
        is a character is searching: there is nothing else to type at here, so nothing is
        being taken away from anything.

        Args:
          event: The key.
        """
        if event.key == "backspace":
            self._typed = self._typed[:-1]
        elif event.is_printable and event.character:
            self._typed += event.character
        else:
            return
        event.prevent_default()
        event.stop()
        self.query_one("#choices", OptionList).highlighted = 0
        self._drawn = 0
        self._fill()

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
        """Clears what was typed, or leaves once there is nothing left to clear.

        A search narrowed to nothing is the one place esc has something to step back to:
        leaving from there would throw away the walk in as well as the wrong letters.
        """
        if self._typed:
            self._typed = ""
            self._drawn = 0
            self._fill()
            return
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


class Flows(Sheet[list[str]]):
    """Which flow to run, which is what tab switches between."""

    def __init__(self, current: str) -> None:
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
        self._fill()

    def _fill(self) -> None:
        """Puts the flows up, with the marker beside the one the cursor is on."""
        from humanize.flows import found

        listing = self.query_one("#choices", OptionList)
        if not self._named:
            self._named = [(name, whose) for whose, name in found()]
            self._counting = len(str(len(self._named)))
        shown = [pair for pair in self._named if self.fits(*pair)]
        at = min(listing.highlighted or 0, max(len(shown) - 1, 0))
        listing.set_options(
            Option(
                self._row(
                    seen, name, whose, here=seen == at, inforce=name == self._current
                ),
                id=name,
            )
            for seen, (name, whose) in enumerate(shown)
        )
        listing.highlighted = at if shown else None
        self._drawn = at
        self.query_one("#keys", Label).update(
            f"Type to search · Enter to choose · Esc to cancel{self.searching()}"
        )

    @on(OptionList.OptionSelected)
    def _took(self, event: OptionList.OptionSelected) -> None:
        """Answers with the flow that was picked.

        Args:
          event: What was chosen.
        """
        self.dismiss([str(event.option.id)])


class Models(Sheet[list[Runs]]):
    """What each of the flow's agents runs, asked once apiece as `/agents` does."""

    BINDINGS: ClassVar = [
        ("escape", "back", "back"),
        ("left", "easier", "less effort"),
        ("right", "harder", "more effort"),
        # Not an arrow, because swarm mode is not a step along the efforts: it is a second
        # thing to say about a turn -- how wide it runs, rather than how hard -- and a turn
        # that is both is written down as both.
        Binding("tab", "swarm", "swarm mode", priority=True),
        # Nor is where the work lands a way of running the model, so it is neither an arrow
        # nor a row: it is a second question about this agent, and it opens a sheet of its
        # own. A chord rather than a letter, because the letters are searching.
        Binding("ctrl+a", "anchor", "anchor", priority=True),
    ]

    def __init__(
        self, flow: str, wanted: tuple[Place, ...], agents: dict[str, tuple[Model, ...]]
    ) -> None:
        """Initializes the configuring.

        Args:
          flow: The flow whose agents these are.
          wanted: One place per agent the flow drives, in the order it takes them: what the
            flow calls each -- "" apiece for a flow that said how many it drives and nothing
            more -- and the moments it needs that one to run.
          agents: The CLIs installed here, and what each says it runs.
        """
        super().__init__()
        self._flow = flow
        self._wanted = wanted
        # One choice rather than two: a model belongs to the CLI that runs it.
        self._runs = [
            (backend, model) for backend in sorted(agents) for model in agents[backend]
        ]
        self._chosen: list[Runs] = []
        self._effort = 0
        #: Whether the turn runs as a fleet rather than as one agent, for a model that takes
        #: it. Held here rather than among the efforts, and asked of each agent afresh.
        self._swarm = False
        #: Where this one's turns land, which is this machine until it is said otherwise.
        self._anchor = ""
        self._counting = len(str(len(self._runs)))
        #: The ones the letters typed so far have left, which is what the cursor is walking.
        self._shown = list(self._runs)

    def _ask(self) -> None:
        """Asks for one more agent, from the models down."""
        at = len(self._chosen)
        named = self._wanted[at].name or f"agent {at + 1} of {len(self._wanted)}"
        self.query_one("#asked", Label).update(f"Select what {named} runs")
        needs = self._wanted[at].moments
        self.query_one("#about", Label).update(
            f"Which coding agent takes this one's turns in {self._flow}, and the model it "
            "runs at. Two agents at one model are still two agents."
            + (
                f" This one has to run {', '.join(sorted(needs))}, so only the CLIs that do "
                "are listed."
                if needs
                else ""
            )
        )
        self._effort = 0
        self._swarm = False
        self._anchor = ""
        self._typed = ""  # each agent is asked about from the whole list again
        self._fill()
        self.query_one("#choices", OptionList).focus()

    def _able(self) -> list[tuple[str, Model]]:
        """The models that could take this agent's turns, which is not always all of them.

        A flow that hangs a hook on a moment only some backends run said so where it declared
        the place; a CLI that does not run that moment is not one to offer for it, since
        choosing it is a flow that would refuse to start.

        Returns:
          One `(cli, model)` pair per model still worth showing.
        """
        # The last one again once every place is answered: putting the rows up moves the
        # cursor, and that asks for them again -- after the last choice has been taken.
        at = min(len(self._chosen), len(self._wanted) - 1)
        needs = self._wanted[at].moments if self._wanted else frozenset[Moment]()
        return [
            (backend, model)
            for backend, model in self._runs
            if not needs or (backend in DRIVEN and needs <= DRIVEN[backend][0].moments)
        ]

    def _fill(self) -> None:
        """Puts the models up, and under them the effort the arrows move along."""
        listing = self.query_one("#choices", OptionList)
        self._shown = [
            (backend, model)
            for backend, model in self._able()
            if self.fits(model.name, backend)
        ]
        at = min(listing.highlighted or 0, max(len(self._shown) - 1, 0))
        listing.set_options(
            Option(
                self._row(seen, model.name, backend, here=seen == at, inforce=False),
                id=f"{backend}/{model.name}",
            )
            for seen, (backend, model) in enumerate(self._shown)
        )
        listing.highlighted = at if self._shown else None
        self._drawn = at
        efforts = self._efforts()
        self._effort = min(self._effort, len(efforts) - 1) if efforts else 0
        tuned = (
            f"[$secondary]◉[/] {efforts[self._effort]} effort  "
            f"[$text-muted]←/→ to adjust[/]"
            if efforts
            else ""
        )
        if tuned and self._swarms():
            said = "on" if self._swarm else "off"
            tuned += (
                f"{_DOT}[$secondary]◉[/] swarm mode {said}  "
                f"[$text-muted]tab to toggle[/]"
            )
        if tuned:
            tuned += (
                f"{_DOT}[$secondary]◉[/] on {escape(self._anchor or 'this machine')}  "
                f"[$text-muted]ctrl+a to move[/]"
            )
        self.query_one("#tuning", Label).update(tuned)
        self.query_one("#keys", Label).update(
            f"Type to search · Enter to choose · Esc to cancel{self.searching()}"
            + (
                f"{_DOT}{escape(' · '.join(runs.spec for runs in self._chosen))}"
                if self._chosen
                else ""
            )
        )

    @work
    async def action_anchor(self) -> None:
        """Asks where this agent's turns land, and comes back here either way.

        A walk out of the anchors without choosing leaves this one where it was: the machine
        is a second question about the agent, and declining to answer it is not declining to
        choose the agent.
        """
        # textual types the property off the bare generic, so what it hands back is an `App`
        # of nothing in particular.
        showing = cast(
            "App[None]",
            self.app,  # pyright: ignore[reportUnknownMemberType]
        )
        where = await showing.push_screen_wait(Anchors(self._anchor))
        if where is not None:
            self._anchor = where
            self._fill()

    def _efforts(self) -> tuple[str, ...]:
        """What the model under the cursor takes, hardest first, or none where none is."""
        under = self._under()
        return under.efforts if under is not None else ()

    def _swarms(self) -> bool:
        """Whether the model under the cursor runs a turn as a fleet as well as as an agent."""
        under = self._under()
        return under is not None and under.swarms

    def _under(self) -> Model | None:
        """The model the cursor is on, or None where the letters typed have left none."""
        if not self._shown:
            return None
        listing = self.query_one("#choices", OptionList)
        return self._shown[min(listing.highlighted or 0, len(self._shown) - 1)][1]

    def action_swarm(self) -> None:
        """Turns swarm mode on or off, for a model that has one to turn on."""
        if self._swarms():
            self._swarm = not self._swarm
            self._fill()

    def action_harder(self) -> None:
        """Moves one along the efforts, towards the one that thinks hardest."""
        self._effort = max(self._effort - 1, 0)
        self._fill()

    def action_easier(self) -> None:
        """Moves one along the efforts, towards the one that thinks least."""
        self._effort = min(self._effort + 1, max(len(self._efforts()) - 1, 0))
        self._fill()

    @on(OptionList.OptionSelected)
    def _took(self, event: OptionList.OptionSelected) -> None:
        """Takes this agent whole, and asks for the next one the flow drives.

        Args:
          event: What was chosen.
        """
        # `swarm` in front of the effort is how Kimi is asked for a fleet: one turn at one
        # effort, run wide. A model that does not take it is chosen at the effort alone.
        wide = SWARM if self._swarm and self._swarms() else ""
        self._chosen.append(
            Runs(
                spec=f"{event.option.id}:{wide}{self._efforts()[self._effort]}",
                anchor=self._anchor,
            )
        )
        if len(self._chosen) < len(self._wanted):
            self._ask()
            return
        self.dismiss(self._chosen)


class Anchors(Sheet[str]):
    """Where one agent's turns land: this machine, or one an anchor reaches.

    The agent itself runs here whatever is chosen -- its credentials, its state directory and
    its link to its model provider stay put. What moves is the project it reads and the
    commands it runs, which is why this is a question about the agent rather than about the
    flow: two agents of one flow may work on two machines.

    Listed rather than typed where the machine is one this one can see -- a container that is
    running, a host with an entry in the ssh config -- and typed where it is not: a target is
    a string, and the row for what has been typed appears as soon as it reads as one.
    """

    def __init__(self, current: str) -> None:
        """Initializes the moving.

        Args:
          current: The target this agent is on now, or "" for this machine.
        """
        super().__init__()
        self._current = current
        self._found: list[tuple[str, str]] | None = None

    def _ask(self) -> None:
        """Lists the machines there are to work on, and says what choosing one does."""
        self.query_one("#asked", Label).update("Select where this agent works")
        self.query_one("#about", Label).update(
            "The machine its work lands on. The agent still runs here; what moves is the "
            "project it reads and the commands it runs. Anywhere else is a target you type "
            "-- ssh://HOST, docker://CONTAINER, tcp://HOST:PORT."
        )
        self.query_one("#tuning", Label).update("")
        self._fill()

    def _fill(self) -> None:
        """Puts the machines up, with whatever has been typed among them if it reads as one."""
        listing = self.query_one("#choices", OptionList)
        if self._found is None:
            # Once: looking costs a `docker ps`, and this is redrawn on every keystroke.
            self._found = machines()
        rows: list[tuple[str, str, str]] = [("", "this machine", "nothing moves")]
        rows.extend((target, target, whose) for target, whose in self._found)
        shown = [row for row in rows if self.fits(row[1], row[2])]
        if self._typed and not any(row[0] == self._typed for row in shown):
            # What has been typed, as soon as it is a target: a machine nobody here can see
            # is still a machine, and this is the only way to name one.
            try:
                anchored(self._typed)
            except ValueError:
                pass
            else:
                shown.append((self._typed, self._typed, "as typed"))
        self._counting = len(str(len(shown)))
        at = min(listing.highlighted or 0, max(len(shown) - 1, 0))
        listing.set_options(
            Option(
                self._row(
                    seen, label, whose, here=seen == at, inforce=target == self._current
                ),
                # Every row is a target, and "" is this machine -- which an id of its own
                # keeps tellable from a row that was never chosen.
                id=f"={target}",
            )
            for seen, (target, label, whose) in enumerate(shown)
        )
        listing.highlighted = at if shown else None
        self._drawn = at
        self.query_one("#keys", Label).update(
            f"Type a target · Enter to choose · Esc to cancel{self.searching()}"
        )

    @on(OptionList.OptionSelected)
    def _took(self, event: OptionList.OptionSelected) -> None:
        """Answers with the target that was picked.

        Args:
          event: What was chosen.
        """
        self.dismiss(str(event.option.id).removeprefix("="))


class Status(ModalScreen[None]):
    """How the run is going: who is working, who handed to whom, and what it has cost.

    Which is where the column that used to sit beside the transcript went. What a flow is
    doing is worth a look now and then and not worth a fifth of the screen the whole time:
    the transcript is what is being read, and the column was taking width off it to say
    something that mostly had not changed since the last glance. Opened while a flow runs,
    since that is when there is anything to see, and redrawn while it is open.
    """

    CSS = _SHEET
    BINDINGS: ClassVar = [("escape", "back", "back")]

    def __init__(
        self, flow: str, named: tuple[str, ...], models: list[Runs], monitor: Monitor
    ) -> None:
        """Reads one run.

        Args:
          flow: The flow being run.
          named: What that flow calls each agent it drives, "" apiece where it names none.
          models: What each of its agents runs, and where its turns land.
          monitor: The run itself, read again each time this is redrawn.
        """
        super().__init__()
        self._flow = flow
        self._named = named
        self._models = models
        self._monitor = monitor

    def compose(self) -> ComposeResult:
        """The rule, what this is, the fields, and the way out."""
        with Vertical(id="sheet"):
            yield Label(id="rule")
            yield Label(id="asked")
            yield Label(id="said")
            yield Label(id="keys")

    def on_mount(self) -> None:
        """Rules the top of the sheet across, says what it is, and starts redrawing."""
        self.query_one("#rule", Label).update(_RULE * self.size.width)
        self.query_one("#asked", Label).update("Status")
        self.query_one("#keys", Label).update("Esc to close")
        self._draw()
        self.set_interval(_LIVE, self._draw)

    def action_back(self) -> None:
        """Leaves, there being nothing here to answer."""
        self.dismiss(None)

    def _draw(self) -> None:
        """Puts up what the run looks like as of now."""
        over = (self._monitor.until or time.monotonic()) - self._monitor.began
        spending = self._monitor.spending()
        # Grouped as Claude Code groups its own: what is set up, what is happening, what it
        # has cost, with a blank line between one group and the next.
        groups: list[list[tuple[str, list[str]]]] = [
            [
                ("Flow", [escape(self._flow)]),
                ("Agents", reads(self._named, self._models) or ["none installed"]),
            ],
            [
                (
                    "Working",
                    [short(who) for who in self._monitor.now_working()]
                    or ["[$text-muted]nobody[/]"],
                ),
                ("Running", [f"{over:.0f}s"]),
                ("Turns", self._monitor.graph() or ["[$text-muted]nothing yet[/]"]),
            ],
            [
                (
                    "Tokens",
                    [
                        f"{escape(spend.model):<26}{thousands(spend.tokens):>8}"
                        f"   [$text-muted]{spend.rate:.0f}/s[/]"
                        for spend in spending
                    ]
                    or ["[$text-muted]nothing spent yet[/]"],
                ),
            ],
        ]
        lines: list[str] = []
        for group in groups:
            for field, values in group:
                for at, value in enumerate(values):
                    # The field is named against the first of its values and the rest are
                    # left to line up under it, which is how a list reads as one field.
                    head = f"{field}:" if at == 0 else ""
                    lines.append(f"{_INDENT}[$text-muted]{head:<{_FIELD}}[/]{value}")
            lines.append("")
        self.query_one("#said", Label).update("\n".join(lines))

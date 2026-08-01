"""The sheets: which flow, how it is set up, what each of its agents runs, and how it goes.

Drawn as Claude Code draws its own `/model`, which is the same question one step along: a rule
of `▔` across the top, the question and a line about it indented three, the choices numbered
with `❯` against the one under the cursor and a `✔` against the one already in force, and
under them the one setting that is adjusted rather than chosen -- the effort -- on a line the
left and right arrows move along. The keys are said at the bottom and nowhere else.

One agent is three steps, in this order and one agent at a time: which coding agent takes its
turns and which account it runs as (:class:`RunsAs`), which model it runs and at what effort
(:class:`Models`), and -- only where the flow said that one may be pointed at a machine --
where its work lands (:class:`Anchors`). The order is the order of what depends on what: an
account belongs to a backend and a model belongs to the CLI that runs it, so neither can be
asked before the CLI has been. The CLIs are read one at a time, a tab apiece and only the ones
installed here, since every model of every CLI in one list is a list that grows each time any
of them ships a model. The effort is the line with the arrows on it, exactly as Claude Code's
is, and beside it the things that really are side questions about the same agent.

`/status` is the last of them, and is read rather than answered -- Claude Code's own, which is
a rule across, fields down the left and their values lined up beside them.
"""

from __future__ import annotations

import contextlib
import time
from typing import (
    TYPE_CHECKING,
    Any,
    ClassVar,
    Literal,
    NamedTuple,
    cast,
    get_args,
    get_origin,
)

from rich.markup import escape
from textual import events, on, work
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Label, OptionList
from textual.widgets.option_list import Option

from humanize.agents import DRIVEN, PERMISSIONS, SWARM, anchored
from humanize.agents.skills import Skill, skills
from humanize.backends import named

from .discover import machines
from .monitor import short, thousands

if TYPE_CHECKING:
    from collections.abc import Generator

    from pydantic import BaseModel
    from pydantic.fields import FieldInfo
    from textual.app import App, ComposeResult

    from humanize.backends import Model, Way
    from humanize.providers import Provider
    from humanize.runner import Place

    from .monitor import Monitor

__all__ = [
    "Anchors",
    "Backends",
    "Configures",
    "Doing",
    "Flows",
    "Models",
    "Picks",
    "Providers",
    "Runs",
    "RunsAs",
    "Sheet",
    "Signing",
    "Signs",
    "Skills",
    "Status",
    "Ways",
    "Whose",
    "called",
    "pointed",
    "reads",
    "setting",
]


class Runs(NamedTuple):
    """What one agent of a flow was set up to run, and where its turns land.

    Attributes:
      spec: The agent itself, as `cli/model:effort` -- the same word a command line takes.
      anchor: The machine its work lands on, as a target, or "" to work on this one.
      skills: The skills of its CLI it is to have, by name, or None for the CLI as it comes
        -- which is every skill it finds.
      permission: What it may do without being asked, as one of `humanize.agents.PERMISSIONS`,
        or "" for the one an agent nobody has been asked about runs at.
      provider: The account its turns run as, by the name a provider of its CLI was made
        under, or "" to run as this machine is already signed in.
    """

    spec: str
    anchor: str = ""
    skills: tuple[str, ...] | None = None
    permission: str = ""
    provider: str = ""


class Whose(NamedTuple):
    """Which coding agent takes one agent's turns, and the account they run as.

    The two halves of the first step, and one answer rather than two because the second is
    only answerable once the first has been: an account is one backend's, so the accounts
    offered are the CLI's own.

    Attributes:
      cli: The backend, by the name humanize drives it under.
      provider: The account, by the name a provider of that CLI was made under, or "" to run
        as this machine is already signed in.
    """

    cli: str
    provider: str = ""


def called(places: tuple[Place, ...], at: int) -> str:
    """What to call the agent being configured, which every step of configuring it says.

    In one place because it is said in three, and an agent that read as two different things
    between one step and the next would be two.

    Args:
      places: One place per agent the flow drives, in the order it takes them.
      at: Which of them is being asked about, counting from zero.

    Returns:
      The name the flow calls it, or where it comes among them for a flow that named none.
    """
    return places[at].name or f"agent {at + 1} of {len(places)}"


def pointed(place: Place) -> bool:
    """Whether where one agent works is a question anybody is asked about it.

    Only for a place the flow declared `Remote`: a flow that says so is a flow that expects
    to be told where that agent works, and one that says nothing has said its agent works
    here. A container the flow named is not asked about either -- the flow settled it, and
    nobody else has any say in it.

    Args:
      place: What the flow declared.

    Returns:
      True if there is a machine to be chosen for it, which is a step of its own.
    """
    from humanize.agents import Remote

    return place.where is Remote or isinstance(place.where, Remote)


def _settled(place: Place) -> str:
    """The container a flow put one of its agents in, where it named one.

    Args:
      place: What the flow declared.

    Returns:
      The image, or "" for an agent that works here and one that is asked where it works --
      neither of which is something the flow settled.
    """
    from humanize.agents import Isolated

    return place.where.image if isinstance(place.where, Isolated) else ""


#: What Claude Code rules the top of a sheet with, and how far in everything under it sits.
_RULE = "▔"
_INDENT = "   "

#: The dot Claude Code separates the parts of a line with.
_DOT = " · "

#: The marker against the choice under the cursor, and against the one already in force.
_HERE = "❯"
_INFORCE = "✔"

#: The switch in front of a row that is turned on and off rather than picked: a box with a
#: tick in it, and the same box empty. Which of the two it is is the whole of what such a row
#: says about itself, so it is drawn as the thing everything else in a terminal draws it as.
_TICKED = "[✔]"
_EMPTY = "[ ]"

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
                # Only where there is one: an agent nobody has narrowed says nothing here,
                # which is what every agent a flow has ever driven would have said. The
                # account it runs as reads the same way -- one that says nothing is the one
                # this machine is signed in as.
                one.permission,
                one.provider,
            )
            if part
        )
        for at, one in enumerate(runs)
    ]


_SHEET = """
Anchors, Backends, Configures, Flows, Models, Providers, RunsAs, Signing, Skills, Status, Ways {
    align: center middle; background: $background; }
#sheet { width: 100%; height: auto; padding: 0; }
#rule { height: 1; color: $primary; }
#asked { padding: 0 0 0 3; text-style: bold; color: $primary; }
#about { padding: 0 3 1 3; color: $text-muted; width: 1fr; }
/* The tabs, for the one sheet that has any. A sheet with none says nothing here, and a
   label with nothing in it is a row nobody paid for. */
#tabs { padding: 0 0 1 3; }
OptionList { border: none; background: $background; max-height: 14; scrollbar-size: 0 0;
             padding: 0; }
/* The marker says where the cursor is, so the row is not filled as well. */
#choices > .option-list--option-highlighted {
    background: $background; color: $foreground; text-style: none; }
/* As wide as the sheet, so that the settings adjusted under the models wrap onto a second
   row rather than running off the side of a narrow terminal: a key nobody can see is a key
   nobody has. */
#tuning { padding: 1 0 1 3; width: 1fr; }
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
        """The rule, the question, the tabs, what there is to choose, what is tuned, the keys.

        Every sheet is made of the same parts whether or not it uses them. The tabs are the
        one part that is taken away again where a sheet has none -- see :meth:`tabbed` -- so
        that a sheet which is one list is drawn as one list and nothing moved down a row.
        """
        with Vertical(id="sheet"):
            yield Label(id="rule")
            yield Label(id="asked")
            yield Label(id="about")
            yield Label(id="tabs")
            yield OptionList(id="choices")
            yield Label(id="tuning")
            yield Label(id="keys")

    def on_mount(self) -> None:
        """Rules the top of the sheet across, and asks."""
        self.query_one("#rule", Label).update(_RULE * self.size.width)
        # Nothing until a sheet says otherwise, and gone rather than blank: a label with
        # nothing in it still takes the row it is padded to, and a sheet that has no tabs
        # must be drawn exactly as it was before there were any.
        self.tabbed("")
        self._ask()

    def tabbed(self, said: str) -> None:
        """Puts a row of tabs above the choices, or takes the row back where there are none.

        Args:
          said: The tabs, as markup, or "" for a sheet that is one list.
        """
        showing = self.query_one("#tabs", Label)
        showing.display = bool(said)
        showing.update(said)

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
        self,
        at: int,
        label: str,
        about: str,
        *,
        here: bool,
        inforce: bool,
        box: str = "",
    ) -> str:
        """One numbered choice, laid out as Claude Code lays one out.

        Args:
          at: Which one it is, counting from zero.
          label: What it is called.
          about: The line about it, which is said quietly.
          here: Whether the cursor is on it.
          inforce: Whether it is the one already in force.
          box: The switch in front of the name, for a list whose rows are switched on and off
            rather than picked between, or "" for a list that is picked from.

        Returns:
          The row, as markup.
        """
        mark = f"{_INDENT}[$primary]{_HERE}[/] " if here else f"{_INDENT}  "
        # Right-aligned, so that the tenth row starts where the ninth does.
        number = f"{at + 1:>{self._counting}}."
        # In `$success` either way: an empty box has no ink in it to colour.
        switch = f"[$success]{escape(box)}[/] " if box else ""
        named = escape(label) + (f" [$success]{_INFORCE}[/]" if inforce else "")
        # Padded on what is shown rather than on what is written: markup is not columns.
        pad = " " * max(
            1,
            _LABEL - len(label) - (2 if inforce else 0) - (len(box) + 1 if box else 0),
        )
        return (
            f"{mark}[$text-muted]{number}[/] {switch}{named}{pad}"
            f"[$text-muted]{escape(about)}[/]"
        )

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


class Models(Sheet[Runs]):
    """Which model one agent runs and how hard it thinks, which is the second of its steps.

    Which CLI it is was settled the step before, because an account belongs to a backend and
    could not be asked about until it was, so this is that CLI's models and nothing else: a
    row is the model, and picking one picks the pair -- a model belongs to the CLI that runs
    it -- with the CLI named above them as a heading, there being nowhere left to switch to.

    The effort is the line with the arrows on it, exactly as Claude Code's is, and on it the
    three that really are side questions about the same agent: how wide the turn runs, what
    it may do without being asked, and which of its CLI's skills it is loaded with. What a
    step of its own answered is read there rather than adjusted.
    """

    BINDINGS: ClassVar = [
        ("escape", "back", "back"),
        ("left", "easier", "less effort"),
        ("right", "harder", "more effort"),
        # Not an arrow, because swarm mode is not a step along the efforts: it is a second
        # thing to say about a turn -- how wide it runs, rather than how hard -- and a turn
        # that is both is written down as both. A chord, because the letters are searching.
        Binding("ctrl+w", "swarm", "swarm mode", priority=True),
        # Nor is what the agent may do while it works: it is one of four words rather than a
        # step along the efforts, so it is stepped through by a chord of its own. Adjusted
        # here rather than chosen from a sheet, because four words fit on the line the effort
        # is on and a list of four is a list nobody would want to walk to.
        Binding("ctrl+p", "permit", "permission", priority=True),
        # And what it is loaded with is a third, for the same reason and in the same way: a
        # side question about this agent, which opens a sheet of its own and comes back here.
        Binding("ctrl+s", "skills", "skills", priority=True),
    ]

    def __init__(
        self,
        flow: str,
        named: str,
        whose: Whose,
        models: tuple[Model, ...],
        place: Place,
        now: Runs | None = None,
    ) -> None:
        """Initializes the choosing.

        Args:
          flow: The flow whose agent this is.
          named: What the flow calls it, which every step of configuring it says.
          whose: The CLI that takes its turns and the account they run as, as the step before
            answered.
          models: What that CLI says it runs.
          place: What the flow declared about this one, which is where a container it settled
            is read from.
          now: What this step answered last time it was walked through, or None for one being
            asked for the first time. Esc is the step before, and a step before that had
            forgotten itself would be a different question.
        """
        super().__init__()
        self._flow = flow
        self._named = named
        self._whose = whose
        self._models = models
        self._place = place
        self._now = now
        self._effort = 0
        #: Whether the turn runs as a fleet rather than as one agent, for a model that takes
        #: it. Held here rather than among the efforts, and asked of each agent afresh.
        self._swarm = False
        #: What it may do without being asked, counting the rungs: the loosest until it is
        #: said otherwise, which is what an agent nobody has been asked about has always run
        #: at.
        self._permission = len(PERMISSIONS) - 1
        #: Which of the CLI's skills this one is to have, or None for one that has not been
        #: asked -- which is the CLI as it comes, and so every skill it finds.
        self._skills: tuple[str, ...] | None = None
        #: Which row the cursor lands on when the list first goes up, which is the model this
        #: step was answered with before, if it was.
        self._start = 0
        #: The models the letters typed so far have left, which is what the cursor is walking.
        self._shown: list[Model] = []

    def _ask(self) -> None:
        """Asks what this one runs, from the models down."""
        self.query_one("#asked", Label).update(f"Select what {self._named} runs")
        self.query_one("#about", Label).update(
            f"Which model of {self._whose.cli} takes this one's turns in {self._flow}, and "
            "how hard it thinks. Two agents at one model are still two agents."
        )
        self._read_back()
        self._fill()
        self.query_one("#choices", OptionList).focus()

    def _read_back(self) -> None:
        """Puts the sheet back where a walk that stepped on from here left it.

        Read off what this step answered with rather than kept beside it: that answer is the
        whole of what was said, and a second copy of it would be a second thing to keep true.
        """
        if self._now is None:
            return
        cli, _, rest = self._now.spec.partition("/")
        if cli != self._whose.cli:
            # Answered about another backend, the step before having been walked back into
            # and turned to a different tab: its models, its efforts and its skills are its
            # own, and none of them means anything here.
            return
        name, _, effort = rest.rpartition(":")
        # `swarm` in front of the effort is how a fleet is written down, so it comes off
        # again before the effort is looked for among the ones the model takes.
        self._swarm = effort.startswith(SWARM)
        wanted = effort.removeprefix(SWARM)
        self._start = next(
            (at for at, one in enumerate(self._models) if one.name == name), 0
        )
        efforts = self._models[self._start].efforts if self._models else ()
        self._effort = efforts.index(wanted) if wanted in efforts else 0
        self._skills = self._now.skills
        # Only a rung that was written down: the loosest is written as nothing at all, which
        # is what an agent nobody was asked about runs at anyway.
        if self._now.permission in PERMISSIONS:
            self._permission = PERMISSIONS.index(self._now.permission)

    def _fill(self) -> None:
        """Puts the CLI's models up, and under them everything else this agent is."""
        listing = self.query_one("#choices", OptionList)
        backend = self._whose.cli
        self._shown = [
            model for model in self._models if self.fits(model.name, backend)
        ]
        self._counting = len(str(len(self._shown)))
        # Where the cursor is, or where it is to land the first time the list goes up: `or 0`
        # would send it back there every time it was walked onto the first row.
        here = listing.highlighted if listing.highlighted is not None else self._start
        at = min(here, max(len(self._shown) - 1, 0))
        listing.set_options(
            Option(
                self._row(seen, model.name, backend, here=seen == at, inforce=False),
                id=f"{backend}/{model.name}",
            )
            for seen, model in enumerate(self._shown)
        )
        listing.highlighted = at if self._shown else None
        self._drawn = at
        # The CLI these are the models of, as a heading rather than a row of tabs: it was
        # chosen a step ago, so there is nowhere to switch to and nothing says there is.
        self.tabbed(f"[b $primary]{escape(backend)}[/]" if backend else "")
        self.query_one("#tuning", Label).update(self._tuned())
        self.query_one("#keys", Label).update(
            f"Type to search · Enter to choose · Esc to go back{self.searching()}"
        )

    def _tuned(self) -> str:
        """The line under the models: the effort, and the side questions about this agent.

        What is adjusted here carries the key that adjusts it. Where this one works is read
        rather than adjusted where the flow settled it, and says so by carrying no key at all;
        the account it runs as is not here at all, being the step before this one.

        Returns:
          The line, as markup, or "" where the letters typed have left no model to say it of.
        """
        efforts = self._efforts()
        self._effort = min(self._effort, len(efforts) - 1) if efforts else 0
        if not efforts:
            return ""
        said = (
            f"[$secondary]◉[/] {efforts[self._effort]} effort  "
            f"[$text-muted]←/→ to adjust[/]"
        )
        if self._swarms():
            on = "on" if self._swarm else "off"
            said += (
                f"{_DOT}[$secondary]◉[/] swarm mode {on}  "
                f"[$text-muted]ctrl+w to toggle[/]"
            )
        having = self._skills
        said += (
            f"{_DOT}[$secondary]◉[/] "
            f"{'every skill' if having is None else f'{len(having)} skills'}  "
            f"[$text-muted]ctrl+s to choose[/]"
        )
        said += (
            f"{_DOT}[$secondary]◉[/] {PERMISSIONS[self._permission]}  "
            f"[$text-muted]ctrl+p to change[/]"
        )
        # The account is not read back here: it was the step before this one, it is on the
        # line above the prompt once the walk is over, and a setting shown where it cannot be
        # changed is a setting somebody tries to change.
        if where := self._where():
            said += f"{_DOT}[$secondary]◉[/] {where}"
        return said

    def _where(self) -> str:
        """Where this one works, where that is settled rather than still to be asked.

        Returns:
          The container the flow named, or the machine a walk that has been past the step
          after this was pointed at, and "" for one that works here -- which is what an agent
          nobody has said anything about has always done, and is nothing new to say.
        """
        if image := _settled(self._place):
            return f"in a container of {escape(image)}"
        anchor = self._now.anchor if self._now is not None else ""
        return f"on {escape(anchor)}" if anchor else ""

    @work
    async def action_skills(self) -> None:
        """Asks which of its CLI's skills this agent is to be without, and comes back here.

        A walk out without answering leaves this one loaded as it was: what the agent runs is
        the question this step asks, and declining to answer a side question is not declining
        that.
        """
        backend = self._whose.cli
        if not backend:
            return
        showing = cast(
            "App[None]",
            self.app,  # pyright: ignore[reportUnknownMemberType]
        )
        chosen = await showing.push_screen_wait(Skills(backend, self._skills))
        if chosen is not None:
            self._skills = chosen
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
        return self._shown[min(listing.highlighted or 0, len(self._shown) - 1)]

    def action_swarm(self) -> None:
        """Turns swarm mode on or off, for a model that has one to turn on."""
        if self._swarms():
            self._swarm = not self._swarm
            self._fill()

    def action_permit(self) -> None:
        """Steps to the next rung of what this agent may do without being asked.

        Round rather than along: the rungs are four and the way back to the one before is the
        way on past the last, which is one key rather than two.
        """
        self._permission = (self._permission + 1) % len(PERMISSIONS)
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
        """Answers with this agent, less where it works, which is the step after.

        Args:
          event: What was chosen.
        """
        # `swarm` in front of the effort is how Kimi is asked for a fleet: one turn at one
        # effort, run wide. A model that does not take it is chosen at the effort alone.
        wide = SWARM if self._swarm and self._swarms() else ""
        self.dismiss(
            Runs(
                spec=f"{event.option.id}:{wide}{self._efforts()[self._effort]}",
                # Whatever the step after this settled last time round, so that walking back
                # into this one and on again is the walk it was rather than a way of losing
                # the machine. A place nobody may point anywhere never has one.
                anchor=self._now.anchor if self._now is not None else "",
                # Nothing said at all is the CLI as it comes, which is None rather than a
                # list of every skill it happens to have installed today.
                skills=self._skills,
                # Only where it is a narrowing: the loosest rung is what an agent nobody has
                # been asked about runs at, and saying so is saying nothing.
                permission=(
                    PERMISSIONS[self._permission]
                    if self._permission < len(PERMISSIONS) - 1
                    else ""
                ),
                provider=self._whose.provider,
            )
        )


class Skills(Sheet[tuple[str, ...]]):
    """Which of a CLI's skills one agent is loaded with, switched on and off one at a time.

    A side question about the agent, like what it may do without being asked: what it runs is
    the step this hangs off, and what it is loaded with is another. Found the way the CLI
    itself finds them --
    the skills you have installed and the ones this project keeps -- so the list is the list
    the agent would have had, and what is left marked is what it will have.

    Every skill starts on, which is how a CLI comes: a sheet that had to be walked through
    before an agent could have any of them would be a setting nobody asked for. What it
    answers with is the ones it is to have, since that is what an agent is then loaded with
    -- a skill installed afterwards is not one anybody chose for this agent.
    """

    BINDINGS: ClassVar = [
        ("escape", "back", "back"),
        # Space is what a checklist is switched with, so it is what this one is switched
        # with. Priority, or it would go into the search like any other character -- which
        # costs nothing here, a skill being named after the directory it is in and so never
        # having a space in its name.
        Binding("space", "switch", "switch this one", priority=True),
        # Enter is the whole sheet rather than the row under the cursor, as it is where a
        # sheet is adjusted rather than picked from: the rows are switched where they stand.
        Binding("enter", "done", "done", priority=True),
    ]

    def __init__(self, backend: str, having: tuple[str, ...] | None) -> None:
        """Initializes the switching.

        Args:
          backend: The CLI whose skills these are.
          having: The ones this agent has already, or None for one that has never been asked
            -- which is the CLI as it comes, and so all of them.
        """
        super().__init__()
        self._backend = backend
        self._having = having
        self._found: list[Skill] | None = None
        #: The ones marked now, which start as the ones it has. Read once the list is in
        #: hand, since "all of them" is only a list of names after the looking.
        self._on: set[str] | None = None

    def _ask(self) -> None:
        """Says whose skills these are, and what switching one off does."""
        self.query_one("#asked", Label).update(f"Select what {self._backend} loads")
        self.query_one("#about", Label).update(
            "The skills this one agent is to have. They are found where the CLI itself "
            "looks -- yours, and this project's -- and every one of them starts on. Another "
            "agent of the same flow may be loaded with a different set."
        )
        self._fill()
        self.query_one("#choices", OptionList).focus()

    def _skills(self) -> list[Skill]:
        """The skills there are to choose between, read once: this is redrawn per keystroke."""
        if self._found is None:
            self._found = skills(self._backend)
            self._counting = len(str(len(self._found)))
            self._on = (
                {one.name for one in self._found}
                if self._having is None
                else {one.name for one in self._found if one.name in self._having}
            )
        return self._found

    def _fill(self) -> None:
        """Puts the skills up, with a mark against the ones this agent will have."""
        listing = self.query_one("#choices", OptionList)
        shown = [
            skill
            for skill in self._skills()
            if self.fits(skill.name, skill.about, skill.whose)
        ]
        on = self._on or set()
        at = min(listing.highlighted or 0, max(len(shown) - 1, 0))
        listing.set_options(
            Option(
                self._row(
                    seen,
                    skill.name,
                    f"{skill.about}  ({skill.whose})" if skill.about else skill.whose,
                    here=seen == at,
                    inforce=False,
                    box=_TICKED if skill.name in on else _EMPTY,
                ),
                id=skill.name,
            )
            for seen, skill in enumerate(shown)
        )
        listing.highlighted = at if shown else None
        self._drawn = at
        self.query_one("#tuning", Label).update(
            "" if self._skills() else f"[$text-muted]{self._nothing()}[/]"
        )
        self.query_one("#keys", Label).update(
            "Type to search · Space to switch on and off · Enter to accept · Esc to go back"
            f"{self.searching()}"
        )

    def _nothing(self) -> str:
        """Why there is nothing to choose between, which is not always the same reason.

        Returns:
          That a CLI which keeps skills has none installed here, or that one which offers no
          way of being told which to load cannot be told -- a sheet that said the second was
          the first would be blaming the machine for what the backend cannot do.
        """
        profile = named(self._backend)
        if profile is None or not (profile.skills or profile.shared or profile.works):
            return f"{escape(self._backend)} cannot be told which skills to load"
        return f"{escape(self._backend)} has no skills installed here"

    @property
    def _under(self) -> str:
        """The skill the cursor is on, or "" where the letters typed have left none."""
        listing = self.query_one("#choices", OptionList)
        at = listing.highlighted
        if at is None or not 0 <= at < listing.option_count:
            return ""
        return str(listing.get_option_at_index(at).id or "")

    def action_switch(self) -> None:
        """Switches the skill under the cursor on, or off again."""
        if not (named := self._under) or self._on is None:
            return
        if named in self._on:
            self._on.discard(named)
        else:
            self._on.add(named)
        self._fill()

    def action_done(self) -> None:
        """Answers with the skills this agent is to have, in the order they are listed."""
        on = self._on or set()
        self.dismiss(tuple(skill.name for skill in self._skills() if skill.name in on))


class Anchors(Sheet[str]):
    """Where one agent's turns land: this machine, or one an anchor reaches.

    The last of the three steps one agent is configured in, and only for a place the flow
    declared `Remote`: a flow that says so is one that expects to be told where that agent
    works, and one that said nothing has said its agent works here. Which is why this is a
    step rather than a chord -- a flow that declares one and buries it in a key is a flow
    whose question only somebody who already knew about it would answer.

    The agent itself runs here whatever is chosen -- its credentials, its state directory and
    its link to its model provider stay put. What moves is the project it reads and the
    commands it runs, which is why this is a question about the agent rather than about the
    flow: two agents of one flow may work on two machines.

    Listed rather than typed where the machine is one this one can see -- a container that is
    running, a host with an entry in the ssh config -- and typed where it is not: a target is
    a string, and the row for what has been typed appears as soon as it reads as one.
    """

    def __init__(self, named: str, current: str = "") -> None:
        """Initializes the moving.

        Args:
          named: What the flow calls the agent this is about, which every step of configuring
            it says.
          current: The target this agent is on now, or "" for this machine.
        """
        super().__init__()
        self._named = named
        self._current = current
        self._found: list[tuple[str, str]] | None = None

    def _ask(self) -> None:
        """Lists the machines there are to work on, and says what choosing one does."""
        self.query_one("#asked", Label).update(f"Select where {self._named} works")
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
            f"Type a target · Enter to choose · Esc to go back{self.searching()}"
        )

    @on(OptionList.OptionSelected)
    def _took(self, event: OptionList.OptionSelected) -> None:
        """Answers with the target that was picked.

        Args:
          event: What was chosen.
        """
        self.dismiss(str(event.option.id).removeprefix("="))


#: How wide the column of setting names is, and the column of their values, so that a sheet
#: of settings reads down three columns: what it is called, what it is, and what it is for.
#: Wide enough for the longest name any flow here has, since a column that a name overruns
#: is one the three of them stop lining up in.
_SETTING = 34
_VALUE = 13

#: What a switch reads as. Both are words pydantic takes back as a boolean, so what is shown
#: is also what is validated -- there is no second spelling of `on` for this to get wrong.
_ON = "on"
_OFF = "off"


def _shown(value: object) -> str:
    """One setting's value, as a line about it says it.

    Args:
      value: What it is set to.

    Returns:
      A switch as `on` or `off`, anything else as it is written, and something unset as the
      empty string rather than as `None` -- a setting nobody has given a value is blank.
    """
    if isinstance(value, bool):
        return _ON if value else _OFF
    return "" if value is None else str(value)


def _grouped(field: FieldInfo) -> str:
    """Which part of the sheet a setting belongs under, if the flow said.

    A flow groups its settings by writing `json_schema_extra={"section": "..."}` where it
    declares them: twenty settings in one list is a list nobody reads, and the flow is the
    only thing that knows which of them belong together.

    Args:
      field: The field, as the model declared it.

    Returns:
      The heading to draw above it, or "" for a flow that grouped nothing.
    """
    extra = field.json_schema_extra
    if not isinstance(extra, dict):
        return ""
    said = cast("dict[str, Any]", extra).get("section")
    return str(said) if said else ""


def setting(config: BaseModel | None) -> list[str]:
    """What a flow was set up with, one line per setting that is not at its default.

    Read in two places -- `/status` and the box a run opens with -- and only the settings
    that were changed: a flow with forty of them says nothing by listing the thirty-nine
    nobody touched, and the one that was touched is the thing worth reading.

    Args:
      config: What the flow was set up with, or None for a flow that takes no setting up or
        was left as it comes.

    Returns:
      One `name value` apiece, in the order the model declares them, and nothing at all for
      a flow left entirely at its defaults.
    """
    if config is None:
        return []
    return [
        f"{name:<{_SETTING}}{_shown(getattr(config, name))}"
        for name, field in type(config).model_fields.items()
        if getattr(config, name) != field.get_default(call_default_factory=True)
    ]


class Configures(Sheet["BaseModel"]):
    """How the flow is set up, asked once between choosing it and choosing its agents.

    A flow says what it can be set up with by declaring a model, and this is that model with
    a cursor on it: one row per field, the name, what it is set to, and the line the field
    was declared with. Nothing here knows what any of the settings mean -- the types say how
    a value is moved, and the model itself says which combinations it will not take, so a
    flow that refuses `gen_idea` without `gen_plan` refuses it here rather than an hour in.

    Every value is held as it is typed and handed to the model to read back, so a field is
    only ever wrong in one place: pydantic coerces `on`, `42` and `discussion` into the bool,
    the int and the literal the flow declared, and says what is wrong with anything else.
    """

    BINDINGS: ClassVar = [
        ("escape", "back", "back"),
        ("left", "prev", "previous value"),
        ("right", "next", "next value"),
        # Enter is the whole sheet rather than the row under the cursor: a setting is
        # adjusted where it stands, so there is nothing here to pick. Priority, or the
        # list under the cursor would take it as choosing a row.
        Binding("enter", "done", "done", priority=True),
    ]

    def __init__(
        self, flow: str, model: type[BaseModel], now: BaseModel | None
    ) -> None:
        """Initializes the setting up.

        Args:
          flow: The flow these settings are for.
          model: What it says it can be set up with.
          now: How it is set up already, or None to start from the model's own defaults.
        """
        super().__init__()
        self._flow = flow
        self._model = model
        self._fields = list(model.model_fields.items())
        self._counting = len(str(len(self._fields)))
        #: Every value as text, which is what is shown and what is read back: one spelling
        #: of a setting, so that what is on screen is what the model is given.
        self._typed_in: dict[str, str] = {
            name: _shown(
                getattr(now, name)
                if now is not None
                else field.get_default(call_default_factory=True)
            )
            for name, field in self._fields
        }
        #: What the model said was wrong with them, if it has been asked yet.
        self._wrong = ""
        #: Which setting the cursor was last on, counting settings rather than rows: the
        #: headings between them are rows nothing can land on, so a row number is not one.
        self._was = 0

    def _ask(self) -> None:
        """Says what is being set up, and what the keys do while it is."""
        self.query_one("#asked", Label).update(f"Set up {self._flow}")
        self.query_one("#about", Label).update(
            "How this flow runs, which it says for itself. Left and right move a setting "
            "along, typing writes one, and enter takes the lot. What is refused here is "
            "refused by the flow rather than by this list."
        )
        self._fill()
        self.query_one("#choices", OptionList).focus()

    def _fill(self) -> None:
        """Puts the settings up, grouped, with the marker beside the one under the cursor."""
        listing = self.query_one("#choices", OptionList)
        at = self._at(listing.highlighted)
        rows: list[Option] = []
        group = ""
        for seen, (name, field) in enumerate(self._fields):
            under = _grouped(field)
            if under != group:
                group = under
                # A heading, and a blank line above it once there is something above it. It
                # cannot be landed on, so the arrows walk the settings and step over these.
                # A flow that grouped nothing gets neither, and reads as one list.
                if group:
                    if rows:
                        rows.append(Option("", disabled=True))
                    rows.append(
                        Option(f"{_INDENT}[$primary]{escape(group)}[/]", disabled=True)
                    )
            rows.append(Option(self._line(seen, name, here=seen == at), id=name))
        listing.set_options(rows)
        listing.highlighted = self._row_of(at) if self._fields else None
        self._drawn = listing.highlighted
        self.query_one("#tuning", Label).update(
            f"[$error]{escape(self._wrong)}[/]" if self._wrong else ""
        )
        # What the keys do on the setting under the cursor, and not what they do elsewhere:
        # typing at a switch does nothing, and offering it is worse than not saying so.
        written = bool(self._fields) and not self._steps(self._fields[at][0])
        self.query_one("#keys", Label).update(
            "Type to set · Backspace to rub out · Enter to accept · Esc to go back"
            if written
            else "←/→ to change · Enter to accept · Esc to go back"
        )

    def _row_of(self, at: int) -> int:
        """Which row of the list one setting is on, once the headings are counted.

        Args:
          at: Which setting it is, counting from zero.

        Returns:
          The row.
        """
        rows = 0
        group = ""
        for seen, (_, field) in enumerate(self._fields):
            under = _grouped(field)
            if under != group:
                group = under
                if group:
                    rows += 2 if rows else 1
            if seen == at:
                return rows
            rows += 1
        return rows

    def _at(self, row: int | None) -> int:
        """Which setting a row of the list is, which is what the cursor is really on.

        Args:
          row: Where the cursor is, or None for a list nothing is highlighted in.

        Returns:
          The setting, counting from zero, and the nearest one where the cursor is on a
          heading -- which is where it lands when the list is first put up.
        """
        listing = self.query_one("#choices", OptionList)
        if row is not None and 0 <= row < listing.option_count:
            named = listing.get_option_at_index(row).id
            if named is not None:
                return next(
                    (
                        seen
                        for seen, (one, _) in enumerate(self._fields)
                        if one == named
                    ),
                    0,
                )
        return self._was

    def _line(self, at: int, name: str, *, here: bool) -> str:
        """One setting: what it is called, what it is set to, and what it is for.

        A setting that is written carries a caret under the cursor, where the next letter
        would land. Without it a blank one reads as a setting nothing can be typed into --
        which is the one thing about this list that has to be visible, since a switch and a
        word look the same until you try to type at one.

        Args:
          at: Which one it is, counting from zero.
          name: The field.
          here: Whether the cursor is on it.

        Returns:
          The row, as markup.
        """
        mark = f"{_INDENT}[$primary]{_HERE}[/] " if here else f"{_INDENT}  "
        number = f"{at + 1:>{self._counting}}."
        value = self._typed_in[name]
        about = dict(self._fields)[name].description or ""
        # A block where the next letter goes, drawn by reversing what is already there --
        # the one thing a list in the terminal's own colours can show without naming one.
        caret = "[reverse] [/reverse]" if here and not self._steps(name) else ""
        # Padded on what is shown rather than on what is written: markup is not columns,
        # and the caret is one of them.
        named = escape(name) + " " * max(1, _SETTING - len(name))
        room = _VALUE - len(value) - (1 if caret else 0)
        return (
            f"{mark}[$text-muted]{number}[/] {named}"
            f"[$secondary]{escape(value)}[/]{caret}{' ' * max(1, room)}"
            f"[$text-muted]{escape(about)}[/]"
        )

    @property
    def _under(self) -> str:
        """The setting the cursor is on, or "" for a model that declares none."""
        if not self._fields:
            return ""
        listing = self.query_one("#choices", OptionList)
        self._was = self._at(listing.highlighted)
        return self._fields[self._was][0]

    def _steps(self, name: str) -> tuple[str, ...]:
        """What a setting steps through, where it is one of a fixed few.

        Args:
          name: The field.

        Returns:
          Every value it takes, in the order the flow wrote them -- the two words of a
          switch, or the words of a literal -- and nothing at all for one that is written
          rather than stepped.
        """
        kind = dict(self._fields)[name].annotation
        # `Literal["a", "b"] | None` and `Literal["a", "b"]` are the same few words to step
        # through, so the union is unwrapped before the literal is read off it.
        for said in (kind, *get_args(kind)):
            if get_origin(said) is Literal:
                return tuple(str(one) for one in get_args(said))
        if kind is bool:
            return (_OFF, _ON)
        return ()

    def _move(self, by: int) -> None:
        """Moves the setting under the cursor along, however that setting moves.

        Args:
          by: One step forward or back.
        """
        name = self._under
        if not name:
            return
        if steps := self._steps(name):
            at = (
                steps.index(self._typed_in[name])
                if self._typed_in[name] in steps
                else 0
            )
            self._typed_in[name] = steps[(at + by) % len(steps)]
        elif dict(self._fields)[name].annotation in (int, float):
            try:
                now = float(self._typed_in[name] or 0)
            except ValueError:
                now = 0
            moved = now + by
            self._typed_in[name] = str(
                int(moved) if dict(self._fields)[name].annotation is int else moved
            )
        else:
            return  # a setting that is written is not one an arrow has a step for
        self._wrong = ""
        self._fill()

    def action_next(self) -> None:
        """Moves the setting under the cursor one value on."""
        self._move(1)

    def action_prev(self) -> None:
        """Moves the setting under the cursor one value back."""
        self._move(-1)

    def action_back(self) -> None:
        """Leaves without setting anything, which leaves the flow as it was."""
        self.dismiss(None)

    def action_done(self) -> None:
        """Reads every setting back into the model, and answers with it if it takes them.

        What the model refuses is shown where it was typed rather than raised at the flow:
        a combination the flow will not run is a combination to correct before it starts,
        and this is the moment it is being said.
        """
        from pydantic import ValidationError

        try:
            self.dismiss(self._model.model_validate(self._typed_in))
        except ValidationError as refused:
            first = refused.errors()[0]
            where = ".".join(str(part) for part in first.get("loc") or ())
            self._wrong = f"{where}: {first['msg']}" if where else str(first["msg"])
            self._fill()

    def on_key(self, event: events.Key) -> None:
        """Takes a letter as writing the setting under the cursor.

        There is nothing to search here -- every setting is on screen at once -- so the keys
        that narrow a list elsewhere are the ones that write a value.

        Args:
          event: The key.
        """
        name = self._under
        if not name or self._steps(name):
            return  # a switch and a literal are stepped rather than written
        if event.key == "backspace":
            self._typed_in[name] = self._typed_in[name][:-1]
        elif event.is_printable and event.character:
            self._typed_in[name] += event.character
        else:
            return
        event.prevent_default()
        event.stop()
        self._wrong = ""
        self._fill()


class Picks(Sheet[str]):
    """A question that is only a list of named things, answered by picking one of them.

    Two of the sheets here are that and nothing else -- which CLI a new account is for, and
    how to sign into it -- and two lists drawn two ways would read as two different kinds of
    question. So the drawing is here, and each of them says only what it asks and what there
    is to choose between.
    """

    #: The question at the top of the sheet, and the line under it saying what choosing one
    #: does. Every sheet of this shape says both for itself.
    asked = ""
    about = ""

    #: What this sheet's own keys do, said on the keys line before the ones every sheet has.
    #: Empty for a sheet that only picks, which is most of them.
    keys = ""

    def __init__(self, current: str = "") -> None:
        """Initializes the choosing.

        Args:
          current: What is in force already, which is the row the tick goes against.
        """
        super().__init__()
        self._current = current
        self._rows: list[tuple[str, str, str]] | None = None

    def rows(self) -> list[tuple[str, str, str]]:
        """What there is to choose between, which each sheet says for itself.

        Returns:
          One `(what picking it answers with, what it is called, the line about it)` apiece,
          in the order to show them.
        """
        raise NotImplementedError

    def nothing(self) -> str:
        """What to say under the list where the list alone does not say it.

        Returns:
          The line, already escaped, or "" for a list that speaks for itself.
        """
        return ""

    def _ask(self) -> None:
        """Says what is being chosen, and puts the choices up."""
        self.query_one("#asked", Label).update(self.asked)
        self.query_one("#about", Label).update(self.about)
        self._fill()
        self.query_one("#choices", OptionList).focus()

    def _fill(self) -> None:
        """Puts the rows up, with the marker beside the one the cursor is on."""
        listing = self.query_one("#choices", OptionList)
        if self._rows is None:
            # Once: looking means reading a directory, and this is redrawn per keystroke.
            self._rows = self.rows()
        shown = [row for row in self._rows if self.fits(row[1], row[2])]
        self._counting = len(str(len(shown)))
        at = min(listing.highlighted or 0, max(len(shown) - 1, 0))
        listing.set_options(
            Option(
                self._row(
                    seen, label, about, here=seen == at, inforce=answer == self._current
                ),
                # Every row answers with a string and "" is one of the answers, which an id
                # of its own keeps tellable from a row that was never chosen.
                id=f"={answer}",
            )
            for seen, (answer, label, about) in enumerate(shown)
        )
        listing.highlighted = at if shown else None
        self._drawn = at
        said = self.nothing()
        self.query_one("#tuning", Label).update(
            f"[$text-muted]{said}[/]" if said else ""
        )
        self.query_one("#keys", Label).update(
            f"{self.keys}Type to search · Enter to choose · Esc to cancel{self.searching()}"
        )

    @on(OptionList.OptionSelected)
    def _took(self, event: OptionList.OptionSelected) -> None:
        """Answers with what was picked.

        Args:
          event: What was chosen.
        """
        self.dismiss(str(event.option.id).removeprefix("="))


def _sets(provider: Provider) -> str:
    """What one account says about itself on a row: the way it was made by, and what it sets.

    Args:
      provider: The account.

    Returns:
      The line, with the variables named and never a value in it -- this is drawn where
      somebody can read it, and a key on a screen is a key in a photograph.
    """
    variables = ", ".join(sorted(provider.env))
    return f"{provider.way}{_DOT}{variables}" if variables else provider.way


class RunsAs(Sheet[Whose]):
    """Which coding agent takes one agent's turns, and the account they run as: its first step.

    Two halves of one question, in this order because an account belongs to a backend: what
    signs in to Claude Code is not what signs in to codex, so the accounts under each tab are
    that backend's own. The CLIs are a tab apiece and only the ones installed here, less any
    the flow ruled out by asking that place for a moment they do not run -- a CLI that would
    make the flow refuse to start is not one to offer for it.

    The account is a step rather than a chord because it decides which credentials the turns
    run under, which is not a side question about anything: two agents of one CLI may be two
    accounts -- one on a subscription and one on somebody's gateway, each refreshing its own
    token -- and that is the whole of what a provider is for.
    """

    BINDINGS: ClassVar = [
        ("escape", "back", "back"),
        # The tabs, on the arrows the list is not using: up and down are the accounts under
        # the tab, so left and right are the tabs themselves. Priority, or the list under the
        # cursor would take them as moving between rows it has none of.
        Binding("left", "prev_cli", "previous CLI", priority=True),
        Binding("right", "next_cli", "next CLI", priority=True),
        # Making one is asked for here rather than somewhere else: this is the moment somebody
        # finds out they have no account for this CLI, or that the one they want is not among
        # these, and sending them out of the question to answer it would lose the question.
        Binding("ctrl+n", "new", "new", priority=True),
    ]

    def __init__(
        self,
        flow: str,
        named: str,
        place: Place,
        agents: dict[str, tuple[Model, ...]],
        now: Whose | None = None,
    ) -> None:
        """Initializes the choosing.

        Args:
          flow: The flow whose agent this is.
          named: What the flow calls it, which every step of configuring it says.
          place: What the flow declared about it, which is what the moments it has to run are
            read from.
          agents: The CLIs installed here, and what each says it runs.
          now: What this step answered last time it was walked through, or None for one being
            asked for the first time -- esc is the step before, and a step before that had
            forgotten itself would be a different question.
        """
        super().__init__()
        self._flow = flow
        self._named = named
        self._place = place
        #: What each CLI installed here runs, which is a tab apiece. What they run is the
        #: next step's; this one needs only the names.
        self._agents = dict(agents)
        self._now = now or Whose("")
        able = self._able()
        #: Which tab is open, counting the CLIs this one could be, opening on the one it is
        #: already for a walk that has been here before.
        self._at = able.index(self._now.cli) if self._now.cli in able else 0
        #: The accounts of the tab that is open, read once per tab: looking means reading a
        #: directory, and this is redrawn on every keystroke.
        self._found: list[tuple[str, str, str]] | None = None
        #: What became of the last account made from here, said under the list: a login that
        #: exited badly is worth knowing about where it was asked for.
        self._said = ""

    def _able(self) -> list[str]:
        """The CLIs that could take this agent's turns, which is not always all of them.

        Which is what the tabs are: the ones installed here, less any the flow has ruled out.
        A flow that hangs a hook on a moment only some backends run said so where it declared
        the place; a CLI that does not run that moment is not one to offer for it, since
        choosing it is a flow that would refuse to start.

        Returns:
          One CLI per tab, in the order the tabs go.
        """
        needs = self._place.moments
        return [
            backend
            for backend in sorted(self._agents)
            if not needs or (backend in DRIVEN and needs <= DRIVEN[backend][0].moments)
        ]

    def _backend(self) -> str:
        """The CLI whose tab is open, or "" where there is no tab to be on."""
        able = self._able()
        return able[self._at % len(able)] if able else ""

    def _tabs(self) -> str:
        """The CLIs as a row of tabs, with the one being read marked and the rest waiting.

        Returns:
          The line, as markup, or "" where there is no CLI to show a tab for at all.
        """
        able = self._able()
        if not able:
            return ""
        here = self._backend()
        said = _DOT.join(
            f"[b $primary]{escape(one)}[/]"
            if one == here
            else f"[$text-muted]{escape(one)}[/]"
            for one in able
        )
        # Only where there is somewhere to switch to: one CLI is a heading rather than tabs.
        if len(able) > 1:
            said += "   [$text-muted]←/→ to switch[/]"
        return said

    def _turn_to(self, by: int) -> None:
        """Opens the tab that many along, wrapping round at either end.

        What is typed goes with the tab it was typed into, as it does on the models: a search
        that narrowed one CLI's accounts to one would narrow the next one's to none, which
        reads as a CLI with nothing in it rather than as a search still running.

        Args:
          by: One tab forward or back.
        """
        able = self._able()
        if len(able) < 2:  # noqa: PLR2004  -- one tab is nowhere to switch to
            return
        self._at = (self._at + by) % len(able)
        self._typed = ""
        self._found = None  # another backend's accounts, which are another list
        self._said = ""
        self.query_one("#choices", OptionList).highlighted = 0
        self._drawn = 0
        self._fill()

    def action_next_cli(self) -> None:
        """Opens the next CLI's tab."""
        self._turn_to(1)

    def action_prev_cli(self) -> None:
        """Opens the one before it."""
        self._turn_to(-1)

    def _ask(self) -> None:
        """Says whose turns these are, and what choosing a CLI and an account settles."""
        self.query_one("#asked", Label).update(
            f"Select what takes {self._named}'s turns, and the account they run as"
        )
        needs = self._place.moments
        self.query_one("#about", Label).update(
            f"Which coding agent takes this one's turns in {self._flow}, one per tab on the "
            "arrows, and under it that CLI's own accounts -- an account is one backend's. Its "
            "sessions, its settings and its skills are the CLI's own whichever it runs as."
            + (
                f" This one has to run {', '.join(sorted(needs))}, so only the CLIs that do "
                "are here."
                if needs
                else ""
            )
        )
        self._fill()
        self.query_one("#choices", OptionList).focus()

    def _fill(self) -> None:
        """Puts the open tab's accounts up, this machine's own first."""
        listing = self.query_one("#choices", OptionList)
        if self._found is None:
            self._found = self._accounts()
        shown = [row for row in self._found if self.fits(row[1], row[2])]
        self._counting = len(str(len(shown)))
        at = min(listing.highlighted or 0, max(len(shown) - 1, 0))
        listing.set_options(
            Option(
                self._row(
                    seen,
                    label,
                    about,
                    here=seen == at,
                    inforce=Whose(self._backend(), answer) == self._now,
                ),
                # Every row answers with an account's name and "" is one of the answers,
                # which an id of its own keeps tellable from a row that was never chosen.
                id=f"={answer}",
            )
            for seen, (answer, label, about) in enumerate(shown)
        )
        listing.highlighted = at if shown else None
        self._drawn = at
        self.tabbed(self._tabs())
        said = self._nothing()
        self.query_one("#tuning", Label).update(
            f"[$text-muted]{said}[/]" if said else ""
        )
        self.query_one("#keys", Label).update(
            "←/→ CLI · ctrl+n to make one · Type to search · Enter to choose · Esc to go back"
            f"{self.searching()}"
        )

    def _accounts(self) -> list[tuple[str, str, str]]:
        """This machine's own first, and then every account the open tab's CLI has here."""
        from humanize import providers

        backend = self._backend()
        if not backend:
            return []
        return [
            # Two words for the account nobody chose: this is a row in a list of accounts, and
            # what it is is the one the CLI is already signed in as.
            ("", "as installed", "signed in as you signed it in"),
            *((one.name, one.name, _sets(one)) for one in providers.providers(backend)),
        ]

    def _nothing(self) -> str:
        """Says what came of making one, or where they come from for a CLI that has none."""
        if self._said:
            return self._said
        backend = self._backend()
        if not backend:
            return "no coding agent installed here can take this one's turns"
        if len(self._found or []) > 1:
            return ""
        return f"{escape(backend)} has no accounts here yet; ctrl+n makes one"

    @work
    async def action_new(self) -> None:
        """Makes an account for this CLI without leaving the question it is chosen in.

        The same walk `/providers` runs, minus the question this sheet has already answered:
        which backend. What comes of it is what the sheet is now showing, so a new account is
        chosen straight away -- making one here is choosing it -- unless its own way in failed,
        which is said under the list and left for whoever is looking to decide about.
        """
        backend = self._backend()
        if not backend:
            return  # no CLI to make an account for, so nothing for the key to be about
        # textual types the property off the bare generic, as it does everywhere else here.
        showing = cast(
            "App[None]",
            self.app,  # pyright: ignore[reportUnknownMemberType]
        )
        outcome = await made(showing, backend)
        if outcome.why:
            self._said = escape(outcome.why)
        if outcome.provider is None:
            self._found = None  # it may have been made and then failed; look again
            self._fill()
            return
        if outcome.status:
            self._said = (
                f"{escape(outcome.provider.name)} is written down, but signing it in "
                f"exited {outcome.status}"
            )
            self._found = None
            self._fill()
            return
        self.dismiss(Whose(backend, outcome.provider.name))

    @on(OptionList.OptionSelected)
    def _took(self, event: OptionList.OptionSelected) -> None:
        """Answers with the CLI whose tab is open and the account that was picked.

        Args:
          event: What was chosen.
        """
        self.dismiss(Whose(self._backend(), str(event.option.id).removeprefix("=")))


class Made(NamedTuple):
    """What making an account came to.

    Attributes:
      provider: The account written down, or None where the walk was left without making one.
      status: What the way's own command exited with, or 0 for a way that runs nothing and
        for one nobody got as far as running.
      why: What went wrong before anything was written down, or "" where nothing did.
      way_runs: Whether the way had a command of its own, which is what tells an account that
        was signed in from one that was only written down.
    """

    provider: Provider | None = None
    status: int = 0
    why: str = ""
    way_runs: bool = False


async def made(host: App[None], cli: str, *, whose: str = "") -> Made:
    """Walks one backend's way in, and writes down the account it makes.

    Here rather than beside whatever asked for it, because both places that ask are here:
    `/providers`, which asks which backend first, and the sheet an agent's own account is
    chosen on, which knows the backend already and would otherwise have to send somebody out
    of the question they are answering to answer it.

    Args:
      host: The interface, which is what the sheets are pushed onto and what hands the
        terminal over while a login owns it.
      cli: The backend the account is for.
      whose: What to call it, for one already named, or "" to ask.

    Returns:
      What came of it: the account, whether its way in exited badly, and what stopped it
      before anything was written down. All three empty for a walk that was left.
    """
    from humanize.providers import login as signing

    way: Way | None = None
    while True:
        if way is None:
            named_way = await host.push_screen_wait(Ways(cli))
            if named_way is None:
                return Made()  # walked out of the first question, which changes nothing
            way = signing.way_of(cli, named_way)
            if way is None:
                return (
                    Made()
                )  # the sheet lists that backend's own, so there are none else
        signs = await host.push_screen_wait(Signing(cli, way, name=whose))
        if signs is None:
            way = None  # back to the ways, which is the step before
            continue
        break
    try:
        provider = signing.make(cli, signs.name or whose, way, signs.answers)
    except (ValueError, OSError) as why:  # a name or a directory that will not do
        return Made(why=str(why))
    if not way.argv:
        return Made(provider=provider)
    # A login is a browser opened, a code read out, a token exchanged: it owns the screen
    # while it runs, and there is nothing for an interface to draw over it.
    with handed_over(host):
        status = signing.sign_in(provider, way, signs.answers)
    return Made(provider=provider, status=status, way_runs=True)


@contextlib.contextmanager
def handed_over(host: App[None]) -> Generator[None]:
    """Gives the terminal away for as long as something else needs to own it.

    Where there is one to give: a driver that cannot be suspended is one nobody is watching --
    a test, a web terminal -- and what was going to run still has to run.

    Args:
      host: The interface holding the terminal.
    """
    from textual.app import SuspendNotSupported

    try:
        with host.suspend():
            yield
    except SuspendNotSupported:
        yield


class Backends(Picks):
    """Which coding agent a new account is for.

    Every backend humanize drives rather than the ones installed here: an account is
    credentials, and credentials are worth writing down before the CLI that will use them is
    on this machine.
    """

    asked = "Select which coding agent this account is for"
    about = (
        "The CLI whose credentials these are. An account is one backend's -- what signs in "
        "to Claude Code is not what signs in to codex -- and the ways in are its own."
    )

    def rows(self) -> list[tuple[str, str, str]]:
        """Every backend there is, saying how each of them can be signed into."""
        from humanize.backends import PROFILES
        from humanize.providers import ways

        return [
            (
                profile.name,
                profile.name,
                ", ".join(way.name for way in ways(profile.name)),
            )
            for profile in PROFILES
        ]


class Ways(Picks):
    """How to sign into one backend: its subscription, a key, a gateway, somebody's cloud.

    What a backend offers rather than what could be written: each of these lands somewhere
    different -- a login writes the CLI's own store, a key is a variable -- and an account is
    one of them, answered.
    """

    asked = "Select how to sign in"
    about = (
        "What this account is. A way with a command of its own is handed the terminal once "
        "the questions are answered, so its own browser or device code owns the screen; one "
        "that is only answers is written down as they are given."
    )

    def __init__(self, backend: str) -> None:
        """Initializes the choosing.

        Args:
          backend: The CLI these are the ways into.
        """
        super().__init__()
        self._backend = backend

    def rows(self) -> list[tuple[str, str, str]]:
        """Every way that backend offers, and the one every backend has."""
        from humanize.providers import ways

        return [(way.name, way.name, way.about) for way in ways(self._backend)]

    def nothing(self) -> str:
        """Says so for a name no backend answers to, which is the only way this is empty."""
        if self._rows:
            return ""
        return f"{escape(self._backend)} is not a coding agent humanize drives"


class Signs(NamedTuple):
    """What an account is to be made out of: what to call it, and what its way was told.

    Attributes:
      name: What the account is called, which is what an agent is configured with.
      answers: What each question was answered with, by the variable that answer becomes.
    """

    name: str
    answers: dict[str, str]


#: What the row asking what to call an account is held under. Not a variable anything is
#: given: a name is what an agent is configured with rather than something a CLI reads.
_CALLED = ""

#: The row a way that asks nothing in particular is answered in, and the question on it. Its
#: own name rather than a variable's, since what is typed here is the variables themselves.
_TYPED = " "
_TYPED_ABOUT = "the variables, as NAME=VALUE, one per line -- ctrl+j breaks the line"


class Signing(Sheet[Signs]):
    """What a way in has to be told before an account can be made out of it.

    A form rather than a list, so it is drawn as `/config` is: one row per question, the
    variable the answer becomes, what has been typed into it, and the question said quietly
    beside it. What the backend called a secret is drawn as bullets and never shown back --
    it is on its way into a credential store, and a screen is somewhere it can be read off.
    """

    BINDINGS: ClassVar = [
        ("escape", "back", "back"),
        # Enter is the whole form rather than the row under the cursor: there is nothing here
        # to pick, every row being written where it stands.
        Binding("enter", "done", "done", priority=True),
    ]

    def __init__(self, cli: str, way: Way, name: str = "") -> None:
        """Initializes the answering.

        Args:
          cli: The backend this account is for.
          way: The way in it is being made by, whose questions these are.
          name: What it is called already, for one being signed in again -- a name it has is
            not a name to ask for twice -- or "" to ask for one.
        """
        super().__init__()
        self._cli = cli
        self._way = way
        self._name = name
        #: One row per thing to be told: what the answer is kept under, the question, and
        #: whether it is a secret. What to call it comes first where it is not known already,
        #: since nothing can be written down without a name.
        self._fields: list[tuple[str, str, bool]] = [
            *([] if name else [(_CALLED, "what to call this account", False)]),
            *((one.env, one.about, one.secret) for one in way.asks),
            # A way that asks nothing in particular is asked for everything at once: the way
            # every backend has is variables of its own, and which ones they are is the
            # answer rather than the question.
            *([] if way.asks else [(_TYPED, _TYPED_ABOUT, True)]),
        ]
        self._counting = len(str(len(self._fields)))
        #: What has been typed into each, starting from the answer a question has when nobody
        #: is asked: a region that is usually right is an answer rather than a blank.
        self._typed_in: dict[str, str] = {_CALLED: name} | {
            one.env: one.fixed for one in way.asks
        }
        #: What was still missing, once the form has been offered.
        self._wrong = ""

    def _ask(self) -> None:
        """Says what is being signed into, and what the keys do while it is."""
        self.query_one("#asked", Label).update(
            f"Sign in to {escape(self._cli)} by {escape(self._way.name)}"
        )
        self.query_one("#about", Label).update(
            "What this way in has to be told. Typing answers the row under the cursor and "
            "enter takes the lot. A secret is drawn as bullets and never shown back."
        )
        self._fill()
        self.query_one("#choices", OptionList).focus()

    def _fill(self) -> None:
        """Puts the questions up, with the caret in the one under the cursor."""
        listing = self.query_one("#choices", OptionList)
        at = self._at
        listing.set_options(
            Option(
                self._line(seen, held, about, secret=secret, here=seen == at),
                id=f"={held}",
            )
            for seen, (held, about, secret) in enumerate(self._fields)
        )
        listing.highlighted = at if self._fields else None
        self._drawn = listing.highlighted
        self.query_one("#tuning", Label).update(
            f"[$error]{escape(self._wrong)}[/]" if self._wrong else ""
        )
        self.query_one("#keys", Label).update(
            "Type to answer · Backspace to rub out · Enter to accept · Esc to go back"
        )

    @property
    def _at(self) -> int:
        """Which question the cursor is on, counting from zero."""
        listing = self.query_one("#choices", OptionList)
        return min(listing.highlighted or 0, max(len(self._fields) - 1, 0))

    def _line(self, at: int, held: str, about: str, *, secret: bool, here: bool) -> str:
        """One question: what the answer becomes, what has been typed, and what is being asked.

        Args:
          at: Which one it is, counting from zero.
          held: The variable the answer is kept under, or "" for the name.
          about: The question, as the backend puts it.
          secret: Whether what is typed is a secret.
          here: Whether the cursor is on it.

        Returns:
          The row, as markup.
        """
        mark = f"{_INDENT}[$primary]{_HERE}[/] " if here else f"{_INDENT}  "
        number = f"{at + 1:>{self._counting}}."
        # A bullet per character for a secret: how much has been typed is worth seeing, and
        # what it was is worth seeing once, on the way in, by the one typing it.
        value = self._typed_in.get(held, "")
        shown = "•" * len(value) if secret else value
        named = held or "name"
        # A block where the next letter goes, as `/config` draws one: every row here is
        # written into, so every one of them has somewhere the next letter lands.
        caret = "[reverse] [/reverse]" if here else ""
        # Padded on what is shown rather than on what is written: markup is not columns.
        label = escape(named) + " " * max(1, _SETTING - len(named))
        room = _VALUE - len(shown) - 1
        return (
            f"{mark}[$text-muted]{number}[/] {label}"
            f"[$secondary]{escape(shown)}[/]{caret}{' ' * max(1, room)}"
            f"[$text-muted]{escape(about)}[/]"
        )

    def on_key(self, event: events.Key) -> None:
        """Takes a letter as answering the question under the cursor.

        There is nothing to search here -- every question is on screen at once -- so the keys
        that narrow a list elsewhere are the ones that answer.

        Args:
          event: The key.
        """
        if not self._fields:
            return
        held = self._fields[self._at][0]
        if event.key == "backspace":
            self._typed_in[held] = self._typed_in.get(held, "")[:-1]
        elif event.is_printable and event.character:
            self._typed_in[held] = self._typed_in.get(held, "") + event.character
        else:
            return
        event.prevent_default()
        event.stop()
        self._wrong = ""
        self._fill()

    def action_done(self) -> None:
        """Answers with what it is to be called and what its way was told, once that is all.

        What is missing is said where it was typed rather than raised at whoever opened the
        sheet: a question left blank is a question to answer, and this is where answering it
        happens.
        """
        from humanize.providers import env_of, where
        from humanize.providers.login import asked

        name = (self._name or self._typed_in.get(_CALLED, "")).strip()
        answers = {
            held: value
            for held, value in self._typed_in.items()
            if held.strip() and value
        }
        try:
            where(self._cli, name)
            if said := self._typed_in.get(_TYPED, "").strip():
                # Read here rather than where the account is made, so that a line that is not
                # a variable is said on the row it was typed on.
                answers |= env_of(said.replace("\r", "\n"))
        except ValueError as why:
            self._wrong = str(why)
            self._fill()
            return
        if still := asked(self._way, answers):
            self._wrong = f"{still[0]} is still to be answered"
            self._fill()
            return
        if not answers and not self._way.argv:
            self._wrong = "an account that says nothing signs nothing in"
            self._fill()
            return
        self.dismiss(Signs(name, answers))


class Doing(NamedTuple):
    """What the accounts sheet was asked for, for the interface to go and do.

    Named as `hmz providers` names the same three things, because they are the same three
    things: what can happen to an account is one list whether it is asked for at a sheet or
    on a command line.

    Attributes:
      what: `add`, `login` or `remove`.
      cli: The backend the account is for, or "" for one that is not made yet.
      name: What it is called, or "" for the same reason.
    """

    what: str
    cli: str = ""
    name: str = ""


#: The three things that can happen to an account, spelled as `hmz providers` spells them.
_ADD = "add"
_LOGIN = "login"
_REMOVE = "remove"


class Providers(Sheet[Doing]):
    """Every account there is to run an agent as, a CLI at a time.

    Read rather than chosen from: which account an agent runs as is asked where that agent is
    chosen, so nothing here is being picked for anything. What it is for is the three things
    that can happen to one -- made, signed in again, taken away -- so those are the keys, and
    enter is the one of them that needs nothing under the cursor.

    Each row is the name, the way it was made by and the variables it sets. Their names and
    never a value: this is drawn where somebody can read it.
    """

    BINDINGS: ClassVar = [
        ("escape", "back", "back"),
        # Letters rather than chords, and priority so they are the keys rather than a search:
        # a list of your own accounts is short enough to read, and every one of these is
        # something to do to it. Enter alongside `a`, since a sheet nothing is picked from
        # has nothing else for the key that picks.
        Binding("enter", "add", "make one", priority=True),
        Binding("a", "add", "make one", priority=True),
        Binding("l", "again", "sign in again", priority=True),
        Binding("r", "drop", "take away", priority=True),
    ]

    def __init__(self) -> None:
        """Initializes the reading."""
        super().__init__()
        self._found: list[Provider] | None = None
        #: Which account the cursor is on, as `cli/name`: the headings between them are rows
        #: nothing can land on, so a row number is not an account.
        self._was = ""

    def on_key(self, event: events.Key) -> None:  # noqa: ARG002  -- every key here is a key
        """Takes no letter as searching, each of the letters here being a key of its own."""
        return

    def _ask(self) -> None:
        """Says what these are, and puts them up."""
        self.query_one("#asked", Label).update("Accounts an agent may run as")
        self.query_one("#about", Label).update(
            "One named set of credentials per account, kept apart from the CLI's own and "
            "from each other's. An agent is given one where the agents are chosen, in the "
            "first of the three steps that configure it, and runs its turns as that account."
        )
        self._fill()
        self.query_one("#choices", OptionList).focus()

    def _providers(self) -> list[Provider]:
        """Every account there is, read once: this is redrawn each time the cursor moves."""
        if self._found is None:
            from humanize import providers

            self._found = providers.providers()
            self._counting = len(str(len(self._found)))
        return self._found

    def _fill(self) -> None:
        """Puts the accounts up under a heading apiece, marked where the cursor is."""
        listing = self.query_one("#choices", OptionList)
        found = self._providers()
        at = listing.highlighted
        if at is not None and 0 <= at < listing.option_count:
            self._was = str(listing.get_option_at_index(at).id or "") or self._was
        if all(f"{one.cli}/{one.name}" != self._was for one in found):
            # Gone, or never there: the cursor starts on the first of them, and a list with
            # nothing in it has nothing for it to be on.
            self._was = f"{found[0].cli}/{found[0].name}" if found else ""
        rows: list[Option] = []
        group, landing = "", 0
        for seen, one in enumerate(found):
            named = f"{one.cli}/{one.name}"
            if one.cli != group:
                group = one.cli
                # A heading, and a blank line above it once there is something above it.
                # Neither can be landed on, so the arrows walk the accounts and step over.
                if rows:
                    rows.append(Option("", disabled=True))
                rows.append(
                    Option(f"{_INDENT}[$primary]{escape(group)}[/]", disabled=True)
                )
            if named == self._was:
                landing = len(rows)
            rows.append(
                Option(
                    self._row(
                        seen,
                        one.name,
                        _sets(one),
                        here=named == self._was,
                        inforce=False,
                    ),
                    id=named,
                )
            )
        listing.set_options(rows)
        listing.highlighted = landing if found else None
        self._drawn = listing.highlighted
        self.query_one("#tuning", Label).update(
            "" if found else "[$text-muted]no accounts yet; enter makes one[/]"
        )
        self.query_one("#keys", Label).update(
            "Enter or a to make one · l to sign one in again · r to take one away · "
            "Esc to close"
        )

    def action_add(self) -> None:
        """Answers that another one is to be made, which the interface walks through."""
        self.dismiss(Doing(_ADD))

    def action_again(self) -> None:
        """Answers that the one under the cursor is to be signed in again."""
        self._doing(_LOGIN)

    def action_drop(self) -> None:
        """Answers that the one under the cursor is to be taken away."""
        self._doing(_REMOVE)

    def _doing(self, what: str) -> None:
        """Answers with something to do to the account under the cursor, if there is one.

        Args:
          what: What is to happen to it.
        """
        cli, _, name = self._was.partition("/")
        if not name:
            return  # nothing in the list, so nothing for a key to be about
        self.dismiss(Doing(what, cli, name))


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
        self,
        flow: str,
        named: tuple[str, ...],
        models: list[Runs],
        monitor: Monitor,
        config: BaseModel | None = None,
    ) -> None:
        """Reads one run.

        Args:
          flow: The flow being run.
          named: What that flow calls each agent it drives, "" apiece where it names none.
          models: What each of its agents runs, and where its turns land.
          monitor: The run itself, read again each time this is redrawn.
          config: What the flow was set up with, for a flow that takes any setting up.
        """
        super().__init__()
        self._flow = flow
        self._named = named
        self._models = models
        self._monitor = monitor
        self._config = config

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
                # Only what was changed: a flow of forty settings says nothing by listing
                # the ones nobody touched, and this is read to see what this run is.
                ("Set", [escape(one) for one in setting(self._config)]),
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

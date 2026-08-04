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
asked before the CLI has been. The backends are read one at a time, a tab apiece: the ones
installed here plus an optional one the sheet can teach somebody to install. Every model of
every CLI in one list is a list that grows each time any of them ships a model. The effort is
the line with the arrows on it, exactly as Claude Code's is, and beside it the things that
really are side questions about the same agent.

`/status` is the last of them, and is read rather than answered -- Claude Code's own, which is
a rule across, fields down the left and their values lined up beside them.
"""

from __future__ import annotations

import contextlib
import shlex
import sys
import time
from pathlib import Path
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

from hmz.agents import PERMISSIONS, SWARM, anchored, driver
from hmz.agents.skills import Skill, skills
from hmz.backends import named

from .discover import machines
from .monitor import short, thousands
from .selecting import Choices

if TYPE_CHECKING:
    from collections.abc import Callable, Generator, Mapping, Sequence

    from pydantic import BaseModel
    from pydantic.fields import FieldInfo
    from textual.app import App, ComposeResult

    from hmz.agents import AgentBase, Moment
    from hmz.backends import Model, Way
    from hmz.flows import Flowverse, Offer
    from hmz.providers import Provider
    from hmz.runner import Place

    from .monitor import Monitor

__all__ = [
    "Accounts",
    "Agent",
    "Anchors",
    "Backends",
    "Catalogue",
    "Chosen",
    "Clis",
    "Configures",
    "Confirms",
    "Drafts",
    "Fitted",
    "Flows",
    "Held",
    "Imports",
    "Kept",
    "Names",
    "Picks",
    "Providers",
    "Runs",
    "Saved",
    "Sheet",
    "Signing",
    "Signs",
    "Skills",
    "Speaks",
    "Status",
    "Ways",
    "called",
    "config_of",
    "model_of",
    "opens_on",
    "places_of",
    "pointed",
    "reads",
    "setting",
    "settled",
]


class Runs(NamedTuple):
    """What one agent of a flow was set up to run, and where its turns land.

    Attributes:
      spec: The agent itself, as `cli/model:effort` -- the same word a command line takes.
      anchor: The machine its work lands on, as a target, or "" to work on this one.
      skills: The skills of its CLI it is to have, by name, or None for the CLI as it comes
        -- which is every skill it finds.
      permission: What it may do without being asked, as one of `hmz.agents.PERMISSIONS`,
        or "" for the one an agent nobody has been asked about runs at.
      provider: The account its turns run as, by the name a provider of its CLI was made
        under, or "" to run as this machine is already signed in.
      goals: Whether backend goals are available. This is always an on/off answer; any
        suggestion attached to the flow's agent place is resolved before this is constructed.
    """

    spec: str
    anchor: str = ""
    skills: tuple[str, ...] | None = None
    permission: str = ""
    provider: str = ""
    goals: bool = True


class Kept(NamedTuple):
    """One agent written down under a name, to be imported from any flow that wants one.

    Beside :class:`Runs` because it is one: an agent is a CLI, an account, a model at an
    effort and what it may do, and a name is the only thing a saved one has that an agent of
    a flow has not -- a flow's is called what the flow calls it.

    Attributes:
      name: What it is called, which is what it is imported by and nothing else.
      runs: What it is.
    """

    name: str
    runs: Runs


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
    from hmz.agents import Remote

    return place.where is Remote or isinstance(place.where, Remote)


def _settled(place: Place) -> str:
    """The container a flow put one of its agents in, where it named one.

    Args:
      place: What the flow declared.

    Returns:
      The image, or "" for an agent that works here and one that is asked where it works --
      neither of which is something the flow settled.
    """
    from hmz.agents import Isolated

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
#: may hold slashes of its own -- Kimi Code's and opencode's are `provider/id` -- and is
#: shown as the CLI is given it, since a name shortened here is not the name of anything.
_LABEL = 26

#: How wide the column of field names on `/status` is, so their values line up beside them.
_FIELD = 18

#: How often `/status` is redrawn, in seconds. It is read while a flow is running, which is
#: the whole point of it: a sheet that froze what it said the moment it opened would be a
#: snapshot of a run, and the run is what is being watched.
_LIVE = 0.5


class Held(NamedTuple):
    """What one agent of a running flow is holding: its conversations, and which is read.

    Attributes:
      many: How many conversations it has open, which is none for an agent that has opened
        none and for every agent of a flow that is not running.
      at: Which of them is being read, counting from zero, or None for an agent none of
        whose conversations is.
      unread: Whether one it holds that is not being read has said something since it was
        last looked at.
      working: Whether any of its conversations has a turn open. Which is the first thing
        somebody looks for with several agents going at once -- who is thinking and who has
        stopped -- and the only one of these that changes by itself.
    """

    many: int = 0
    at: int | None = None
    unread: bool = False
    working: bool = False


#: What says an agent is working and what says it is not. A filled circle and a hollow one:
#: the same two marks the sheets use for what is in force and what is not, and the one thing
#: on this line that moves on its own.
_WORKING, _IDLE = "●", "○"


def _holds(held: Held) -> str:
    """What one agent's conversations say about themselves beside what it runs.

    Args:
      held: What it is holding.

    Returns:
      Whether it is working, then `2 of 5` for the agent holding the one being read -- which
      of them it is being the half worth knowing -- or the count alone for the others, and
      `unread` after it where one of those has said something since it was last looked at.
      Nothing at all for an agent holding none, which is every agent of a flow that is not
      running.
    """
    if not held.many:
        return ""
    reading = f"{held.at + 1} of {held.many}" if held.at is not None else f"{held.many}"
    said = f"{_WORKING} {reading}" if held.working else f"{_IDLE} {reading}"
    return f"{said}{_DOT}unread" if held.unread else said


def reads(
    named: tuple[str, ...], runs: list[Runs], holding: Sequence[Held] = ()
) -> list[str]:
    """One line per agent a flow drives: what it runs, where, and what it is holding.

    In one place because it is read in two -- above the prompt while a flow runs, and on
    `/status` -- and an agent that read as two different things in them would be two. What it
    is holding is only asked for above the prompt, that being where a conversation is read
    and said to; `/status` asks for the same line without it, and it says nothing there.

    Args:
      named: What the flow calls each of them, "" apiece where it names none.
      runs: What each of them runs, and where its turns land.
      holding: The conversations each of them has open, in the same order, or nothing at all
        for a flow that is not running -- which holds none.

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
                _holds(holding[at]) if at < len(holding) else "",
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
#tabs { padding: 0 0 1 3; width: 1fr; }
OptionList { border: none; background: $background; scrollbar-size: 0 0; padding: 0; }
/* The marker says where the cursor is, so the row is not filled as well. */
#choices > .option-list--option-highlighted {
    background: $background; color: $foreground; text-style: none; }
/* As wide as the sheet, so that what is said under the list and the keys under that wrap
   onto a second row rather than running off the side of a narrow terminal: a key nobody can
   see is a key nobody has. */
#tuning { padding: 1 0 1 3; width: 1fr; }
#keys { padding: 0 0 0 3; color: $text-muted; width: 1fr; }
/* The fields carry their own indent, as the numbered rows above them do. */
#said { padding: 0 0 1 0; }
"""


#: The one question that is not a sheet: a box in the middle of the screen, over the menu it
#: is about rather than instead of it. A sheet is walked to and fills the width it is drawn
#: in; this arrives, says one thing, and is answered in a keypress -- so it is drawn as the
#: thing every terminal draws that as, which is a bordered box with the question in it. The
#: parts a sheet has and this has no use for are taken away rather than left blank.
_POPUP = """
Confirms { align: center middle; background: transparent; }
#sheet { width: 66; max-width: 100%; height: auto; padding: 1 2; border: round $primary;
         background: $background; }
#rule { display: none; }
#tuning { display: none; }
#asked { padding: 0; text-style: bold; color: $primary; }
#about { padding: 0 0 1 0; color: $text-muted; width: 1fr; }
OptionList { border: none; background: $background; scrollbar-size: 0 0; padding: 0; }
#choices > .option-list--option-highlighted {
    background: $background; color: $foreground; text-style: none; }
#keys { padding: 1 0 0 0; color: $text-muted; width: 1fr; }
"""


#: What a menu's own keys are, said at the bottom of every sheet that has tabs.
_TURNS = "tab/shift+tab to switch"

#: And what steps between the lists one page is made of, said beside them for the same
#: reason: a key that is not written where it works is a key somebody has to already know.
_STEPS = "←/→ to switch"

#: The most rows of choices a sheet shows however tall the terminal is: a list longer than
#: this is one that is walked rather than read.
_MOST = 14
#: The fewest it shortens to before giving up. A terminal with no room for three rows has no
#: room for the sheet either, and a list shortened to nothing is not a list.
_LEAST = 3


class Body(Vertical):
    """What a sheet is drawn down, which says when it has grown taller than the terminal.

    A sheet is a question with its keys under it, and the one part of it that can be any
    length is the list in the middle: every flow there is, every model a CLI runs. Drawn as
    tall as it likes, that list pushes the keys off the bottom of a short terminal -- so the
    column says when its height changes and the list is shortened to fit. Resize does not
    bubble, so nothing else would hear about it.
    """

    def on_resize(self) -> None:
        """Tells whoever is holding this column that it is a different height now."""
        sheet = self.screen
        if isinstance(sheet, Sheet):
            sheet.shortens()


class Sheet[T](ModalScreen[T | None]):
    """One question drawn the way Claude Code draws one, answered by picking a line.

    What answering it comes to is the sheet's own: a flow is a name, an agent is what it runs
    and where, and walking out without answering is None wherever it is asked.

    A sheet of several pages says so: the titles are across the top and tab and shift+tab turn
    between them, which is the one pair of keys a terminal has for exactly that. Nothing here
    is a chord -- a sheet asks one thing and its keys are its own, so a key that needed ctrl
    held down would be a key somebody had to already know.
    """

    CSS = _SHEET
    BINDINGS: ClassVar = [("escape", "back", "back")]

    #: The pages this sheet is, in the order they are turned between, or nothing at all for a
    #: sheet that is one page. A sheet with tabs shows their titles whether or not there are
    #: two: a page nobody can see the name of is a page nobody knows they are on.
    TABS: ClassVar[tuple[str, ...]] = ()

    #: Which row the marker was last drawn against. Putting the rows up moves the cursor,
    #: which asks for them to be put up again -- and the message saying so is posted rather
    #: than called, so a flag set around the drawing is already clear by the time it arrives.
    #: What breaks the loop is having nothing to do: the marker is already where it goes.
    _drawn: int | None = None
    #: How many columns the numbering takes, so that every row starts in the same one.
    _counting = 1
    #: What has been typed to narrow the list down. A list of every model of every CLI is
    #: longer than a screen, and a list you walk to the end of to find one thing is one you
    #: read rather than use -- so there is somewhere for the letters to go.
    _typed = ""
    #: Whether the letters are going there now. Asked for rather than assumed: every other
    #: key on these sheets is a letter, and a sheet where typing always searched is a sheet
    #: with no letters left to press.
    _searching = False
    #: Which page is open, counting the tabs.
    _tab = 0
    #: How many rows of choices there is room for, or None before it has been worked out.
    #: Kept so that working it out again changes nothing where nothing has changed: setting
    #: it is what changes the height that asks for it to be worked out.
    _room: int | None = None
    #: Which row a key that has to be pressed twice has been pressed once on, or "" for none.
    _arming = ""

    #: What this sheet has put on letter keys, by action. They are the sheet's keys only
    #: while nothing is being typed into a search -- see :meth:`check_action`.
    LETTERS: ClassVar[frozenset[str]] = frozenset()

    def turnable(self) -> tuple[bool, ...]:
        """Which pages may be opened now, which is not always all of them.

        Returns:
          One per tab, in the order they go. All of them unless a sheet says otherwise -- a
          page that cannot be opened is one the tabs step over and one the titles say is
          shut, rather than one that is not there at all.
        """
        return tuple(True for _ in self.TABS)

    def action_next_tab(self) -> None:
        """Opens the next page there is to open."""
        self._turn_page(1)

    def action_prev_tab(self) -> None:
        """Opens the one before it."""
        self._turn_page(-1)

    def _turn_page(self, by: int) -> None:
        """Turns to the next page that may be opened, wrapping round at either end.

        Nothing is applied on the way: a menu is answered once, when it is left, so turning a
        page is reading rather than choosing.

        Args:
          by: One page forward or back.
        """
        able = self.turnable()
        if sum(able) < 2:  # noqa: PLR2004 -- one page is nowhere to turn to
            return
        at = self._tab
        for _ in range(len(self.TABS)):
            at = (at + by) % len(self.TABS)
            if able[at]:
                break
        if at == self._tab:
            return
        self._tab = at
        # What was typed goes with the page it was typed into, as it goes with a tab
        # anywhere else: a search that narrowed one page to one row would narrow the next to
        # none, which reads as a page with nothing in it rather than as a search still on.
        self._typed, self._searching = "", False
        self.query_one("#choices", OptionList).highlighted = 0
        self._drawn = 0
        self._turned()
        self._fill()

    def _turned(self) -> None:
        """What a sheet does as a page opens, which is nothing unless it says otherwise."""

    def _tab_line(self) -> str:
        """The titles, with the one being read marked and the shut ones struck through."""
        if not self.TABS:
            return ""
        able = self.turnable()
        said = _DOT.join(
            f"[b $primary]{escape(one)}[/]"
            if at == self._tab
            else f"[$text-muted]{escape(one)}[/]"
            if able[at]
            else f"[$text-muted][s]{escape(one)}[/s][/]"
            for at, one in enumerate(self.TABS)
        )
        if sum(able) > 1:
            said += f"   [$text-muted]{_TURNS}[/]"
        return said

    def action_search(self) -> None:
        """Starts narrowing the list by what is typed, until esc says to stop."""
        self._searching = True
        self.query_one("#choices", OptionList).highlighted = 0
        self._drawn = 0
        self._fill()

    def fits(self, *fields: str) -> bool:
        """Whether a row is one of the ones still worth showing.

        Args:
          fields: Everything the row says, which is all of it that is searched: what a thing
            is called, and where it came from.

        Returns:
          True if what has been typed is spread through one of them in order, so that a few
          letters anywhere in a name find it -- nobody types a model id out to narrow a list
          of them. One of them rather than all of them run together, or a search would run
          off the end of the name it was narrowing to and finish itself in the word beside
          it: `chat` would find `flame_chase builtin`, which is a match nobody typed.
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
        """What to say about the search, which is nothing at all until it has been asked for.

        Returns:
          The line to put after the keys: which key starts a search where none is running,
          and what has been typed so far where one is -- with the block the next letter lands
          on, so that a search nothing has been typed into yet still looks like one.
        """
        if not self._searching:
            return f"{_DOT}s to search"
        return (
            f"{_DOT}search [$secondary]{escape(self._typed)}[/][reverse] [/reverse]"
            f"{_DOT}Esc to leave it"
        )

    def on_key(self, event: events.Key) -> None:
        """Takes a letter as narrowing the list, once a search has been asked for.

        Only then: every other key on these sheets is a letter of its own, and a list where
        typing always searched would be a list with no keys left. The arrows walk it and enter
        takes what is under the cursor, either way.

        Args:
          event: The key.
        """
        if not self._searching:
            return
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
        with Body(id="sheet"):
            yield Label(id="rule")
            yield Label(id="asked")
            yield Label(id="about")
            yield Label(id="tabs")
            yield Choices(id="choices")
            yield Label(id="tuning")
            yield Label(id="keys")

    def on_mount(self) -> None:
        """Rules the top of the sheet across, and asks."""
        self.query_one("#choices", OptionList).styles.max_height = _MOST
        self.query_one("#rule", Label).update(_RULE * self.size.width)
        # The titles where there are any, and gone rather than blank where there are not: a
        # label with nothing in it still takes the row it is padded to, and a sheet that is
        # one page must be drawn exactly as it was before any sheet had two.
        self.tabbed(self._tab_line())
        self._ask()

    def tabbed(self, said: str) -> None:
        """Puts a row of tabs above the choices, or takes the row back where there are none.

        Args:
          said: The tabs, as markup, or "" for a sheet that is one list.
        """
        showing = self.query_one("#tabs", Label)
        showing.display = bool(said)
        showing.update(said)

    def on_resize(self) -> None:
        """Rules the new width across, and shortens the list to the room left under it."""
        if not self.query("#sheet"):
            return  # resized before there is anything on it, which is nothing to fit
        self.query_one("#rule", Label).update(_RULE * self.size.width)
        self.shortens()

    def shortens(self) -> None:
        """Shortens the list until what is under it is inside the terminal.

        The list is what gives. Everything else on a sheet is a line or two -- what is being
        asked, what it comes to, the keys -- and the rows are what there are a hundred of, so
        a sheet that does not fit is a sheet whose list is too long for the terminal it is
        drawn in rather than a sheet with too much on it. The keys are the last row, so they
        are what falls off the bottom, and a key nobody can see is a key nobody has.

        Called each time the column changes height, which is each time the list is put up
        again, and each time the terminal changes size. It settles at once: how tall the rest
        of the sheet is does not depend on how many rows the list is showing.
        """
        listing = self.query_one("#choices", OptionList)
        column = self.query_one("#sheet", Body).outer_size.height
        rest = column - listing.outer_size.height
        room = max(_LEAST, min(_MOST, self.size.height - rest))
        if room == self._room:
            return
        self._room = room
        listing.styles.max_height = room

    def action_back(self) -> None:
        """Comes out of the search, or leaves once there is no search to come out of.

        A search is the one place esc has something to step back to: leaving from there would
        throw away the walk in as well as the wrong letters.
        """
        if self._searching:
            self._searching, self._typed = False, ""
            self._drawn = 0
            self._fill()
            return
        self.leaving()

    def leaving(self) -> None:
        """What esc comes to once there is no search to leave, which is walking out.

        A sheet holding changes that have not been applied says something else here -- see
        :class:`Drafts` -- because walking out of one of those is a decision rather than a
        step back.
        """
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
        # A key that has to be pressed twice is armed against the row it was pressed on, so
        # moving off that row puts it down again: the second press must be a second press at
        # the same thing, or it is a stray keypress taking something else away.
        self._arming = ""
        self._fill()

    def check_action(
        self,
        action: str,
        parameters: tuple[object, ...],  # noqa: ARG002 -- the same key, whatever it carries
    ) -> bool | None:
        """Whether one of this sheet's own keys is live, which a search turns most of them off.

        A key that is a letter is the sheet's only while nothing is being typed: the whole
        point of asking for a search is that the letters go into it. Everything else -- esc,
        the arrows, enter, the tabs -- means what it means either way.

        Args:
          action: What the key would do.
          parameters: What it would do it with.

        Returns:
          Whether to run it. A binding refused here is one the key falls through, so the
          letter reaches the search rather than being swallowed.
        """
        return not (self._searching and action in self.LETTERS)

    def under(self) -> str:
        """What the cursor is on, by the id the row was put up under.

        Returns:
          The id, less the `=` a row whose answer may be the empty string carries, or "" for
          a list with nothing in it and for a cursor sitting on a heading.
        """
        listing = self.query_one("#choices", OptionList)
        at = listing.highlighted
        if at is None or not 0 <= at < listing.option_count:
            return ""
        return str(listing.get_option_at_index(at).id or "").removeprefix("=")

    def _armed(self, what: str) -> bool:
        """Whether a key that has to be pressed twice has been pressed once already.

        Taking something away is the one thing on these sheets that cannot be undone, so it is
        asked for twice: the first press arms the row under the cursor and says so, and the
        second takes it away. Moving the cursor puts it down again -- see :meth:`_moved` --
        which is what makes a stray keypress harmless.

        Args:
          what: The row, by its id.

        Returns:
          True if this is the second press and the thing is to go.
        """
        if self._arming == what:
            self._arming = ""
            return True
        self._arming = what
        return False

    def _fill(self) -> None:
        """Puts the choices up, which each sheet says for itself."""
        raise NotImplementedError

    def _ask(self) -> None:
        """Draws whatever is being asked for now, which each sheet says for itself."""
        raise NotImplementedError


#: What the sheet that asks about unsaved changes answers with.
_KEEP, _DROP = "keep", "drop"


class Drafts[T](Sheet[T]):
    """A sheet that holds everything changed in it until it is asked to apply the lot.

    Which is what makes several pages one menu: turning a page applies nothing, so what is
    read on the second page is what the first page is holding rather than what is written
    down. Nothing lands until the menu is left and saving is confirmed -- and esc on a menu
    holding changes asks, because walking out of one is a decision rather than a step back.
    """

    #: Whether anything has been changed since it opened, which is the whole of what esc has
    #: to ask about.
    _changed = False

    def changed(self) -> None:
        """Says that something has been changed, so that esc asks before throwing it away."""
        self._changed = True

    def applied(self) -> None:
        """Answers with everything held, which each menu says for itself."""
        raise NotImplementedError

    def leaving(self) -> None:
        """Asks whether to save what is held, and does whichever was asked for.

        Nothing at all where nothing was changed: a walk in to look and out again is not a
        question anybody wants asked of them.
        """
        if not self._changed:
            self.dismiss(None)
            return
        self.asks_to_save()

    @work
    async def asks_to_save(self) -> None:
        """Puts the question up, and does what it is answered with."""
        showing = cast(
            "App[None]",
            self.app,  # pyright: ignore[reportUnknownMemberType]
        )
        said = await showing.push_screen_wait(Confirms())
        if said == _KEEP:
            self.applied()
        elif said == _DROP:
            self.dismiss(None)
        # And anything else is staying here, which is what a third answer is for.


class Chosen(NamedTuple):
    """What the flow menu was answered with: what to run, on what, and set up how.

    One answer rather than three, because the menu is one thing answered once: what is held
    on each of its pages lands together when it is saved, or none of it does.

    Attributes:
      flow: The flow to run, by the name it was offered under.
      agents: What each of its agents is, in the order the flow takes them.
      config: What the flow itself is set up with, or None for a flow that takes no setting
        up and one that was left as it comes.
    """

    flow: str
    agents: tuple[Runs, ...]
    config: BaseModel | None = None


def opens_on(
    agents: Mapping[str, tuple[Model, ...]], *, goals: bool = True
) -> list[Runs]:
    """The one agent to fall back on where nothing has been remembered for a place.

    The first backend installed here that has said what it runs, at the first model it named
    -- which is that CLI's own idea of what it runs by default, and the only idea of it worth
    having. Nothing is written down here: a model named in this file would be a model this
    file was right about on the day it was written.

    Args:
      agents: The backends there are, and what each of them says it runs.
      goals: Whether backend goals start available to it.

    Returns:
      The one agent, or nothing at all where no backend here has yet said what it runs --
      which is a catalogue to fill rather than a model to guess at.
    """
    for backend, found in agents.items():
        if found:
            # Not the hardest effort, which is where the cursor starts: that is the one to
            # reach for, and this is the one to spend before anybody has asked for anything.
            # `high` is an effort every model of every backend here takes.
            return [Runs(f"{backend}/{found[0].name}:high", goals=goals)]
    return []


def places_of(flow: str) -> tuple[Place, ...] | None:
    """The agents a flow drives, or None for a flow that will not load.

    Args:
      flow: The flow, by the name it was offered under -- not by the file that name resolves
        to, since a file may hold several and which of them was asked for is the half after
        the colon.

    Returns:
      One place per agent it drives, and None where reading the flow raised at all -- which
      is a flow to report rather than a reason for a menu not to draw.
    """
    from hmz.runner import wanted

    try:
        return wanted(flow)
    except Exception:  # noqa: BLE001 -- a flow that will not load is still not a crash
        return None


def model_of(flow: str) -> type[BaseModel] | None:
    """What a flow says it can be set up with, if it says anything.

    Args:
      flow: The flow, by name or as a path.

    Returns:
      The model to ask with, or None for a flow that takes no setting up -- and for one that
      will not load, which is a flow to report where it is run rather than here.
    """
    from hmz.runner import configures

    try:
        return configures(flow)
    except Exception:  # noqa: BLE001 -- a flow that will not load is still not a crash
        return None


def config_of(flow: str, kept: dict[str, Any]) -> BaseModel | None:
    """How a flow was last set up, read back through the flow's own model rather than trusted.

    Args:
      flow: The flow.
      kept: What was written down for it, field by field.

    Returns:
      What it was set up with, or None for a flow that takes no setting up, has not been set
      up here, or has since changed enough that what was kept no longer reads -- a settings
      file is a convenience, and one that no longer fits is one to start over from.
    """
    model = model_of(flow)
    if model is None or not kept:
        return None
    try:
        return model.model_validate(kept)
    except Exception:  # noqa: BLE001 -- what was kept no longer fits the flow
        return None


def settled(
    runs: Sequence[Runs],
    places: Sequence[Place],
    agents: Mapping[str, tuple[Model, ...]] | None = None,
) -> list[Runs]:
    """One agent per place a flow drives, out of however many were remembered for it.

    A flow that has grown an agent since it was last run here is a flow with a place nothing
    was remembered for, and one that has lost one is a flow with an agent nobody will drive.
    Neither is a reason to start over: what is there is kept, and what is missing falls back
    on the agent the interface opens talking to.

    Args:
      runs: What was remembered, in the order the flow took them then.
      places: What the flow drives now.
      agents: The backends there are, for the place nothing was remembered for, or None
        where there is nothing to fall back on -- which leaves such a place unanswered.

    Returns:
      One apiece, with goals forced on for a place the flow declared it needs them at -- that
      one is the flow's own requirement rather than anybody's choice.
    """
    spare = opens_on(agents) if agents is not None else []
    held: list[Runs] = []
    for at, place in enumerate(places):
        if at < len(runs):
            one = runs[at]
        elif spare:
            # What the flow suggested for a place nothing was remembered for: a flow that
            # says its agent starts without goals is one whose fallback agent starts that
            # way too, rather than one whose suggestion only counts on a command line.
            one = spare[0]._replace(goals=place.goals_default)
        else:
            # Nothing remembered and nothing to fall back on, which is a machine with no
            # coding agent installed on it: a place with no agent is a place with no agent,
            # and an agent naming no model would be a worse answer than none.
            break
        held.append(one._replace(goals=True) if place.goal else one)
    return held


def _complete(runs: Runs) -> bool:
    """Whether one agent has been answered at all, which is a CLI and a model of that CLI.

    Args:
      runs: The agent.

    Returns:
      True if there is something to run it on.
    """
    cli, _, rest = runs.spec.partition("/")
    model, _, _ = rest.rpartition(":")
    return bool(cli and model)


#: What separates the two halves of a row's id on the flows page: which place it came from,
#: and which flow it is. A byte no name has in it, since either half may hold anything -- a
#: flow of yours is offered by its path, and a path holds slashes and dots and spaces.
_HALVES = "\x1f"

#: The pages the flow menu is, in the order they are turned between.
_FLOW_PAGE, _AGENT_PAGE = 0, 1


class Flows(Drafts[Chosen]):
    """Which flow runs and what each of its agents is: one menu, a page apiece.

    Two pages because they are two questions about one thing, and because they are not open
    at the same moments. A flow is chosen in order to be started, so choosing one while one is
    running is not a thing to offer at all -- that page is shut while a flow runs, and says so
    rather than going away. What its agents are is the other way round: an agent that is
    thinking too little, on the wrong account, or allowed too much is found out halfway
    through a run, so that page is never shut.

    The flows are read a place at a time -- every flowverse there is, fetched or not, and then
    this project's flows and yours -- with the left and right arrows stepping between the
    places and the list holding only the one being read. All of them run together under
    headings was one list nobody could see the end of, and one where walking to a flow meant
    walking past every flow that came before it. The three things that can happen to a
    flowverse are keys of this page, and are about the place being read: this is the moment
    somebody finds out that the flow they want is in one they have not added, or that the one
    they have is out of date.

    Choosing a flow asks what that flow itself takes, where it takes anything, and then turns
    to what will drive it. A key that set the flow up was a key nobody pressed: a flow with
    settings is chosen in order to be run with settings, and the moment it is chosen is the
    one moment somebody is thinking about that flow rather than about its agents.

    Nothing is applied by turning a page or by walking out. What the menu holds is a draft of
    the whole of it, and it lands when it is saved on the way out.
    """

    TABS: ClassVar = ("Flow", "Agents")
    LETTERS: ClassVar = frozenset({"search", "adding", "refresh", "drop"})

    BINDINGS: ClassVar = [
        ("escape", "back", "back"),
        # The pages, on the one pair of keys a terminal has for exactly that. Priority, or
        # the list under the cursor would take them as moving the focus about.
        Binding("tab", "next_tab", "next page", priority=True),
        Binding("shift+tab", "prev_tab", "previous page", priority=True),
        # The places the flows come from, on the other pair: the list walks up and down, so
        # across is what is left for stepping between the lists there are. Priority, or the
        # list under the cursor would take them as moving between columns it has none of.
        Binding("left", "before", "the place before", priority=True),
        Binding("right", "after", "the place after", priority=True),
        # Letters rather than chords, and priority so they are the keys rather than the
        # search: a search is asked for, and while one is running these fall through to it.
        Binding("s", "search", "search", priority=True),
        Binding("a", "adding", "add a flowverse", priority=True),
        Binding("r", "refresh", "fetch it again", priority=True),
        Binding("d", "drop", "take it away", priority=True),
    ]

    def __init__(
        self,
        flow: str,
        runs: Sequence[Runs],
        config: BaseModel | None,
        agents: dict[str, tuple[Model, ...]],
        kept: dict[str, Any],
        *,
        unavailable: frozenset[str] = frozenset(),
        running: bool = False,
        opening: int = 0,
    ) -> None:
        """Initializes the menu on what is set up now.

        Args:
          flow: The flow running now, or the one this workspace is set up to run.
          runs: What each of its agents is, in the order the flow takes them.
          config: What the flow itself is set up with, for one that takes setting up.
          agents: The backends offered here, and what each of them says it runs.
          kept: What each flow was last set up with here, by flow -- read when the draft flow
            changes, so that turning to a flow this workspace has run finds it as it was left.
          unavailable: The optional backends among them that still need installing.
          running: Whether a flow is running, which is what shuts the first page.
          opening: Which page to open on, for whoever opened the menu to reach one of them
            directly. A page that is shut is not opened on whatever is asked for.
        """
        super().__init__()
        self._agents = dict(agents)
        self._unavailable = unavailable
        self._underway = running
        self._kept = kept
        # Said outright, both of them: the flow is read where it is set, so what it is has to
        # be settled without reading what reads it.
        self._flow: str = flow
        self._places: tuple[Place, ...] = places_of(flow) or ()
        if runs:
            self._runs = (
                self._fitted(settled(runs, self._places, self._agents))
                if self._places
                else list(runs)
            )
            self._config = config
        else:
            # A flow the interface is not set up on, opened straight into: what it was last
            # set up with here is what it opens holding, exactly as turning to it would be.
            self._runs = self._fitted(
                settled(self._remembered(flow), self._places, self._agents)
            )
            self._config = config_of(flow, self._held(flow).get("config") or {})
        #: Every flow there is, read once: this is redrawn on every keystroke, and reading it
        #: means running each flow file to see what it holds. Cleared when a flowverse is
        #: fetched or taken away, which is when the list is something else.
        self._offers: list[Offer] | None = None
        #: Which row of the flows the cursor is on, as `where it came from` and `which flow`:
        #: a place with nothing in it is a row with no flow on it at all, so a row number is
        #: not a flow. Kept whole so that it still says which list it was a row of.
        self._was = ""
        #: Which place's flows are being read, the arrows stepping between them. "" until the
        #: page is first drawn: which place the flow in force came from is a thing only the
        #: list of every flow there is can say, and reading that list is running every file.
        self._where = ""
        #: What became of the last fetch, said under the list.
        self._said = ""
        #: What is being fetched now, so that a second fetch is not started over it and so
        #: that what is said under the list is what is being fetched. "" for none.
        self._fetching = ""
        # The flows are shut while one is running, so the menu opens on the page that is not.
        self._tab = _AGENT_PAGE if running else opening % len(self.TABS)

    def turnable(self) -> tuple[bool, ...]:
        """Which pages may be opened: the agents always, and the flows while none runs."""
        return (not self._underway, True)

    def _follows(self, listing: OptionList) -> None:
        """Takes which row the cursor is on off the list, rather than off a row number.

        Read here rather than kept as the cursor moves, so that the two cannot disagree: the
        list is a different list under each place, and the row under the cursor is the only
        thing that says which flow is meant. Kept as the whole id -- where it came from and
        which flow it is -- so that a row remembered under one place cannot be taken for a
        row of the next.

        Args:
          listing: The list.
        """
        at = listing.highlighted
        if at is None or not 0 <= at < listing.option_count:
            return
        named = str(listing.get_option_at_index(at).id or "")
        if named:
            self._was = named

    def _fitted(self, runs: Sequence[Runs]) -> list[Runs]:
        """One row per agent the flow drives, whatever there was to fill it with.

        A place nothing was remembered for and nothing falls back on still has a row here:
        this is the page it is set up on, and a place with no row is a place nobody can
        answer. What such a row says is that it has not been answered yet.

        Args:
          runs: What there is, in the order the flow takes them.

        Returns:
          One apiece, padded with an agent that names nothing.
        """
        return [
            runs[at] if at < len(runs) else Runs("") for at in range(len(self._places))
        ]

    def _held(self, name: str) -> dict[str, Any]:
        """What one flow was last set up with here, which is nothing for one never run."""
        held = self._kept.get(name)
        return cast("dict[str, Any]", held) if isinstance(held, dict) else {}

    def _remembered(self, name: str) -> list[Runs]:
        """What one flow's agents were last set up as here, in the order it takes them.

        Args:
          name: The flow.

        Returns:
          One apiece, and nothing at all for a flow this workspace has never run -- which is
          a flow whose agents fall back on the one the interface opens talking to.
        """
        from .settings import read_back

        agents: dict[str, Any] = self._held(name).get("agents") or {}
        return [
            runs
            for runs in (
                read_back(cast("dict[str, Any]", one))
                for one in agents.values()
                if isinstance(one, dict)
            )
            if runs is not None
        ]

    def _ask(self) -> None:
        """Says what the menu is, puts up the page it opened on, and catches up on fetches."""
        self.query_one("#asked", Label).update("Flow")
        self._fill()
        self.query_one("#choices", OptionList).focus()
        self._catches_up()

    @work
    async def _catches_up(self) -> None:
        """Fetches whatever has never been fetched, as the menu opens.

        A flowverse that is here and has never been fetched is a list with nothing in it and
        a key to press about it, which is a step nobody would choose to take: it is here
        because its flows are wanted. humanize's own repository of the rest is the one this
        is ever true of -- one that was added was cloned as it was added -- and it is the one
        every flow that is not in the package is in.

        Off the loop and out of the way: the menu is drawn first and stays drawn, what is
        being read is left where it is, and a fetch that fails says so under the list. Once
        per opening, however it goes, so that a machine with no network says so once rather
        than hammering a server on every keystroke.
        """
        from hmz.flows import flowverses
        from hmz.flows.verses import fetch

        for one in flowverses():
            if not one.url or one.fetched:
                continue
            name = one.name

            def fetching(named: str = name) -> str:
                fetch(named)
                return named

            await self._fetches(name, fetching, reading=False)

    def _turned(self) -> None:
        """Puts the cursor back on the flow being read when the flows page opens again."""
        self._said = ""

    def _fill(self) -> None:
        """Puts up whichever page is open, and the titles above it."""
        self.query_one("#about", Label).update(
            "Which flow the agents are driven through. The first thing you say once it is "
            "chosen is what it is to do. A flow anywhere else is a path you type."
            if self._tab == _FLOW_PAGE
            else f"What each agent {escape(self._flow)} drives is: the CLI that takes its "
            "turns, the account they run as, the model at an effort, and what it may do. "
            "Enter opens one. Nothing lands until this menu is saved on the way out."
        )
        if self._tab != _FLOW_PAGE:
            self.tabbed(self._tab_line())
            self._agents_page()
            return
        # The places under the pages, since that is what the list under them is one of: which
        # is settled before either is drawn, so that the strip and the list agree.
        wheres = self._stepping()
        if self._where not in wheres:
            self._where = self._opens(wheres)
        self.tabbed(f"{self._tab_line()}\n{self._where_line(wheres)}")
        self._flows_page()

    def _all(self) -> list[Offer]:
        """Every flow there is, read once."""
        from hmz.flows import found

        if self._offers is None:
            self._offers = found()
        return self._offers

    def _wheres(self) -> list[str]:
        """The places flows come from, in the order the arrows step through them.

        Returns:
          Every flowverse there is, fetched or not, and then this project's flows and yours
          where there are any. A flowverse is one of them whether or not it has been
          downloaded -- fetching it is what having it here is for -- but your own directories
          are not places to add anything to, so an empty one is nothing to step to.
        """
        from hmz.flows import flowverses, where

        verses = [one.name for one in flowverses()]
        return verses + [
            whose
            for whose, _ in where
            if whose not in verses and any(one.whose == whose for one in self._all())
        ]

    def _stepping(self) -> list[str]:
        """The places there are to step between, which a search narrows to the ones it found.

        Returns:
          Every place while nothing is typed. While something is, only the places holding a
          flow that matches it -- a search is for finding a flow whose flowverse is the thing
          nobody remembers, so it MUST NOT leave somebody stepping through empty lists to
          reach the one row it found. All of them again where it found nothing anywhere,
          there being no narrower list to offer than the one that is already empty.
        """
        wheres = self._wheres()
        if not self._typed:
            return wheres
        found = [
            whose
            for whose in wheres
            if any(one.whose == whose and self.fits(one.name) for one in self._all())
        ]
        return found or wheres

    def _opens(self, wheres: list[str]) -> str:
        """Which place is read when the page is drawn without one already being read.

        Args:
          wheres: The places there are to step between.

        Returns:
          The one the flow in force came from, that being the flow this page is about, and
          otherwise the first there is.
        """
        return next(
            (
                one.whose
                for one in self._all()
                if one.name == self._flow and one.whose in wheres
            ),
            wheres[0] if wheres else "",
        )

    def _where_line(self, wheres: list[str]) -> str:
        """The places flows come from, with the one being read marked and the keys said.

        Args:
          wheres: The places, in the order the arrows step through them.

        Returns:
          The strip, as markup. Every place, so that the one being read is read as one of
          however many there are: a flowverse nobody can see is a flowverse nobody steps to.
        """
        said = _DOT.join(
            f"[b $primary]{escape(one)}[/]"
            if one == self._where
            else f"[$text-muted]{escape(one)}[/]"
            for one in wheres
        )
        if len(wheres) > 1:
            said += f"   [$text-muted]{_STEPS}[/]"
        return said

    def _verse(self, named: str) -> Flowverse | None:
        """The flowverse of that name, or None for one of your own directories."""
        from hmz.flows import flowverses

        return next((one for one in flowverses() if one.name == named), None)

    def _whose(self) -> str:
        """Which place the keys of this page are about, which is the one being read.

        The place rather than whatever row the cursor happens to be on: a flowverse with
        nothing in it is a list with no rows to be on, and fetching it is exactly what
        somebody looking at it came to do.
        """
        return self._where

    def action_before(self) -> None:
        """Reads the place before this one."""
        self._steps(-1)

    def action_after(self) -> None:
        """Reads the one after it."""
        self._steps(1)

    def _steps(self, by: int) -> None:
        """Turns to another of the places flows come from, wrapping round at either end.

        Args:
          by: One place on or back.
        """
        if self._tab != _FLOW_PAGE:
            return  # the agents of one flow come from nowhere but that flow
        wheres = self._stepping()
        if len(wheres) < 2:  # noqa: PLR2004 -- one place is nowhere to step to
            return
        at = wheres.index(self._where) if self._where in wheres else 0
        self._where = wheres[(at + by) % len(wheres)]
        # What a key was armed against and what a fetch had to say were both about the place
        # being stepped off, and neither is about the one being stepped on to.
        self._was, self._arming, self._said = "", "", ""
        self._fill()

    def _flows_page(self) -> None:
        """Puts up the flows of the place being read, and nothing from any other place."""
        listing = self.query_one("#choices", OptionList)
        self._follows(listing)
        mine = [
            one
            for one in self._all()
            if one.whose == self._where and self.fits(one.name)
        ]
        self._counting = len(str(max(len(mine), 1)))
        held = [f"{self._where}{_HALVES}{one.name}" for one in mine]
        if not held and not self._typed:
            # A place with nothing in it, which for a flowverse is what having it here is
            # for: an empty list that explained nothing would read as one with no flows.
            held = [f"{self._where}{_HALVES}"]
        if self._was not in held:
            # Stepped on to, narrowed away, or never there: the cursor lands on the flow in
            # force, or on the first row, and an empty list has nothing to be on at all.
            self._was = next(
                (one for one in held if one.partition(_HALVES)[2] == self._flow),
                held[0] if held else "",
            )
        rows = [
            Option(
                self._row(
                    at,
                    one.name,
                    _briefly(one.about, self.size.width),
                    here=held[at] == self._was,
                    inforce=one.name == self._flow,
                ),
                id=held[at],
            )
            for at, one in enumerate(mine)
        ]
        if not rows and held:
            rows = [
                Option(
                    f"{_INDENT}  [$text-muted]{self._empty(self._where)}[/]", id=held[0]
                )
            ]
        listing.set_options(rows)
        listing.highlighted = held.index(self._was) if self._was in held else None
        self._drawn = listing.highlighted
        said = self._nothing()
        self.query_one("#tuning", Label).update(
            f"[$text-muted]{said}[/]" if said else ""
        )
        self.query_one("#keys", Label).update(
            "Enter to choose · a adds a flowverse · r fetches one · d twice takes one away · "
            f"Esc to close{self.searching()}"
        )

    def _empty(self, whose: str) -> str:
        """What a place with no flows in it says on the row where its flows would be."""
        verse = self._verse(whose)
        if verse is not None and not verse.fetched:
            return "not fetched yet; r fetches it"
        return "nothing in it yet"

    def _nothing(self) -> str:
        """What to say under the flows: how a fetch went, or that a search found nothing."""
        if self._fetching:
            return f"fetching {escape(self._fetching)}…"
        if self._said:
            return self._said
        if self._typed and not any(self.fits(one.name) for one in self._all()):
            return "no flow of that name"
        return ""

    def _agents_page(self) -> None:
        """Puts up one row per agent the flow drives, and what each of them is now."""
        listing = self.query_one("#choices", OptionList)
        named = tuple(place.name for place in self._places)
        lines = reads(named, self._runs)
        self._counting = len(str(max(len(self._places), 1)))
        at = min(listing.highlighted or 0, max(len(self._places) - 1, 0))
        listing.set_options(
            Option(
                self._row(
                    seen,
                    called(self._places, seen),
                    lines[seen].split(_DOT, 1)[-1]
                    if self._runs[seen].spec
                    else "not chosen yet",
                    here=seen == at,
                    inforce=False,
                ),
                id=f"={seen}",
            )
            for seen in range(len(self._places))
        )
        listing.highlighted = at if self._places else None
        self._drawn = listing.highlighted
        said = self._said or ("" if self._places else self._noagents())
        self.query_one("#tuning", Label).update(
            f"[$text-muted]{said}[/]" if said else ""
        )
        self.query_one("#keys", Label).update("Enter to set one up · Esc to close")

    def _noagents(self) -> str:
        """Why there is no agent to set up, which is not always the same reason."""
        if places_of(self._flow) is None:
            return f"{escape(self._flow)} will not load; nothing here can be set up"
        return f"{escape(self._flow)} drives no agents; it talks only to you"

    @work
    async def _configures(self) -> None:
        """Asks what the flow itself takes, and turns to what will drive it.

        Which is the moment to ask it: a flow that takes settings has just been chosen, and
        what it is set up with is a thing about the flow rather than about its agents. A flow
        that takes none is not asked -- a sheet with nothing on it is not a question -- and
        the walk is the same either way, so nobody has to know which kind they picked.
        """
        model = model_of(self._flow)
        if model is not None:
            showing = cast(
                "App[None]",
                self.app,  # pyright: ignore[reportUnknownMemberType]
            )
            held = await showing.push_screen_wait(
                Configures(
                    self._flow,
                    model,
                    self._config if isinstance(self._config, model) else None,
                )
            )
            if held is not None:
                self._config = held
                self.changed()
            # And walking out of it leaves the flow set up as the draft has it, which is
            # still a flow to go on and answer the agents of.
        self._said = ""
        self._turn_page(1)

    @work
    async def action_adding(self) -> None:
        """Adds a flowverse without leaving the question it was going to be chosen from."""
        if self._tab != _FLOW_PAGE:
            return
        showing = cast(
            "App[None]",
            self.app,  # pyright: ignore[reportUnknownMemberType]
        )
        said = await showing.push_screen_wait(Fetches())
        if said is None:
            return
        url, name = said
        await self._fetches(name or url, lambda: _added(url, name))

    @work
    async def action_refresh(self) -> None:
        """Fetches the flowverse under the cursor again, or for the first time."""
        from hmz.flows.verses import fetch

        if self._tab != _FLOW_PAGE:
            return
        verse = self._verse(self._whose())
        if verse is None:
            self._said = (
                f"{escape(self._whose())} is a directory of your own, not a fetch"
            )
            self._fill()
            return
        if not verse.url:
            self._said = (
                f"{escape(verse.name)} came with humanize; there is nothing to fetch"
            )
            self._fill()
            return
        name = verse.name

        def fetching() -> str:
            fetch(name)
            return name

        await self._fetches(name, fetching)

    def action_drop(self) -> None:
        """Takes the flowverse being read away, flows and all, once d is pressed twice."""
        from hmz.flows.verses import remove

        if self._tab != _FLOW_PAGE:
            return
        whose = self._whose()
        verse = self._verse(whose)
        if verse is None:
            return  # a directory of your own is not one of these to take away
        if not self._armed(whose):
            self._said = f"press d again to take {escape(whose)} away, flows and all"
            self._fill()
            return
        try:
            remove(verse.name)
        except (OSError, ValueError) as why:
            self._said = escape(str(why))
            self._fill()
            return
        # The place that was being read has gone, so the page reads whichever place the flow
        # in force came from, exactly as it did when it opened.
        self._offers, self._where, self._was = None, "", ""
        self._said = f"{escape(verse.name)} is no longer here"
        self._fill()

    async def _fetches(
        self, named: str, doing: Callable[[], str], *, reading: bool = True
    ) -> None:
        """Runs one git fetch off the event loop, and shows the list it left behind.

        Off the loop because a clone is seconds of network: an interface that stopped
        redrawing while it ran would be one that looked as though it had gone away.

        Args:
          named: What is being fetched, said under the list while it runs. What is being
            fetched rather than what is being read: they are the same for the key that
            fetches one and different for every other way of getting here.
          doing: What to do, answering with the flowverse it left behind.
          reading: Whether to read what was fetched afterwards. What somebody asked for is
            what they want to see; what was fetched because it never had been is not
            something to move anybody off the list they opened the menu on.
        """
        import asyncio

        if self._fetching:
            return
        self._fetching, self._said = named or "it", ""
        self._fill()
        try:
            name = await asyncio.to_thread(doing)
        except (OSError, ValueError) as why:
            # Said under the list rather than raised at whoever opened the menu: the question
            # this page is asking is still worth answering.
            self._said = escape(str(why))
            self._fetching = ""
            self._fill()
            return
        self._fetching, self._offers = "", None
        # Reading what was just fetched, on the first flow it brought: that list is what
        # somebody who fetched it fetched it to see, and one that was added is not a place
        # anybody has stepped to yet.
        first = next((one for one in self._all() if one.whose == name), None)
        if reading and first is not None:
            self._where, self._was = name, f"{name}{_HALVES}{first.name}"
        self._fill()

    @on(OptionList.OptionSelected)
    def _took(self, event: OptionList.OptionSelected) -> None:
        """Chooses the flow under the cursor, or opens the agent under it.

        Args:
          event: What was chosen.
        """
        if self._tab == _FLOW_PAGE:
            _, _, name = str(event.option.id or "").partition(_HALVES)
            if name:
                self._chose(name)
            return
        self._configuring(int(str(event.option.id or "=0").removeprefix("=")))

    def _chose(self, name: str) -> None:
        """Takes a flow as the one to run, and reads back what it was last set up with.

        Nothing is written down: what the menu holds is a draft, and a flow chosen and then
        walked away from must leave the interface exactly as ready as it was.

        Args:
          name: The flow, by the name it was offered under.
        """
        if name != self._flow:
            places = places_of(name)
            if places is None:
                self._said = f"{escape(name)} will not load"
                self._fill()
                return
            self._flow, self._places = name, places
            self._runs = self._fitted(
                settled(self._remembered(name), places, self._agents)
            )
            self._config = config_of(name, self._held(name).get("config") or {})
            self.changed()
        # On to what the flow itself takes, where it takes anything, and then to what will
        # drive it: three things about one flow, asked in the order they depend on nothing.
        self._configures()

    @work
    async def _configuring(self, at: int) -> None:
        """Opens one agent of the flow, and holds whatever comes back as a draft.

        Args:
          at: Which of them, counting from zero.
        """
        if not 0 <= at < len(self._places):
            return
        showing = cast(
            "App[None]",
            self.app,  # pyright: ignore[reportUnknownMemberType]
        )
        chosen = await showing.push_screen_wait(
            Agent(
                called(self._places, at),
                self._runs[at],
                self._agents,
                place=self._places[at],
                unavailable=self._unavailable,
            )
        )
        if chosen is None:
            return  # walked out of it, which leaves that agent as the draft has it
        self._runs[at] = chosen.runs
        self.changed()
        self._fill()

    def applied(self) -> None:
        """Answers with the flow, its agents and how it is set up, all of it at once.

        Unless one of them has not been answered: a flow driven by an agent that names no
        model is a flow that stops on its first turn, and the page it would be answered on is
        the page to be looking at when that is said.
        """
        missing = [
            called(self._places, at)
            for at, one in enumerate(self._runs)
            if not _complete(one)
        ]
        if missing:
            self._tab = _AGENT_PAGE
            self._said = f"{escape(', '.join(missing))} has no model yet"
            self._fill()
            return
        self.dismiss(Chosen(self._flow, tuple(self._runs), self._config))


def _added(url: str, name: str) -> str:
    """Fetches a flowverse and answers with what it is called here."""
    from hmz.flows.verses import add

    return add(url, name).name


def _written(
    at: int, counting: int, named: str, about: str, shown: str, *, here: bool
) -> str:
    """One row that is written into rather than picked between.

    Args:
      at: Which one it is, counting from zero.
      counting: How wide the numbering is, so every row starts in the same column.
      named: What the answer is kept under.
      about: What is being asked, said quietly beside it.
      shown: What has been typed, as it is to be shown.
      here: Whether the cursor is on it.

    Returns:
      The row, as markup.
    """
    mark = f"{_INDENT}[$primary]{_HERE}[/] " if here else f"{_INDENT}  "
    number = f"{at + 1:>{counting}}."
    # A block where the next letter goes, as the settings of a flow draw one: every row here
    # is written into, so every one of them has somewhere the next letter lands.
    caret = "[reverse] [/reverse]" if here else ""
    # Padded on what is shown rather than on what is written: markup is not columns.
    label = escape(named) + " " * max(1, _SETTING - len(named))
    room = _VALUE - len(shown) - 1
    return (
        f"{mark}[$text-muted]{number}[/] {label}"
        f"[$secondary]{escape(shown)}[/]{caret}{' ' * max(1, room)}"
        f"[$text-muted]{escape(about)}[/]"
    )


def _briefly(said: str, width: int) -> str:
    """One flow's line about itself, clipped to the room the row has for it.

    Args:
      said: The line, which is the first line of what the flow says about itself and so is
        as long as that sentence is.
      width: How wide the sheet is.

    Returns:
      As much of it as fits beside the name, ending in an ellipsis where it was cut.
    """
    room = max(width - len(_INDENT) - _LABEL - 8, 20)
    return said if len(said) <= room else f"{said[: room - 1].rstrip()}…"


class Fetches(Sheet[tuple[str, str]]):
    """Where a flowverse is, and what it is to be called here.

    A form rather than a list, as signing in to an account is: there is nothing to pick, both
    rows being written where they stand.
    """

    BINDINGS: ClassVar = [
        ("escape", "back", "back"),
        Binding("enter", "done", "done", priority=True),
    ]

    #: What to ask for, and what the answer means. The name is second because it is the one
    #: with an answer already: a flowverse is called what its repository is called.
    _ASKS = (
        ("repository", "a URL, or owner/repo for one on GitHub"),
        ("name", "what to call it here, blank for the repository's own name"),
    )

    def __init__(self) -> None:
        """Initializes the asking."""
        super().__init__()
        self._counting = len(str(len(self._ASKS)))
        self._typed_in: dict[str, str] = {}
        #: What was still missing, once the form has been offered.
        self._wrong = ""

    def _ask(self) -> None:
        """Says what a flowverse is, and what the keys do while it is being named."""
        self.query_one("#asked", Label).update("Add a flowverse")
        self.query_one("#about", Label).update(
            "A git repository with a `flows/` directory in it: one `.py` file per flow, and "
            "whatever they import beside them. It is cloned into ~/.humanize/flowverses, and "
            "every flow in it is then offered under the name it is kept under."
        )
        self._fill()
        self.query_one("#choices", OptionList).focus()

    def _fill(self) -> None:
        """Puts the two rows up, with the caret in the one under the cursor."""
        listing = self.query_one("#choices", OptionList)
        at = self._at
        listing.set_options(
            Option(
                _written(
                    seen,
                    self._counting,
                    held,
                    about,
                    self._typed_in.get(held, ""),
                    here=seen == at,
                ),
                id=f"={held}",
            )
            for seen, (held, about) in enumerate(self._ASKS)
        )
        listing.highlighted = at
        self._drawn = at
        self.query_one("#tuning", Label).update(
            f"[$error]{escape(self._wrong)}[/]" if self._wrong else ""
        )
        self.query_one("#keys", Label).update(
            "Type to answer · Backspace to rub out · Enter to fetch it · Esc to go back"
        )

    @property
    def _at(self) -> int:
        """Which row the cursor is on, counting from zero."""
        listing = self.query_one("#choices", OptionList)
        return min(listing.highlighted or 0, len(self._ASKS) - 1)

    def on_key(self, event: events.Key) -> None:
        """Takes a letter as answering the row under the cursor.

        Args:
          event: The key.
        """
        held = self._ASKS[self._at][0]
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
        """Answers with where it is and what to call it, once there is somewhere to fetch."""
        from hmz.flows.verses import where as kept

        url = self._typed_in.get("repository", "").strip()
        name = self._typed_in.get("name", "").strip()
        if not url:
            self._wrong = "a flowverse is a repository, and none was named"
            self._fill()
            return
        if name:
            try:
                kept(name)
            except ValueError as why:
                self._wrong = str(why)
                self._fill()
                return
        self.dismiss((url, name))


class Speaks(Sheet[tuple[str, str]]):
    """A CLI of your own that speaks the Agent Client Protocol, and what starts it.

    A form rather than a list, as adding a flowverse is: there is nothing to pick, both rows
    being written where they stand. Two questions because the protocol answers neither -- it
    has no discovery and no flag every agent agrees on -- so the command is asked for, and the
    name it is to be known by here is asked for beside it.
    """

    BINDINGS: ClassVar = [
        ("escape", "back", "back"),
        Binding("enter", "done", "done", priority=True),
    ]

    #: What to ask for, and what the answer means. The command first, since the name has an
    #: answer already: a CLI is called what it is installed as.
    _ASKS = (
        ("command", "what starts it, as you would type it: my-agent --acp"),
        ("name", "what to call it here, blank for the command's own name"),
    )

    def __init__(self) -> None:
        """Initializes the asking."""
        super().__init__()
        self._counting = len(str(len(self._ASKS)))
        self._typed_in: dict[str, str] = {}
        #: What was still missing, once the form has been offered.
        self._wrong = ""

    def _ask(self) -> None:
        """Says what one of these is, and what the keys do while it is being named."""
        self.query_one("#asked", Label).update("Add a CLI that speaks ACP")
        self.query_one("#about", Label).update(
            "Any coding agent that speaks the Agent Client Protocol can be driven from here. "
            "humanize spawns the command you give and talks to it over its own stdin and "
            "stdout. The protocol says nothing about which models it runs or how hard it can "
            "be asked to think, so it runs as whoever installed it configured it."
        )
        self._fill()
        self.query_one("#choices", OptionList).focus()

    def _fill(self) -> None:
        """Puts the two rows up, with the caret in the one under the cursor."""
        listing = self.query_one("#choices", OptionList)
        at = self._at
        listing.set_options(
            Option(
                _written(
                    seen,
                    self._counting,
                    held,
                    about,
                    self._typed_in.get(held, ""),
                    here=seen == at,
                ),
                id=f"={held}",
            )
            for seen, (held, about) in enumerate(self._ASKS)
        )
        listing.highlighted = at
        self._drawn = at
        self.query_one("#tuning", Label).update(
            f"[$error]{escape(self._wrong)}[/]" if self._wrong else ""
        )
        self.query_one("#keys", Label).update(
            "Type to answer · Backspace to rub out · Enter to add it · Esc to go back"
        )

    @property
    def _at(self) -> int:
        """Which row the cursor is on, counting from zero."""
        listing = self.query_one("#choices", OptionList)
        return min(listing.highlighted or 0, len(self._ASKS) - 1)

    def on_key(self, event: events.Key) -> None:
        """Takes a letter as answering the row under the cursor.

        Args:
          event: The key.
        """
        held = self._ASKS[self._at][0]
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
        """Answers with the command and the name, once there is something to start."""
        said = self._typed_in.get("command", "").strip()
        name = self._typed_in.get("name", "").strip()
        if not said:
            self._wrong = "nothing was given to start it with"
            self._fill()
            return
        try:
            argv = shlex.split(said)
        except ValueError as why:  # an unbalanced quote is a line to correct
            self._wrong = str(why)
            self._fill()
            return
        if not argv:
            self._wrong = "nothing was given to start it with"
            self._fill()
            return
        self.dismiss((said, name or Path(argv[0]).name))


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

    LETTERS: ClassVar = frozenset({"search"})

    BINDINGS: ClassVar = [
        ("escape", "back", "back"),
        Binding("s", "search", "search", priority=True),
        # Space is what a checklist is switched with, so it is what this one is switched
        # with, search or no search: a skill is named after the directory it is in, so a
        # space is never something anybody is trying to type into one.
        Binding("space", "switch", "switch this one", priority=True),
        # Enter is the whole sheet rather than the row under the cursor, as it is where a
        # sheet is adjusted rather than picked from: the rows are switched where they stand.
        # Not a letter, so it accepts the sheet while a search is running too.
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
            "Space to switch on and off · Enter to accept · Esc to go back"
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

    A row of the sheet one agent is set up on, and only for a place the flow declared
    `Remote`: a flow that says so is one that expects to be told where that agent works, and
    one that said nothing has said its agent works here.

    The agent itself runs here whatever is chosen -- its credentials, its state directory and
    its link to its model provider stay put. What moves is the project it reads and the
    commands it runs, which is why this is a question about the agent rather than about the
    flow: two agents of one flow may work on two machines.

    Listed rather than typed where the machine is one this one can see -- a container that is
    running, a host with an entry in the ssh config -- and typed where it is not: a target is
    a string, and the row for what has been typed appears among them, as soon as it reads as
    one, while a search is running.
    """

    LETTERS: ClassVar = frozenset({"search"})

    BINDINGS: ClassVar = [
        ("escape", "back", "back"),
        Binding("s", "search", "search", priority=True),
    ]

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
            f"Enter to choose · s then a target names one of your own{self.searching()}"
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


def _flowing(started: str) -> list[str]:
    """Which flow is running, and inside which, for the row that names one.

    A flow may reach for another by name and run it, so the flow a run is in is not always
    the flow that was started -- and a sheet that named only the one somebody chose would be
    a sheet that stopped being true the moment a flow called another.

    Args:
      started: The flow that was chosen, which is what this says with nothing running.

    Returns:
      One line apiece, the one that was started first and whatever it called under it, each
      with how long it has been going; and just the one that is set up to run where nothing
      is running.
    """
    from hmz.runner import running

    now = running()
    if not now:
        return [escape(started)]
    return [
        f"{'  ' * at}{'▸ ' if at else ''}{escape(one.flow)}"
        f"   [$text-muted]{time.monotonic() - one.since:.0f}s[/]"
        for at, one in enumerate(now)
    ]


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

    LETTERS: ClassVar = frozenset({"search"})

    BINDINGS: ClassVar = [
        ("escape", "back", "back"),
        # A list is read before it is searched, so searching is asked for: every letter here
        # is otherwise a key, and a list where typing always searched would have none.
        Binding("s", "search", "search", priority=True),
    ]

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
            f"{self.keys}Enter to choose · Esc to cancel{self.searching()}"
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


def _drives(backend: str) -> type[AgentBase] | None:
    """What drives one backend, or None for a name nothing here drives.

    A CLI somebody added themselves is driven too -- by the one class that speaks the Agent
    Client Protocol -- so this asks what would build it rather than reading one table.

    Args:
      backend: The backend, by name.

    Returns:
      The agent class, or None.
    """
    try:
        return driver(backend)[0]
    except KeyError:
        return None


def _installing(backend: str) -> str:
    """The command that adds an optional backend to this Python environment."""
    if backend != "dsh":
        return f"install {backend}, then reopen humanize"
    executable = str(Path(sys.executable).absolute())
    command = (
        f"uv pip install --python {shlex.quote(executable)} "
        "'deepseek-harness-sdk>=0.1.0rc6,<0.2'"
    )
    return f"DeepSeek Harness is not installed; run: {command}; then reopen hmz"


class Made(NamedTuple):
    """What making an account came to.

    Attributes:
      provider: The account written down, or None where the walk was left without making one.
      status: What the way's own command exited with, or 0 for a way that runs nothing and
        for one nobody got as far as running.
      why: What went wrong before anything was written down, or "" where nothing did.
      way_runs: Whether the way had a command of its own, which is what tells an account that
        was signed in from one that was only written down.
      runs: How many models its CLI said it runs as this account, asked as soon as the account
        landed. Zero for one that was never got as far as asking, and for one whose CLI would
        not say -- which is not an account that cannot be used, only one whose models have to
        be asked for again before there are any to choose from.
    """

    provider: Provider | None = None
    status: int = 0
    why: str = ""
    way_runs: bool = False
    runs: int = 0


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
    from hmz.providers import login as signing

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
        return Made(provider=provider, runs=await asks(cli, provider.name))
    # A login is a browser opened, a code read out, a token exchanged: it owns the screen
    # while it runs, and there is nothing for an interface to draw over it.
    with handed_over(host):
        status = signing.sign_in(provider, way, signs.answers)
    return Made(
        provider=provider,
        status=status,
        way_runs=True,
        # An account whose way in exited badly has nothing to say about what it runs, and
        # asking it would only be a second way of finding that out.
        runs=0 if status else await asks(cli, provider.name),
    )


async def asks(cli: str, name: str) -> int:
    """Asks a new account's CLI what it runs, so that there is a list when one is asked for.

    Here rather than where an account is written down: what a backend runs is that account's
    and is found by starting that backend, which is a thing to do once an account exists and
    not a thing the store of them should be doing at all.

    Off the event loop, because it is a coding agent starting up.

    Args:
      cli: The backend the account is for.
      name: What the account is called.

    Returns:
      How many models it said it runs, and zero where it would not say -- which is a list to
      ask for again rather than an account that will not work.
    """
    import asyncio

    from hmz import models

    try:
        return len(await asyncio.to_thread(models.ask, cli, name))
    except Exception:  # noqa: BLE001 -- a CLI that will not say is one to ask again later
        return 0


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
        from hmz.backends import profiles
        from hmz.providers import ways

        return [
            (
                profile.name,
                profile.name,
                ", ".join(way.name for way in ways(profile.name)),
            )
            for profile in profiles()
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
        from hmz.providers import ways

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
_TYPED_ABOUT = (
    "the variables, as NAME=VALUE, one per line -- shift+enter breaks the line"
)

#: What breaks a line where enter means something else, which is everywhere here. Two of
#: them: a terminal reports shift+enter as itself only where it speaks a keyboard protocol
#: that has a way to say so, and `ctrl+j` is a line feed and arrives from anywhere.
_BREAKS = ("shift+enter", "ctrl+j")


class Signing(Sheet[Signs]):
    """What a way in has to be told before an account can be made out of it.

    A form rather than a list, so it is drawn as the settings of a flow are: one row per
    question, the variable the answer becomes, what has been typed into it, and the question
    said quietly beside it. What the backend called a secret is drawn as bullets and never
    shown back --
    it is on its way into a credential store, and a screen is somewhere it can be read off.
    """

    BINDINGS: ClassVar = [
        ("escape", "back", "back"),
        # Enter is the whole form rather than the row under the cursor: there is nothing here
        # to pick, every row being written where it stands.
        Binding("enter", "done", "done", priority=True),
    ]

    def __init__(
        self,
        cli: str,
        way: Way,
        name: str = "",
        held: Mapping[str, str] | None = None,
    ) -> None:
        """Initializes the answering.

        Args:
          cli: The backend this account is for.
          way: The way in it is being made by, whose questions these are.
          name: What it is called already, for one being signed in again -- a name it has is
            not a name to ask for twice -- or "" to ask for one.
          held: What that account holds now, for one being corrected rather than made. A
            secret among them is not read back on to the screen: it is on its way into a
            credential store, and a screen is somewhere it can be read off. So a corrected
            account is one whose secrets are typed again, which is what correcting one is.
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
        #: is asked: a region that is usually right is an answer rather than a blank. And then
        #: from what the account being corrected holds, less its secrets -- which is what
        #: makes correcting one a matter of the row that is wrong rather than all of them.
        asked = {one.env: one for one in way.asks}
        self._typed_in: dict[str, str] = (
            {_CALLED: name}
            | {one.env: one.fixed for one in way.asks}
            | {
                where: value
                for where, value in (held or {}).items()
                # Only what may be read back: the row for a secret starts empty, since
                # nothing here reads one off the store to draw it as bullets nobody can
                # correct. A secret is typed again or it is left as it was.
                if where in asked and not asked[where].secret
            }
        )
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
        # A bullet per character for a secret: how much has been typed is worth seeing, and
        # what it was is worth seeing once, on the way in, by the one typing it.
        value = self._typed_in.get(held, "")
        shown = "•" * len(value) if secret else value
        return _written(at, self._counting, held or "name", about, shown, here=here)

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
        elif event.key in _BREAKS and held == _TYPED:
            # The one row that takes a list rather than a value: several variables, a line
            # each, which is why it is the one row a line can be broken in.
            self._typed_in[held] = self._typed_in.get(held, "") + "\n"
        elif event.is_printable and event.character:
            self._typed_in[held] = self._typed_in.get(held, "") + event.character
        else:
            return
        event.prevent_default()
        event.stop()
        self._wrong = ""
        self._fill()

    def on_paste(self, event: events.Paste) -> None:
        """Pastes an answer into the question under the cursor."""
        if not self._fields or not event.text:
            event.stop()
            return
        held = self._fields[self._at][0]
        pasted = event.text.replace("\r\n", "\n").replace("\r", "\n")
        if held != _TYPED:
            # A clipboard commonly ends in a newline. Single-value fields follow
            # Textual Input and take one line; only the free-form env row is multiline.
            pasted = pasted.split("\n", 1)[0]
        self._typed_in[held] = self._typed_in.get(held, "") + pasted
        event.stop()
        self._wrong = ""
        self._fill()

    def action_done(self) -> None:
        """Answers with what it is to be called and what its way was told, once that is all.

        What is missing is said where it was typed rather than raised at whoever opened the
        sheet: a question left blank is a question to answer, and this is where answering it
        happens.
        """
        from hmz.providers import env_of, where
        from hmz.providers.login import asked

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


class Confirms(Picks):
    """Whether to keep what a menu is holding, asked as it is walked out of.

    A menu applies nothing until it is left, so leaving one is the moment the changes in it
    either land or do not. Asked rather than assumed either way: what was changed took typing
    to change, and throwing it away silently is worse than one more question.

    Drawn as a box in the middle of the screen rather than as a sheet, because it is not one:
    a sheet is a question somebody walked to, and this is one that arrived over the menu they
    were walking out of. Two answers, since the third -- going back to the menu -- is what esc
    already is everywhere else, and an answer that is also a key is a row that says the key is
    not there.
    """

    CSS = _POPUP

    asked = "Save what was changed?"
    about = "Nothing in this menu has been applied yet."

    def rows(self) -> list[tuple[str, str, str]]:
        """The two things there are to do about a menu holding changes."""
        return [
            (_KEEP, "save and close", "write it down and apply it"),
            (_DROP, "discard and close", "leave everything as it was"),
        ]

    def check_action(
        self,
        action: str,
        parameters: tuple[object, ...],
    ) -> bool | None:
        """Whether one of the keys is live, which a question of two answers narrows.

        Args:
          action: What the key would do.
          parameters: What it would do it with.

        Returns:
          Whether to run it. Never the search: two rows are read rather than narrowed, and a
          box in the middle of the screen has no room to say what was typed into one.
        """
        return action != "search" and super().check_action(action, parameters)

    def _fill(self) -> None:
        """Puts the two answers up, and says what esc is here.

        Esc is the third answer -- back to the menu, changing nothing -- so it says so. Every
        other sheet leaves on it, and one that said `cancel` over a menu holding changes would
        read as the one thing it is not.
        """
        super()._fill()
        self.query_one("#keys", Label).update(
            "Enter to choose · Esc to go back to the menu"
        )


class Fitted(NamedTuple):
    """One agent as a sheet answered with it: what it is, and what it is called.

    Attributes:
      runs: The agent itself.
      name: What it is saved under, for one being edited in the agents menu, and "" for one
        of a flow's -- an agent of a flow is called what the flow calls it, which is not
        something anybody here may rename.
    """

    runs: Runs
    name: str = ""


#: How wide the column of aspect names is on the sheet one agent is set up on, and the column
#: of their values, so that it reads down three columns: what is being said, what it is, and
#: what it means. Wide enough for a model id, which is the longest of them by a distance.
_ASPECT = 12
_HOW = 34

#: What a switch on that sheet reads as.
_YES, _NO = "on", "off"

#: The account an agent runs as when nobody has chosen one, which is always the first row it
#: is chosen from: the machine is signed in already, and that is what an agent nobody was
#: asked about has always run as.
_LOCAL = "as local"

#: The rows the sheet is made of, by the id each is put up under. In the order they are asked,
#: which is the order of what depends on what: the CLI settles which accounts and which models
#: there are, and the account settles which models that CLI will name.
_IMPORT = "import"
_NAME = "name"
_CLI = "cli"
_ACCOUNT = "provider"
_MODEL = "model"
_EFFORT = "effort"
_SWARM = "swarm"
_SKILLS = "skills"
_PERMIT = "permission"
_GOALS = "goals"
_WHERE = "where"
_SAVE = "save"

#: Which of them are stepped along where they stand rather than opened, and which are opened.
_STEPPED = (_EFFORT, _SWARM, _PERMIT, _GOALS)


class Agent(Drafts[Fitted]):
    """Everything one agent is, on one sheet, each row opened or stepped where it stands.

    Which is the walk of three sheets that used to ask it, folded into the thing it was asking
    about. An agent is not three questions -- it is one thing with a CLI, an account, a model
    at an effort, a set of skills, a rung of what it may do and a machine its work lands on --
    and asking it as a walk meant that changing the effort of an agent already set up was four
    keypresses through two sheets that had nothing to say.

    The order the rows go in is still the order of what depends on what: the CLI settles which
    accounts there are to choose from and which models that CLI will name, and the account
    settles which of them it may name. Changing the CLI therefore lets go of the model, which
    belonged to the CLI before it.

    A saved agent can be copied in at the top and saved out at the bottom. What is imported is
    a copy: an agent tuned inside a flow is that flow's, and writing the changes back into the
    thing it was copied from would change every other flow that had imported it.
    """

    BINDINGS: ClassVar = [
        ("escape", "back", "back"),
        # The two settings that are a step along rather than a list to open: how hard it
        # thinks, and what it may do. Both are a handful of rungs in an order, which is what
        # an arrow is for. Priority, or the list under the cursor would take them as moving
        # between rows it has none of.
        Binding("left", "easier", "back one", priority=True),
        Binding("right", "harder", "on one", priority=True),
    ]

    def __init__(
        self,
        named: str,
        runs: Runs,
        agents: dict[str, tuple[Model, ...]],
        *,
        place: Place | None = None,
        unavailable: frozenset[str] = frozenset(),
        name: str = "",
        naming: bool = False,
    ) -> None:
        """Initializes the sheet on what the agent is now.

        Args:
          named: What to call the agent being set up, which the question at the top says.
          runs: What it is now, which every row reads back.
          agents: The backends offered here, and what each of them says it runs.
          place: What the flow declared about this one, or None for a saved agent -- which
            belongs to no flow and so is asked every question there is.
          unavailable: The optional backends that still need installing.
          name: What it is saved under, for one being edited in the agents menu.
          naming: Whether it has a name of its own to be typed, which a flow's agent has not.
        """
        super().__init__()
        self._named = named
        self._agents = dict(agents)
        self._unavailable = unavailable
        self._place = place
        self._called = name
        self._is_named = naming
        cli, _, rest = runs.spec.partition("/")
        model, _, effort = rest.rpartition(":")
        self._cli, self._model = cli, model
        # `swarm` in front of the effort is how a fleet is written down, so it comes off again
        # before the effort is looked for among the ones the model takes.
        self._swarm = effort.startswith(SWARM)
        self._effort = effort.removeprefix(SWARM)
        self._skills = runs.skills
        self._permission = (
            PERMISSIONS.index(runs.permission)
            if runs.permission in PERMISSIONS
            else len(PERMISSIONS) - 1
        )
        self._provider = runs.provider
        self._goals = True if place is not None and place.goal else runs.goals
        self._anchor = runs.anchor
        #: What the chosen CLI says it runs as the chosen account, read once per pair: this
        #: is redrawn each time the cursor moves, and reading it is reading a file.
        self._catalogue: tuple[Model, ...] | None = None
        self._read_for: tuple[str, str] = ("", "")
        #: What became of asking a CLI what it runs, or of saving this one, said under the
        #: rows rather than raised at whoever opened the sheet.
        self._said = ""

    def _ask(self) -> None:
        """Says whose agent this is, and what setting it up settles."""
        self.query_one("#asked", Label).update(f"Set up {escape(self._named)}")
        self.query_one("#about", Label).update(
            "What this one agent is. Enter opens the row under the cursor, and the arrows "
            "step the ones that are a rung rather than a list. Nothing is applied until this "
            "sheet is left and saving is confirmed."
        )
        self._fill()
        self.query_one("#choices", OptionList).focus()

    def _rows(self) -> list[tuple[str, str, str]]:
        """Every row this agent is made of: its id, what it is now, and what it means.

        Returns:
          One `(id, what it is set to, the line about it)` apiece, in the order they are
          asked. A row nobody is being asked about is not among them: a flow that settled
          where its agent works has not left that question open.
        """
        having = self._skills
        rows: list[tuple[str, str, str]] = []
        if self._is_named:
            rows.append((_NAME, self._called, "what this agent is saved under"))
        if self._place is not None:
            rows.append((_IMPORT, "", "copy a saved agent into this one"))
        rows.extend(
            [
                (_CLI, self._cli or "—", "which coding agent takes its turns"),
                (_ACCOUNT, self._provider or _LOCAL, "the account those turns run as"),
                (_MODEL, self._model or "—", "which of that CLI's models it runs"),
                (_EFFORT, self._effort or "—", "how hard it thinks"),
            ]
        )
        if self._swarms():
            rows.append(
                (_SWARM, _YES if self._swarm else _NO, "one turn run as a fleet")
            )
        rows.extend(
            [
                (
                    _SKILLS,
                    "every skill" if having is None else f"{len(having)} skills",
                    "which of its CLI's skills it is loaded with",
                ),
                (
                    _PERMIT,
                    PERMISSIONS[self._permission],
                    "what it may do without being asked",
                ),
                (
                    _GOALS,
                    _YES if self._goals else _NO,
                    "required by the flow"
                    if self._place is not None and self._place.goal
                    else "whether the backend's own goals are available",
                ),
            ]
        )
        if self._place is None or pointed(self._place):
            rows.append(
                (
                    _WHERE,
                    self._anchor or "this machine",
                    "the machine its work lands on",
                )
            )
        elif image := _settled(self._place):
            rows.append((_WHERE, f"in a container of {image}", "the flow settled this"))
        if not self._is_named:
            rows.append((_SAVE, "", "save this as an agent you can import"))
        return rows

    def _fill(self) -> None:
        """Puts the rows up, with the marker beside the one the cursor is on."""
        listing = self.query_one("#choices", OptionList)
        rows = self._rows()
        self._counting = len(str(max(len(rows), 1)))
        at = min(listing.highlighted or 0, max(len(rows) - 1, 0))
        listing.set_options(
            Option(
                self._line(seen, held, value, about, here=seen == at),
                id=f"={held}",
            )
            for seen, (held, value, about) in enumerate(rows)
        )
        listing.highlighted = at if rows else None
        self._drawn = at
        self.query_one("#tuning", Label).update(
            f"[$text-muted]{self._said}[/]" if self._said else ""
        )
        held = rows[at][0] if rows else ""
        self.query_one("#keys", Label).update(
            "←/→ to change · Esc to close"
            if held in _STEPPED
            else "Type to name it · Esc to close"
            if held == _NAME
            else "Enter to open · Esc to close"
        )

    def _line(self, at: int, held: str, value: str, about: str, *, here: bool) -> str:
        """One row: what is being said, what it is set to, and what it means.

        Args:
          at: Which one it is, counting from zero.
          held: What the row is called.
          value: What it is set to.
          about: The line about it, said quietly.
          here: Whether the cursor is on it.

        Returns:
          The row, as markup.
        """
        mark = f"{_INDENT}[$primary]{_HERE}[/] " if here else f"{_INDENT}  "
        number = f"{at + 1:>{self._counting}}."
        # A block where the next letter goes, on the one row that is written rather than
        # opened: without it a blank name reads as a row nothing can be typed into.
        caret = "[reverse] [/reverse]" if here and held == _NAME else ""
        # A row that opens something says so, as a menu anywhere says it.
        opens = "" if held in _STEPPED or held == _NAME else " ▸"
        # Padded on what is shown rather than on what is written: markup is not columns.
        named = escape(held) + " " * max(1, _ASPECT - len(held))
        room = _HOW - len(value) - len(opens) - (1 if caret else 0)
        return (
            f"{mark}[$text-muted]{number}[/] {named}"
            f"[$secondary]{escape(value)}[/]{caret}[$text-muted]{opens}[/]"
            f"{' ' * max(1, room)}[$text-muted]{escape(about)}[/]"
        )

    def _models(self) -> tuple[Model, ...]:
        """What the chosen CLI says it runs as the chosen account, read once per pair."""
        from hmz import models

        if self._catalogue is None or self._read_for != (self._cli, self._provider):
            self._read_for = (self._cli, self._provider)
            self._catalogue = (
                models.offered(self._cli, self._provider)
                if self._provider
                else self._agents.get(self._cli, ())
            )
        return self._catalogue

    def _under_model(self) -> Model | None:
        """The model this agent runs, as the CLI described it, or None where it named none."""
        return next(
            (one for one in self._models() if one.name == self._model),
            None,
        )

    def _efforts(self) -> tuple[str, ...]:
        """What the chosen model takes, hardest first.

        Returns:
          The efforts, or the one this agent is already at for a model the CLI has not
          described -- an agent read back off a file names a model whose catalogue may not
          have been fetched yet, and its effort is still the effort it runs at.
        """
        model = self._under_model()
        if model is not None and model.efforts:
            return model.efforts
        return (self._effort,) if self._effort else ()

    def _swarms(self) -> bool:
        """Whether the chosen model runs a turn as a fleet as well as as an agent."""
        model = self._under_model()
        return model is not None and model.swarms

    def _made(self) -> Runs:
        """This agent as it now stands, which is what the sheet answers with."""
        # `swarm` in front of the effort is how a fleet is asked for: one turn at one effort,
        # run wide. A model that does not take it is asked for at the effort alone.
        wide = SWARM if self._swarm and self._swarms() else ""
        return Runs(
            spec=f"{self._cli}/{self._model}:{wide}{self._effort}",
            anchor=self._anchor,
            # Nothing said at all is the CLI as it comes, which is None rather than a list of
            # every skill it happens to have installed today.
            skills=self._skills,
            # Only where it is a narrowing: the loosest rung is what an agent nobody has been
            # asked about runs at, and saying so is saying nothing.
            permission=(
                PERMISSIONS[self._permission]
                if self._permission < len(PERMISSIONS) - 1
                else ""
            ),
            provider=self._provider,
            goals=self._goals,
        )

    def applied(self) -> None:
        """Answers with the agent as it now stands, and what it is called."""
        self.dismiss(Fitted(self._made(), self._called))

    @property
    def _held(self) -> str:
        """Which row the cursor is on, by id."""
        return self.under()

    def on_key(self, event: events.Key) -> None:
        """Takes a letter as writing the name, which is the one row that is written.

        There is nothing to search here -- every row is on the screen at once -- so the keys
        that narrow a list elsewhere are the ones that name this agent.

        Args:
          event: The key.
        """
        if self._held != _NAME:
            return
        if event.key == "backspace":
            self._called = self._called[:-1]
        elif event.is_printable and event.character:
            self._called += event.character
        else:
            return
        event.prevent_default()
        event.stop()
        self.changed()
        self._fill()

    def action_harder(self) -> None:
        """Steps the row under the cursor one on, where it is one that is stepped."""
        self._step(-1)

    def action_easier(self) -> None:
        """Steps it one back."""
        self._step(1)

    def _step(self, by: int) -> None:
        """Moves whichever rung the cursor is on, however that one moves.

        Args:
          by: One step along the efforts towards the one that thinks least, which is the same
            direction as one step back through everything else.
        """
        held = self._held
        if held == _EFFORT:
            efforts = self._efforts()
            if not efforts:
                return
            at = efforts.index(self._effort) if self._effort in efforts else 0
            self._effort = efforts[min(max(at + by, 0), len(efforts) - 1)]
        elif held == _SWARM:
            self._swarm = not self._swarm
        elif held == _PERMIT:
            # Round rather than along: the rungs are four and the way back to the one before
            # is the way on past the last, which is one key rather than two.
            self._permission = (self._permission - by) % len(PERMISSIONS)
        elif held == _GOALS:
            if self._place is not None and self._place.goal:
                return  # the flow requires them, so there is nothing here to turn off
            self._goals = not self._goals
        else:
            return
        self.changed()
        self._said = ""
        self._fill()

    @on(OptionList.OptionSelected)
    def _took(self, event: OptionList.OptionSelected) -> None:
        """Opens the row under the cursor, or steps it where it is one that is stepped.

        Args:
          event: What was chosen.
        """
        held = str(event.option.id or "").removeprefix("=")
        if held in _STEPPED:
            self._step(-1)
            return
        if held in (_CLI, _ACCOUNT, _MODEL, _SKILLS, _WHERE, _IMPORT, _SAVE):
            self._opens(held)

    @work
    async def _opens(self, held: str) -> None:
        """Asks whatever that row is a way of asking, and holds the answer.

        Args:
          held: The row, by id.
        """
        showing = cast(
            "App[None]",
            self.app,  # pyright: ignore[reportUnknownMemberType]
        )
        if held == _CLI:
            await self._chose_cli(showing)
        elif held == _ACCOUNT:
            await self._chose_account(showing)
        elif held == _MODEL:
            await self._chose_model(showing)
        elif held == _SKILLS:
            await self._chose_skills(showing)
        elif held == _WHERE:
            await self._chose_where(showing)
        elif held == _IMPORT:
            await self._imports(showing)
        else:
            await self._saves(showing)
        self._fill()

    async def _chose_cli(self, showing: App[None]) -> None:
        """Asks which coding agent takes this one's turns, and lets go of what was its."""
        chosen = await showing.push_screen_wait(
            Clis(
                self._agents,
                self._cli,
                place=self._place,
                unavailable=self._unavailable,
            )
        )
        if chosen is None or chosen == self._cli:
            return
        # An account belongs to a backend and a model belongs to the CLI that runs it, so
        # neither of them survives the CLI changing under it.
        self._cli, self._provider, self._model, self._effort = chosen, "", "", ""
        self._skills, self._swarm = None, False
        self._said = ""
        self.changed()

    async def _chose_account(self, showing: App[None]) -> None:
        """Asks which account its turns run as, out of that CLI's own."""
        if not self._cli:
            self._said = "choose the coding agent first; the accounts are its own"
            return
        chosen = await showing.push_screen_wait(Accounts(self._cli, self._provider))
        if chosen is None or chosen == self._provider:
            return
        # What one account may name is not what another may: the models are the account's.
        self._provider, self._said = chosen, ""
        self.changed()

    async def _chose_model(self, showing: App[None]) -> None:
        """Asks which of that CLI's models it runs, and starts it at the hardest effort."""
        if not self._cli:
            self._said = "choose the coding agent first; a model belongs to the CLI"
            return
        chosen = await showing.push_screen_wait(
            Catalogue(self._cli, self._provider, self._models(), self._model)
        )
        if chosen is None:
            return
        self._model, self._said = chosen, ""
        self._catalogue, self._read_for = None, ("", "")
        efforts = self._efforts()
        if self._effort not in efforts:
            # The hardest the model takes, which is where the cursor of the sheet that used
            # to ask this started: what is reached for rather than what is spent by default.
            self._effort = efforts[0] if efforts else ""
        self.changed()

    async def _chose_skills(self, showing: App[None]) -> None:
        """Asks which of its CLI's skills it is loaded with."""
        if not self._cli:
            self._said = "choose the coding agent first; the skills are its own"
            return
        chosen = await showing.push_screen_wait(Skills(self._cli, self._skills))
        if chosen is None:
            return
        self._skills, self._said = chosen, ""
        self.changed()

    async def _chose_where(self, showing: App[None]) -> None:
        """Asks which machine its work lands on, where that is a question anybody is asked."""
        if self._place is not None and not pointed(self._place):
            self._said = "the flow settled where this one works"
            return
        where = await showing.push_screen_wait(Anchors(self._named, self._anchor))
        if where is None:
            return
        self._anchor, self._said = where, ""
        self.changed()

    async def _imports(self, showing: App[None]) -> None:
        """Copies a saved agent into this one, name and all but the name."""
        from .settings import Templates

        held = Templates().all()
        if not held:
            self._said = "no agents have been saved yet; /agents saves one"
            return
        chosen = await showing.push_screen_wait(Imports(held))
        if chosen is None:
            return
        one = next((each for each in held if each.name == chosen), None)
        if one is None:
            return
        cli, _, rest = one.runs.spec.partition("/")
        model, _, effort = rest.rpartition(":")
        self._cli, self._model = cli, model
        self._swarm = effort.startswith(SWARM)
        self._effort = effort.removeprefix(SWARM)
        self._skills, self._provider = one.runs.skills, one.runs.provider
        self._permission = (
            PERMISSIONS.index(one.runs.permission)
            if one.runs.permission in PERMISSIONS
            else len(PERMISSIONS) - 1
        )
        self._anchor = one.runs.anchor
        # What the flow requires is the flow's, and is not a thing an import may overwrite.
        if self._place is None or not self._place.goal:
            self._goals = one.runs.goals
        self._catalogue, self._read_for = None, ("", "")
        self._said = (
            f"copied from {escape(chosen)}; changing it here changes only this one"
        )
        self.changed()

    async def _saves(self, showing: App[None]) -> None:
        """Writes this agent down under a name, new or one already there."""
        from .settings import Kept, Templates

        if not (self._cli and self._model):
            self._said = "an agent with no model is not one to save"
            return
        store = Templates()
        listed = store.all()
        name = await showing.push_screen_wait(Names(listed, self._named))
        if not name:
            return
        runs = self._made()
        store.keep(
            [Kept(name, runs) if one.name == name else one for one in listed]
            if any(one.name == name for one in listed)
            else [*listed, Kept(name, runs)]
        )
        self._said = f"saved as {escape(name)}"


class Clis(Picks):
    """Which coding agent takes one agent's turns, out of the ones that could.

    Not always all of them: a flow that hangs a hook on a moment only some backends run said
    so where it declared the place, and a CLI that does not run that moment is one choosing
    would make the flow refuse to start.
    """

    asked = "Select which coding agent takes its turns"
    about = (
        "The CLI behind this agent. Its accounts, its models, its skills and how hard it can "
        "be asked to think are all its own, so choosing another lets go of them."
    )

    def __init__(
        self,
        agents: dict[str, tuple[Model, ...]],
        current: str = "",
        *,
        place: Place | None = None,
        unavailable: frozenset[str] = frozenset(),
    ) -> None:
        """Initializes the choosing.

        Args:
          agents: The backends offered here, and what each of them says it runs.
          current: The one it is now.
          place: What the flow declared about this agent, or None for a saved agent, which
            belongs to no flow and so is refused nothing.
          unavailable: The optional backends that still need installing.
        """
        super().__init__(current)
        self._agents = dict(agents)
        self._place = place
        self._unavailable = unavailable

    def rows(self) -> list[tuple[str, str, str]]:
        """Every CLI that could take this one's turns, and what each of them runs."""
        needs: frozenset[Moment] = (
            self._place.moments if self._place is not None else frozenset()
        )
        pursuing = self._place is not None and self._place.goal
        listed: list[tuple[str, str, str]] = []
        for backend in sorted(self._agents):
            drives = _drives(backend)
            if drives is None or not needs <= drives.moments:
                continue
            if pursuing and not drives.pursues:
                continue
            listed.append(
                (
                    backend,
                    backend,
                    _installing(backend)
                    if backend in self._unavailable
                    else f"{len(self._agents[backend])} models"
                    if self._agents[backend]
                    else "has not said what it runs yet",
                )
            )
        return listed

    def nothing(self) -> str:
        """Says so where the flow has ruled every backend here out, which is worth knowing."""
        return (
            ""
            if self._rows
            else "no coding agent installed here can take this one's turns"
        )


class Accounts(Picks):
    """Which account one agent's turns run as, out of one CLI's own.

    The machine's own is always the first of them: an agent nobody has been asked about runs
    as whoever signed the CLI in, and that is a row rather than a blank. Making one is a key
    here, this being the moment somebody finds out they have none for this CLI.
    """

    asked = "Select the account its turns run as"
    about = (
        "An account is one backend's -- what signs in to Claude Code is not what signs in to "
        "codex -- so these are that CLI's own. Its sessions, its settings and its skills are "
        "the CLI's whichever account it runs as."
    )
    keys = "a to make one · "
    LETTERS: ClassVar = frozenset({"search", "new"})

    BINDINGS: ClassVar = [
        ("escape", "back", "back"),
        Binding("s", "search", "search", priority=True),
        Binding("a", "new", "make one", priority=True),
    ]

    def __init__(self, backend: str, current: str = "") -> None:
        """Initializes the choosing.

        Args:
          backend: The CLI whose accounts these are.
          current: The account it runs as now, or "" for the machine's own.
        """
        super().__init__(current)
        self._backend = backend
        self._said = ""

    def rows(self) -> list[tuple[str, str, str]]:
        """The machine's own first, and then every account that CLI has here."""
        from hmz import providers

        found = providers.providers(self._backend)
        if self._backend == "dsh":
            found = [
                one
                for one in found
                if one.way == "key" and one.env.get("DEEPSEEK_API_KEY", "").strip()
            ]
        return [
            (
                "",
                _LOCAL,
                "using credentials and the base URL saved by dsh, or this environment"
                if self._backend == "dsh"
                else "signed in as you signed it in",
            ),
            *((one.name, one.name, _sets(one)) for one in found),
        ]

    def nothing(self) -> str:
        """Says what came of making one, or where they come from for a CLI that has none."""
        if self._said:
            return self._said
        if self._backend == "dsh" and len(self._rows or []) < 2:  # noqa: PLR2004
            return (
                "DeepSeek Harness needs an API key; a stores one, or set DEEPSEEK_API_KEY "
                "and reopen hmz"
            )
        if len(self._rows or []) > 1:
            return ""
        return f"{escape(self._backend)} has no accounts here yet; a makes one"

    @work
    async def action_new(self) -> None:
        """Makes an account for this CLI without leaving the question it is chosen in.

        The same walk `/providers` runs, minus the question it has already answered: which
        backend. What comes of it is what this list is now showing, so a new account is chosen
        straight away -- making one here is choosing it -- unless its own way in failed, which
        is said under the list and left for whoever is looking to decide about.
        """
        showing = cast(
            "App[None]",
            self.app,  # pyright: ignore[reportUnknownMemberType]
        )
        outcome = await made(showing, self._backend)
        if outcome.why:
            self._said = escape(outcome.why)
        if outcome.provider is None:
            self._rows = None  # it may have been made and then failed; look again
            self._fill()
            return
        if outcome.status:
            self._said = (
                f"{escape(outcome.provider.name)} is written down, but signing it in "
                f"exited {outcome.status}"
            )
            self._rows = None
            self._fill()
            return
        self.dismiss(outcome.provider.name)


class Catalogue(Picks):
    """Which model one agent runs, out of what its CLI last said it runs as its account.

    The rows are what that CLI said rather than a list written down anywhere: a CLI ships a
    model without asking anybody, and which of them a turn may name is the account's. `r` asks
    it again, which is what somebody who came here for a model that is not in the list wants
    -- and is the whole reason the key is on this sheet rather than somewhere else.
    """

    LETTERS: ClassVar = frozenset({"search", "refresh"})
    keys = "r to ask it again · "

    BINDINGS: ClassVar = [
        ("escape", "back", "back"),
        Binding("s", "search", "search", priority=True),
        Binding("r", "refresh", "ask it what it runs", priority=True),
    ]

    def __init__(
        self,
        backend: str,
        provider: str,
        models: tuple[Model, ...],
        current: str = "",
    ) -> None:
        """Initializes the choosing.

        Args:
          backend: The CLI whose models these are.
          provider: The account it was asked as, or "" for the machine's own.
          models: What it last said it runs as that account, which is nothing at all for one
            that has never been asked -- and is what `r` here fills.
          current: The model it runs now.
        """
        super().__init__(current)
        self.asked = f"Select what {backend} runs"
        self.about = (
            f"Which model of {backend} takes this one's turns, and how hard it may be asked "
            "to think. These are what it last said it runs as this account; r asks it again."
        )
        self._backend = backend
        self._provider = provider
        self._models = models
        self._asking = False
        self._said = ""

    def rows(self) -> list[tuple[str, str, str]]:
        """Every model that CLI named, and what efforts each of them takes."""
        return [
            (
                one.name,
                one.name,
                ", ".join(one.efforts) + (f"{_DOT}swarms" if one.swarms else ""),
            )
            for one in self._models
        ]

    def nothing(self) -> str:
        """What to say where there is no model to say anything else about."""
        if self._asking:
            return f"asking {escape(self._backend)} what it runs…"
        if self._said:
            return self._said
        if self._models:
            return ""  # narrowed away by what was typed, which the search itself says
        whose = f" as {escape(self._provider)}" if self._provider else ""
        return (
            f"{escape(self._backend)} has not said what it runs{whose} yet; r asks it"
        )

    @work
    async def action_refresh(self) -> None:
        """Asks this CLI what it runs as this account, and puts up what it answers.

        Off the event loop, because asking means starting a coding agent and some of them take
        the better part of a minute over it: an interface that stopped redrawing while it ran
        would be one that looked as though it had gone away.
        """
        import asyncio

        from hmz import models

        if not self._backend or self._asking:
            return
        self._asking, self._said = True, ""
        self._fill()
        try:
            found = await asyncio.to_thread(models.ask, self._backend, self._provider)
        except Exception as why:  # noqa: BLE001 -- a CLI that would not answer, however
            # Said under the list rather than raised at whoever opened the sheet: a CLI that
            # is not signed in cannot say what it runs, and the question here still stands.
            self._said = escape(str(why) or type(why).__name__)
            self._asking = False
            self._fill()
            return
        self._asking, self._models = False, found
        self._said = "" if found else f"{escape(self._backend)} named no models it runs"
        self._rows = None
        self.query_one("#choices", OptionList).highlighted = 0
        self._drawn = 0
        self._fill()


class Imports(Picks):
    """Which saved agent to copy into the one being set up.

    A copy rather than a link: an agent tuned inside a flow is that flow's, and writing the
    changes back into the thing it was copied from would change every other flow that had
    imported it.
    """

    asked = "Select an agent to copy in"
    about = (
        "The agents saved under a name, which /agents keeps. What is copied is everything "
        "the agent is; changing it afterwards changes this one alone."
    )

    def __init__(self, held: Sequence[Kept]) -> None:
        """Initializes the choosing.

        Args:
          held: The agents written down, in the order they are kept in.
        """
        super().__init__()
        self._held = list(held)

    def rows(self) -> list[tuple[str, str, str]]:
        """Every agent written down, and what each of them is."""
        return [(one.name, one.name, reads((), [one.runs])[0]) for one in self._held]


class Names(Sheet[str]):
    """What to save an agent as: a name already there to write over, or one typed.

    Listed rather than typed where there is one to list, because writing over the agent
    somebody meant is the common half of this: a name typed a second time with a letter
    different is a second agent nobody wanted.
    """

    LETTERS: ClassVar = frozenset({"search"})

    BINDINGS: ClassVar = [
        ("escape", "back", "back"),
        Binding("s", "search", "search", priority=True),
    ]

    def __init__(self, held: Sequence[Kept], suggested: str = "") -> None:
        """Initializes the naming.

        Args:
          held: The agents written down already, any of which may be written over.
          suggested: What to offer as a name for a new one, which is what the agent being
            saved is called where it is called anything.
        """
        super().__init__()
        self._held = list(held)
        self._suggested = suggested

    def _ask(self) -> None:
        """Says what saving one does, and puts the names up."""
        self.query_one("#asked", Label).update("Save this agent as")
        self.query_one("#about", Label).update(
            "The name it is imported by. Choosing one already here writes over it; s and "
            "then a name of your own saves it as a new one."
        )
        self._fill()
        self.query_one("#choices", OptionList).focus()

    def _fill(self) -> None:
        """Puts the names up, with whatever has been typed among them as a new one."""
        listing = self.query_one("#choices", OptionList)
        rows = [(one.name, one.name, reads((), [one.runs])[0]) for one in self._held]
        shown = [row for row in rows if self.fits(row[1], row[2])]
        wanted = self._typed.strip() or (
            "" if shown or self._typed else self._suggested
        )
        if wanted and all(row[0] != wanted for row in shown):
            shown.append((wanted, wanted, "a new one under this name"))
        self._counting = len(str(max(len(shown), 1)))
        at = min(listing.highlighted or 0, max(len(shown) - 1, 0))
        listing.set_options(
            Option(
                self._row(seen, label, about, here=seen == at, inforce=False),
                id=f"={answer}",
            )
            for seen, (answer, label, about) in enumerate(shown)
        )
        listing.highlighted = at if shown else None
        self._drawn = at
        self.query_one("#keys", Label).update(
            f"Enter to save · Esc to go back{self.searching()}"
        )

    @on(OptionList.OptionSelected)
    def _took(self, event: OptionList.OptionSelected) -> None:
        """Answers with the name that was picked.

        Args:
          event: What was chosen.
        """
        self.dismiss(str(event.option.id).removeprefix("="))


class Saved(Drafts[list[str]]):
    """Every agent written down under a name, which is what a flow's agents are imported from.

    An agent is a CLI, an account, a model at an effort and what it may do without being
    asked, and none of that is a thing about the flow that happens to be driving it. So it is
    worth saying once and reaching for: the reviewer you always use, the cheap one you fan out
    across, the one on somebody else's gateway.

    Nothing here is being chosen for anything. What it is for is the three things that can
    happen to one -- made, set up, taken away -- so those are the keys, and none of them lands
    until the menu is saved on the way out.
    """

    TABS: ClassVar = ("Agents",)
    LETTERS: ClassVar = frozenset({"search", "adding", "drop"})

    BINDINGS: ClassVar = [
        ("escape", "back", "back"),
        Binding("tab", "next_tab", "next page", priority=True),
        Binding("shift+tab", "prev_tab", "previous page", priority=True),
        Binding("s", "search", "search", priority=True),
        Binding("a", "adding", "add one", priority=True),
        Binding("d", "drop", "take one away", priority=True),
    ]

    def __init__(self, agents: dict[str, tuple[Model, ...]]) -> None:
        """Reads what has been written down.

        Args:
          agents: The backends offered here, and what each of them says it runs.
        """
        super().__init__()
        from .settings import Templates

        self._agents = dict(agents)
        #: What the menu is holding, which is what is written down when it is saved.
        self._held: list[Kept] = list(Templates().all())
        #: Which of them the cursor is on, by name.
        self._was = self._held[0].name if self._held else ""
        self._said = ""

    def _ask(self) -> None:
        """Says what these are, and puts them up."""
        self.query_one("#asked", Label).update("Agents")
        self.query_one("#about", Label).update(
            "One named agent apiece: the CLI that takes its turns, the account they run as, "
            "the model at an effort and what it may do. A flow imports a copy of one where "
            "its agents are chosen, so changing one here does not change a flow already set "
            "up with it."
        )
        self._fill()
        self.query_one("#choices", OptionList).focus()

    def _fill(self) -> None:
        """Puts the agents up, with the marker beside the one the cursor is on."""
        listing = self.query_one("#choices", OptionList)
        self._follows(listing)
        shown = [one for one in self._held if self.fits(one.name, one.runs.spec)]
        self._counting = len(str(max(len(shown), 1)))
        if all(one.name != self._was for one in shown):
            self._was = shown[0].name if shown else ""
        at = next((seen for seen, one in enumerate(shown) if one.name == self._was), 0)
        listing.set_options(
            Option(
                self._row(
                    seen,
                    one.name,
                    reads((), [one.runs])[0],
                    here=seen == at,
                    inforce=False,
                ),
                id=f"={one.name}",
            )
            for seen, one in enumerate(shown)
        )
        listing.highlighted = at if shown else None
        self._drawn = listing.highlighted
        self.tabbed(self._tab_line())
        said = self._said or ("" if self._held else "no agents saved yet; a saves one")
        self.query_one("#tuning", Label).update(
            f"[$text-muted]{said}[/]" if said else ""
        )
        self.query_one("#keys", Label).update(
            "Enter to set one up · a adds one · d twice takes one away · "
            f"Esc to close{self.searching()}"
        )

    def _follows(self, listing: OptionList) -> None:
        """Takes which agent the cursor is on off the list, by the name it is kept under.

        Args:
          listing: The list.
        """
        at = listing.highlighted
        if at is not None and 0 <= at < listing.option_count:
            named = str(listing.get_option_at_index(at).id or "").removeprefix("=")
            if named:
                self._was = named

    def action_adding(self) -> None:
        """Sets up an agent that is not there yet, and holds it if it is named."""
        spare = opens_on(self._agents)
        self._sets(Kept("", spare[0] if spare else Runs("")), new=True)

    def action_drop(self) -> None:
        """Takes the agent under the cursor away, once d has been pressed twice."""
        name = self.under()
        if not name:
            return
        if not self._armed(name):
            self._said = f"press d again to take {escape(name)} away"
            self._fill()
            return
        self._held = [one for one in self._held if one.name != name]
        self._said = f"{escape(name)} goes when this menu is saved"
        self.changed()
        self._fill()

    @on(OptionList.OptionSelected)
    def _took(self, event: OptionList.OptionSelected) -> None:
        """Sets up the agent under the cursor.

        Args:
          event: What was chosen.
        """
        name = str(event.option.id or "").removeprefix("=")
        one = next((each for each in self._held if each.name == name), None)
        if one is not None:
            self._sets(one, new=False)

    @work
    async def _sets(self, one: Kept, *, new: bool) -> None:
        """Opens one agent, and holds whatever comes back.

        Args:
          one: The agent as it is now.
          new: Whether it is one that is not written down yet, which is what decides between
            adding it and writing over it.
        """
        showing = cast(
            "App[None]",
            self.app,  # pyright: ignore[reportUnknownMemberType]
        )
        fitted = await showing.push_screen_wait(
            Agent(
                one.name or "a new agent",
                one.runs,
                self._agents,
                name=one.name,
                naming=True,
            )
        )
        if fitted is None:
            return  # walked out of it, which leaves this one as it was
        named = fitted.name.strip()
        if not named:
            self._said = "an agent with no name is not one anything can import"
            self._fill()
            return
        # Written over where it is one already held, and added where it is not -- by the name
        # it now has, so that renaming one is renaming it rather than making a second. Where
        # it was in the list is where it stays: a list that reordered itself as an agent was
        # renamed would move the cursor out from under whoever was reading it.
        at = next(
            (seen for seen, each in enumerate(self._held) if each.name == one.name),
            len(self._held),
        )
        held = [each for each in self._held if each.name not in (named, one.name)]
        at = min(at, len(held)) if not new else len(held)
        self._held = [*held[:at], Kept(named, fitted.runs), *held[at:]]
        self._was, self._said = named, ""
        self.changed()
        self._fill()

    def applied(self) -> None:
        """Writes down exactly what the menu is holding, and says what it now holds."""
        from .settings import Templates

        Templates().keep(self._held)
        self.dismiss(
            [
                f"[dim]{len(self._held)} agents saved: "
                f"{escape(', '.join(one.name for one in self._held))}[/dim]"
                if self._held
                else "[dim]no agents are saved any more[/dim]"
            ]
        )


class Providers(Drafts[list[str]]):
    """Every account there is to run an agent as, under a heading per CLI.

    Read rather than chosen from: which account an agent runs as is asked where that agent is
    set up, so nothing here is being picked for anything. What it is for is what can happen to
    one -- made, set up again, signed in again, marked as where a turn goes when another
    account fails, taken away -- so those are the keys.

    What is written down without running anything is held until the menu is saved: taking one
    away, marking one as a fallback, correcting what one holds. What cannot be held is what
    runs a command of its own -- making an account and signing one in own the terminal while
    they run, and something that has already happened is not a draft.

    Each row is the name, the way it was made by and the variables it sets. Their names and
    never a value: this is drawn where somebody can read it.
    """

    TABS: ClassVar = ("Providers",)
    LETTERS: ClassVar = frozenset(
        {"search", "adding", "drop", "again", "fallback", "speaks"}
    )

    BINDINGS: ClassVar = [
        ("escape", "back", "back"),
        Binding("tab", "next_tab", "next page", priority=True),
        Binding("shift+tab", "prev_tab", "previous page", priority=True),
        Binding("s", "search", "search", priority=True),
        Binding("a", "adding", "make one", priority=True),
        Binding("d", "drop", "take one away", priority=True),
        Binding("l", "again", "sign in again", priority=True),
        Binding("f", "fallback", "as fallback", priority=True),
        # And the one thing here that is not an account: a CLI of your own to run them on.
        Binding("c", "speaks", "add an ACP CLI", priority=True),
    ]

    def __init__(self) -> None:
        """Reads every account there is."""
        super().__init__()
        self._found: list[Provider] = []
        #: The ones to take away when this is saved, as `cli/name`.
        self._gone: set[str] = set()
        #: The ones whose fallback mark is to be turned round when this is saved.
        self._marks: set[str] = set()
        #: What each corrected one is to hold, by `cli/name`.
        self._edits: dict[str, dict[str, str]] = {}
        #: Which account the cursor is on, as `cli/name`: the headings between them are rows
        #: nothing can land on, so a row number is not an account.
        self._was = ""
        #: What is worth saying under the list, and what is worth saying in the transcript
        #: once this menu is done with.
        self._said = ""
        self._told: list[str] = []

    def _ask(self) -> None:
        """Says what these are, and puts them up."""
        self.query_one("#asked", Label).update("Providers")
        self.query_one("#about", Label).update(
            "One named set of credentials per account, kept apart from the CLI's own and "
            "from each other's. An agent is given one where it is set up, and runs its turns "
            "as that account. Taking one away and marking one as a fallback land when this "
            "menu is saved; making one and signing one in happen as they are asked for."
        )
        self._read()
        self._fill()
        self.query_one("#choices", OptionList).focus()

    def _read(self) -> None:
        """Reads every account off the disk, which is what the rows are drawn from."""
        from hmz import providers

        self._found = providers.providers()

    def _named(self, one: Provider) -> str:
        """One account as it is keyed here, which is by the CLI it belongs to and its name."""
        return f"{one.cli}/{one.name}"

    def _about(self, one: Provider) -> str:
        """What a row says about one account, and what is going to happen to it."""
        said = _sets(one)
        if self._named(one) in self._edits:
            said += f"{_DOT}corrected"
        if (one.fallback) != (self._named(one) in self._marks):
            said += f"{_DOT}fallback"
        if self._named(one) in self._gone:
            said += f"{_DOT}to be taken away"
        return said

    def _fill(self) -> None:
        """Puts the accounts up under a heading apiece, marked where the cursor is."""
        listing = self.query_one("#choices", OptionList)
        self._follows(listing)
        shown = [one for one in self._found if self.fits(one.name, one.cli, one.way)]
        self._counting = len(str(max(len(shown), 1)))
        if all(self._named(one) != self._was for one in shown):
            # Gone, or never there: the cursor starts on the first of them, and a list with
            # nothing in it has nothing for it to be on.
            self._was = self._named(shown[0]) if shown else ""
        rows: list[Option] = []
        group, landing = "", 0
        for seen, one in enumerate(shown):
            named = self._named(one)
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
                        self._about(one),
                        here=named == self._was,
                        inforce=False,
                    ),
                    id=f"={named}",
                )
            )
        listing.set_options(rows)
        listing.highlighted = landing if shown else None
        self._drawn = listing.highlighted
        self.tabbed(self._tab_line())
        said = self._said or ("" if self._found else "no accounts yet; a makes one")
        self.query_one("#tuning", Label).update(
            f"[$text-muted]{said}[/]" if said else ""
        )
        self.query_one("#keys", Label).update(
            "Enter to correct one · a makes one · l signs one in again · f as fallback · "
            f"d twice takes one away · c adds an ACP CLI · Esc to close{self.searching()}"
        )

    def _follows(self, listing: OptionList) -> None:
        """Takes which account the cursor is on off the list, by `cli/name`.

        The headings between them are rows nothing can land on, so a row number is not an
        account and the id on the row is the only thing that says which one is meant.

        Args:
          listing: The list.
        """
        at = listing.highlighted
        if at is not None and 0 <= at < listing.option_count:
            named = str(listing.get_option_at_index(at).id or "").removeprefix("=")
            if named:
                self._was = named

    def _under(self) -> Provider | None:
        """The account the cursor is on, or None where the list has nothing in it."""
        return next((one for one in self._found if self._named(one) == self._was), None)

    def action_fallback(self) -> None:
        """Turns round whether the account under the cursor is where a failed turn goes."""
        one = self._under()
        if one is None:
            return
        named = self._named(one)
        if named in self._marks:
            self._marks.discard(named)
        else:
            self._marks.add(named)
        self._said = ""
        self.changed()
        self._fill()

    def action_drop(self) -> None:
        """Marks the account under the cursor to be taken away, once d is pressed twice."""
        one = self._under()
        if one is None:
            return
        named = self._named(one)
        if named in self._gone:
            self._gone.discard(named)  # said twice is said and taken back
            self._said = f"{escape(named)} stays"
            self.changed()
            self._fill()
            return
        if not self._armed(named):
            self._said = (
                f"press d again to take {escape(named)} away, credentials and all"
            )
            self._fill()
            return
        self._gone.add(named)
        self._said = f"{escape(named)} goes when this menu is saved"
        self.changed()
        self._fill()

    @on(OptionList.OptionSelected)
    def _took(self, event: OptionList.OptionSelected) -> None:
        """Corrects what the account under the cursor holds.

        Args:
          event: What was chosen.
        """
        named = str(event.option.id or "").removeprefix("=")
        one = next((each for each in self._found if self._named(each) == named), None)
        if one is not None:
            self._corrects(one)

    @work
    async def _corrects(self, one: Provider) -> None:
        """Asks what one account is to hold, starting from what it holds now.

        A secret is never read back on to the screen, so what is typed here replaces what was
        there rather than being edited into it: a key is written once and read never.

        Args:
          one: The account.
        """
        from hmz.providers import login as signing

        way = signing.way_of(one.cli, one.way)
        if way is None:
            self._said = f"{escape(one.way)} is not a way in {escape(one.cli)} has"
            self._fill()
            return
        showing = cast(
            "App[None]",
            self.app,  # pyright: ignore[reportUnknownMemberType]
        )
        signs = await showing.push_screen_wait(
            Signing(one.cli, way, name=one.name, held=one.env)
        )
        if signs is None:
            return  # walked out, which corrects nothing
        self._edits[self._named(one)] = signs.answers
        self._said = f"{escape(self._named(one))} is corrected when this menu is saved"
        self.changed()
        self._fill()

    @work
    async def action_adding(self) -> None:
        """Asks which CLI, and then walks that backend's own way in.

        Two questions rather than one, because the second is only answerable once the first
        has been: a backend's ways in are its own. What comes of it has already happened by
        the time it lands -- a login owns the terminal while it runs -- so it is not one of
        the things this menu holds until it is saved.
        """
        showing = cast(
            "App[None]",
            self.app,  # pyright: ignore[reportUnknownMemberType]
        )
        while True:
            cli = await showing.push_screen_wait(Backends())
            if cli is None:
                return  # nothing before this to step back into
            outcome = await made(showing, cli)
            # Walking out of the first question the walk itself asks is a step back into the
            # one asked here, since that is the step before it.
            if outcome.provider is not None or outcome.why:
                break
        one = outcome.provider
        if one is None:  # a name or a directory that will not do
            self._said = escape(outcome.why)
            self._fill()
            return
        self._told.append(
            f"[dim]{escape(one.cli)}/{escape(one.name)} is written down at "
            f"{escape(str(one.at))}[/dim]"
        )
        if outcome.way_runs and not outcome.status:
            # Said as well as written down: a way with a command of its own owned the
            # terminal while it ran, and whether it landed is the half worth reading.
            self._told.append(
                f"[dim]{escape(one.cli)}/{escape(one.name)} is signed in[/dim]"
            )
        elif outcome.status:
            self._told.append(f"hmz: signing it in exited {outcome.status}")
        self._said = self._landed(one, outcome.status, runs=outcome.runs)
        self._read()
        self._was = self._named(one)
        self._fill()

    def _landed(self, one: Provider, status: int, *, runs: int) -> str:
        """What to say about an account that has just been made or signed in again.

        Args:
          one: The account.
          status: What its way in exited with, or 0 for one that ran nothing.
          runs: How many models its CLI then said it runs as it.

        Returns:
          The line to say under the list.
        """
        if status:
            return f"signing {escape(one.name)} in exited {status}"
        if runs:
            return f"{escape(one.cli)} says it runs {runs} models as {escape(one.name)}"
        return (
            f"{escape(one.cli)} did not say what it runs as {escape(one.name)}; "
            "r on its models asks again"
        )

    @work
    async def action_again(self) -> None:
        """Runs one account's own way in again, asking for whatever it still needs."""
        from hmz.providers import login as signing

        one = self._under()
        if one is None:
            return
        way = signing.way_of(one.cli, one.way)
        if way is None or not way.argv:
            self._said = (
                f"{escape(one.name)} was made by {escape(one.way)}, which has nothing to "
                "run; enter corrects what it holds instead"
            )
            self._fill()
            return
        showing = cast(
            "App[None]",
            self.app,  # pyright: ignore[reportUnknownMemberType]
        )
        # What it already holds answers what it can. A key the CLI keeps in its own store is
        # not among them -- it was never kept here -- so it is asked for again.
        answers = dict(one.env)
        if signing.asked(way, answers):
            signs = await showing.push_screen_wait(Signing(one.cli, way, name=one.name))
            if signs is None:
                return  # walked out, which signs nothing in and changes nothing
            answers |= signs.answers
        try:
            with handed_over(showing):
                status = signing.sign_in(one, way, answers)
        except OSError as why:  # the backend's own command is not on this machine
            self._said = escape(f"{way.argv[0]}: {why}")
            self._fill()
            return
        # Signed in again is possibly a different account, and certainly a fresh answer to
        # what it runs: an account that has just changed hands is one to ask again.
        self._said = self._landed(
            one, status, runs=0 if status else await asks(one.cli, one.name)
        )
        self._told.append(
            f"[dim]{escape(one.cli)}/{escape(one.name)} is signed in[/dim]"
            if not status
            else f"hmz: {escape(way.argv[0])} exited {status}"
        )
        self._fill()

    @work
    async def action_speaks(self) -> None:
        """Asks for a CLI of your own that speaks ACP, and writes it down as a backend.

        Here rather than anywhere else because this is the moment somebody finds out that the
        agent they want to run is not one humanize drives. What is written down outlives the
        run, so it is a backend from the next prompt on, in this workspace and every other --
        which is why it is not one of the things this menu holds until it is saved.
        """
        from hmz import backends

        showing = cast(
            "App[None]",
            self.app,  # pyright: ignore[reportUnknownMemberType]
        )
        said = await showing.push_screen_wait(Speaks())
        if said is None:
            return
        command, name = said
        try:
            backends.remember(name, shlex.split(command))
        except (OSError, ValueError) as why:
            self._said = escape(str(why))
            self._fill()
            return
        self._said = f"{escape(name)} is a backend from here on"
        self._told.append(
            f"[dim]{escape(name)} is written down: `{escape(command)}` starts it, "
            "and it is a backend from here on[/dim]"
        )
        self._fill()

    def applied(self) -> None:
        """Does everything the menu was holding, and answers with what became of each."""
        from hmz import providers

        told = list(self._told)
        for one in self._found:
            named = self._named(one)
            if named in self._gone:
                continue  # taken away below, so there is nothing to correct or mark on it
            if (answers := self._edits.get(named)) is not None:
                try:
                    providers.add(one.cli, one.name, one.way, answers)
                except (OSError, ValueError) as why:
                    told.append(f"hmz: {escape(str(why))}")
                    continue
                told.append(f"[dim]{escape(named)} is corrected[/dim]")
            if named in self._marks:
                providers.marks(one.cli, one.name, fallback=not one.fallback)
                told.append(
                    f"[dim]{escape(named)} is "
                    + (
                        "no longer a fallback"
                        if one.fallback
                        else "where a turn goes when another account fails"
                    )
                    + "[/dim]"
                )
        for named in sorted(self._gone):
            cli, _, name = named.partition("/")
            try:
                gone = providers.remove(cli, name)
            except ValueError as why:  # a name nothing could ever have been kept under
                told.append(f"hmz: {escape(str(why))}")
                continue
            told.append(
                f"[dim]{escape(named)} is gone, credentials and all[/dim]"
                if gone
                else f"hmz: no provider {escape(named)}"
            )
        self.dismiss(told)

    def leaving(self) -> None:
        """Asks about what is held, and answers with what happened where nothing is.

        A menu that made an account and then held nothing still has something to say: what it
        did, it did as it was asked to, and the transcript is where that is said.
        """
        if not self._changed:
            self.dismiss(self._told or None)
            return
        self.asks_to_save()


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
                ("Flow", _flowing(self._flow)),
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

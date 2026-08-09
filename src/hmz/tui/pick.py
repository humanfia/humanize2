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

from hmz import telemetry
from hmz.agents import PERMISSIONS, SWARM, anchored, driver
from hmz.agents.skills import Skill, skills
from hmz.backends import named
from hmz.kept import Kept, Runs
from hmz.telemetry import KEPT, SAYS, SENT

from .discover import installed, machines, ready_to_open
from .monitor import Shape, short, thousands
from .selecting import Choices

if TYPE_CHECKING:
    from collections.abc import Callable, Generator, Mapping, Sequence

    from pydantic import BaseModel
    from pydantic.fields import FieldInfo
    from textual.app import App, ComposeResult

    from hmz.agents import AgentBase, Moment
    from hmz.backends import Model, Way
    from hmz.cycle import Ran
    from hmz.flows import Flowverse, Offer, Place
    from hmz.providers import Provider

    from .monitor import Monitor

__all__ = [
    "EVERY",
    "Account",
    "Accounts",
    "Agent",
    "Alike",
    "Anchors",
    "Backends",
    "Catalogue",
    "Chosen",
    "Clis",
    "Configures",
    "Confirms",
    "Cycles",
    "Does",
    "Doing",
    "Drafts",
    "Drawn",
    "Fitted",
    "Flows",
    "Flowverses",
    "Held",
    "Holds",
    "Imports",
    "Names",
    "Picks",
    "Providers",
    "Saved",
    "Sheet",
    "Signing",
    "Signs",
    "Skills",
    "Speaks",
    "Status",
    "Ways",
    "called",
    "carries_on",
    "config_of",
    "model_of",
    "opens_on",
    "places_of",
    "pointed",
    "reads",
    "setting",
    "settled",
]


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
    """What one agent of a running flow is holding, and whether it is the one being read.

    Attributes:
      many: How many conversations it has open, which is none for an agent that has opened
        none and for every agent of a flow that is not running.
      reading: Whether this agent's transcript is the one on the screen. All of its
        conversations are that one transcript, so this is a yes or a no rather than which of
        them: an agent is what is stepped onto, and a loop that opens one conversation a
        turn runs them all down the same screen.
      unread: Whether it has said something since it was last looked at.
      working: Whether any of its conversations has a turn open. Which is the first thing
        somebody looks for with several agents going at once -- who is thinking and who has
        stopped -- and the only one of these that changes by itself.
    """

    many: int = 0
    reading: bool = False
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
      Whether it is working, how many conversations it has, `reading` for the one whose
      transcript is on the screen and `unread` for one that has said something since it was
      last looked at. Nothing at all for an agent holding none, which is every agent of a
      flow that is not running.
    """
    if not held.many:
        return ""
    said = f"{_WORKING if held.working else _IDLE} {held.many}"
    if held.reading:
        return f"{said}{_DOT}reading"
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
            # Answered a menu and then threw the answers away, which is somebody finding out
            # that what they had done was not what they meant to do.
            telemetry.snag("changes-dropped", sheet=type(self).__name__)
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

    The first backend installed here that has said what it runs and can be opened without
    further setup, at the first model it named -- which is that CLI's own idea of what it runs
    by default, and the only idea of it worth having. Nothing is written down here: a model
    named in this file would be a model this file was right about on the day it was written.

    Args:
      agents: The backends there are, and what each of them says it runs.
      goals: Whether backend goals start available to it.

    Returns:
      The one agent, or nothing at all where no backend here has both said what it runs and
      can be opened without further setup.
    """
    where = Path.cwd()
    for backend, found in agents.items():
        if found and ready_to_open(backend, where):
            # Not the hardest effort, which is where the cursor starts: that is the one to
            # reach for, and this is the one to spend before anybody has asked for anything.
            # `high` where the model takes it, which is nearly always -- and the least it
            # does take otherwise, since a model that is offered at three efforts and run at
            # a fourth is a turn its backend refuses before it starts.
            one = found[0]
            # And no effort at all for a model that takes none, which is what a backend
            # whose models carry their own effort in their names says of the rest of them.
            effort = "high" if "high" in one.efforts else ""
            if not effort and one.efforts:
                effort = one.efforts[-1]
            return [Runs(f"{backend}/{one.name}:{effort}", goals=goals)]
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
    from hmz.flows import wanted

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
    from hmz.flows import configures

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
_SAVE = "save"


#: What this project's own flows are listed under, which is where a copy of one lands: the
#: first of the places a flow of your own may be, as `hmz.flows` names them.
_MINE = "local"


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
    walking past every flow that came before it. Stepping between the places is about which
    list of flows is being read; what can happen to a flowverse is `/flowverses`, which is a
    question about the places rather than about which flow to run.

    Choosing a flow asks what that flow itself takes, where it takes anything, and then turns
    to what will drive it. A key that set the flow up was a key nobody pressed: a flow with
    settings is chosen in order to be run with settings, and the moment it is chosen is the
    one moment somebody is thinking about that flow rather than about its agents.

    Nothing is applied by turning a page. What the menu holds is a draft of the whole of it,
    and it lands together from the save row or when saving is confirmed on the way out.
    """

    TABS: ClassVar = ("Flow", "Agents")
    LETTERS: ClassVar = frozenset({"search", "fork"})

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
        Binding("f", "fork", "copy it here to change", priority=True),
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
        from hmz.kept import read_back

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

            await self._fetches(name, fetching)

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
            "Enter opens one, and save applies the complete flow setup."
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
            f"Enter to choose · f copies it here · Esc to close{self.searching()}"
        )

    def _empty(self, whose: str) -> str:
        """What a place with no flows in it says on the row where its flows would be."""
        verse = self._verse(whose)
        if verse is not None and not verse.fetched:
            return "not fetched yet; /flowverses fetches it"
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
        """Puts up each agent the flow drives, followed by saving the complete setup."""
        listing = self.query_one("#choices", OptionList)
        named = tuple(place.name for place in self._places)
        lines = reads(named, self._runs)
        total = len(self._places) + 1
        self._counting = len(str(total))
        at = min(listing.highlighted or 0, total - 1)
        rows = [
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
        ]
        rows.append(
            Option(
                self._row(
                    len(self._places),
                    _SAVE,
                    "save the flow and all of its agents",
                    here=at == len(self._places),
                    inforce=False,
                ),
                id=f"={_SAVE}",
            )
        )
        listing.set_options(rows)
        listing.highlighted = at
        self._drawn = listing.highlighted
        said = self._said or ("" if self._places else self._noagents())
        self.query_one("#tuning", Label).update(
            f"[$text-muted]{said}[/]" if said else ""
        )
        self.query_one("#keys", Label).update(
            "Enter to save · Esc to close"
            if at == len(self._places)
            else "Enter to set one up · Esc to close"
        )

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

    def action_fork(self) -> None:
        """Copies the flow under the cursor into this project's own, to be changed.

        A flow is a directory, so a copy of one is a flow of yours: the entry point, what it
        imports and the skills it brings all come across, under the name it already had --
        and your own flows are looked in first, so from then on that name means your copy.

        Which is the way to change a flow at all. A flowverse is somebody else's repository,
        fetched again over whatever was written into it, so an edit made there is an edit
        that goes away; a copy here is yours, and is what `f` is for.
        """
        from hmz.flows import fork

        if self._tab != _FLOW_PAGE:
            return
        named = self._was.partition(_HALVES)[2]
        if not named:
            self._said = "no flow under the cursor to copy"
            self._fill()
            return
        try:
            at = fork(named)
        except (OSError, ValueError) as why:
            self._said = escape(str(why))
            self._fill()
            return
        # The list is something else now: there is a flow of yours that was not there, and
        # the name it took means it from here on.
        self._offers, self._was = None, ""
        self._where = _MINE
        mine = escape(named.rpartition("/")[2])
        self._said = (
            f"copied to {escape(at)} -- yours to change, and {mine} now means it"
        )
        self._fill()

    async def _fetches(self, named: str, doing: Callable[[], str]) -> None:
        """Runs one git fetch off the event loop, and shows the list it left behind.

        Off the loop because a clone is seconds of network: a menu that stopped redrawing
        while it ran would be one that looked as though it had gone away. What is being read
        is left where it is: this is the flowverse nobody has fetched being fetched because
        its flows are wanted, rather than somebody asking to be taken to it.

        Args:
          named: What is being fetched, said under the list while it runs.
          doing: What to do, answering with the flowverse it left behind.
        """
        import asyncio

        if self._fetching:
            return
        self._fetching, self._said = named or "it", ""
        self._fill()
        try:
            await asyncio.to_thread(doing)
        except (OSError, ValueError) as why:
            # Said under the list rather than raised at whoever opened the menu: the question
            # this page is asking is still worth answering.
            self._said = escape(str(why))
            self._fetching = ""
            self._fill()
            return
        self._fetching, self._offers = "", None
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
        held = str(event.option.id or "").removeprefix("=")
        if held == _SAVE:
            self.applied()
            return
        try:
            at = int(held)
        except ValueError:
            return
        self._configuring(at)

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
            telemetry.snag("save-refused", missing=len(missing))
            self._said = f"{escape(', '.join(missing))} has no model yet"
            self._fill()
            return
        self.dismiss(Chosen(self._flow, tuple(self._runs), self._config))


def _added(url: str, name: str) -> str:
    """Fetches a flowverse and answers with what it is called here."""
    from hmz.flows.verses import add

    return add(url, name).name


def _came_from(one: Flowverse) -> str:
    """Where a flowverse came from, as a row may show it.

    Asked of which flowverse it is rather than of whether its URL is empty: an empty URL
    means both `the package's own` and `a directory whose origin could not be read`, and
    answering the second with the first would put humanize's name on somebody else's flows.

    Args:
      one: The flowverse.

    Returns:
      The URL with whatever was signed into it taken out -- a private one is added as
      `https://x-access-token:$TOKEN@...`, and this is drawn where somebody can read it --
      or a phrase for the two that came from nowhere.
    """
    from hmz.flows.verses import BUILTIN, plain

    if one.name == BUILTIN:
        return "the flows humanize ships"
    return plain(one.url) if one.url else "not a clone of anything"


class Holds(Sheet[None]):
    """What one flowverse holds, which is read rather than chosen from.

    A reading and not a menu: which flow to run is asked on `/flow`, where the flows of every
    place are walked. This is the other question -- what is in this one -- and it is the one
    question about a flowverse that costs something to answer, since what a file holds is not
    a fact its name carries: reading a flow means running it.
    """

    LETTERS: ClassVar = frozenset({"search"})

    BINDINGS: ClassVar = [
        ("escape", "back", "back"),
        Binding("s", "search", "search", priority=True),
    ]

    def __init__(self, one: Flowverse) -> None:
        """Reads one flowverse's flows.

        Args:
          one: The flowverse.
        """
        super().__init__()
        self._verse = one
        self._offers: list[Offer] | None = None

    def _ask(self) -> None:
        """Says which flowverse this is, and puts its flows up."""
        self.query_one("#asked", Label).update(self._verse.name)
        self.query_one("#about", Label).update(
            f"What this flowverse holds, read from {escape(_came_from(self._verse))}. "
            "Which of them to run is asked on /flow, where every place's flows are."
        )
        self._fill()
        self.query_one("#choices", OptionList).focus()

    def _flows(self) -> list[Offer]:
        """The flows it holds, read once: reading one means running its entry point."""
        from hmz.flows import offers

        if self._offers is None:
            try:
                self._offers = offers(self._verse)
            except OSError:
                self._offers = []
        return self._offers

    def _fill(self) -> None:
        """Puts the flows up, each with the line it says about itself."""
        listing = self.query_one("#choices", OptionList)
        shown = [one for one in self._flows() if self.fits(one.name, one.about)]
        self._counting = len(str(max(len(shown), 1)))
        at = min(listing.highlighted or 0, max(len(shown) - 1, 0))
        listing.set_options(
            Option(
                self._row(
                    seen,
                    one.name,
                    _briefly(one.about, self.size.width),
                    here=seen == at,
                    inforce=False,
                ),
                id=f"={one.name}",
            )
            for seen, one in enumerate(shown)
        )
        listing.highlighted = at if shown else None
        self._drawn = listing.highlighted
        said = "" if shown else self._nothing()
        self.query_one("#tuning", Label).update(
            f"[$text-muted]{said}[/]" if said else ""
        )
        self.query_one("#keys", Label).update(f"Esc to close{self.searching()}")

    def _nothing(self) -> str:
        """Why there is nothing in it, which is not always the same reason."""
        if not self._verse.fetched:
            return "not fetched yet; r fetches it"
        if self._typed:
            return "no flow of that name in it"
        return "nothing in it: a flowverse keeps its flows in flows/"


class Flowverses(Sheet[list[str]]):
    """The places flows come from: what there is, what one holds, and what can happen to one.

    Its own menu rather than keys on the one a flow is chosen at. Adding a repository,
    fetching one again and taking one away are things done to the list of places rather than
    to the flow under the cursor, and a sheet that asks `which flow` with three keys on it
    about something else is a sheet asking two questions. `/flow` still steps between the
    places with the arrows, that being about which list of flows is being read.

    What happens here happens as it is asked for rather than being held until the menu is
    saved: each of these runs git, and something that has already been cloned is not a draft.
    """

    LETTERS: ClassVar = frozenset({"search", "adding", "refresh", "drop"})

    BINDINGS: ClassVar = [
        ("escape", "back", "back"),
        Binding("s", "search", "search", priority=True),
        Binding("a", "adding", "add one", priority=True),
        Binding("r", "refresh", "fetch it again", priority=True),
        Binding("d", "drop", "take it away", priority=True),
    ]

    def __init__(self) -> None:
        """Reads every flowverse there is."""
        super().__init__()
        self._found: list[Flowverse] = []
        #: Which one the cursor is on, by name: a search narrows the rows, so a row number is
        #: not a flowverse.
        self._was = ""
        #: What became of the last thing that happened, said under the list.
        self._said = ""
        #: What is being fetched now, so that a second fetch is not started over it.
        self._fetching = ""
        #: What is worth saying in the transcript once this menu is done with.
        self._told: list[str] = []

    def _ask(self) -> None:
        """Says what these are, and puts them up."""
        self.query_one("#asked", Label).update("Flowverses")
        self.query_one("#about", Label).update(
            "Where flows come from: a git repository with a flows/ directory apiece, cloned "
            "under humanize's home and offered under the name it is kept there. Enter says "
            "what one holds. What happens here happens as it is asked for."
        )
        self._read()
        self._fill()
        self.query_one("#choices", OptionList).focus()

    def _read(self) -> None:
        """Reads the flowverses off the disk, which is what the rows are drawn from."""
        from hmz.flows import flowverses

        self._found = flowverses()

    def _about(self, one: Flowverse) -> str:
        """What a row says about one flowverse: where it came from, and whether it is here."""
        said = _came_from(one)
        if not one.fetched:
            return f"{said}{_DOT}not fetched yet"
        return said

    def _fill(self) -> None:
        """Puts the flowverses up, marked where the cursor is."""
        listing = self.query_one("#choices", OptionList)
        self._follows(listing)
        shown = [one for one in self._found if self.fits(one.name, one.url)]
        self._counting = len(str(max(len(shown), 1)))
        if all(one.name != self._was for one in shown):
            self._was = shown[0].name if shown else ""
        listing.set_options(
            Option(
                self._row(
                    seen,
                    one.name,
                    self._about(one),
                    here=one.name == self._was,
                    inforce=False,
                ),
                id=f"={one.name}",
            )
            for seen, one in enumerate(shown)
        )
        listing.highlighted = (
            next((at for at, one in enumerate(shown) if one.name == self._was), 0)
            if shown
            else None
        )
        self._drawn = listing.highlighted
        said = f"fetching {escape(self._fetching)}…" if self._fetching else self._said
        self.query_one("#tuning", Label).update(
            f"[$text-muted]{said}[/]" if said else ""
        )
        self.query_one("#keys", Label).update(
            "Enter says what one holds · a adds one · r fetches one again · "
            f"d twice takes one away · Esc to close{self.searching()}"
        )

    def _follows(self, listing: OptionList) -> None:
        """Takes which flowverse the cursor is on off the list, by name."""
        at = listing.highlighted
        if at is not None and 0 <= at < listing.option_count:
            named = str(listing.get_option_at_index(at).id or "").removeprefix("=")
            if named:
                self._was = named

    def _under(self) -> Flowverse | None:
        """The flowverse the cursor is on, or None where the list has nothing in it."""
        return next((one for one in self._found if one.name == self._was), None)

    @on(OptionList.OptionSelected)
    def _took(self, event: OptionList.OptionSelected) -> None:
        """Opens what the flowverse under the cursor holds.

        Args:
          event: What was chosen.
        """
        named = str(event.option.id or "").removeprefix("=")
        one = next((each for each in self._found if each.name == named), None)
        if one is not None:
            self._holds(one)

    @work
    async def _holds(self, one: Flowverse) -> None:
        """Reads what one flowverse holds, which means running each flow in it."""
        showing = cast(
            "App[None]",
            self.app,  # pyright: ignore[reportUnknownMemberType]
        )
        await showing.push_screen_wait(Holds(one))
        self._fill()

    @work
    async def action_adding(self) -> None:
        """Asks where a flowverse is and what to call it here, and clones it."""
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

        one = self._under()
        if one is None:
            return
        if not one.url:
            self._said = (
                f"{escape(one.name)} came with humanize; there is nothing to fetch"
            )
            self._fill()
            return
        name = one.name

        def fetching() -> str:
            fetch(name)
            return name

        await self._fetches(name, fetching)

    def action_drop(self) -> None:
        """Takes the flowverse under the cursor away, flows and all, once d is twice."""
        from hmz.flows.verses import remove

        one = self._under()
        if one is None:
            return
        if not self._armed(one.name):
            self._said = f"press d again to take {escape(one.name)} away, flows and all"
            self._fill()
            return
        try:
            remove(one.name)
        except (OSError, ValueError) as why:
            self._said = escape(str(why))
            self._fill()
            return
        self._said = f"{escape(one.name)} is no longer here"
        self._told.append(f"[dim]{escape(one.name)} is no longer here[/dim]")
        self._was = ""
        self._read()
        self._fill()

    async def _fetches(self, named: str, doing: Callable[[], str]) -> None:
        """Runs one git fetch off the event loop, and shows the list it left behind.

        Off the loop because a clone is seconds of network: an interface that stopped
        redrawing while it ran would be one that looked as though it had gone away.

        Args:
          named: What is being fetched, said under the list while it runs.
          doing: What to do, answering with the flowverse it left behind.
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
            self._said, self._fetching = escape(str(why)), ""
            self._fill()
            return
        self._fetching = ""
        self._said = f"{escape(name)} is fetched"
        self._told.append(f"[dim]{escape(name)} is fetched[/dim]")
        self._read()
        self._was = name
        self._fill()

    def leaving(self) -> None:
        """Leaves, saying in the transcript whatever happened while this was open."""
        self.dismiss(self._told or None)


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


class Skills(Sheet[None]):
    """What one CLI would load here, shown and not touched.

    A skill installed on this machine is that CLI's own: installed the way it installs one,
    switched off the way it switches one off, and the same for every agent of every flow.
    humanize used to switch them per agent and no longer does -- what a person has installed
    is not something a flow is entitled to rewrite, and a list that could be adjusted here
    while the CLI's own list said otherwise was two answers to one question.

    So this is a reading: what the agent will be carrying, where each of them came from, and
    the line saying where to go to change it. What humanize does add is the flow's own
    skills, which are mounted onto the sessions it opens rather than installed here.
    """

    LETTERS: ClassVar = frozenset({"search"})

    BINDINGS: ClassVar = [
        ("escape", "back", "back"),
        Binding("s", "search", "search", priority=True),
        # Enter leaves it, as escape does: there is nothing on this sheet to answer with, so
        # the key that accepts a sheet is the key that closes this one.
        Binding("enter", "back", "done", priority=True),
    ]

    def __init__(self, backend: str) -> None:
        """Initializes the reading.

        Args:
          backend: The CLI whose skills these are.
        """
        super().__init__()
        self._backend = backend
        self._found: list[Skill] | None = None

    def _ask(self) -> None:
        """Says whose skills these are, and who is to be asked to change them."""
        self.query_one("#asked", Label).update(f"What {self._backend} loads here")
        self.query_one("#about", Label).update(
            "The skills this CLI finds, which every agent of it carries. They are its own: "
            f"install one, or switch one off, the way {escape(self._backend)} itself does "
            "it. A flow's own skills are mounted onto the sessions it opens and are not "
            "installed here."
        )
        self._fill()
        self.query_one("#choices", OptionList).focus()

    def _skills(self) -> list[Skill]:
        """The skills there are to show, read once: this is redrawn per keystroke."""
        if self._found is None:
            self._found = skills(self._backend)
            self._counting = len(str(len(self._found)))
        return self._found

    def _fill(self) -> None:
        """Puts the skills up, each with where it came from."""
        listing = self.query_one("#choices", OptionList)
        shown = [
            skill
            for skill in self._skills()
            if self.fits(skill.name, skill.about, skill.whose)
        ]
        at = min(listing.highlighted or 0, max(len(shown) - 1, 0))
        listing.set_options(
            Option(
                self._row(
                    seen,
                    skill.name,
                    f"{skill.about}  ({skill.whose})" if skill.about else skill.whose,
                    here=seen == at,
                    inforce=False,
                ),
                id=skill.name,
            )
            for seen, skill in enumerate(shown)
        )
        listing.highlighted = at if shown else None
        self._drawn = at
        self.query_one("#tuning", Label).update(
            f"[$text-muted]{self._said()}[/]" if self._said() else ""
        )
        self.query_one("#keys", Label).update(f"Esc to go back{self.searching()}")

    def _said(self) -> str:
        """The line under the list: where to go to change any of this, or why there is none.

        Returns:
          That these are the CLI's own and are managed there, for a CLI that keeps skills;
          that a CLI which keeps none anywhere has none to show; and, where it keeps them
          and none is installed, that there are none here yet.
        """
        profile = named(self._backend)
        if profile is None or not (
            profile.skills or profile.shared or profile.config or profile.works
        ):
            return f"{escape(self._backend)} keeps no skills of its own here"
        if not self._skills():
            return (
                f"{escape(self._backend)} has none installed here; install one the way "
                f"{escape(self._backend)} installs one"
            )
        return (
            f"These are {escape(self._backend)}'s own: add one, or switch one off, where "
            f"{escape(self._backend)} keeps them"
        )


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


class Falls(Sheet[str]):
    """Which account a turn under this one carries on under when it fails.

    A name rather than a mark: each account names the next, so what a turn walks is a chain
    -- a subscription that runs out falls to a key, and a key that is refused falls to a
    gateway -- rather than there being one place every failure of that CLI goes.

    Only that CLI's own accounts are offered: an account is credentials for one backend, and
    a turn cannot be carried on under credentials for another.
    """

    LETTERS: ClassVar = frozenset({"search"})

    BINDINGS: ClassVar = [
        ("escape", "back", "back"),
        Binding("s", "search", "search", priority=True),
    ]

    def __init__(self, cli: str, name: str, current: str = "") -> None:
        """Initializes the choosing.

        Args:
          cli: The backend these accounts are of.
          name: The account this is about, which is not among the ones offered.
          current: What it falls back to now, or "" for the end of the line.
        """
        super().__init__()
        self._cli = cli
        self._name = name
        self._current = current
        self._found: list[Provider] | None = None

    def _ask(self) -> None:
        """Says whose accounts these are, and what carrying on under one means."""
        self.query_one("#asked", Label).update(
            f"Where {self._cli}/{self._name} falls back to"
            if self._name
            else f"Where {self._cli}, as this machine is signed in, falls back to"
        )
        self.query_one("#about", Label).update(
            "The account a turn under this one carries on under, once the tries it was "
            "given are spent. It happens inside the conversation that was running, and the "
            "account it moves to has a fallback of its own -- so what a turn walks is a "
            "chain, to the end of it."
        )
        self.query_one("#tuning", Label).update("")
        self._fill()

    def _accounts(self) -> list[Provider]:
        """That CLI's own accounts, read once: this is redrawn per keystroke."""
        from hmz import providers

        if self._found is None:
            self._found = [
                one for one in providers.providers(self._cli) if one.name != self._name
            ]
        return self._found

    def _fill(self) -> None:
        """Puts the accounts up, with the end of the line first."""
        listing = self.query_one("#choices", OptionList)
        rows: list[tuple[str, str, str]] = [
            ("", "nowhere", "the end of the line: a failed turn is a failed turn")
        ]
        rows.extend((one.name, one.name, _sets(one)) for one in self._accounts())
        shown = [row for row in rows if self.fits(row[1], row[2])]
        self._counting = len(str(max(len(shown), 1)))
        at = min(listing.highlighted or 0, max(len(shown) - 1, 0))
        listing.set_options(
            Option(
                self._row(
                    seen, label, about, here=seen == at, inforce=name == self._current
                ),
                id=f"={name}",
            )
            for seen, (name, label, about) in enumerate(shown)
        )
        listing.highlighted = at if shown else None
        self._drawn = at
        self.query_one("#tuning", Label).update(
            ""
            if self._accounts()
            else f"[$text-muted]{escape(self._cli)} has no other account to fall back "
            "to; a on the menu behind this makes one[/]"
        )
        self.query_one("#keys", Label).update(
            f"Enter to choose · Esc to go back{self.searching()}"
        )

    @on(OptionList.OptionSelected)
    def _took(self, event: OptionList.OptionSelected) -> None:
        """Answers with the account that was picked, or "" for the end of the line."""
        self.dismiss(str(event.option.id).removeprefix("="))


#: How many times over a turn may be tried again, and how long the retrying may be given.
#: Rungs rather than a number to type: this is a setting somebody steps through until it
#: reads right, and a text box for an integer is a text box to validate.
_TRIES = (0, 1, 2, 3, 5, 8, 13, 21)
_FOR = (0.0, 30.0, 60.0, 300.0, 900.0, 3600.0)

#: The rows the retry sheet is made of.
_HOW_MANY = "tries"
_POLICY = "policy"
_HOW_LONG = "for"


class Retries(Sheet[tuple[int, str, float]]):
    """How a turn under one account is tried again before the chain moves on.

    A turn fails for two kinds of reason and only one of them is worth another try: a prompt
    the model refused is the same refusal every time, and a gateway that answered 503 is the
    same call away from working. So an account says how many tries it gets, how long to wait
    between them, and how long the whole of it may go on for.

    Three rungs rather than three things to type: each is stepped where it stands, which is
    how every other setting in an order is answered here.
    """

    BINDINGS: ClassVar = [
        ("escape", "back", "back"),
        Binding("left", "easier", "back one", priority=True),
        Binding("right", "harder", "on one", priority=True),
        Binding("enter", "done", "done", priority=True),
    ]

    def __init__(self, named: str, retries: int, policy: str, timeout: float) -> None:
        """Initializes the sheet on what the account says now.

        Args:
          named: The account this is about, which the question at the top says.
          retries: How many tries beyond the first it gets now.
          policy: How long it waits between them now.
          timeout: The longest the retrying may go on for now, or 0.0 for no limit.
        """
        super().__init__()
        self._named = named
        self._retries = retries
        self._policy = policy
        self._timeout = timeout

    def _ask(self) -> None:
        """Says whose account this is about, and what trying again means."""
        self.query_one("#asked", Label).update(f"How {self._named} is tried again")
        self.query_one("#about", Label).update(
            "What happens when a turn under this account fails. The arrows step the row "
            "under the cursor. Once the tries are spent, the turn carries on under whatever "
            "this account falls back to."
        )
        self._fill()
        self.query_one("#choices", OptionList).focus()

    def _rows(self) -> list[tuple[str, str, str]]:
        """Every row this is made of: its id, what it is now, and what it means."""
        from hmz.providers import retry

        said = retry.named(self._policy)
        return [
            (
                _HOW_MANY,
                "none" if not self._retries else str(self._retries),
                "how many times over a failed turn is tried again",
            ),
            (
                _POLICY,
                self._policy,
                said.about if said is not None else "how long to wait between tries",
            ),
            (
                _HOW_LONG,
                _lasting(self._timeout),
                "the longest the trying again may go on for",
            ),
        ]

    def _fill(self) -> None:
        """Puts the three rows up, with the cursor where it was."""
        listing = self.query_one("#choices", OptionList)
        rows = self._rows()
        self._counting = len(str(len(rows)))
        at = min(listing.highlighted or 0, len(rows) - 1)
        listing.set_options(
            Option(
                self._row(
                    seen, name, f"{value}   {about}", here=seen == at, inforce=False
                ),
                id=f"={name}",
            )
            for seen, (name, value, about) in enumerate(rows)
        )
        listing.highlighted = at
        self._drawn = at
        self.query_one("#tuning", Label).update(
            "[$text-muted]none, and a failed turn is a failed turn[/]"
            if not self._retries
            else ""
        )
        self.query_one("#keys", Label).update(
            "Left and right to step this one · Enter to accept · Esc to go back"
        )

    def action_easier(self) -> None:
        """Steps the row under the cursor back one."""
        self._step(-1)

    def action_harder(self) -> None:
        """Steps it on one."""
        self._step(1)

    def _step(self, by: int) -> None:
        """Moves whichever row the cursor is on, wrapping round at either end.

        Args:
          by: One rung on or back.
        """
        from hmz.providers import retry

        listing = self.query_one("#choices", OptionList)
        at = listing.highlighted or 0
        held = self._rows()[at][0] if 0 <= at < len(self._rows()) else ""
        if held == _HOW_MANY:
            self._retries = _stepped(_TRIES, self._retries, by)
        elif held == _POLICY:
            names = [one.name for one in retry.POLICIES]
            self._policy = _stepped(names, self._policy, by)
        elif held == _HOW_LONG:
            self._timeout = _stepped(_FOR, self._timeout, by)
        else:
            return
        self._fill()

    def action_done(self) -> None:
        """Answers with what the account is to say from here on."""
        self.dismiss((self._retries, self._policy, self._timeout))


def _stepped[T](among: Sequence[T], held: T, by: int) -> T:
    """One rung on or back through a list, wrapping round and starting from the nearest.

    Args:
      among: The rungs, in order.
      held: What it is now, which need not be one of them -- a setting written by hand is
        stepped from the first rung rather than refused.
      by: One on or back.

    Returns:
      The rung to move to.
    """
    at = among.index(held) if held in among else 0
    return among[(at + by) % len(among)]


def _lasting(seconds: float) -> str:
    """How long something may go on for, as a row of a sheet says it."""
    if not seconds:
        return "as long as it takes"
    if seconds < 60:  # noqa: PLR2004 -- a minute, in the units the number is in
        return f"{seconds:.0f}s"
    return f"{seconds / 60:.0f}m"


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
    from hmz.flows import running

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


class Alike(Sheet[tuple[str, ...]]):
    """Which other CLIs to write one account down for as well.

    A vendor's credential is the vendor's rather than the CLI's: an Anthropic key is an
    Anthropic key whether Claude Code, pi, opencode or mimocode is holding it. So an account
    just made is often an account several other backends could be run as, and this is the
    moment to say so -- making the same key four times by hand is four places to correct when
    it is rotated.

    A form of switches rather than a list to pick from: it asks about all of them at once.
    The ones installed here start on, since those are the ones an agent could be run on
    tomorrow; the rest are listed and off, an account being worth writing down before the CLI
    that will use it is on this machine.
    """

    LETTERS: ClassVar = frozenset()

    BINDINGS: ClassVar = [
        ("escape", "back", "back"),
        # Enter is the whole form rather than the row under the cursor, as it is on every
        # other sheet here that is written into rather than picked from.
        Binding("enter", "done", "done", priority=True),
        Binding("space", "flip", "turn one on or off", priority=True),
        Binding("left", "off", "off", priority=True),
        Binding("right", "on", "on", priority=True),
    ]

    def __init__(self, one: Provider, among: Sequence[str]) -> None:
        """Asks about one account.

        Args:
          one: The account that has just been made or corrected.
          among: The other backends it could be run as, in the order to show them.
        """
        super().__init__()
        self._one = one
        self._among = list(among)
        here = installed()
        self._on = {cli for cli in self._among if cli in here}

    def _ask(self) -> None:
        """Says what this is, and puts the backends up."""
        self.query_one("#asked", Label).update(
            f"{self._one.cli}/{self._one.name} runs more than {self._one.cli}"
        )
        self.query_one("#about", Label).update(
            "What this account holds is the vendor's rather than the CLI's, so these "
            "backends could each be run as it. Copying it writes the same account down for "
            "them under the same name, over one already there -- which is how a key rotated "
            "is a key rotated everywhere at once."
        )
        self._fill()
        self.query_one("#choices", OptionList).focus()

    def _fill(self) -> None:
        """Puts the backends up, each with its switch."""
        listing = self.query_one("#choices", OptionList)
        self._counting = len(str(max(len(self._among), 1)))
        at = min(listing.highlighted or 0, max(len(self._among) - 1, 0))
        here = installed()
        listing.set_options(
            Option(
                self._row(
                    seen,
                    cli,
                    "installed here" if cli in here else "not installed here yet",
                    here=seen == at,
                    inforce=False,
                    box="[x]" if cli in self._on else "[ ]",
                ),
                id=f"={cli}",
            )
            for seen, cli in enumerate(self._among)
        )
        listing.highlighted = at if self._among else None
        self._drawn = at
        self.query_one("#tuning", Label).update("")
        self.query_one("#keys", Label).update(
            "Space or the arrows turn one on and off · Enter copies it to the ones on · "
            "Esc copies it to none"
        )

    def action_flip(self) -> None:
        """Turns the one under the cursor round."""
        self._steps()

    def action_on(self) -> None:
        """Turns it on."""
        self._steps(onto=True)

    def action_off(self) -> None:
        """Turns it off."""
        self._steps(onto=False)

    def _steps(self, *, onto: bool | None = None) -> None:
        """Sets the switch under the cursor.

        Args:
          onto: What to set it to, or None to turn it round.
        """
        listing = self.query_one("#choices", OptionList)
        at = listing.highlighted
        if at is None or not 0 <= at < len(self._among):
            return
        cli = self._among[at]
        wanted = (cli not in self._on) if onto is None else onto
        if wanted:
            self._on.add(cli)
        else:
            self._on.discard(cli)
        self._fill()

    @on(OptionList.OptionSelected)
    def _took(self, event: OptionList.OptionSelected) -> None:
        """Answers with everything switched on, enter being the whole form.

        Args:
          event: What was chosen, which is unread: the row is not what this asks about.
        """
        del event
        self.action_done()

    def action_done(self) -> None:
        """Answers with the backends to copy this account to, in the order they were shown."""
        self.dismiss(tuple(cli for cli in self._among if cli in self._on))


async def also(host: App[None], one: Provider) -> tuple[str, ...]:
    """Asks which other backends to write one account down for, and writes it down for them.

    Args:
      host: The interface, which is what the sheet is pushed onto.
      one: The account.

    Returns:
      What it was copied to, and nothing at all where it could run nothing else, where the
      question was walked out of, or where every copy failed.
    """
    from hmz import providers

    among = providers.serves(one)
    if not among:
        return ()
    said = await host.push_screen_wait(Alike(one, among))
    copied: list[str] = []
    for cli in said or ():
        try:
            providers.copies(one, cli)
        except (OSError, ValueError):
            continue  # a backend that will not take it is one it is not copied to
        copied.append(cli)
    return tuple(copied)


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
      copied: The other backends this account was written down for as well, which is nothing
        for one that could run nothing else and for one nobody asked to copy.
    """

    provider: Provider | None = None
    status: int = 0
    why: str = ""
    way_runs: bool = False
    runs: int = 0
    copied: tuple[str, ...] = ()


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
        return Made(
            provider=provider,
            runs=await asks(cli, provider.name),
            # And, for an account several backends could be run as, which of them to write
            # it down for too -- asked here because this is the moment it exists.
            copied=await also(host, provider),
        )
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
        copied=() if status else await also(host, provider),
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


#: The row on the list of backends that is not a backend: a CLI of your own, driven over the
#: Agent Client Protocol. Written down here because this is the moment somebody finds out
#: that the agent they want to run is not one humanize drives -- which is a question about
#: which CLI, and so belongs on the sheet that asks which CLI.
_SPEAKS = "\x00speaks"


class Backends(Picks):
    """Which coding agent a new account is for.

    Every backend humanize drives rather than the ones installed here: an account is
    credentials, and credentials are worth writing down before the CLI that will use them is
    on this machine. And, last, the one row here that is not an account at all: a CLI of your
    own that speaks ACP, which is what somebody who has got this far and cannot find their
    agent in the list came to say.
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
        ] + [
            (
                _SPEAKS,
                "a CLI of your own",
                "one that speaks ACP, written down as a backend from here on",
            )
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


#: The two answers to the question humanize asks about itself on a first start.
_REPORTS, _QUIET = "on", "off"

#: The rows the settings menu is made of, by the id each is put up under.
_SENTRY = "reports"
_SENT = "sent"
_WORKSPACE = "workspace"
_RUNS = "flow"
_PROFILES = "profile"
_FORGET = "forget"


class Adjusted(NamedTuple):
    """What the settings menu answers with: what to change, and what to forget.

    Attributes:
      enable_sentry: Whether humanize reports its own failures from now on, or None where
        that was not touched.
      profile: Whether a run in this directory is profiled as well as traced.
      forget: Whether to forget what this workspace was set up to run.
    """

    enable_sentry: bool | None = None
    profile: bool = False
    forget: bool = False


class Adjusts(Drafts[Adjusted]):
    """What humanize remembers: the settings that are everywhere, and this directory's.

    Two pages because they are two kinds of thing rather than two halves of one. What is on
    the first is true of this machine however many projects are driven from it -- whether
    humanize reports its own failures is the whole of it today -- and what is on the second is
    one directory's: the flow it opens on, and the agents that flow was last set up with.

    A menu rather than a file to edit, for the reason every other menu here is one: what is
    written down is written down in humanize's own words, and a person should not have to know
    the shape of a YAML file to turn a thing off. Nothing lands until it is left and saving is
    confirmed, exactly as everywhere else.
    """

    TABS: ClassVar = ("Everywhere", "This directory")

    BINDINGS: ClassVar = [
        ("escape", "back", "back"),
        Binding("tab", "next_tab", "next page", priority=True),
        Binding("shift+tab", "prev_tab", "previous page", priority=True),
        Binding("left", "easier", "back one", priority=True),
        Binding("right", "harder", "on one", priority=True),
    ]

    def __init__(
        self,
        *,
        enable_sentry: bool | None,
        workspace: str,
        flow: str,
        agents: int,
        flows: int,
        overridden: bool = False,
        profile: bool = False,
    ) -> None:
        """Initializes the menu on what is remembered now.

        Args:
          enable_sentry: Whether humanize reports its own failures, or None while nobody has
            been asked.
          workspace: The directory this is the second page of.
          flow: The flow it was last set up to run, or "" for one it never was.
          agents: How many agents that flow was set up with here.
          flows: How many flows this directory has been set up to run.
          overridden: Whether the environment is answering the reporting question for this
            run, so that a row saying one thing while humanize does another says so.
          profile: Whether a run here is profiled as well as traced.
        """
        super().__init__()
        self._sentry = enable_sentry
        self._overridden = overridden
        self._workspace = workspace
        self._flow = flow
        self._agents = agents
        self._flows = flows
        self._profile = profile
        self._forget = False
        self._said = (
            f"{SAYS} is set, so this run does the opposite of what this says"
            if overridden
            else ""
        )

    def _ask(self) -> None:
        """Says what the menu is, and puts up the page it opened on."""
        self.query_one("#asked", Label).update("Settings")
        self._fill()
        self.query_one("#choices", OptionList).focus()

    def _rows(self) -> list[tuple[str, str, str]]:
        """The rows of whichever page is open: its id, what it says, and what it means."""
        if self._tab:
            return [
                (
                    _WORKSPACE,
                    _shortly(self._workspace),
                    "the directory these are remembered for",
                ),
                (
                    _RUNS,
                    self._flow or "nothing yet",
                    f"the flow it opens on, set up with {_many(self._agents, 'agent')}",
                ),
                (
                    _PROFILES,
                    _YES if self._profile else _NO,
                    "profile the programs a run here starts",
                ),
                (
                    _FORGET,
                    _YES if self._forget else _NO,
                    f"forget what is remembered here, across {_many(self._flows, 'flow')}",
                ),
            ]
        return [
            (
                _SENTRY,
                {True: _YES, False: _NO, None: "not answered yet"}[self._sentry],
                "report what goes wrong to humanize",
            ),
            (_SENT, "", "what a report carries, and what it never does"),
        ]

    def _fill(self) -> None:
        """Puts up whichever page is open, and the titles above it."""
        self.query_one("#about", Label).update(
            "What humanize remembers about this machine. The arrows step the row under the "
            "cursor. Nothing lands until this menu is left and saving is confirmed."
            if not self._tab
            else "What humanize remembers about this directory: the flow it opens on, and "
            "what that flow was last set up to run."
        )
        listing = self.query_one("#choices", OptionList)
        rows = self._rows()
        self._counting = len(str(len(rows)))
        at = min(listing.highlighted or 0, len(rows) - 1)
        listing.set_options(
            Option(
                self._row(
                    seen,
                    name,
                    f"{value}   {about}" if value else about,
                    here=seen == at,
                    inforce=False,
                ),
                id=f"={name}",
            )
            for seen, (name, value, about) in enumerate(rows)
        )
        listing.highlighted = at
        self._drawn = at
        self.tabbed(self._tab_line())
        self.query_one("#tuning", Label).update(
            f"[$text-muted]{self._said}[/]" if self._said else ""
        )
        self.query_one("#keys", Label).update(
            "Left and right to step this one · Enter opens what it opens · Esc to close"
        )

    def action_easier(self) -> None:
        """Steps the row under the cursor back one, which for a switch is the same as on."""
        self._step()

    def action_harder(self) -> None:
        """Steps it on one."""
        self._step()

    def _step(self) -> None:
        """Turns round whichever switch the cursor is on."""
        listing = self.query_one("#choices", OptionList)
        at = listing.highlighted or 0
        rows = self._rows()
        held = rows[at][0] if 0 <= at < len(rows) else ""
        if held == _SENTRY:
            self._sentry = not self._sentry
        elif held == _PROFILES:
            self._profile = not self._profile
        elif held == _FORGET:
            self._forget = not self._forget
        else:
            return
        self._said = ""
        self.changed()
        self._fill()

    @on(OptionList.OptionSelected)
    def _took(self, event: OptionList.OptionSelected) -> None:
        """Says what a report carries, for the one row that is a thing to read."""
        held = str(event.option.id or "").removeprefix("=")
        if held == _SENT:
            sent, kept = "; ".join(SENT), "; ".join(KEPT)
            self._said = f"Sent: {sent}. Never: {kept}."
            self._fill()
            return
        self._step()

    def applied(self) -> None:
        """Answers with what was changed, which is nothing where nothing was."""
        self.dismiss(
            Adjusted(
                enable_sentry=self._sentry,
                profile=self._profile,
                forget=self._forget,
            )
        )


#: How much of a directory a row says: the last of it, which is what tells one project from
#: another. The rest is a home directory, which says nothing and is nobody else's business.
_ENOUGH = 2


def _shortly(said: str) -> str:
    """One path, as much of it as a row has room for: the last parts of it."""
    parts = said.rstrip("/").split("/")
    return "/".join(parts[-_ENOUGH:]) if len(parts) > _ENOUGH else said


class Reports(Picks):
    """Whether humanize reports its own failures, asked once, on a first start.

    Asked rather than assumed either way. Assumed on, it would be a tool that started sending
    things about somebody's machine before they had heard of it; assumed off, it would be a
    tool whose crashes nobody ever sees, which on something this young is how a bug survives
    a year. So it is a question, put once, with what it means written out beside it -- what
    goes, and what does not -- and answered for every project from then on.

    Drawn as a box in the middle of the screen, for the reason the save question is: it is
    not a sheet somebody walked to. Esc leaves it unanswered, and unanswered is asked again
    next time rather than taken as a no.
    """

    CSS = _POPUP

    asked = "Report what goes wrong to humanize?"

    def __init__(self) -> None:
        """Initializes the question on its default answer, which is yes."""
        super().__init__()
        sent, kept = "; ".join(SENT), "; ".join(KEPT)
        self.about = (
            f"humanize is early, and a crash nobody sees is a bug nobody fixes. "
            f"Sent: {sent}. Never sent: {kept}."
        )

    def rows(self) -> list[tuple[str, str, str]]:
        """The two answers, the one that helps first."""
        return [
            (
                _REPORTS,
                "yes, report them",
                "what broke, and what was running when it did",
            ),
            (_QUIET, "no, send nothing", "nothing about this machine leaves it"),
        ]

    def check_action(
        self,
        action: str,
        parameters: tuple[object, ...],
    ) -> bool | None:
        """Whether one of the keys is live, which a question of two answers narrows."""
        return action != "search" and super().check_action(action, parameters)

    def _fill(self) -> None:
        """Puts the two answers up, and says what esc is here."""
        super()._fill()
        self.query_one("#keys", Label).update(
            "Enter to choose · Esc to be asked again next time · /settings changes it later"
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
_SAVE_AS = "save as"

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

    A saved agent can be copied in at the top and saved as a reusable copy at the bottom. What
    is imported is a copy: an agent tuned inside a flow is that flow's, and writing the changes
    back into the thing it was copied from would change every other flow that had imported it.
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
        # Said outright, all of them: each is read where it is set -- what a CLI runs is
        # looked up as the CLI that is chosen now -- so what they are has to be settled
        # without reading what reads them.
        self._cli: str = cli
        self._model: str = model
        # `swarm` in front of the effort is how a fleet is written down, so it comes off again
        # before the effort is looked for among the ones the model takes.
        self._swarm: bool = effort.startswith(SWARM)
        self._effort: str = effort.removeprefix(SWARM)
        self._permission = (
            PERMISSIONS.index(runs.permission)
            if runs.permission in PERMISSIONS
            else len(PERMISSIONS) - 1
        )
        self._provider: str = runs.provider
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
        saving = (
            "Save accepts this setup; save as keeps a reusable copy."
            if self._place is not None
            else "Save accepts this setup."
        )
        self.query_one("#about", Label).update(
            "What this one agent is. Enter opens the row under the cursor, and the arrows "
            f"step the ones that are a rung rather than a list. {saving}"
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
                    "as its CLI finds them",
                    "what it will be carrying, which its CLI keeps",
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
        rows.append((_SAVE, "", "accept this agent setup"))
        if self._place is not None:
            rows.append((_SAVE_AS, "", "save a reusable agent you can import"))
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
            else "Enter to save · Esc to close"
            if held == _SAVE
            else "Enter to save a copy · Esc to close"
            if held == _SAVE_AS
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
        opens = "" if held in _STEPPED or held in (_NAME, _SAVE) else " ▸"
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
          have been fetched yet, and its effort is still the effort it runs at. A model whose
          own name carries its effort -- Antigravity lists `gemini-3.7-flash-low` -- says so
          by offering that one and no other.
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
        if held == _SAVE:
            self.applied()
            return
        if held in (_CLI, _ACCOUNT, _MODEL, _SKILLS, _WHERE, _IMPORT, _SAVE_AS):
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
        elif held == _SAVE_AS:
            await self._saves_as(showing)
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
        self._swarm = False
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
        """Shows what its CLI would load, which is the CLI's own and is not changed here."""
        if not self._cli:
            self._said = "choose the coding agent first; the skills are its own"
            return
        await showing.push_screen_wait(Skills(self._cli))

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
        from hmz.kept import Templates

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
        self._provider = one.runs.provider
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

    async def _saves_as(self, showing: App[None]) -> None:
        """Writes this agent down under a name, new or one already there."""
        from hmz.kept import Templates

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
        from hmz.kept import Templates

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
        from hmz.kept import Templates

        Templates().keep(self._held)
        self.dismiss(
            [
                f"[dim]{len(self._held)} agents saved: "
                f"{escape(', '.join(one.name for one in self._held))}[/dim]"
                if self._held
                else "[dim]no agents are saved any more[/dim]"
            ]
        )


#: What can be done to one account, which is what enter opens rather than what a row of
#: letter keys does. Each of these is a question about the account under the cursor, and a
#: menu of four is a menu; four keys nobody can see are four keys nobody presses.
_CORRECTS, _SIGNS_IN, _FALLS_BACK, _TRIED = "corrects", "signs-in", "falls", "tried"


class Account(Picks):
    """What to do with one account: correct it, sign it in again, chain it, retry it.

    Its own menu rather than a letter apiece on the list of accounts. They are four questions
    about the account under the cursor, and a sheet whose keys are `l`, `f` and `t` is a sheet
    whose keys have to be learned from a line at the bottom of it -- while enter, which every
    list already means, was doing one of the four.
    """

    def __init__(self, cli: str, name: str) -> None:
        """Asks about one account.

        Args:
          cli: The backend it belongs to.
          name: What it is called, or "" for the account this machine is already signed into.
        """
        super().__init__()
        self._cli = cli
        self._name = name
        self.asked = f"{cli}/{name}" if name else f"{cli}, as this machine is signed in"
        self.about = (
            "What to do with this account. Correcting it, saying where it falls back to and "
            "saying how it is tried again land when the accounts menu is saved; signing in "
            "happens as it is asked for."
        )

    def rows(self) -> list[tuple[str, str, str]]:
        """The four, less the two there is nothing to do for this machine's own account."""
        held = [
            (
                _FALLS_BACK,
                "falls back to",
                "which account a turn carries on under when this one fails",
            ),
            (
                _TRIED,
                "how it is tried again",
                "how many tries, which wait, and how long in all",
            ),
        ]
        if not self._name:
            return held
        return [
            (
                _CORRECTS,
                "correct what it holds",
                "the answers its way in was made with, asked again",
            ),
            (
                _SIGNS_IN,
                "sign in again",
                "run its own way in again; it owns the terminal while it does",
            ),
            *held,
        ]

    def nothing(self) -> str:
        """Why two of them are not here, for the account humanize did not make."""
        if self._name:
            return ""
        return (
            f"this is {escape(self._cli)} as this machine is already signed in: humanize "
            "keeps no credentials for it, so there is nothing to correct or sign in"
        )


class Providers(Drafts[list[str]]):
    """Every account there is to run an agent as, under a heading per CLI.

    Read rather than chosen from: which account an agent runs as is asked where that agent is
    set up, so nothing here is being picked for anything. What it is for is what can happen to
    one -- made, set up again, signed in again, marked as where a turn goes when another
    account fails, taken away -- and all but the first two of those are one menu, opened with
    enter on the account they are about. A row of letter keys was a row of keys somebody had
    to read off the bottom of the screen while enter, which every list already means, did one
    of the four.

    What is written down without running anything is held until the menu is saved: taking one
    away, marking one as a fallback, correcting what one holds. What cannot be held is what
    runs a command of its own -- making an account and signing one in own the terminal while
    they run, and something that has already happened is not a draft.

    Each row is the name, the way it was made by and the variables it sets. Their names and
    never a value: this is drawn where somebody can read it.
    """

    TABS: ClassVar = ("Providers",)
    LETTERS: ClassVar = frozenset({"search", "adding", "drop"})

    BINDINGS: ClassVar = [
        ("escape", "back", "back"),
        Binding("tab", "next_tab", "next page", priority=True),
        Binding("shift+tab", "prev_tab", "previous page", priority=True),
        Binding("s", "search", "search", priority=True),
        Binding("a", "adding", "make one", priority=True),
        Binding("d", "drop", "take one away", priority=True),
    ]

    def __init__(self) -> None:
        """Reads every account there is."""
        super().__init__()
        self._found: list[Provider] = []
        #: The ones to take away when this is saved, as `cli/name`.
        self._gone: set[str] = set()
        #: What each one is to fall back to when this is saved, by `cli/name`: the name of
        #: another account of that CLI, or "" for the end of the line.
        self._chains: dict[str, str] = {}
        #: How each one is to be tried again when this is saved, by `cli/name`.
        self._tries: dict[str, tuple[int, str, float]] = {}
        #: What each corrected one is to hold, by `cli/name`.
        self._edits: dict[str, dict[str, str]] = {}
        #: Which other backends each corrected one is to be written down for as well, by
        #: `cli/name`: an account that several CLIs can be run as is corrected for all of
        #: them at once, which is the point of having copied it in the first place.
        self._alike: dict[str, tuple[str, ...]] = {}
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
            "as that account. Enter opens what there is to do with one. Taking one away, "
            "saying where it falls back to and saying how it is tried again land when this "
            "menu is saved; making one and signing one in happen as they are asked for."
        )
        self._read()
        self._fill()
        self.query_one("#choices", OptionList).focus()

    def _read(self) -> None:
        """Reads every account off the disk, which is what the rows are drawn from.

        The account this machine is already signed into is one of them, under each CLI that
        has one of its own: it is what an agent nobody gave an account runs as, and it is
        where that agent's chain begins, so it is a row to press f and t on like any other.
        Under a CLI with no accounts there is nothing for it to fall back to, so it is a row
        there only where something has already been said about it -- a chain that outlived
        the accounts it named, or tries set from a command line -- which must not be a
        setting in force that nothing shows.

        Last in each CLI's group rather than first: what somebody came here to read is the
        accounts they made, and this is the one that was always there.
        """
        from hmz import providers
        from hmz.backends import profiles

        held = providers.providers()
        whose = {each.cli for each in held}
        mine = [
            one
            for profile in profiles()
            if (one := providers.find(profile.name, providers.LOCAL)) is not None
            and (profile.name in whose or one.fallback or one.retries)
        ]
        self._found = sorted(
            [*held, *mine], key=lambda one: (one.cli, not one.name, one.name)
        )

    def _named(self, one: Provider) -> str:
        """One account as it is keyed here, which is by the CLI it belongs to and its name."""
        return f"{one.cli}/{one.name}"

    def _about(self, one: Provider) -> str:
        """What a row says about one account, and what is going to happen to it."""
        said = (
            _sets(one) if one.name else "the CLI as this machine is already signed in"
        )
        if self._named(one) in self._edits:
            said += f"{_DOT}corrected"
        falls = self._chains.get(self._named(one), one.fallback)
        if falls:
            said += f"{_DOT}falls back to {falls}"
        tried = self._tries.get(
            self._named(one), (one.retries, one.policy, one.timeout)
        )
        if tried[0]:
            said += f"{_DOT}{tried[0]} tries, {tried[1]}"
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
                        one.name or "as local",
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
            "Enter for what to do with one · a makes one · d twice takes one away · "
            f"Esc to close{self.searching()}"
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

    def _machines(self, cli: str, doing: str) -> str:
        """Why the account this machine is signed into is not one to do that to.

        Args:
          cli: The backend it is of.
          doing: What was asked for.

        Returns:
          The line to say under the list. humanize did not make that account and keeps no
          credentials for it -- it is the CLI as whoever is at this machine runs it -- so the
          only things to say about it are where it falls back to and how it is tried again,
          which is what enter offers on it.
        """
        telemetry.snag("key-does-nothing", sheet="Providers", doing=doing)
        return (
            f"there is nothing to {doing}: this is {escape(cli)} as this machine is already "
            "signed in. Enter says what it does take"
        )

    @work
    async def action_fallback(self, one: Provider | None = None) -> None:
        """Asks which account a turn under this one carries on under when it fails.

        Args:
          one: The account, or None for the one the cursor is on.
        """
        one = one or self._under()
        if one is None:
            return
        named = self._named(one)
        showing = cast(
            "App[None]",
            self.app,  # pyright: ignore[reportUnknownMemberType]
        )
        chosen = await showing.push_screen_wait(
            Falls(one.cli, one.name, self._chains.get(named, one.fallback))
        )
        if chosen is None:
            return  # walked out, which changes nothing
        if chosen == one.fallback:
            self._chains.pop(named, None)
        else:
            self._chains[named] = chosen
        self._said = ""
        self.changed()
        self._fill()

    @work
    async def action_tries(self, one: Provider | None = None) -> None:
        """Asks how a turn under one account is tried again.

        Args:
          one: The account, or None for the one the cursor is on.
        """
        one = one or self._under()
        if one is None:
            return
        named = self._named(one)
        held = self._tries.get(named, (one.retries, one.policy, one.timeout))
        showing = cast(
            "App[None]",
            self.app,  # pyright: ignore[reportUnknownMemberType]
        )
        chosen = await showing.push_screen_wait(
            Retries(
                named if one.name else f"{one.cli}, as this machine is signed in,",
                *held,
            )
        )
        if chosen is None:
            return
        if chosen == (one.retries, one.policy, one.timeout):
            self._tries.pop(named, None)
        else:
            self._tries[named] = chosen
        self._said = ""
        self.changed()
        self._fill()

    def action_drop(self) -> None:
        """Marks the account under the cursor to be taken away, once d is pressed twice."""
        one = self._under()
        if one is None:
            return
        if not one.name:
            self._said = self._machines(one.cli, "take away")
            self._fill()
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
        """Opens what there is to do with the account under the cursor.

        Args:
          event: What was chosen.
        """
        named = str(event.option.id or "").removeprefix("=")
        one = next((each for each in self._found if self._named(each) == named), None)
        if one is not None:
            self._doing(one)

    @work
    async def _doing(self, one: Provider) -> None:
        """Asks what to do with one account, and does it.

        Args:
          one: The account.
        """
        showing = cast(
            "App[None]",
            self.app,  # pyright: ignore[reportUnknownMemberType]
        )
        said = await showing.push_screen_wait(Account(one.cli, one.name))
        if said is None:
            return  # walked out of it, which does nothing to the account
        if said == _CORRECTS:
            self._corrects(one)
        elif said == _SIGNS_IN:
            self.action_again(one)
        elif said == _FALLS_BACK:
            self.action_fallback(one)
        elif said == _TRIED:
            self.action_tries(one)

    @work
    async def _corrects(self, one: Provider) -> None:
        """Asks what one account is to hold, starting from what it holds now.

        A secret is never read back on to the screen, so what is typed here replaces what was
        there rather than being edited into it: a key is written once and read never.

        Args:
          one: The account.
        """
        from dataclasses import replace

        from hmz import providers
        from hmz.providers import login as signing

        if not one.name:
            self._said = self._machines(one.cli, "correct")
            self._fill()
            return
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
        named = self._named(one)
        self._edits[named] = signs.answers
        # And which other backends are to hold what it now holds, asked of the account as it
        # is being corrected rather than as it was: a key rotated is a key rotated everywhere
        # it was copied to, which is what correcting one is usually for.
        corrected = replace(one, env=signs.answers)
        among = providers.serves(corrected)
        self._alike.pop(named, None)
        if among:
            chosen = await showing.push_screen_wait(Alike(corrected, among))
            if chosen:
                self._alike[named] = tuple(chosen)
        self._said = f"{escape(named)} is corrected when this menu is saved"
        if self._alike.get(named):
            self._said += f", for {escape(', '.join(self._alike[named]))} as well"
        self.changed()
        self._fill()

    @work
    async def action_adding(self) -> None:
        """Asks which CLI, and then walks that backend's own way in.

        Two questions rather than one, because the second is only answerable once the first
        has been: a backend's ways in are its own. What comes of it has already happened by
        the time it lands -- a login owns the terminal while it runs -- so it is not one of
        the things this menu holds until it is saved.

        The list of CLIs is also where a CLI of your own is written down: somebody who cannot
        find their agent in it is somebody whose agent is not one humanize drives, and that
        is a thing to say where the question was asked rather than on a key of the sheet
        before it.
        """
        showing = cast(
            "App[None]",
            self.app,  # pyright: ignore[reportUnknownMemberType]
        )
        while True:
            cli = await showing.push_screen_wait(Backends())
            if cli is None:
                return  # nothing before this to step back into
            if cli == _SPEAKS:
                await self._speaks()
                return
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
        if outcome.copied:
            self._told.append(
                f"[dim]{escape(one.name)} is written down for "
                f"{escape(', '.join(outcome.copied))} too[/dim]"
            )
        self._said = self._landed(one, outcome.status, runs=outcome.runs)
        if outcome.copied:
            self._said += f"{_DOT}and runs {escape(', '.join(outcome.copied))} too"
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
    async def action_again(self, one: Provider | None = None) -> None:
        """Runs one account's own way in again, asking for whatever it still needs.

        Args:
          one: The account, or None for the one the cursor is on.
        """
        from hmz.providers import login as signing

        one = one or self._under()
        if one is None:
            return
        if not one.name:
            self._said = self._machines(one.cli, "sign in")
            self._fill()
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

    async def _speaks(self) -> None:
        """Asks for a CLI of your own that speaks ACP, and writes it down as a backend.

        Reached from the list of backends a new account is for, because that is the moment
        somebody finds out that the agent they want to run is not one humanize drives. What
        is written down outlives the run, so it is a backend from the next prompt on, in this
        workspace and every other -- which is why it is not one of the things this menu holds
        until it is saved.
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
        # Taken away first, and then everything that is left: a chain pointed at an account
        # that is going in the same save is a chain that goes nowhere, and one written before
        # the removal would be written and then quietly left dangling.
        for taken in sorted(self._gone):
            cli, _, name = taken.partition("/")
            try:
                gone = providers.remove(cli, name)
            except ValueError as why:  # a name nothing could ever have been kept under
                told.append(f"hmz: {escape(str(why))}")
                continue
            told.append(
                f"[dim]{escape(taken)} is gone, credentials and all[/dim]"
                if gone
                else f"hmz: no provider {escape(taken)}"
            )
        for one in self._found:
            named = self._named(one)
            if named in self._gone:
                continue  # gone above, so there is nothing to correct or point anywhere
            if (answers := self._edits.get(named)) is not None:
                try:
                    corrected = providers.add(one.cli, one.name, one.way, answers)
                except (OSError, ValueError) as why:
                    told.append(f"hmz: {escape(str(why))}")
                    continue
                told.append(f"[dim]{escape(named)} is corrected[/dim]")
                for cli in self._alike.get(named, ()):
                    try:
                        providers.copies(corrected, cli)
                    except (OSError, ValueError) as why:
                        told.append(f"hmz: {escape(str(why))}")
                        continue
                    told.append(
                        f"[dim]{escape(cli)}/{escape(one.name)} is corrected with it[/dim]"
                    )
            if (falls := self._chains.get(named)) is not None:
                try:
                    providers.points(one.cli, one.name, falls)
                except ValueError as why:
                    told.append(f"hmz: {escape(str(why))}")
                else:
                    told.append(
                        f"[dim]{escape(named)} falls back to {escape(falls)}[/dim]"
                        if falls
                        else f"[dim]{escape(named)} falls back to nowhere[/dim]"
                    )
            if (tried := self._tries.get(named)) is not None:
                try:
                    providers.retrying(one.cli, one.name, *tried)
                except ValueError as why:
                    told.append(f"hmz: {escape(str(why))}")
                else:
                    told.append(
                        f"[dim]{escape(named)} is tried {tried[0]} more times, "
                        f"{escape(tried[1])}[/dim]"
                        if tried[0]
                        else f"[dim]{escape(named)} is tried once[/dim]"
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


#: What can be done with a run that has already happened: pick it up where it stopped, for a
#: flow that says it can be, gather what it left behind into a trace, and say where it is
#: written down. The first is answered outside this module -- starting a flow is the
#: interface's -- so it is named where it is read.
carries_on, _COLLECTS, _WHERE_IT_IS = "carry-on", "collect", "where"

#: How much of a task a row of the runs shows, before it is what a run is rather than a line.
_ENOUGH_TASK = 60


class Doing(NamedTuple):
    """What somebody asked to have done with one run that has already happened.

    Attributes:
      cycle: The run, by the directory it is written in, or None where this is only what the
        sheet has to say on the way out.
      doing: What to do with it, which is what the menu under it answered, and "" where the
        sheet did it itself.
      said: What happened while the sheet was open, for the transcript: a menu that gathered
        a trace and said nothing afterwards is one nobody can read back.
    """

    cycle: Path | None = None
    doing: str = ""
    said: tuple[str, ...] = ()


def _many(count: int, thing: str) -> str:
    """How many of something there were, said as English says it.

    Args:
      count: How many.
      thing: What they are, in the singular.

    Returns:
      The two words -- `1 session`, `3 sessions` -- since a sheet is prose and `1 sessions`
      is a sheet that reads as a template somebody forgot to finish.
    """
    return f"{count} {thing}" if count == 1 else f"{count} {thing}s"


def _asked_for(task: str) -> str:
    """What a run was asked to do, as much of it as a row has room for.

    Args:
      task: The whole of it, which is however long whoever started the run made it.

    Returns:
      Its first line's worth, on one line, cut with an ellipsis where it was cut.
    """
    said = " ".join(task.split())
    return said if len(said) <= _ENOUGH_TASK else f"{said[: _ENOUGH_TASK - 1]}…"


def _when(said: str) -> str:
    """One of the moments a cycle writes down, as a row of a list says one.

    Args:
      said: The moment, as it was written -- `2026-08-16T03:04:05.123Z`.

    Returns:
      It, to the minute, and whatever was written where that is not what it is.
    """
    if len(said) < len("YYYY-MM-DDTHH:MM"):
        return said
    return said[:16].replace("T", " ")


class Does(Picks):
    """What to do with one run that has already happened.

    Which is a second question rather than more keys on the first: a list of runs is a list
    somebody is reading, and what there is to do with one of them depends on the one under
    the cursor -- a flow that says it can be picked up is picked up, and one that says
    nothing is a run to read rather than a run to continue.
    """

    def __init__(self, ran: Ran, *, resumable: bool) -> None:
        """Asks about one run.

        Args:
          ran: The run, as it was written down.
          resumable: Whether its flow says now that it can be picked up, which is asked of
            the flow rather than of the run: a flow may have been rewritten since.
        """
        super().__init__()
        self._ran = ran
        self._resumable = resumable
        self.asked = f"{_when(ran.began)}{_DOT}{ran.flow}"
        self.about = (
            f"What to do with this run. It {_how(ran)}, driving "
            f"{_many(len(ran.agents), 'agent')} through "
            f"{_many(len(ran.sessions), 'session')}."
        )

    def rows(self) -> list[tuple[str, str, str]]:
        """Carrying on where it stopped, where that is a thing this flow can do, and reading."""
        held: list[tuple[str, str, str]] = []
        if self._resumable:
            held.append(
                (
                    carries_on,
                    "carry on from here",
                    "run the flow again on what this run left behind",
                )
            )
        held.append(
            (
                _COLLECTS,
                "collect a trace",
                "its sessions, and the programs it ran, as one trace to read",
            )
        )
        held.append(
            (
                _WHERE_IT_IS,
                "where it is",
                "the directory this run is written in, sessions and all",
            )
        )
        return held

    def nothing(self) -> str:
        """Why carrying on is not one of the things there are to do, where it is not."""
        if self._resumable:
            return ""
        return (
            f"{escape(self._ran.flow)} does not say it can be picked up, so there is "
            "nothing to carry on from"
        )


def _how(ran: Ran) -> str:
    """How one run ended, as a line about it reads.

    Args:
      ran: The run.

    Returns:
      What became of it, in words: a run with no end written down is one that was abandoned
      where it stood -- the machine it was on went, or the interface came down under it.
    """
    return {
        "done": "finished",
        "failed": "failed",
        "stopped": "was stopped",
    }.get(ran.how, "was left unfinished")


def collected(ran: Ran) -> tuple[Path, str]:
    """Gathers what one run left behind into a trace file, and says what is in it.

    That run's own sessions and no others: a directory may have been run in a hundred times,
    and a trace filed under one of those runs while holding the other ninety-nine is a trace
    of nothing anybody asked about. They are asked for by the ids the run wrote down rather
    than by directory, so a flow that worked in a machine's mirror is in its own trace too.

    Beside the run rather than in this directory: a cycle is what a run was, and the trace of
    that run belongs with the sessions it points at and the state it left. A trace of what a
    directory holds whoever opened it is `hmz trace collect --all`, and a trace to attach to
    an issue is `--output`: both are a command line, there being no run here to hang either
    on.

    Args:
      ran: The run.

    Returns:
      Where the trace was written, and a line saying what it holds.
    """
    import datetime

    from hmz.cycle import TRACES, opened
    from hmz.tracing.collector import collect
    from hmz.tracing.profile import PROFILE

    at = ran.at / TRACES
    at.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now(datetime.UTC).strftime("%Y%m%dT%H%M%SZ")
    where = at / f"{stamp}.trace.json"
    agents = opened(ran.at)
    document = collect(
        None,
        sessions=[ident for ids in agents.values() for ident in ids],
        agents=agents or None,
        output=where,
        profile=ran.at / PROFILE,
    )
    said = document["otherData"]
    held = f"{said.get('sessions', '0')} sessions, {said.get('slices', '0')} slices"
    if said.get("programs"):
        held += f", {said['programs']} programs"
    return where, held


class Cycles(Sheet[Doing]):
    """Every run of a flow in this directory, newest first, and what to do with one.

    A run is written down as it happens -- which flow, on what, by which agents, and which
    sessions each of them opened -- and until now nothing showed them. What they are for is
    two things: reading one back afterwards, which is what the links to its sessions are, and
    carrying one on, which is what a flow that says it can be picked up is for.

    Read rather than chosen from, so enter opens what there is to do with the run under the
    cursor rather than doing any of it.
    """

    LETTERS: ClassVar = frozenset({"search"})

    BINDINGS: ClassVar = [
        ("escape", "back", "back"),
        Binding("s", "search", "search", priority=True),
    ]

    def __init__(self, workspace: Path | None = None, *, running: bool = False) -> None:
        """Reads every run of this directory.

        Args:
          workspace: Which directory's, defaulting to this one.
          running: Whether a flow is running now, which is what makes carrying one on a
            thing to say no to rather than a thing to offer.
        """
        super().__init__()
        from hmz.cycle import cycles, read

        #: Newest first: what somebody opening this came to look at is the run that has just
        #: happened, and a list of a hundred is one nobody scrolls to the end of.
        self._ran = [
            one
            for one in (read(at) for at in reversed(cycles(workspace)))
            if one is not None
        ]
        self._underway = running
        #: Which run the cursor is on, by the directory it is written in: rows are narrowed
        #: by a search, so a row number is not a run.
        self._was = ""
        #: What is worth saying under the list.
        self._said = ""
        #: Whether each flow says now that it can be picked up, by flow: reading one means
        #: running its file, so it is asked once and only for the flows asked about.
        self._resumes: dict[str, bool] = {}
        #: What is worth saying in the transcript once this sheet is done with.
        self._told: list[str] = []

    def _ask(self) -> None:
        """Says what these are, and puts them up."""
        self.query_one("#asked", Label).update("Cycles")
        self.query_one("#about", Label).update(
            "Every run of a flow in this directory, newest first: what it was, how it went, "
            "and how many sessions it opened. Enter says what there is to do with one."
        )
        self._fill()
        self.query_one("#choices", OptionList).focus()

    def _about(self, ran: Ran) -> str:
        """What a row says about one run: what it was asked to do, how it went, and its size.

        How it went only where it went some other way than finishing: a list of runs is
        mostly runs that finished, and a column saying so of nearly all of them is a column
        that says nothing while taking the room the ones that did not need.
        """
        said = _asked_for(ran.task) if ran.task else "no task"
        held = f"{said}{_DOT}{_many(len(ran.sessions), 'session')}"
        if ran.how != "done":
            held += f"{_DOT}{_how(ran)}"
        # Asked of the flow rather than read off the run, for the reason the menu asks it of
        # the flow: a flow is a directory on disk, and one marked resumable since that run is
        # one whose older runs can be picked up now.
        return f"{held}{_DOT}can be picked up" if self._picks_up(ran.flow) else held

    def _fill(self) -> None:
        """Puts the runs up, marked where the cursor is."""
        listing = self.query_one("#choices", OptionList)
        self._follows(listing)
        shown = [one for one in self._ran if self.fits(one.flow, one.task, one.name)]
        self._counting = len(str(max(len(shown), 1)))
        if all(one.name != self._was for one in shown):
            self._was = shown[0].name if shown else ""
        listing.set_options(
            Option(
                self._row(
                    seen,
                    f"{_when(one.began)}{_DOT}{one.flow}",
                    _briefly(self._about(one), self.size.width),
                    here=one.name == self._was,
                    inforce=False,
                ),
                id=f"={one.name}",
            )
            for seen, one in enumerate(shown)
        )
        listing.highlighted = (
            next((at for at, one in enumerate(shown) if one.name == self._was), 0)
            if shown
            else None
        )
        self._drawn = listing.highlighted
        said = self._said or ("" if self._ran else self._nothing())
        self.query_one("#tuning", Label).update(
            f"[$text-muted]{said}[/]" if said else ""
        )
        self.query_one("#keys", Label).update(
            f"Enter for what to do with one · Esc to close{self.searching()}"
        )

    def leaving(self) -> None:
        """Leaves, saying in the transcript whatever was gathered while this was open."""
        self.dismiss(Doing(said=tuple(self._told)) if self._told else None)

    def _nothing(self) -> str:
        """What an empty list says, which is that nothing has been run here yet."""
        return "no flow has been run in this directory yet"

    async def _collects(self, ran: Ran) -> None:
        """Gathers what one run left behind into a trace, beside the run itself.

        Off the event loop: reading a run's sessions back is every log every backend wrote
        for it, which is seconds on a long run -- and an interface that stopped redrawing
        while it ran would be one that looked as though it had gone away.

        Args:
          ran: The run.
        """
        import asyncio

        self._said = f"collecting {escape(ran.name)}…"
        self._fill()
        try:
            at, held = await asyncio.to_thread(collected, ran)
        except (OSError, ValueError) as why:
            self._said = escape(str(why))
            self._fill()
            return
        self._said = f"{escape(str(at))}{_DOT}{escape(held)}"
        self._told.append(f"[dim]{escape(str(at))} — {escape(held)}[/dim]")
        self._fill()

    def _follows(self, listing: OptionList) -> None:
        """Takes which run the cursor is on off the list, by the directory it is written in."""
        at = listing.highlighted
        if at is not None and 0 <= at < listing.option_count:
            named = str(listing.get_option_at_index(at).id or "").removeprefix("=")
            if named:
                self._was = named

    def _under(self) -> Ran | None:
        """The run the cursor is on, or None where the list has nothing in it."""
        return next((one for one in self._ran if one.name == self._was), None)

    def _picks_up(self, flow: str) -> bool:
        """Whether one flow says now that it can be picked up.

        Asked of the flow rather than of the run that recorded it: a flow is a directory on
        disk and may have been rewritten since, and what can happen next is what it says now.
        Asked once per flow, since reading one means running its file.

        Args:
          flow: The flow, as the run named it.

        Returns:
          Whether it is resumable, and False for one that will not load at all -- a flow that
          cannot be read cannot be run, which is what carrying on would come to.
        """
        from hmz.flows import resumes

        if flow not in self._resumes:
            try:
                self._resumes[flow] = resumes(flow)
            except Exception:  # noqa: BLE001 -- a flow is a file, and reading one runs it
                self._resumes[flow] = False
        return self._resumes[flow]

    @on(OptionList.OptionSelected)
    def _took(self, event: OptionList.OptionSelected) -> None:
        """Opens what there is to do with the run under the cursor.

        Args:
          event: What was chosen.
        """
        named = str(event.option.id or "").removeprefix("=")
        one = next((each for each in self._ran if each.name == named), None)
        if one is not None:
            self._doing(one)

    @work
    async def _doing(self, ran: Ran) -> None:
        """Asks what to do with one run, and does it or answers with it.

        Args:
          ran: The run.
        """
        showing = cast(
            "App[None]",
            self.app,  # pyright: ignore[reportUnknownMemberType]
        )
        said = await showing.push_screen_wait(
            Does(ran, resumable=self._picks_up(ran.flow))
        )
        if said is None:
            return  # walked out of it, which does nothing to the run
        if said == _WHERE_IT_IS:
            self._said = escape(str(ran.at))
            self._fill()
            return
        if said == _COLLECTS:
            await self._collects(ran)
            return
        if said == carries_on and self._underway:
            # Said here rather than on the way out: the question this sheet is asking is
            # still worth answering, and a flow is stopped with esc rather than from here.
            self._said = "a flow is running; ctrl+c twice stops it before another can be picked up"
            self._fill()
            return
        self.dismiss(Doing(ran.at, said, tuple(self._told)))


#: What the diagram draws one agent's box with, and what it joins two of them by. Light
#: box-drawing, which is what a terminal has for a box that is a label rather than a frame.
_BOX = ("┌", "┐", "└", "┘", "─", "│")

#: What says a handover went down the diagram and what says it came back up it, and what
#: stands between two agents the flow never handed between directly.
_DOWN, _UP, _NEITHER = "↓", "↑", "┆"

#: How wide one agent's box is drawn, at most. Wide enough for an agent's name beside what
#: it runs, and narrow enough that two of them do not need a terminal nobody has.
_WIDEST = 64

#: The transcript every agent's work appears on, which is what the first row of the diagram
#: attaches to and what this sheet answers with where that row is taken. Written down once,
#: here, and read from `hmz.tui.app` rather than said again there: the sheet answers with
#: what the interface reads, and two names for it are two that could come apart.
#:
#: Nobody's, since it is not an agent's: an agent id is what every other transcript is kept
#: under, and no agent is called this.
EVERY = ""


class Drawn(NamedTuple):
    """One agent of a run, as the diagram on `/status` draws it.

    Attributes:
      who: The agent id, which is what attaching to it names and what the graph counts it
        under.
      named: What the flow calls it, or "" for a flow that names none of its agents.
      runs: What it runs, as the line that says what each agent is says it.
      working: Whether it has a turn open right now.
      reading: Whether its transcript is the one on the screen behind this sheet.
    """

    who: str
    named: str = ""
    runs: str = ""
    working: bool = False
    reading: bool = False


def _boxed(said: list[tuple[str, str]], width: int) -> list[str]:
    """One agent, drawn as a box the width of the diagram.

    Args:
      said: The lines to put in it, each as the colour to draw it in and the plain words to
        draw. Plain, so that what will not fit can be cut before any markup is put round it:
        a bracket an agent's name happens to hold is a bracket, and an escape of one is
        characters that are not columns.
      width: How wide to draw it, borders included.

    Returns:
      The box, a line at a time, each exactly as wide as the last.
    """
    left, right, under_left, under_right, across, side = _BOX
    room = width - 4
    return [
        f"[$text-muted]{left}{across * (width - 2)}{right}[/]",
        *(
            f"[$text-muted]{side}[/] [{colour}]{escape(_fits(line, room))}[/]"
            f"{' ' * max(0, room - len(_fits(line, room)))} [$text-muted]{side}[/]"
            for colour, line in said
        ),
        f"[$text-muted]{under_left}{across * (width - 2)}{under_right}[/]",
    ]


def _fits(said: str, room: int) -> str:
    """One line of a box, cut to the room there is for it rather than running past its side.

    Args:
      said: The words, as they are.
      room: How many columns there are between the two sides of the box.

    Returns:
      Them, or as much of them as fits with an ellipsis where the rest was.
    """
    return said if len(said) <= room else said[: room - 1] + "…"


def _joins(down: int, up: int, width: int) -> list[str]:
    """The arrows between two boxes, saying which way the flow went and how often.

    Args:
      down: How many times the agent above handed to the one below.
      up: How many times it came back the other way.
      width: How wide the boxes are, so the arrows sit under them rather than beside them.

    Returns:
      The one line between the two boxes.
    """
    ways = [f"{_DOWN} {down}" for _ in range(1) if down] + [
        f"{_UP} {up}" for _ in range(1) if up
    ]
    said = "   ".join(ways) or _NEITHER
    return [f"[$text-muted]{' ' * min(4, max(0, width // 2 - 2))}{said}[/]"]


def diagram(drawn: Sequence[Drawn], shape: Shape, width: int) -> list[list[str]]:
    """The agents of a run and the handovers between them, as one box apiece.

    The shape of a flow is not written anywhere: a flow is a Python file that may branch any
    way it likes, so what it did is read off the turns going past. Drawn down the page in the
    order the flow takes its agents, with the handovers between neighbours as the arrows that
    join them -- which is the shape of nearly every flow there is, since a flow is written as
    one agent after another. The rest are said under it rather than drawn as lines crossing
    the page, there being no way to draw those in a terminal that reads as anything.

    Args:
      drawn: The agents, in the order the flow takes them.
      shape: The run as a graph, which says who is working and who handed to whom.
      width: How much room there is across.

    Returns:
      One block of lines per agent, in the same order: the arrows above it and then its box,
      so that a list of blocks is the diagram from top to bottom.
    """
    across = max(24, min(_WIDEST, width - len(_INDENT) - 5))
    blocks: list[list[str]] = []
    for at, one in enumerate(drawn):
        block = (
            []
            if at == 0
            else _joins(
                shape.handovers.get((drawn[at - 1].who, one.who), 0),
                shape.handovers.get((one.who, drawn[at - 1].who), 0),
                across,
            )
        )
        taken = shape.turns.get(one.who, 0)
        mark = _WORKING if one.working else _IDLE
        head = _DOT.join(part for part in (one.named, short(one.who)) if part)
        under = _DOT.join(
            part
            for part in (
                one.runs,
                f"{taken} turn{'' if taken == 1 else 's'}" if taken else "",
                "reading" if one.reading else "",
            )
            if part
        )
        colour = "$secondary" if one.working else "$text-muted"
        drawn_block = block + _boxed(
            [(colour, f"{mark} {head}"), ("$text-muted", under)], across
        )
        blocks.append([f"{_INDENT}{line}" for line in drawn_block])
    return blocks


def elsewhere(drawn: Sequence[Drawn], shape: Shape) -> list[str]:
    """The handovers the diagram has no arrow for, said rather than drawn.

    Which are the ones between agents the boxes did not put next to each other: a line
    crossing the page from the first box to the fourth is a line nothing in a terminal draws
    readably, so it is a row under the diagram instead.

    Args:
      drawn: The agents, in the order the flow takes them.
      shape: The run as a graph.

    Returns:
      One line per handover the boxes have no arrow for, which is nothing at all for the
      flows that are one agent after another.
    """
    order = {one.who: at for at, one in enumerate(drawn)}
    return [
        f"{escape(short(sender))} → {escape(short(taker))}{_DOT}×{often}"
        for (sender, taker), often in sorted(shape.handovers.items())
        if abs(order.get(sender, -1) - order.get(taker, -1)) != 1
        or sender not in order
        or taker not in order
    ]


class Status(Sheet[str]):
    """How the run is going, and the shape of it: who is working, and who handed to whom.

    Which is where the column that used to sit beside the transcript went. What a flow is
    doing is worth a look now and then and not worth a fifth of the screen the whole time:
    the transcript is what is being read, and the column was taking width off it to say
    something that mostly had not changed since the last glance.

    It is also where an agent is picked out to be read. tab steps between the ones working,
    which is what somebody wants while several are thinking; this is the whole flow drawn at
    once, so it is where the one that has stopped -- or has not started -- is reached. Enter
    or a click on a box answers with that agent, and the first row is the transcript every
    agent's work appears on, which is the way back to watching the flow.

    Redrawn while it is open, since what it is about moves without anybody touching it.
    """

    def __init__(
        self,
        flow: str,
        named: tuple[str, ...],
        models: list[Runs],
        monitor: Monitor,
        config: BaseModel | None = None,
        drawn: Sequence[Drawn] = (),
        reading: str = EVERY,
    ) -> None:
        """Reads one run.

        Args:
          flow: The flow being run.
          named: What that flow calls each agent it drives, "" apiece where it names none.
          models: What each of its agents runs, and where its turns land.
          monitor: The run itself, read again each time this is redrawn.
          config: What the flow was set up with, for a flow that takes any setting up.
          drawn: The agents there are to read, in the order the flow takes them, or nothing
            at all with no flow running -- which is a sheet about what is set up rather than
            about what it is doing.
          reading: Which transcript is on the screen behind this, so the diagram can say so.
        """
        super().__init__()
        self._flow = flow
        self._named = named
        self._models = models
        self._monitor = monitor
        self._config = config
        self._boxes = list(drawn)
        self._reading = reading
        #: Which row the cursor is on, by agent: the list is put up again twice a second,
        #: and a row number would move under it as the flow opens and drops agents.
        self._was = reading
        #: The boxes as they were last drawn, so that a redraw which would draw the same
        #: thing draws nothing. This is on a timer, and a list rebuilt twice a second is one
        #: that loses the click somebody was making on it and jumps under anybody scrolling.
        self._shown: list[str] = []

    def _ask(self) -> None:
        """Says what this is, puts the flow up, and starts redrawing."""
        self.query_one("#asked", Label).update("Status")
        self.query_one("#about", Label).update(
            "How the run is going, and the shape of it. Enter reads an agent -- whether or "
            "not it is working, which is what tab is held to."
        )
        self._fill()
        self.query_one("#choices", OptionList).focus()
        self.set_interval(_LIVE, self._fill)

    def _fill(self) -> None:
        """Puts the flow up as it stands, keeping the cursor where it was.

        Put up again rather than adjusted, because everything on it moves: an agent starts a
        turn, a handover happens, a token is spent. The cursor is held by agent rather than
        by row so that it stays on the same box while that happens.
        """
        listing = self.query_one("#choices", OptionList)
        at = listing.highlighted
        if at is not None and 0 <= at < listing.option_count:
            self._was = str(listing.get_option_at_index(at).id or "")
        working = sum(1 for one in self._boxes if one.working)
        rows = [
            Option(
                f"{_INDENT}[{'$secondary' if working else '$text-muted'}]▣[/] every agent"
                f"{_DOT}[$text-muted]"
                f"{working} of {len(self._boxes)} working[/]"
                + (f"{_DOT}[$text-muted]reading[/]" if self._reading == EVERY else ""),
                id=EVERY,
            )
        ]
        shape = self._monitor.shape()
        rows += [
            Option("\n".join(block), id=one.who)
            for one, block in zip(
                self._boxes, diagram(self._boxes, shape, self.size.width), strict=True
            )
        ]
        drawn = [str(row.prompt) for row in rows]
        if drawn != self._shown:
            self._shown = drawn
            listing.clear_options()
            listing.add_options(rows)
            listing.highlighted = next(
                (one for one, row in enumerate(rows) if str(row.id or "") == self._was),
                0,
            )
            self.shortens()
        # Said every time either way: what the run has come to moves whether or not the shape
        # of it does, and a line of text redrawn under the list is nothing to click on.
        self._says(shape)

    def _says(self, shape: Shape) -> None:
        """Puts what the run has come to under the diagram: what it is, and what it has cost.

        Args:
          shape: The run as a graph, taken at the same moment the boxes were.
        """
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
                    [short(who) for who in sorted(shape.working)]
                    or ["[$text-muted]nobody[/]"],
                ),
                ("Running", [f"{over:.0f}s"]),
                # Only the ones the boxes have no arrow for: the rest are drawn above.
                ("Also", elsewhere(self._boxes, shape)),
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
                    # No indent of its own: what is under the diagram is drawn in the block
                    # the sheet already indents, and a second one would step it in past the
                    # boxes it is about.
                    head = f"{field}:" if at == 0 else ""
                    lines.append(f"[$text-muted]{head:<{_FIELD}}[/]{value}")
            lines.append("")
        self.query_one("#tuning", Label).update("\n".join(lines))
        self.query_one("#keys", Label).update(f"↑↓ move{_DOT}enter read{_DOT}esc close")

    @on(OptionList.OptionSelected)
    def _took(self, event: OptionList.OptionSelected) -> None:
        """Answers with the transcript to read, which is what a click on a box means."""
        self.dismiss(str(event.option.id or EVERY))

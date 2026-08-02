"""humanize as a coding agent's own terminal, with a flow underneath instead of one agent.

Laid out the way Claude Code is, and no wider: a transcript the width of the terminal, an
editor under it between two rules, and a status line under that. Nothing sits beside them --
how the run is going is on `/status`, `/flow` chooses the loop, and `/agents` sets what each
of the flow's agents runs.

The transcript is one conversation rather than every agent's at once. A flow drives several
agents and each of them holds as many conversations as it likes, so tab and shift+tab attach
to the next and the previous of the ones it has open: what is read is one of them, and so is
what is said to.

It opens on the flow that is only talking to one agent, so that saying something is all it
takes to start. A flow is what you reach for once talking to one agent is not the shape of
the work, and nobody knows that before they have said anything.

The editor means both things at once: a line starting with `/` is a command, and any other
line is the task if nothing is running yet, or is said to the conversation being read.

Drawn in the terminal's own colours: every surface is the terminal's background and every
colour is one of the sixteen it already has a setting for, so nothing is read from it and
nothing is imposed on it.
"""

from __future__ import annotations

import asyncio
import contextlib
import functools
import os
import shlex
import subprocess
import sys
import threading
import time
import traceback
import weakref
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, NamedTuple, cast

import pyfiglet
from rich.box import ROUNDED
from rich.console import Group
from rich.markup import escape
from rich.panel import Panel
from rich.text import Text
from textual import events, on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.content import Content
from textual.message import Message
from textual.theme import Theme
from textual.widgets import OptionList, Static, TextArea
from textual.widgets.option_list import Option

from hmz.backends import Model
from hmz.runner import flow_and_agents

from .complete import about, hinted, offered, takes
from .discover import installed
from .history import History
from .monitor import Monitor, short, thousands
from .pick import (
    Anchors,
    Backends,
    Configures,
    Flows,
    Held,
    Models,
    Providers,
    Runs,
    RunsAs,
    Signing,
    Status,
    Whose,
    asks,
    called,
    handed_over,
    made,
    pointed,
    reads,
)
from .selecting import Choices, Transcript
from .settings import Settings
from .tally import Tally

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from pydantic import BaseModel

    from hmz.agents import AgentBase, Event, Question, SessionBase
    from hmz.backends import Model, Way
    from hmz.providers import Provider
    from hmz.runner import Place

#: What the editor understands, named as opencode names them, one step along: what answers
#: here is a flow rather than an agent, so opencode's `/agents` is `/flow`, and what a flow
#: runs on is an agent apiece rather than one model, so its `/models` is `/agents` -- which
#: asks three things of each agent the flow drives. `hmz collect` and `hmz anchor` are not here:
#: neither is a thing to do to a flow that is running, and both are a command line of their
#: own.
_OWN = (
    "flow",
    "config",
    "agents",
    "providers",
    "status",
    "clear",
    "details",
    "afk",
    "export",
    "exit",
)

#: What the box this opens with says about how to begin. The model of the thing rather than
#: the keys: what a key does right now is on the status line, and is only worth saying in one
#: place -- so these are the nouns instead, which are the ones a flow is written in.
_HELP = (
    "Say what to do, and the flow starts on it.",
    "/flow chooses the loop, /agents what it drives.",
    "/providers holds the accounts they run as.",
)

#: How often the right-hand column and the status line are redrawn, in seconds.
_REFRESH = 0.5

#: How long a second ctrl+c still counts as the same one, in seconds.
_AGAIN = 2.0

#: How long the status line says that something was copied, in seconds. Long enough to be
#: read after a drag that ended somewhere else on the screen, and gone before it is mistaken
#: for a thing about the run.
_COPIED = 2.0

#: How many lines of what is waiting to be said are pinned above the prompt before the rest
#: is counted instead. A pin that grew without limit would push the transcript off the screen
#: to say that a lot is queued, which one line says. The stylesheet holds it to one row more
#: than this, for the line that does the counting.
_PINNED = 5

#: How narrow a terminal a pinned line is still given room in, so that the arithmetic below
#: cannot ask for a negative number of columns.
_NARROW = 20

#: How many conversations the transcript is kept for, and how many lines of each. A flow runs
#: for days and a Ralph loop opens a conversation a turn, so keeping every line of every one
#: of them is a run that grows until somebody stops it. Eight is more than a flow has open at
#: once -- an agent or two apiece -- so what falls off the end is a conversation there is no
#: longer anything to attach to; two thousand lines is more of one than anybody reads back
#: through, and about what a long turn's tools and thinking come to.
_KEPT = 8
_LINES = 2000

#: The three steps one agent of a flow is configured in, in the order they are asked: which
#: coding agent takes its turns and as whom, which model it runs and at what effort, and --
#: only for a place the flow said may be pointed anywhere -- which machine its work lands on.
#: Each depends on the one before it: an account belongs to a backend, and a model belongs to
#: the CLI that runs it.
_WHO, _WHAT, _WHERE = 0, 1, 2

#: The flow the interface opens on, which is the one that is only talking to one agent.
_STARTS_ON = "chat"


def _where() -> str:
    """The directory this is working in, as somebody reading a status line wants it.

    Read each time rather than kept: a flow is a Python file and may change directory under
    the interface, and the one thing this line must not do is name the wrong one.

    Returns:
      The path, with a home directory written as `~` -- the shortening every shell does, and
      the only one that shortens without losing anything.
    """
    here = Path.cwd()
    try:
        home = Path.home()
    except RuntimeError:
        return str(here)  # nobody's home directory, so nothing to shorten it against
    return str("~" / here.relative_to(home)) if here.is_relative_to(home) else str(here)


def _clipped(said: str, room: int) -> str:
    """One line of what is waiting, cut to a row rather than wrapped over several.

    Args:
      said: The line.
      room: How many columns there are for it.

    Returns:
      It, or as much of it as fits with an ellipsis where the rest was.
    """
    return said if len(said) <= room else said[: room - 1] + "…"


def _opens_on(*, goals: bool = True) -> list[Runs]:
    """The one agent the interface opens talking to, where there is one to open on.

    The first backend installed here that has said what it runs, at the first model it named
    -- which is that CLI's own idea of what it runs by default, and the only idea of it worth
    having. Nothing is written down here: a model to open on that was named in this file
    would be a model this file was right about on the day it was written.

    Returns:
      The one agent, or nothing at all where no backend here has yet said what it runs --
      which is a catalogue to fill rather than a model to guess at.
    """
    for backend, found in installed().items():
        if found:
            # Not the hardest effort, which is what the picker's cursor starts on: that is
            # the one to reach for, and this is the one to spend before anyone has asked for
            # anything. `high` is an effort every model of every backend here takes.
            return [Runs(f"{backend}/{found[0].name}:high", goals=goals)]
    return []


#: How many cells the bar opencode spins in its status line is wide. Blocks, not braille --
#: watching it run is what says so.
_BLOCKS = 8

#: What Claude Code marks each thing on screen with, taken from its own source and its own
#: screen: `⏺` where it can and `●` everywhere else for anything the agent said or did, `❯`
#: for a line you typed and for the prompt itself, `⎿` under a tool for what it came back
#: with, and `✻` for the line that closes a turn.
_SAID = "⏺" if sys.platform == "darwin" else "●"
_YOURS = "❯"
_CAME_BACK = "⎿"
_WORKED = "✻"

#: What it rules the prompt with, above and below, and what it rules a sheet with.
_RULE = "─"

#: The dot Claude Code separates the parts of a line with.
_DOT = " · "

#: The frames Claude Code spins while a turn is running, and the words it spins them beside.
_SPINNER = ("·|·", "·/·", "·—·", "·\\·")

#: The terminal's own colours, named so that the stylesheet can ask for them.
#:
#: Every surface is `ansi_default` -- the terminal's background, whatever it has been set to --
#: and everything the interface has to draw is one of the sixteen colours that terminal already
#: has a setting for. So it is not that the colours are read and matched: there is nothing to
#: read, because none of the colours are ours. A theme that named even one of them would be a
#: guess about the background it lands on, and that guess is what a black interface in a white
#: terminal is.
#:
#: `dark` is nearly inert here. It picks the palette Textual would convert ANSI colours through,
#: and `ansi` says not to convert them at all -- they go to the terminal as the terminal's own.
_TERMINAL = Theme(
    name="terminal",
    primary="ansi_blue",
    secondary="ansi_cyan",
    accent="ansi_bright_black",
    warning="ansi_yellow",
    error="ansi_red",
    success="ansi_green",
    foreground="ansi_default",
    background="ansi_default",
    surface="ansi_default",
    panel="ansi_default",
    boost="ansi_default",
    dark=True,
    ansi=True,
    variables={
        # The two Textual's own stylesheet asks an ANSI theme for. Default, like the rest:
        # they end up as the border of an inline app, and that border is the terminal's.
        "ansi-background": "ansi_default",
        "ansi-foreground": "ansi_default",
        # Where the cursor is. Both ends of the pair are named, because a highlight is the
        # one thing that must not be left to the terminal: against `ansi_default` on
        # `ansi_default` there is nothing to see, and a row that says which one is under the
        # cursor by being a shade of the background says it to nobody. Blue with white on it
        # carries its own contrast, so it reads the same whatever it is drawn over.
        "block-cursor-background": "ansi_blue",
        "block-cursor-foreground": "ansi_bright_white",
        "block-cursor-text-style": "bold",
        "block-cursor-blurred-background": "ansi_bright_black",
        "block-cursor-blurred-foreground": "ansi_bright_white",
        "block-cursor-blurred-text-style": "none",
        "input-cursor-background": "ansi_blue",
        "input-cursor-foreground": "ansi_bright_white",
        "input-cursor-text-style": "none",
        # What is selected, in the editor and anywhere on the screen: the same pair either
        # way, since it is one gesture and means one thing. Both ends named, for the reason
        # the cursor's are -- a selection drawn as a shade of the background is one nobody
        # can see the edges of, and the edges are what somebody dragging is watching.
        "input-selection-background": "ansi_bright_black",
        "input-selection-foreground": "ansi_bright_white",
        "screen-selection-background": "ansi_bright_black",
        "screen-selection-foreground": "ansi_bright_white",
        "block-hover-background": "ansi_default",
        # Chrome and anything said quietly, at the one slot every scheme keeps a grey in.
        # Not the foreground at half strength: half of `ansi_default` is `ansi_default`,
        # since there is nothing to blend it against until it reaches the terminal.
        "text-muted": "ansi_bright_black",
        "text-disabled": "ansi_bright_black",
        "border-blurred": "ansi_bright_black",
        "scrollbar": "ansi_bright_black",
        "scrollbar-background": "ansi_default",
        "scrollbar-hover": "ansi_bright_black",
        "scrollbar-active": "ansi_blue",
    },
)


class _Shown(NamedTuple):
    """One thing that has been put in the transcript, kept so that it can be drawn again.

    Attributes:
      content: What was drawn -- markup for a line, and the box this opens with as itself.
      shrink: Whether it is drawn to fit. The box is not: it is measured against the width it
        is rendered at, and one drawn to fit comes out split down its right-hand edge.
    """

    content: object
    shrink: bool


@dataclass
class _Kept:
    """What one conversation has to show, held against it rather than against the screen.

    Attributes:
      lines: What has been put in the transcript against it, oldest first and held to the
        last `_LINES` of them, the ones before that falling off the front.
      unread: Whether it has said something since it was last read, which is what the line
        above the prompt marks an agent holding one with.
      packed: Whether the last part shown was one the next may run on from. A thing about the
        conversation rather than about the screen: two of them talking at once would
        otherwise space each other's lines.
    """

    lines: deque[_Shown] = field(
        default_factory=lambda: deque[_Shown](maxlen=_LINES),
    )
    unread: bool = False
    packed: bool = False


class Editor(TextArea):
    """The prompt: multi-line, but enter sends rather than breaking the line."""

    BINDINGS: ClassVar = [
        Binding("enter", "send", "send", priority=True),
        # Both, because only one of them always arrives. A terminal reports shift+enter as
        # itself only where it speaks the keyboard protocol that has a way to say so, and
        # sends a bare carriage return where it does not -- which is enter, and would send
        # the line. `ctrl+j` is a line feed, so it reaches here from any terminal there is.
        Binding("shift+enter", "newline", "newline", priority=True),
        Binding("ctrl+j", "newline", "newline", priority=True),
    ]

    class Sent(Message):
        """What was typed, now that it has been sent."""

        def __init__(self, text: str) -> None:
            """Initializes the message.

            Args:
              text: What was typed.
            """
            super().__init__()
            self.text = text

    def action_send(self) -> None:
        """Takes what is offered, if anything is, and otherwise sends what is in the editor.

        Enter means over the offers what it means over any list: take the one under the
        cursor. What was typed goes when the offers are gone -- which is a line they have
        nothing more to add to, or esc, which puts them away. The line left showing about a
        finished command is not one of them: it is read, and enter sends what it is about.
        """
        listing = self.screen.query_one("#offers", OptionList)
        if listing.has_class("offering") and listing.highlighted is not None:
            self.take(str(listing.get_option_at_index(listing.highlighted).id))
            return
        said, self.text = self.text.strip(), ""
        if said:
            self.post_message(self.Sent(said))

    def action_newline(self) -> None:
        """Breaks the line, which is what enter would do anywhere else."""
        self.insert("\n")

    #: Whether what is in the editor was put there by walking what was typed here before,
    #: rather than typed. Nothing is offered against it while that is so: a line walked to
    #: is a line that already exists, and a list opening over it would take the arrows that
    #: are walking it -- one step back through a command, and there is no step forward.
    #: Sticky, because the message saying the text changed is posted rather than called: a
    #: flag held only around the assignment is clear again by the time it arrives. The next
    #: key that is not an arrow is a key that is typing, and clears it.
    walking = False

    async def _on_key(self, event: events.Key) -> None:
        """Gives tab and the arrows to the offers, but only while there are any.

        Bound here rather than on the application, and only when the list is showing: a key
        the offers are not using is the editor's, and a prompt of more than one line needs
        its arrows back. With nothing offered they walk what was typed here before, and only
        from the ends of what is being typed now -- up off the first line, down off the last
        -- so that a prompt of several lines is still moved around in. Tab reaches here only
        while there are offers to take: with none it is the interface's, which attaches to
        the next conversation with it.
        """
        if event.key not in ("up", "down"):
            self.walking = False
        listing = self.screen.query_one("#offers", OptionList)
        if not listing.has_class("offering"):
            if event.key in ("up", "down"):
                # textual types the property off the bare generic, so what it hands
                # back is an `App` of nothing in particular.
                history = cast(
                    "Humanize",
                    self.app,  # pyright: ignore[reportUnknownMemberType]
                ).history
                row, _ = self.cursor_location
                if event.key == "up" and row == 0:
                    said = history.back(self.text)
                elif event.key == "down" and row == self.document.line_count - 1:
                    said = history.forward()
                else:
                    return  # inside a prompt of more than one line, which is the editor's
                if said is None:
                    return  # nothing that way, so the key is the editor's as it always was
                event.prevent_default()
                event.stop()
                self.walking = True
                self.text = said
                self.move_cursor(self.document.end)
            return
        if event.key == "tab":
            event.prevent_default()
            event.stop()
            if listing.highlighted is not None:
                self.take(str(listing.get_option_at_index(listing.highlighted).id))
        elif event.key in ("up", "down"):
            event.prevent_default()
            event.stop()
            listing.action_cursor_down() if event.key == "down" else (
                listing.action_cursor_up()
            )
        elif event.key == "escape":
            event.prevent_default()
            event.stop()
            # Positional because textual's is: the class names follow it as *args.
            listing.set_class(False, "offering")  # noqa: FBT003

    def on_mouse_up(self) -> None:
        """Copies what was just dragged across in the editor, as everywhere else does.

        The editor selects for itself rather than letting the screen do it -- it holds a
        selection so that what is typed can be changed, not only read -- so the screen has
        nothing to copy after a drag in here, and this is the only place that knows there was
        one. A click rather than a drag leaves nothing selected, and copies nothing.
        """
        # textual types the property off the bare generic, so what it hands back is an
        # `App` of nothing in particular.
        cast(
            "Humanize",
            self.app,  # pyright: ignore[reportUnknownMemberType]
        ).copied(self.selected_text)

    def take(self, whole: str) -> None:
        """Replaces the part being finished with what was offered for it.

        Args:
          whole: The offer, in full.
        """
        typed = self.text
        self.text = typed[: len(typed) - len(typed.split(" ")[-1])] + whole + " "
        self.move_cursor(self.document.end)


class Humanize(App[None]):
    """A transcript, an editor under it, and a status line under that."""

    CSS = """
    /* Nothing here names a colour of its own. Every surface is the terminal's, and what has
       to stand out is either one of the sixteen colours the terminal already has a setting
       for or a reversal of it -- so the interface reads as part of whatever it was opened
       in, without asking the terminal a single question about itself. */
    Screen { background: $surface; }
    /* An ANSI surface is transparent, and Textual paints a modal over what is behind it by
       blending -- which over a transparent screen blends with nothing. Named, so a sheet is
       a sheet rather than something the transcript reads through. */
    ModalScreen { background: $background; }
    #transcript { width: 1fr; height: 1fr; padding: 0; }

    /* What was said to a flow and has not been taken yet, pinned above the prompt rather
       than written into the transcript: it has not happened, and a transcript is what has.
       Claude Code holds a queued message here too, and for the same reason -- it is still
       yours to see go, rather than something to scroll back for.

       On the left of the block that sits on the editor, beside what the run is running as:
       one thing above the prompt rather than two, so that neither pushes the other up the
       screen. As wide as what is in it, the right-hand side taking the rest. */
    #pinned { height: auto; }
    #queued { display: none; width: auto; height: auto; max-height: 6; padding: 0 2;
              color: $text-muted; }
    #queued.waiting { display: block; }

    /* Above the prompt and unbordered, at most ten rows: what Claude Code offers a
       half-typed command in. The row under the cursor is coloured, not filled. */
    #offers { display: none; max-height: 10; padding: 0 2; background: $background;
              border: none; scrollbar-size: 0 0; }
    #offers.offering, #offers.hinting { display: block; }
    #offers > .option-list--option-highlighted {
        background: $background; color: $primary; text-style: none; }

    /* The prompt: a rule across, what you are typing behind a `❯`, a rule across. Which is
       how Claude Code draws its own -- no box, no bar, no shadow. */
    #above { width: 1fr; height: auto; padding: 0 1; color: $text-muted;
             text-align: right; }
    .rule { height: 1; color: $text-muted; }
    #prompt { height: auto; background: $background; }
    #caret { width: 2; color: $text-muted; }
    #editor { height: auto; max-height: 10; border: none; padding: 0;
              background: $background; }
    #status { height: 1; padding: 0 2; color: $text-muted; }
    """

    #: Off, and its key given back. Nothing here is chosen from a dialog -- a `/` offers the
    #: commands and a flag offers whatever it is for -- so a palette of them over the top is a
    #: second way to say the same things, and one nothing else in this interface leads to.
    ENABLE_COMMAND_PALETTE = False

    BINDINGS: ClassVar = [
        Binding("ctrl+c", "interrupt", "interrupt", priority=True),
        # What the status line says while a flow runs, and what opencode's esc does there.
        # The editor takes esc first while it is offering something, and only then.
        Binding("escape", "stop_flow", "interrupt", show=False),
        # Forwards and backwards through the conversations the flow has open. Priority, since
        # tab and shift+tab are the screen's own way of moving the focus about, and there is
        # nowhere here for the focus to go.
        Binding("tab", "attach_next", "next agent", priority=True),
        Binding("shift+tab", "attach_previous", "previous agent", priority=True),
    ]

    def check_action(
        self,
        action: str,
        parameters: tuple[object, ...],  # noqa: ARG002  -- the same key, whatever it carries
    ) -> bool | None:
        """Whether one of the interface's own keys is live, with something up over it.

        Attaching to a conversation is not, twice over: a sheet is open in order to be
        answered, and both keys are its own while it is there, and the offers are open to be
        taken from, which is what tab does over them. A binding that is refused here is one
        the sheet or the editor is then offered rather than one that is swallowed, since the
        interface's own are priority bindings and would otherwise be matched first wherever
        the cursor was.

        Args:
          action: What the key would do.
          parameters: What it would do it with.

        Returns:
          Whether to run it.
        """
        # Every other one of ours is either the editor's, which a sheet has taken the focus
        # from, or means the same thing wherever it is pressed.
        if action not in ("attach_next", "attach_previous"):
            return True
        if len(self.screen_stack) > 1:
            return False
        # Asked of whatever is on the screen rather than of one widget, since a key may be
        # pressed before the offers themselves have been laid out.
        offering = any(offers.has_class("offering") for offers in self.query("#offers"))
        return not (action == "attach_next" and offering)

    def action_quit(self) -> None:  # pyright: ignore[reportIncompatibleMethodOverride]
        """Leaves, having first stopped whatever was running.

        A flow is a loop and a turn can think for minutes, so leaving without stopping it
        would leave the interface gone and the work going -- which reads as a hang.
        """
        for agent in self._agents:
            agent.stop()
        self._agents = []
        self.exit()

    def action_interrupt(self) -> None:
        """Takes back the nearest thing there is to take back, and leaves on two of these.

        Which is what ctrl+c means in a coding agent's terminal: the half-written line if
        there is one, the flow if there is not, and the interface itself if the last one
        already took something back -- so that leaving is always two presses away and never
        one, whatever was going on.
        """
        twice = time.monotonic() - self._interrupted < _AGAIN
        self._interrupted = time.monotonic()
        if twice:
            self.action_quit()
            return
        editor = self.query_one(Editor)
        if editor.text:
            editor.text = ""
            return
        if self._agents:
            self.action_stop_flow()
            return
        self.show("[dim]press ctrl+c again to exit[/dim]")

    def __init__(
        self,
        flow: str = "",
        agents: Sequence[Runs] = (),
        config: BaseModel | None = None,
    ) -> None:
        """Initializes an interface holding no agents, because nothing is running yet.

        Args:
          flow: The flow to open on, which is what `hmz -f` names -- or "" to open on what
            this workspace was last set up to run, and on the one that only talks to one
            agent where it has run nothing.
          agents: What each of that flow's agents runs, in the order it takes them, or
            nothing to open on what was remembered.
          config: What that flow is set up with, or None to open on what was remembered.
            Checked by whatever read the line: an interface is opened set up, not corrected.
        """
        # `ansi_color` up front rather than left to the theme: Textual picks the filter it
        # runs every colour through inside `App.__init__`, before a theme set below could
        # have said anything, and under `NO_COLOR` the wrong one there turns the whole
        # interface a single shade of black.
        super().__init__(ansi_color=True)
        # Drawn in the terminal's own colours rather than a scheme of ours. `TEXTUAL_THEME`
        # still wins, for anyone who would rather have one -- read here rather than left to
        # Textual, whose own default for it was settled when this module was imported. One
        # naming a theme that is not there falls back rather than refusing to start.
        self.register_theme(_TERMINAL)
        asked = os.environ.get("TEXTUAL_THEME", "")
        self.theme = asked if asked in self.available_themes else _TERMINAL.name
        #: The agents of the flow running now, which is who a typed line is said to.
        self._agents: list[AgentBase] = []
        #: What the flow has done so far, which is what the right-hand column shows, and who
        #: reads the agents' own logs into it while it runs.
        self._monitor = Monitor()
        self._tally = Tally([], self._monitor)
        #: Whether what a turn did on its way to an answer -- the tools it used, the thinking
        #: it did aloud -- is shown, which `/details` toggles.
        self._details = True
        #: Whether an agent may stop and ask, which `/afk` toggles. It may, until you say you
        #: are not there: a question nobody answers is a flow that has stopped.
        self._afk = False
        #: The question a turn has stopped on, if one has, and where its answer goes -- and
        #: which conversation it was shown on, so that what it will take for an answer is
        #: shown under it rather than wherever the person is looking by the time it lands.
        self._asked_on: weakref.ref[SessionBase] | None = None
        self._asking: Question | None = None
        self._answer = ""
        self._answered = threading.Event()
        #: When ctrl+c was last pressed, so that two of them in a row read as two.
        self._interrupted = 0.0
        #: When something was last copied off the screen, so that the status line can say so
        #: for a moment: a clipboard is written to silently, and a gesture that says nothing
        #: is one nobody knows worked.
        self._copied = 0.0
        #: The flow to run and what each of its agents runs, which start out as the flow that
        #: is only talking to one agent and the first agent there is to talk to. So the first
        #: thing you say starts something rather than being told to pick a flow first: a flow
        #: is what you reach for once talking to one agent is not the shape of the work, and
        #: nobody knows that before they have said anything.
        #:
        #: Nothing at all until some backend here has said what it runs, which is asked for in
        #: the background as this opens: a model to open on is one of that CLI's own, and
        #: there is no telling what those are without asking it.
        #: What this workspace was last set up to run, so that opening it again finds it
        #: that way rather than back at the default.
        self.settings = Settings()
        self._flow_named = flow or self.settings.flow or _STARTS_ON
        self._models = list(agents)
        #: One place per agent the flow drives: what the flow calls it, which is "" apiece
        #: for a flow that said how many it drives and nothing more, and the moments it needs
        #: that one to run. Kept beside the models rather than read off the flow each time the
        #: line above the prompt is drawn: that means loading and running a Python file, and
        #: this is drawn twice a second.
        self._wanted = self._places_of(self._flow_named)
        if not self._models:
            self._models = self.settings.agents(
                self._flow_named,
                tuple(place.goals_default for place in self._wanted),
            ) or _opens_on(
                goals=self._wanted[0].goals_default if self._wanted else True
            )
            # If the flow would not load, `_places_of` falls back to agents already in hand;
            # the remembered ones were not in hand on the first read.
            if not self._wanted and self._models:
                self._wanted = self._places_of(self._flow_named)
        self._models = [
            Runs(
                runs.spec,
                runs.anchor,
                runs.skills,
                runs.permission,
                runs.provider,
                goals=True,
            )
            if at < len(self._wanted) and self._wanted[at].goal
            else runs
            for at, runs in enumerate(self._models)
        ]
        #: What the flow itself is set up with, for a flow that says it can be set up at
        #: all: an instance of the model it declared, or None. Read back from what this
        #: workspace last ran, so a flow of many settings opens the way it was left.
        self._config = config or self._config_of(self._flow_named)
        #: What has been typed here before, which the arrows walk. Read now rather than each
        #: time it is asked for: a run started here writes this project's own history into
        #: being, and what is being walked must not change under whoever is walking it.
        self.history = History()
        #: When each agent's turn started, for the line that closes it.
        self._began: dict[str, float] = {}
        #: What each conversation has to show, against the conversation itself, so that
        #: attaching to one draws what it has said rather than every agent's at once. Keyed
        #: weakly: a flow drops a conversation a turn, and a transcript that held one open
        #: would be the interface keeping alive what the flow has let go of. The one under
        #: None is the interface's own, which is what there is to show before anything is
        #: attached -- the box this opens with, and whatever started the flow.
        self._kept: dict[weakref.ref[SessionBase] | None, _Kept] = {}
        #: The conversation being read: what the transcript shows, and where a typed line
        #: goes. Held by identity rather than by where it comes in the list, since the list
        #: churns; beside it the agent it belonged to and where it came, so that one which
        #: has gone can be replaced by the nearest thing there is to it.
        self._attached: weakref.ref[SessionBase] | None = None
        self._attached_was: tuple[str, int] = ("", 0)
        #: The conversations with a turn open, which are the only ones a typed line can go
        #: into: one written to a conversation between turns is answered on its own, outside
        #: the flow. Weakly held, for the reason the transcript is.
        self._working: weakref.WeakSet[SessionBase] = weakref.WeakSet()
        #: Said while no turn was open, for whichever turn starts next to take. Written from
        #: the event loop and drained from whichever thread a flow runs on, so it is held
        #: under a lock: `a running flow never drops a line` is only true if nothing races.
        self._queued: list[str] = []
        #: Said into a turn that was running, and not yet answered for: what a backend takes
        #: from us is not what the agent has heard, and every one of them says the second
        #: thing separately, as a `took`. Held under the same lock as `(agent, words)`, at
        #: most one per agent -- the next goes only once this one is answered for.
        self._given: list[tuple[str, str]] = []
        self._saying = threading.Lock()
        #: Whether the person has just been asked what to say next and answered out of the
        #: queue, in which case the turn that answer starts has its line already.
        self._handed = False
        #: Set when something is said, so a flow waiting to be told hears it at once rather
        #: than at the next tick, and whether a flow is waiting to be told at all.
        self._spoke = threading.Event()
        self._awaiting = False

    def _places_of(self, flow: str) -> tuple[Place, ...]:
        """The agents a flow drives: what it calls each one, and what each has to be able to do.

        Args:
          flow: The flow, by name or as a path.

        Returns:
          One place apiece -- and one unnamed place per agent already in hand for a flow that
          will not load, since a name is a label on something that runs and not a reason for
          anything to stop.
        """
        from hmz.runner import Place, wanted

        try:
            # By the name it was chosen under, not by the file that name resolves to: a file
            # may hold several flows, and which of them was asked for is the half after the
            # colon -- which resolving the name to a path throws away.
            return wanted(flow)
        except Exception:  # noqa: BLE001 -- a flow that will not load is still not a crash
            return tuple(
                Place(name="", person=False, moments=frozenset()) for _ in self._models
            )

    @staticmethod
    def _model_of(flow: str) -> type[BaseModel] | None:
        """What a flow says it can be set up with, if it says anything.

        Args:
          flow: The flow, by name or as a path.

        Returns:
          The model to ask with, or None for a flow that takes no setting up -- and for one
          that will not load, which is a flow to report where it is run rather than here.
        """
        from hmz.runner import configures

        try:
            return configures(flow)
        except Exception:  # noqa: BLE001 -- a flow that will not load is still not a crash
            return None

    def _config_of(self, flow: str) -> BaseModel | None:
        """How this workspace last set a flow up, read back through the flow's own model.

        Args:
          flow: The flow.

        Returns:
          What it was set up with, or None for a flow that takes no setting up, has not been
          set up here, or has since changed enough that what was kept no longer reads -- a
          setting file is a convenience, and one that no longer fits is one to start over
          from rather than to refuse to open on.
        """
        model = self._model_of(flow)
        if model is None:
            return None
        kept = self.settings.config(flow)
        if not kept:
            return None
        try:
            return model.model_validate(kept)
        except Exception:  # noqa: BLE001 -- what was kept no longer fits the flow
            return None

    @property
    def _named_by(self) -> tuple[str, ...]:
        """What the flow calls each agent it drives, which is what a line about one says."""
        return tuple(place.name for place in self._wanted)

    def compose(self) -> ComposeResult:
        """The transcript, the offers, the editor, the status. The width is the transcript's.

        Nothing sits beside it. What the flow is doing is on `/status`, which is opened when
        it is wanted: a column saying so the whole time costs a fifth of every line of every
        transcript, to say something that has usually not changed since it was last looked at.
        """
        yield Transcript(id="transcript")
        yield Choices(id="offers")
        # Both sides of the same block, right on top of the editor: what is waiting to go on
        # the left, what it would be going to on the right. Read from the bottom up -- the
        # last thing typed and the running total sit on the row above the rule.
        with Horizontal(id="pinned"):
            yield Static(id="queued")
            yield Static(id="above")
        yield Static(id="rule-above", classes="rule")
        with Horizontal(id="prompt"):
            yield Static(_YOURS, id="caret")
            yield Editor(id="editor", show_line_numbers=False)
        yield Static(id="rule-below", classes="rule")
        yield Static(id="status")

    def on_mount(self) -> None:
        """Says what this understands, then waits to be told something."""
        # Everything printed anywhere under this process lands in the transcript, which is what
        # makes a flow watchable: a session tees each agent's streams to ours as they arrive.
        self.begin_capture_print(self)
        self._welcome()
        self._draw()
        self.set_interval(_REFRESH, self._draw)
        self._asks_what_runs()
        # The editor is the only thing to type at, so it is the only thing that takes focus:
        # a transcript or a list that could hold it would swallow the keystrokes meant for it.
        for elsewhere in self.query("#transcript, #offers"):
            elsewhere.can_focus = False
        self.query_one(Editor).focus()

    @work
    async def _asks_what_runs(self) -> None:
        """Asks each backend here what it runs, the once, for the account nobody chose.

        Only the ones that have never been asked: what a CLI runs is kept, and this is the
        first filling of it -- the moment before that, there is nothing to offer at any of the
        sheets and nothing to open talking to.

        In the background and one at a time, because asking means starting a coding agent:
        a prompt cannot wait on one, and six at once is six of them. A backend that will not
        answer is left alone rather than retried -- ctrl+r on the models is what asks again.
        """
        import asyncio

        from hmz import models

        for backend in installed():
            if models.asked(backend):
                continue
            try:
                await asyncio.to_thread(models.ask, backend)
            except Exception as why:  # noqa: BLE001 -- a CLI that will not say what it runs
                # Not raised at whoever opened the interface: nobody asked for this, and a
                # backend that will not answer is one to ask again from the models.
                self.log(f"{backend} did not say what it runs: {why}")
                continue
            # Which may be the first model there is to open on, for an interface that opened
            # with nothing installed to talk to.
            if not self._models:
                self._models = _opens_on(
                    goals=self._wanted[0].goals_default if self._wanted else True
                )
            self._draw()

    def _welcome(self) -> None:
        """The box this opens with: what this is, and how to begin.

        The description is the one the package was built with rather than a second copy of
        it, so the sentence this answers to is the sentence it was published under.

        What is set up to run is not in it, nor is where it would run. Those are on the lines
        round the editor, where they are redrawn twice a second, and a second copy of either
        here could only be the copy that was true when the interface opened -- the transcript
        is append-only, so a line written into it is a line about the moment it was written.

        Its title rides in the top border and its corners are round, which is the one boxed
        thing on the screen: everything after it is text down the terminal. Drawn as a panel
        rather than as lines of rules, so that every side of it is measured against the same
        width at the moment it is rendered -- lines written to a width guessed before the
        screen was laid out come out of the transcript split down the right-hand edge. And
        it is only as wide as what is in it: a box ruled the whole way across an empty screen
        is mostly rule, and nothing in it is wider than the name drawn across the top.
        """
        from importlib.metadata import metadata, version

        self._into(
            None,
            Panel(
                Group(
                    Text(self._banner(), style="blue", no_wrap=True),
                    Text(""),
                    Text(str(metadata("hmz")["Summary"] or "")),
                    Text(""),
                    *(Text(line, style="dim") for line in _HELP),
                ),
                # Room around it, above and below and at both ends: the name drawn large is
                # the first thing on the screen and reads as cramped without any.
                padding=(1, 4),
                box=ROUNDED,
                border_style="dim",
                title=f"[dim]humanize v{version('hmz')}[/dim]",
                title_align="left",
                expand=False,
            ),
            shrink=False,
        )

    def _banner(self) -> str:
        """The name, drawn large.

        Returns:
          The word as block letters where the terminal is wide enough to hold them, and as
          the small face where it is not. Two of them and no more: a banner that wrapped
          would be worse than no banner, and one that is picked from a dozen faces by width
          is a dozen ways for it to be wrong.
        """
        for face in ("ansi_shadow", "small"):
            art = pyfiglet.figlet_format("humanize", font=face).rstrip("\n")
            drawn = [line for line in art.splitlines() if line.strip()]
            # Against what is left after the box: a border and four columns of room a side.
            if max(len(line) for line in drawn) <= self.size.width - 10:
                return "\n".join(drawn)
        return "\n".join(drawn)

    def on_print(self, event: events.Print) -> None:
        """Puts something printed under this process into the transcript, as a barred block.

        Output is barred rather than indented because that is what opencode does with it:
        a command and what it said are one block, set apart from the words around them.
        """
        if event.text.strip():
            for line in escape(event.text.rstrip("\n")).splitlines():
                self.show(f"[dim]  {_CAME_BACK}  {line}[/]")

    def on_text_selected(self) -> None:
        """Puts what was just selected with the mouse on the clipboard.

        Letting go of a selection is the whole gesture. The interface has the mouse -- it is
        drawing the highlight itself, the terminal never having been told a drag was going on
        -- so a selection nobody copied is one that goes nowhere.

        What is copied is the text the transcript was written as rather than the screen: a
        line that took four rows comes back as the line, without the breaks the width put in
        it and without the spaces that padded each row out to the edge.
        """
        self.copied(self.screen.get_selected_text() or "")

    def copied(self, text: str) -> None:
        """Puts something on the clipboard, and says on the status line that it went.

        By the escape a terminal takes for its clipboard, which is the only way to reach the
        clipboard of the machine somebody is sitting at while the interface runs on another
        one. Nothing else about it is ours: a terminal that will not take the escape is one to
        turn it on in, and holding shift while dragging is what every terminal keeps for
        itself.

        Args:
          text: What to copy, and "" for a gesture that came to nothing -- a click that
            landed on no text, an empty selection -- which is not a thing to say happened.
        """
        if not text:
            return
        self.copy_to_clipboard(text)
        self._copied = time.monotonic()
        self._draw()

    def _said_by_you(self, text: str) -> None:
        """Puts something you said in the transcript, behind the `❯` Claude Code marks it with.

        Args:
          text: What was said.
        """
        # What the conversation being read says next starts its own part.
        self._keeping(self._reading()).packed = False
        said = escape(text).splitlines() or [""]
        self.show("")
        self.show(f"[dim]{_YOURS}[/] {said[0]}")
        for line in said[1:]:
            self.show(f"  {line}")

    def show(self, text: str, style: str = "") -> None:
        """Puts a line in the transcript, on the conversation being read.

        The interface's own lines go where you are looking: what you typed, what a command
        came back with, what went wrong. They are not any conversation's, and a transcript
        that dropped them would be one where half of what you did never happened.

        Args:
          text: What to show, taken as markup when no style is given and as plain text
            otherwise -- so that a bracket an agent wrote stays a bracket.
          style: How to show it, as a Rich style, or "" to show it as it is.
        """
        body = text if style == "" else f"[{style}]{escape(text)}[/{style}]"
        self._into(None, body)

    def _into(
        self, session: SessionBase | None, content: object, *, shrink: bool = True
    ) -> None:
        """Keeps something against the conversation it belongs to, and draws it if it is read.

        Args:
          session: Whose it is, or None for the interface's own -- which belongs to whichever
            conversation is being read, since that is the one it was said over.
          content: What to draw, as markup or as something Rich renders.
          shrink: Whether to draw it to fit.
        """
        reading = self._reading()
        where = session if session is not None else reading
        kept = self._keeping(where)
        kept.lines.append(_Shown(content, shrink))
        if where is reading:
            self.query_one("#transcript", Transcript).write(content, shrink=shrink)
        else:
            kept.unread = True  # and the line above the prompt says so until it is read

    def _keeping(self, session: SessionBase | None) -> _Kept:
        """What is kept of one conversation, opening a place for it the first time.

        Args:
          session: The conversation, or None for the interface's own with nothing attached.

        Returns:
          What it has to show, which is what attaching to it draws.
        """
        key = weakref.ref(session) if session is not None else None
        if (kept := self._kept.get(key)) is not None:
            return kept
        kept = self._kept[key] = _Kept()
        # The oldest conversations go first, and never the one being read or the one just
        # opened: a flow that opens one a turn would otherwise be kept in full for as long as
        # it runs, and what is dropped this way is one there is nothing left to attach to.
        over = len([one for one in self._kept if one is not None]) - _KEPT
        dropping = [one for one in self._kept if one not in (None, key, self._attached)]
        for gone in dropping[: max(over, 0)]:
            del self._kept[gone]
        return kept

    def _conversations(self) -> list[tuple[AgentBase, SessionBase]]:
        """Every conversation the flow has open, in the order tab steps through them.

        The person is not among them: they are an agent a flow talks to rather than one it
        drives, and the conversation with them is this prompt.

        Returns:
          The agent and the conversation, agents in the order the flow takes them and each of
          their conversations oldest first.
        """
        from hmz.agents import HumanAgent

        return [
            (agent, session)
            for agent in self._agents
            if not isinstance(agent, HumanAgent)
            for session in agent.sessions
        ]

    def _reading(self) -> SessionBase | None:
        """The conversation being read, moving on where the one it was has gone.

        Conversations come and go -- a Ralph loop opens one a turn and drops the one before
        it -- so what is attached is held by identity, and one that has gone is replaced by
        the newest of that agent's, a loop that dropped one having already opened the next.
        Failing that, whatever is nearest to where it was, so that an agent leaving the flow
        entirely still leaves something to read.

        Returns:
          The conversation, or None while the flow has none open: one that has not started a
          conversation yet, and one that is over.
        """
        held = self._attached() if self._attached is not None else None
        open_now = self._conversations()
        if held is not None and any(session is held for _, session in open_now):
            return held
        if not open_now:
            self._attached = None
            return None
        who, was = self._attached_was
        theirs = [at for at, (agent, _) in enumerate(open_now) if agent.id == who]
        return self._now_reading(
            open_now, theirs[-1] if theirs else min(was, len(open_now) - 1)
        )

    def _now_reading(
        self,
        open_now: list[tuple[AgentBase, SessionBase]],
        at: int,
        *,
        stepped: bool = False,
    ) -> SessionBase:
        """Reads one of the conversations there are, carrying on under a line saying so.

        The screen is not cleared to do it. A flow that opens a conversation a turn would
        otherwise wipe the screen every time it did, and what was on it -- the turn you were
        reading, the line you typed, what went wrong -- would be gone for having been said to
        a conversation that is over. So what is on the screen stays on it, a line says what is
        being read from here down, and the conversation now being read is drawn under that.

        Args:
          open_now: The conversations there are, as :meth:`_conversations` gives them.
          at: Which of them to read.
          stepped: Whether somebody pressed tab for this, rather than the conversation being
            read having gone out from under them.

        Returns:
          The conversation now being read.
        """
        agent, session = open_now[at]
        # Whether one was being read, and which -- two questions, because a conversation the
        # flow has let go of is a reference that answers None while still saying there was one.
        reading, was = (
            self._attached is not None,
            self._attached() if self._attached is not None else None,
        )
        self._attached = weakref.ref(session)
        self._attached_was = (agent.id, at)
        kept = self._keeping(session)
        # What was shown with nothing attached is the head of this conversation: the box this
        # opened with, and whatever was said to start the flow. It is on the screen already --
        # it was read where it was written -- and it is kept against this conversation so that
        # a transcript drawn again from what was kept does not start mid-sentence.
        head = self._kept.pop(None, None)
        if head is not None:
            kept.lines = deque([*head.lines, *kept.lines], maxlen=_LINES)
        kept.unread = False
        if session is was:
            return (
                session  # what is being read has not changed, so nothing has happened
            )
        self._reading_now(agent, at, open_now, gone=reading and not stepped)
        if head is None:
            # Under the line that says so: what this conversation has said, which is nothing
            # for one just opened and everything for one being read again. Not for the first
            # of a run -- what was kept against it then is the head, which is already up.
            shown = self.query_one("#transcript", Transcript)
            for line in kept.lines:
                shown.write(line.content, shrink=line.shrink)
        return session

    def _reading_now(
        self,
        agent: AgentBase,
        at: int,
        open_now: list[tuple[AgentBase, SessionBase]],
        *,
        gone: bool,
    ) -> None:
        """Says which conversation is being read from here down, and why where that is not you.

        Written straight to the screen rather than kept against a conversation: it is a thing
        that happened to the screen rather than a thing either conversation said, and one kept
        against a conversation would be said again every time that one was read.

        Args:
          agent: Whose conversation it is.
          at: Where it comes among all of them.
          open_now: All of them, so that this one can be counted among that agent's.
          gone: Whether the conversation being read went out from under whoever was reading it,
            rather than being stepped off.
        """
        theirs = [one for one, (whose, _) in enumerate(open_now) if whose is agent]
        which = (
            f"{_DOT}{theirs.index(at) + 1} of {len(theirs)}" if len(theirs) > 1 else ""
        )
        # A blank line first, for the reason every other part of a turn has one: what is above
        # this belongs to another conversation, and the two run together without it.
        shown = self.query_one("#transcript", Transcript)
        shown.write("")
        shown.write(
            f"[dim]— {'that conversation has gone, now ' if gone else ''}"
            f"reading {escape(short(agent.id))}{which} —[/dim]"
        )

    def _unread(self, session: SessionBase) -> bool:
        """Whether one conversation has said something since it was last read.

        Args:
          session: The conversation.

        Returns:
          True if there is something on it nobody has looked at.
        """
        kept = self._kept.get(weakref.ref(session))
        return kept is not None and kept.unread

    def _held(self) -> list[Held]:
        """How many conversations each of the flow's agents has, and which one is being read.

        Returns:
          One per agent the flow drives, in the order it takes them -- and nothing at all
          with no flow running, which is a line about what is set up rather than about what
          it is doing.
        """
        from hmz.agents import HumanAgent

        reading = self._reading()
        held: list[Held] = []
        for agent in self._agents:
            if isinstance(agent, HumanAgent):
                continue
            sessions = agent.sessions
            at = next(
                (one for one, session in enumerate(sessions) if session is reading),
                None,
            )
            held.append(
                Held(
                    many=len(sessions),
                    at=at,
                    unread=any(
                        self._unread(session)
                        for one, session in enumerate(sessions)
                        if one != at
                    ),
                    working=any(session in self._working for session in sessions),
                )
            )
        return held

    def action_attach_next(self) -> None:
        """Reads the next conversation the flow has open, which is what tab is for.

        Forwards through the agents it drives and each of their conversations, and round
        again at the end: a flow may have a dozen of them open, and stepping to the next is
        quicker than anything that has to be opened in order to be chosen from.
        """
        self._attach_by(1)

    def action_attach_previous(self) -> None:
        """Reads the conversation before this one, which is what shift+tab is for."""
        self._attach_by(-1)

    def _attach_by(self, step: int) -> None:
        """Moves what is being read to the next conversation that is working, either way round.

        The ones that are working, rather than every one the flow has open: with a flow that
        drives ten agents, what somebody is stepping between is the ones thinking right now.
        A conversation between its turns is still read once it is reached -- what is being
        read is left alone until this is pressed -- but it is not stepped onto.

        Args:
          step: How far, and which way.
        """
        open_now = self._conversations()
        working = [one for one in open_now if one[1] in self._working]
        if not working:
            return  # nothing is working, which is a key that does nothing rather than an error
        held = self._reading()
        # From where the read one stands among all of them, so that stepping on from a
        # conversation that has since stopped goes to the next one that has not.
        at = next(
            (one for one, (_, session) in enumerate(open_now) if session is held), -1
        )
        ahead = [
            one for one, (_, session) in enumerate(open_now) if session in self._working
        ]
        if step > 0:
            landing = next((one for one in ahead if one > at), ahead[0])
        else:
            landing = next((one for one in reversed(ahead) if one < at), ahead[-1])
        self._now_reading(open_now, landing, stepped=True)
        self._draw()

    @on(TextArea.Changed)
    @on(TextArea.SelectionChanged)
    def _offer(self) -> None:
        """Offers whatever the line being typed could be finished with.

        Reconsidered when the cursor moves as well as when the text does: an offer made at
        the end of a line does not still stand once the cursor is back in the middle of it.
        """
        editor = self.query_one(Editor)
        typed = editor.text
        # At the end of what is being typed, and being typed rather than walked to.
        at_end = editor.cursor_location == editor.document.end and not editor.walking
        offers = offered(typed, _OWN) if at_end else []
        # Nothing left to finish, but a command still being written: its own line stays up,
        # since what it takes after its name is written there and is what is wanted just
        # then. Shown and not offered -- `offering` is what says a key is the list's.
        hint = hinted(typed, _OWN) if at_end and not offers else ""
        listing = self.query_one("#offers", OptionList)
        listing.clear_options()
        listing.set_class(bool(offers), "offering")
        listing.set_class(bool(hint), "hinting")
        if hint:
            listing.add_option(self._offer_of(f"/{hint}"))
        if offers:
            # Name on the left and what it is for on the right, as opencode lists its own.
            # The bare name is kept as the option's id, since that is what replaces the text.
            # The name and what it takes on the left, what it is for on the right. The bare
            # name is the option's id, since that is what replaces the text: taking an offer
            # must not type the arguments in as well.
            listing.add_options([self._offer_of(offer) for offer in offers])
            listing.highlighted = 0

    @staticmethod
    def _offer_of(offer: str) -> Option:
        """One row of the list: what would be typed, and what it is for.

        Args:
          offer: What taking it would leave in the editor, in full.

        Returns:
          The row. The bare name is its id, since that is what replaces the text -- taking
          an offer must not type the arguments in as well.
        """
        named = offer.removeprefix("/")
        # Escaped: what a command takes is written in brackets, and a bracket left as it is
        # would be read as markup and swallowed -- which is what `[path]` did. Padded first,
        # since the escaping adds characters that are not columns.
        return Option(
            escape(f"{f'{offer} {takes(named)}'.rstrip():<19}")
            + f"[dim]{escape(about(named))}[/dim]",
            id=offer,
        )

    def _draw(self) -> None:
        """Redraws the lines around the editor: what is above it, the rules, the status.

        Called on a timer, which keeps ticking while the interface is being taken down -- so
        there may be nothing left to draw on.
        """
        if not self.is_running:
            return
        spending = self._monitor.spending()
        spent = sum(spend.tokens for spend in spending)
        rate = sum(spend.rate for spend in spending)
        # Left, first match wins, as opencode's status line resolves it: what is running if
        # anything is, else where this is. Right, the usage. The two ends are pushed apart.
        working = self._monitor.now_working()
        if self._agents and not working and self._awaiting:
            # A flow that has run out of things to do until it is told one. Spinning a bar at
            # it would read as a turn that has been thinking for as long as you have been
            # deciding what to say, which is the opposite of what is happening.
            left = (
                f"[$text-muted]{_SPINNER[0]} waiting for you{_DOT}esc to interrupt[/]"
            )
        elif working or self._agents:
            bar = _SPINNER[int(time.monotonic() / _REFRESH) % len(_SPINNER)]
            # Whoever is talking and how long their turn has been going, or -- between two
            # turns -- the flow itself and how long the run has. A flow sleeps off a round,
            # commits, reads what the last turn wrote, and none of that is a flow that has
            # stopped: a clock still moving is what says so.
            since = min(
                (self._began[who] for who in working if who in self._began),
                default=self._monitor.began,
            )
            named = ", ".join(short(who) for who in working) or self._flowing()
            left = (
                f"[$secondary]{bar}[/] {escape(named)}… "
                f"[$text-muted]({time.monotonic() - since:.0f}s{_DOT}esc to interrupt)[/]"
            )
        else:
            # The flow that is set up to run, and the directory it would run in. Only with
            # nothing running: the two lines above are about a run once there is one, and
            # where it is working has not changed since it started.
            left = (
                f"[$secondary]◉[/] {escape(self._flowing())}"
                f"[$text-muted]{_DOT}{escape(_where())}[/]"
            )
        # For a moment after it happens, beside whatever else the line says: writing to a
        # clipboard is silent, and a person who has just dragged across half a screen is
        # owed the one word that says it went somewhere.
        if time.monotonic() - self._copied < _COPIED:
            left += f"[$text-muted]{_DOT}copied[/]"
        # Above the prompt on the right, where Claude Code says what it is running as. One
        # agent to a line rather than a row of them separated by commas: a flow drives several
        # and they are read one at a time, against the name the flow calls each one by -- and
        # with the conversations each of them is holding, since one of those is what is being
        # read and what a typed line goes to.
        lines = reads(self._named_by, self._models, self._held()) or [
            "no agent installed"
        ]
        if spent:
            lines.append(f"{thousands(spent)} tokens{_DOT}{rate:.0f}/s")
        # Beside it, and cut to what it leaves: the two are one block, and a pinned line
        # the width of the screen would push what the run is running as off the side of it.
        waiting = self._waiting_lines(max(len(line) for line in lines) + 2)
        if waiting:
            # Bottom up, both sides ending on the row above the rule: the last thing typed
            # and the running total are the two halves of where the run has got to, and one
            # of them hanging a row above the other reads as two things rather than one.
            rows = max(len(waiting), len(lines))
            lines = [""] * (rows - len(lines)) + lines
            waiting = [""] * (rows - len(waiting)) + waiting
        self.query_one("#above", Static).update(
            "[$text-muted]" + "\n".join(lines) + "[/]"
        )
        pinned = self.query_one("#queued", Static)
        pinned.set_class(bool(waiting), "waiting")
        # As content rather than as markup: this is what somebody typed, and a `[TODO]` in it
        # is a word rather than a tag. Neither escaper is safe here -- both only escape a
        # bracket that already looks like a tag to them, and the two disagree about which do.
        pinned.update(Content("\n".join(waiting)))
        for ruled in self.query(".rule").results(Static):
            ruled.update(_RULE * self.size.width)
        right = f"[$text-muted]{_DOT.join(self._keys())}[/]"
        # Measured as drawn rather than as written: markup is not what takes up columns.
        # Textual's own, since these are Textual's markup and name its colours.
        gap = (
            self.size.width
            - 4
            - sum(Content.from_markup(end).cell_length for end in (left, right))
        )
        self.query_one("#status", Static).update(
            left + " " * max(2, gap) + right, layout=False
        )

    def _flowing(self) -> str:
        """What is running now, flow inside flow, for the line that names one.

        A flow may reach for another by name and run it, so what is running is a list rather
        than a name: the one that was started, and whatever it called, innermost last. Read
        from the runner rather than asked of the flow -- a flow is a Python file and may branch
        any way it likes, so what it is doing is only ever visible where it was started.

        Returns:
          The flows, innermost last, and the one that is set up to run where none is running --
          which is what this line says with nothing going on.
        """
        from hmz.runner import running

        return " ▸ ".join(one.flow for one in running()) or self._flow_named

    def _waiting_lines(self, beside: int = 0) -> list[str]:
        """What has been said to the flow and not taken yet, as the pin above the prompt.

        Behind the same `❯` the transcript marks what you said with, and dim: it is yours,
        and it has not gone anywhere yet. Held to a few lines, with the rest counted -- a pin
        that grew without limit would push the transcript off the screen to say that a lot
        was queued, which the count says in one line.

        Args:
          beside: How many columns the block to the right of it takes, which are not the
            pin's to draw in.

        Returns:
          The lines to draw, oldest first, as text rather than as markup -- a bracket
          somebody typed is a bracket, and nothing here is drawn in a colour of its own.
          Nothing at all with nothing waiting.
        """
        with self._saying:
            # What has gone to an agent went before anything still queued, the queue being
            # drained from the front, so it reads oldest first the same way the transcript does.
            held = list(self._given) + [("", said) for said in self._queued]
        if not held:
            return []
        # One line of the pin is one row of the screen: what is over is cut with an ellipsis
        # rather than wrapped, or a pasted paragraph would be five lines and fifty rows, and
        # the transcript, the editor and the status line would all go off the bottom.
        room = max(_NARROW, self.size.width - beside - len(_YOURS) - 5)
        lines: list[str] = []
        for at, (who, said) in enumerate(held):
            first, *rest = said.splitlines() or [""]
            # Who has it, for a word already put to somebody: a flow drives several agents,
            # and which of them is holding your line is the half of this worth knowing.
            with_it = f"{_DOT}with {short(who)}" if who else ""
            # As the transcript sets one: the first line behind the marker, the rest lined
            # up under it.
            shown = [
                f"{_YOURS} {_clipped(first, room - len(with_it))}{with_it}",
                *(f"  {_clipped(line, room)}" for line in rest),
            ]
            if lines and len(lines) + len(shown) > _PINNED:
                # This one will not fit whole, so it is counted with the ones after it
                # rather than shown in half.
                lines.append(f"  … {len(held) - at} more waiting")
                return lines
            if len(shown) > _PINNED:
                # The first, and longer on its own than there is room for: what is left of
                # it is counted too, so that half a message never reads as the whole of one.
                lines.extend(shown[: _PINNED - 1])
                left = f"… {len(shown) - _PINNED + 1} more lines"
                if at + 1 < len(held):
                    left += f" and {len(held) - at - 1} more waiting"
                lines.append(f"  {left}")
                return lines
            lines.extend(shown)
            if len(lines) >= _PINNED and at + 1 < len(held):
                lines.append(f"  … {len(held) - at - 1} more waiting")
                return lines
        return lines

    def _switched(self, argv: list[str], *, now: bool) -> bool | None:
        """What a switch becomes: what was asked for, or the other of what it is.

        A toggle is what you reach for at a prompt and the wrong thing to write down: a line
        that says `on` means on whichever way the switch was left, which is what anything
        replaying a session needs.

        Args:
          argv: What followed the command, which is nothing, `on`, or `off`.
          now: How the switch is set.

        Returns:
          How to set it, or None for a line that named something else -- which is said and
          left alone rather than guessed at.
        """
        said = argv[0].lower() if argv else ""
        if said in ("on", "off"):
            return said == "on"
        if said:
            self.show(f"hmz: say on or off, not {argv[0]!r}", "red")
            return None
        return not now

    def _keys(self) -> list[str]:
        """The keys that do something right now, said in the order they are reached for.

        Only the ones that work: a shortcut listed in a state it does nothing in is worse
        than one that is not listed at all, and there is nowhere else to look them up.
        """
        if self.query_one("#offers", OptionList).has_class("offering"):
            return ["↑↓ move", "tab take", "esc dismiss"]
        keys: list[str] = []
        if self.query_one(Editor).text:
            # Enter does nothing with nothing typed, and a key that does nothing is not one
            # to offer: what it would do next is what it is called here.
            keys.append(
                "enter answer"
                if self._asking is not None
                else "enter say"
                if self._agents
                else "enter start"
            )
        if self._conversations():
            # Only with something to read: with one conversation open it is what attaches to
            # it, and with none it is a key that does nothing.
            keys.append("tab agent")
        keys.append("/ commands")
        keys.append("shift+enter newline")
        if self._agents:
            keys.append("esc stop")
        keys.append(
            "ctrl+c quit" if not self.query_one(Editor).text else "ctrl+c clear"
        )
        return keys

    def _mid_run(self, what: str) -> bool:
        """Whether a flow is running, and says so where that is why nothing happened.

        Which is the answer for anything that would change what is running while it runs.
        A flow holds the agents it was handed and drives them by its own control flow: swapped
        underneath it, the run carries on against the ones it already has, and the interface
        starts saying it is running something it is not. Stop it, then choose.

        Args:
          what: The command being turned down, so that the line says which one.

        Returns:
          True if a flow is running, having said so.
        """
        if not self._agents:
            return False
        self.show(f"hmz: {what} while a flow is running: esc stops it first", "red")
        return True

    def action_status(self) -> None:
        """Opens the sheet saying how the run is going, which is readable while it runs.

        Unlike the two that choose something: this one is read and changes nothing, so there
        is nothing for it to conflict with.
        """
        self.push_screen(
            Status(
                self._flow_named,
                self._named_by,
                self._models,
                self._monitor,
                self._config,
            )
        )

    @on(Editor.Sent)
    def _sent(self, event: Editor.Sent) -> None:
        """Takes what was typed as a command, or as something to say to the agent."""
        line = event.text
        # Written down whatever it turns out to be: a task, a word put into a running flow,
        # a command. All three were typed, and any of them may be worth typing again.
        self.history.add(line)
        if not line.startswith("/"):
            self._said(line)
            return
        self._said_by_you(line)
        name, _, rest = line[1:].partition(" ")
        try:
            argv = shlex.split(rest)
        except (
            ValueError
        ) as error:  # an unbalanced quote is a line to correct, not a crash
            self.show(f"hmz: {error}", "red")
            return
        if name == "exit":
            self.action_quit()
        elif name == "clear":
            self.action_clear()
        elif name == "flow":
            self.action_flow(argv[0] if argv else "")
        elif name == "config":
            self.action_config()
        elif name == "agents":
            self.action_agents()
        elif name == "providers":
            self.action_providers()
        elif name == "status":
            self.action_status()
        elif name == "details":
            if (switched := self._switched(argv, now=self._details)) is None:
                return
            self._details = switched
            shown = "shown" if self._details else "hidden"
            self.show(f"[dim]tool calls and thinking {shown}[/dim]")
        elif name == "afk":
            if (switched := self._switched(argv, now=self._afk)) is None:
                return
            self._afk = switched
            self.show(
                "[dim]away: an agent that wants to ask is told nobody is here[/dim]"
                if self._afk
                else "[dim]here: an agent may stop and ask you[/dim]"
            )
        elif name == "export":
            self._export()
        else:
            self.show(f"hmz: no such command: /{name}", "red")

    def action_clear(self) -> None:
        """Clears the screen, and nothing else.

        There is nothing else for it to clear. A turn carries no context across a cycle: a
        flow is handed agents that were made for that run and drops them at the end of it, so
        what is on screen is the whole of what starting over would have thrown away. What is
        running is left running, and what it has done so far is still beside it.

        The screen is one conversation, so what is cleared is that one's: clearing every
        conversation would be `/clear` reaching into ones nobody was looking at.
        """
        self._keeping(self._reading()).lines.clear()
        self.query_one("#transcript", Transcript).clear()
        self._welcome()  # a cleared screen is a screen just opened, and one opens with this
        self._draw()

    def action_stop_flow(self) -> None:
        """Stops the whole flow, not just the turn -- which is what esc is for.

        Every agent is told to take no further turn, so the one running now is closed out and
        the loop driving it ends rather than handing on to the next agent. The agents are let
        go of here rather than when the flow's own thread notices, so that the next thing
        said starts something instead of being put to a flow that is on its way out. Silent
        when nothing is running: esc is pressed to dismiss things, and a complaint apiece
        would be in the way.
        """
        for agent in self._agents:
            agent.stop()
        if self._agents:
            self.show("[dim]— stopping the flow —[/dim]")
        self._agents = []
        self._spoke.set()  # and a flow waiting to be told hears that it is over
        self._never_sent("the flow stopped first")

    def on_unmount(self) -> None:
        """Stops whatever is running as the interface goes, however it goes.

        A flow waiting to be told something waits on this interface, and nothing else will
        release it: an interface that went away without saying so would leave a thread
        waiting on a prompt that is not there, holding a backend open behind it. Said to
        nobody rather than to the transcript, which has gone with everything else.
        """
        for agent in self._agents:
            agent.stop()
        self._agents = []
        self._spoke.set()

    def _never_sent(self, because: str) -> None:
        """Puts whatever was still waiting into the transcript, nothing being left to take it.

        A flow ends two ways -- stopped by hand, or of its own accord -- and both leave the
        pin holding lines that are not on their way anywhere. They come off it and into the
        transcript as what they turned out to be: a line typed at a flow that is gone has to
        be somewhere, or the next thing typed would quietly take its place.

        Args:
          because: What to say about why it never went.
        """
        with self._saying:
            held, self._queued = self._queued, []
            given, self._given = [text for _, text in self._given], []
        if not (held or given):
            return
        for (
            said
        ) in given:  # oldest first: what went to an agent went before what is queued
            self._said_by_you(said)
        if given:
            # Put to an agent, which never said it had it: it may well have reached the
            # model, and saying it never went would be as wrong as saying it landed.
            self.show(f"[dim]   put to the agent, never taken back: {because}[/dim]")
        for said in held:
            self._said_by_you(said)
        if held:
            self.show(f"[dim]   never sent: {because}[/dim]")
        self._draw()

    def _export(self) -> None:
        """Writes the transcript beside the trace files, as opencode writes its markdown.

        What was written rather than what was drawn, which is the same thing a selection gives
        back: a file of lines broken where the terminal happened to run out of room is a file
        nothing can be read out of again.
        """
        import datetime

        stamp = datetime.datetime.now(datetime.UTC).strftime("%Y%m%dT%H%M%SZ")
        where = Path(".humanize") / f"{stamp}.session.md"
        where.parent.mkdir(parents=True, exist_ok=True)
        where.write_text(self.query_one("#transcript", Transcript).text)
        self.show(f"[dim]{where}[/dim]")

    @work
    async def action_flow(self, named: str = "", *, setting: bool = True) -> None:
        """Switches which flow runs, how it is set up, and what each of its agents is.

        Asked as one walk rather than as a handful of dialogs: how the flow is set up is asked
        next because only the flow that was just chosen says what there is to set, and each of
        its agents after that because a flow says for itself how many it drives -- three steps
        apiece, which :meth:`_each_agent` walks. Esc off any of them is a step back to the one
        before, since what you would be walking back from is the choice that led there.

        Args:
          named: A flow of your own, as a path. Left out, the ones humanize came with are
            listed instead -- a path is typed, since guessing which files below here are
            flows means reading all of them.
          setting: Whether to ask how the flow is set up on the way past. `/agents` is the
            one that does not: it is the other half of `/config`, and a question it did not
            ask is one it must not put up.
        """
        from hmz.runner import wanted

        if self._mid_run("no choosing a flow"):
            return
        while True:
            picked = named or await self.push_screen_wait(Flows(self._flow_named))
            if picked is None:
                return
            # Nothing is taken until a choice lands: walking in to look at the flows and
            # walking back out again must leave the interface as ready to be typed at as it
            # was, rather than holding a flow with nothing to run it on.
            switching = picked if isinstance(picked, str) else picked[0]
            agents = installed()
            if not agents:
                self.show("hmz: no coding agent is installed here", "red")
                return
            try:
                # One place per agent the flow drives: what it calls each -- a name apiece
                # where it declared them as a named tuple -- how many there are either way,
                # and what it needs each of them to be able to do. Asked by the name it was
                # chosen under: a file may hold several flows, and the half after the colon
                # is which of them this is.
                places = wanted(switching)
            except Exception as why:  # noqa: BLE001 -- a flow that will not load
                self.show(f"hmz: {why}", "red")
                return
            # How the flow itself runs, for a flow that says it can be set up: asked of the
            # flow being switched to rather than of the one in force, since the settings
            # belong to the model that flow declared and to no other.
            model = self._model_of(switching) if setting else None
            held = (
                self._config
                if switching == self._flow_named
                else self._config_of(switching)
            )
            if model is not None:
                held = await self.push_screen_wait(
                    Configures(
                        switching, model, held if isinstance(held, model) else None
                    )
                )
                if held is None:
                    if named:
                        return  # nothing to step back into: this walk began here
                    continue  # back to the flows, which is where this walk came from
            chosen = await self._each_agent(switching, places, agents)
            if chosen is not None:
                # A flow is chosen in order to be run, so whatever is running stops: the
                # interface opens on one already, and a choice that quietly went to the back
                # of the queue behind it would read as no choice at all. Answering the same
                # way twice is not a choice, though, and must not end the conversation.
                if (switching, list(chosen), held) != (
                    self._flow_named,
                    self._models,
                    self._config,
                ):
                    self.action_stop_flow()
                self._flow_named, self._models = switching, list(chosen)
                self._wanted, self._config = places, held
                self.settings.remember(
                    switching,
                    self._named_by,
                    self._models,
                    held.model_dump(mode="json") if held is not None else None,
                )
                self.show("[dim]say what to do, and the flow starts on it[/dim]")
                self._draw()
                return
            if named and model is None:
                return  # a flow of your own, and nothing before this to step back into
            if named:
                # Back to how it is set up, which is the step this walk came through.
                continue
            # And otherwise round again, which is the step back off the leftmost column.

    async def _each_agent(
        self,
        flow: str,
        places: tuple[Place, ...],
        agents: dict[str, tuple[Model, ...]],
    ) -> list[Runs] | None:
        """Asks what each agent of a flow is, three steps apiece and one agent at a time.

        Three because each depends on the one before it: which coding agent takes its turns
        and which account it runs as, then which of that CLI's models at what effort, then --
        only where the flow said this one may be pointed at a machine -- where its work lands.
        An account belongs to a backend and a model belongs to the CLI that runs it, so
        neither is answerable until the CLI has been chosen.

        Esc off any of them is the step before: off the third into the second, off the second
        into the first, off the first into the agent before it, and off the first step of the
        first agent, out of the walk entirely -- which changes nothing at all. Stepping back
        into a step finds it as it was left, since a question that had forgotten its own
        answer would be a different question.

        Args:
          flow: The flow whose agents these are.
          places: One place per agent it drives, in the order it takes them.
          agents: The CLIs installed here, and what each of them says it runs.

        Returns:
          What each of them runs, in the order the flow takes them -- and nothing at all for
          a flow that drives none, which is a flow that talks only to the person at this
          prompt. None where the walk was left.
        """
        from hmz import models

        whose: dict[int, Whose] = {}
        runs: dict[int, Runs] = {}
        at, step = 0, _WHO
        while at < len(places):
            named = called(places, at)
            if step == _WHO:
                signed = await self.push_screen_wait(
                    RunsAs(flow, named, places[at], agents, whose.get(at))
                )
                if signed is None:
                    at -= 1
                    if at < 0:
                        return None  # the step before the first of these is out of the walk
                    step = _WHERE if pointed(places[at]) else _WHAT
                    continue
                whose[at] = signed
                step = _WHAT
            elif step == _WHAT:
                held = whose[at]
                chosen = await self.push_screen_wait(
                    Models(
                        flow,
                        named,
                        held,
                        # What that account may name rather than what the CLI says as whoever
                        # is at this machine: two accounts of one CLI are two catalogues, and
                        # the step before this one settled which. The one nobody chose is
                        # already in hand, having been read when the walk began.
                        models.offered(held.cli, held.provider)
                        if held.provider
                        else agents.get(held.cli, ()),
                        places[at],
                        runs.get(at),
                    )
                )
                if chosen is None:
                    step = _WHO
                    continue
                runs[at] = chosen
                if pointed(places[at]):
                    step = _WHERE
                else:
                    # A place the flow said nothing about works here and is not asked, so
                    # answering the model is the whole of that agent.
                    at, step = at + 1, _WHO
            else:
                where = await self.push_screen_wait(Anchors(named, runs[at].anchor))
                if where is None:
                    step = _WHAT
                    continue
                runs[at] = runs[at]._replace(anchor=where)
                at, step = at + 1, _WHO
        return [runs[one] for one in range(len(places))]

    def action_agents(self) -> None:
        """Sets what each of the flow's agents runs, which is what `/agents` is for.

        Neither the flow nor how it is set up is asked for again: `/config` is the other
        half, and this one is about what the flow runs on. So esc is a way out rather than a
        step back into a question this did not come through.
        """
        if self._mid_run("no setting agents"):
            return
        self.action_flow(self._flow_named, setting=False)

    @work
    async def action_config(self) -> None:
        """Sets up the flow itself, which is what `/config` is for.

        Only what the flow says it takes, and nothing about the agents: `/agents` is the
        other half, and a flow that says it takes no setting up says so here.
        """
        if self._mid_run("no setting up a flow"):
            return
        model = self._model_of(self._flow_named)
        if model is None:
            self.show(f"hmz: {self._flow_named} takes no setting up", "red")
            return
        held = await self.push_screen_wait(
            Configures(
                self._flow_named,
                model,
                self._config if isinstance(self._config, model) else None,
            )
        )
        if held is None:
            return
        self._config = held
        self.settings.remember(
            self._flow_named,
            self._named_by,
            self._models,
            held.model_dump(mode="json"),
        )
        self._draw()

    @work
    async def action_providers(self) -> None:
        """Walks the accounts an agent may be run as, which is what `/providers` is for.

        The sheet comes back after each thing done to one, since what it says is what there
        is now: an account made or taken away is a list that has changed. Esc closes it, and
        esc off any of the sheets it opens is a step back into the one before -- so a walk in
        to look at them and out again changes nothing.

        Not refused while a flow runs. What it holds is not what is running: an agent reads
        the account it was configured with once, so one made or taken away now is one the
        next run sees. A login that takes the terminal does hold the rest of the interface up
        while it has it, which is what handing the terminal over means.
        """
        while True:
            doing = await self.push_screen_wait(Providers())
            if doing is None:
                return
            # The three words `hmz providers` uses for the same three things, which is where
            # the sheet took them from: one vocabulary for one list of things to do.
            if doing.what == "add":
                await self._make_provider()
            elif doing.what == "login":
                await self._sign_provider_in(doing.cli, doing.name)
            else:
                self._drop_provider(doing.cli, doing.name)

    async def _make_provider(self) -> None:
        """Asks which CLI, and then walks that backend's own way in.

        Two questions rather than one, because the second is only answerable once the first
        has been: a backend's ways in are its own. The rest of the walk is the one the sheet
        an agent's account is chosen on runs, so making one from either place is the same
        thing done in the same order.
        """
        while True:
            cli = await self.push_screen_wait(Backends())
            if cli is None:
                return  # nothing before this to step back into
            outcome = await made(self, cli)
            # Walking out of the first question the walk itself asks is a step back into the
            # one asked here, since that is the step before it. Only here: the same walk from
            # the sheet an agent's account is chosen on has nothing behind it but that sheet.
            if outcome.provider is not None or outcome.why:
                break
        made_one = outcome.provider
        if made_one is None:  # a name or a directory that will not do
            self.show(f"hmz: {outcome.why}", "red")
            return
        self.show(
            f"[dim]{escape(made_one.cli)}/{escape(made_one.name)} is written down at "
            f"{escape(str(made_one.at))}[/dim]"
        )
        if outcome.status:
            self.show(f"hmz: signing it in exited {outcome.status}", "red")
            return
        if outcome.way_runs:
            self.show(
                f"[dim]{escape(made_one.cli)}/{escape(made_one.name)} is signed in[/dim]"
            )
        # What it runs is asked as soon as it lands, since that is what an account is for.
        self.show(
            f"[dim]{escape(made_one.cli)} says it runs {outcome.runs} models as "
            f"{escape(made_one.name)}[/dim]"
            if outcome.runs
            else f"[dim]{escape(made_one.cli)} did not say what it runs as "
            f"{escape(made_one.name)}; ctrl+r on its models asks again[/dim]"
        )

    async def _sign_provider_in(self, cli: str, name: str) -> None:
        """Runs one account's own way in again, asking for whatever it still needs.

        Args:
          cli: The backend it is for.
          name: What the account is called.
        """
        from hmz import providers as held
        from hmz.providers import login as signing

        provider = held.find(cli, name)
        if provider is None:
            self.show(f"hmz: no provider {cli}/{name}", "red")
            return
        way = signing.way_of(cli, provider.way)
        if way is None or not way.argv:
            self.show(
                f"hmz: {cli}/{name} was made by {provider.way}, which has nothing to run; "
                "make it again to change what it holds",
                "red",
            )
            return
        # What it already holds answers what it can. A key the CLI keeps in its own store is
        # not among them -- it was never kept here -- so it is asked for again.
        answers = dict(provider.env)
        if signing.asked(way, answers):
            signs = await self.push_screen_wait(Signing(cli, way, name=name))
            if signs is None:
                return  # walked out, which signs nothing in and changes nothing
            answers |= signs.answers
        if not self._signed_in(provider, way, answers):
            return
        # Signed in again is possibly a different account, and certainly a fresh answer to
        # what it runs: an account that has just changed hands is one to ask again.
        runs = await asks(cli, name)
        self.show(
            f"[dim]{escape(cli)} says it runs {runs} models as {escape(name)}[/dim]"
            if runs
            else f"[dim]{escape(cli)} did not say what it runs as {escape(name)}; "
            "ctrl+r on its models asks again[/dim]"
        )

    def _signed_in(self, provider: Provider, way: Way, answers: dict[str, str]) -> bool:
        """Hands the terminal to a backend's own way in, and says what came of it.

        A login is a browser opened, a code read out, a token exchanged: it owns the screen
        while it runs, and there is nothing for this interface to draw over it. A way that is
        only answers has already happened, having been written down.

        Args:
          provider: The account being signed in.
          way: The way in, whose own command is what runs.
          answers: What its questions were answered with.

        Returns:
          Whether it landed, so that what follows a login knows there was one.
        """
        from hmz.providers import login as signing

        if not way.argv:
            return False
        try:
            with handed_over(self):
                status = signing.sign_in(provider, way, answers)
        except OSError as why:  # the backend's own command is not on this machine
            self.show(f"hmz: {way.argv[0]}: {why}", "red")
            return False
        if status:
            self.show(f"hmz: {way.argv[0]} exited {status}", "red")
            return False
        self.show(
            f"[dim]{escape(provider.cli)}/{escape(provider.name)} is signed in[/dim]"
        )
        return True

    def _drop_provider(self, cli: str, name: str) -> None:
        """Takes one account away, credentials and all, and says so.

        Args:
          cli: The backend it is for.
          name: What it is called.
        """
        from hmz import providers as held

        try:
            gone = held.remove(cli, name)
        except ValueError as why:  # a name nothing could ever have been kept under
            self.show(f"hmz: {why}", "red")
            return
        if not gone:
            self.show(f"hmz: no provider {cli}/{name}", "red")
            return
        self.show(
            f"[dim]{escape(cli)}/{escape(name)} is gone, credentials and all[/dim]"
        )

    def _at_turn_start(self) -> list[str]:
        """What a turn starting folds into its prompt, which is one waiting line, or none.

        None when the person has just handed the flow the line it is starting this turn on:
        that line is this turn's, and taking the one behind it as well would put the two in
        front of the agent together and have them answered once -- which is the same thing
        going wrong from the other side.

        Returns:
          The one line to fold in, or nothing at all.
        """
        with self._saying:
            if self._handed:
                self._handed = False
                return []
        return self._take()

    def _take(self) -> list[str]:
        """Takes the oldest thing said while nobody was working, and leaves the rest.

        One line, not the queue: five lines typed in a row are five things said, and folding
        them into one prompt would have them answered once. The one behind this goes into
        the turn after, or into this one the moment it is running.

        The queue is the interface's rather than any one agent's: a line is typed at the flow
        and reaches whichever agent asks for it first, which is what "a typed line reaches
        whoever has the turn" means. Both hooks drain it, and both drain it destructively, so
        a line is delivered once however it is asked for.

        Returns:
          The oldest thing said, as the one-line list a turn folds into its prompt, which is
          nothing at all when nothing is waiting.
        """
        with self._saying:
            if not self._queued:
                return []
            held = [self._queued.pop(0)]
        self._on_screen(self._went, held)
        return held

    def _on_screen(
        self, doing: Callable[..., None], *said: object, **and_so: object
    ) -> None:
        """Draws something from whichever thread is asking, which is not always the same one.

        A turn asks for what is waiting from its own thread; a flow between turns asks from
        the flow's; and a test drives the interface from the event loop itself. Only the
        first two can go through `call_from_thread`; the loop itself may just draw.

        Args:
          doing: What to draw with.
          said: What to draw.
          and_so: The rest of what to draw with.
        """
        try:
            asyncio.get_running_loop()
        except RuntimeError:  # no loop here, so this is a thread of somebody's own
            with contextlib.suppress(RuntimeError):  # or the interface has gone
                self.call_from_thread(lambda: doing(*said, **and_so))
            return
        if self.is_running:  # and one that has gone has nothing left to draw on
            doing(*said, **and_so)

    def _went(self, held: list[str]) -> None:
        """Puts what was waiting into the transcript, now that it has gone.

        Args:
          held: What was taken, oldest first.
        """
        for said in held:
            self._said_by_you(said)
        self._draw()

    def _listen(self, agent: AgentBase) -> str | None:
        """Waits at the prompt for a flow that has nothing to do until it is told something.

        Called from the flow's own thread, which waits here. Nothing on the event loop is
        touched, so the interface goes on being an interface while a flow waits in it.

        Asked of the agent that is waiting rather than of whatever is running now: a flow
        that has been stopped takes a while to unwind, and one still sitting here when the
        next flow has started would otherwise read that flow's agents as its own -- and take
        the line meant for it.

        Args:
          agent: Whose flow is waiting, which is the one this answers about.

        Returns:
          What was said next, or None once this flow is over -- stopped by hand, or the
          interface going away, either of which has to release this rather than leave a
          thread waiting on a prompt that is not there.
        """
        if agent.stopped or agent not in self._agents:
            return None
        self._awaiting = True
        try:
            while True:
                # Cleared before the queue is read, so that a line arriving between the two
                # sets it again and is not waited through.
                self._spoke.clear()
                if agent.stopped or agent not in self._agents:
                    return None
                if held := self._take():
                    # Whatever turn this answer starts is that line's turn, and takes
                    # nothing else out of the queue on the way in.
                    with self._saying:
                        self._handed = True
                    return "\n\n".join(held)
                self._spoke.wait(_REFRESH)
        finally:
            self._awaiting = False

    def _as_they_were_set_up(self, chosen: list[AgentBase]) -> list[AgentBase]:
        """Sets each agent up as it was chosen: where it works, what it holds, who it is.

        Done to the agents rather than said on the line that made them: all of them are
        settings of the agent, and `hmz exec` reads a line that says what each one runs and
        nothing else. An agent that works here, was never asked about skills and runs as this
        machine is signed in is left exactly as it was.

        Args:
          chosen: The agents the line named, in the order the flow takes them.

        Returns:
          The same agents, or one set up in place of any that was given a machine, told which
          of its CLI's skills to have, or told which account to run as.

        Raises:
            ValueError: If a target cannot be read, or an agent was given an account there is
              no such thing as -- both before any of them has run, since either is a line to
              correct at the prompt rather than a traceback out of a flow's own thread.
        """
        from dataclasses import replace

        from hmz import providers
        from hmz.agents import anchored

        moved: list[AgentBase] = []
        for at, agent in enumerate(chosen):
            runs = self._models[at] if at < len(self._models) else Runs("")
            if (
                not runs.anchor
                and runs.skills is None
                and not runs.permission
                and not runs.provider
                and agent.config.goals is runs.goals
            ):
                moved.append(agent)
                continue
            if runs.provider and providers.find(agent.backend, runs.provider) is None:
                # Asked now rather than when the first turn needs it: an agent that cannot
                # find the account it was told to run as must not quietly run as whoever
                # started it is signed in as, and must not do it half an hour in.
                raise ValueError(
                    f"no {agent.backend} provider called {runs.provider!r}"
                )
            # The config is frozen, so an agent that works elsewhere, without a skill its CLI
            # would have loaded, allowed less than an agent nobody asked about, or signed in
            # as somebody else, is another agent at the same model and effort -- which is
            # what it is.
            moved.append(
                type(agent)(
                    replace(
                        agent.config,
                        machine=anchored(runs.anchor),
                        skills=runs.skills,
                        provider=runs.provider,
                        goals=runs.goals,
                        **({"permission": runs.permission} if runs.permission else {}),
                    )
                )
            )
        return moved

    def _flow(self, argv: list[str]) -> None:
        """Starts a flow, keeping its agents so that a typed line can reach one.

        Args:
          argv: The command line, as `hmz exec` takes it.
        """
        from hmz.runner import Runner

        if self._agents:
            self.show("hmz: a flow is already running", "red")
            return
        try:
            path, chosen, task, _ = flow_and_agents(argv)
        except SystemExit:
            return  # argparse has already said what was wrong, and it went to the transcript
        try:
            chosen = self._as_they_were_set_up(chosen)
        except ValueError as why:  # a target that cannot be read is a line to correct
            self.show(f"hmz: {why}", "red")
            return
        try:
            # Loaded here rather than on the thread it will run on, so that the agents it
            # drives are in hand before anything is hooked up to them: a flow that says it
            # talks to the person drives one more than was chosen, and the person is reached
            # through this interface like everything else. How the flow itself is set up
            # goes with them: it is a setting of the flow rather than of any agent, so it
            # is not on the line that says what each of them runs.
            runner = Runner(path, chosen, self._config)
        except Exception as why:  # noqa: BLE001 -- a flow that will not load is a line to fix
            self.show(f"hmz: {why}", "red")
            return
        agents = list(runner.agents)
        self._agents = agents
        self._monitor = Monitor()
        # What the run costs is read from the logs the agents keep, which they write as they
        # go: a backend only says what a turn cost once the turn is over, and a turn is long.
        self._tally = Tally(agents, self._monitor)
        self._tally.watch()
        with self._saying:
            self._queued, self._given, self._handed = [], [], False

        for agent in agents:
            agent.watch(self._heard)
            # Whichever turn starts next takes the oldest line that was held.
            agent.waiting = self._at_turn_start
            # Bound to the agent, so that each of these answers about the flow that is
            # asking rather than about whichever flow is running by the time it is asked.
            agent.ask = functools.partial(self._ask, agent)
            agent.prompting = functools.partial(self._listen, agent)
        self._draw()

        # This run's, whatever is being watched by the time it ends.
        watching, tally = self._monitor, self._tally

        def drive() -> int:
            try:
                runner.run(task)
            finally:
                tally.stops()  # read once more, for what the last turn wrote on its way out
                watching.stops()  # the clock the rate is over is the run's, and it is over
                # Only this run's own, and only while it is still the one running. A flow
                # takes a while to unwind after it is stopped -- a loop sleeps off its round,
                # a server is given seconds to go -- and the next flow may have started in
                # the meantime. Clearing then would leave the running one unreachable, and
                # saying it was done would be saying it of the wrong flow.
                if self._agents is agents:
                    self._agents = []
                    with contextlib.suppress(RuntimeError):
                        self.call_from_thread(
                            self.show, "[dim]— the flow is done —[/dim]"
                        )
                    # And whatever it never got round to taking, which is now on its way
                    # nowhere: a flow that ends of its own accord strands the pin exactly as
                    # one that is stopped does.
                    self._on_screen(self._never_sent, "the flow ended first")
            return 0

        self._background(drive)

    def _heard(
        self, agent: AgentBase, session: SessionBase | None, event: Event
    ) -> None:
        """Shows what a turn said, on the transcript of the conversation that said it.

        And takes what it cost into what the right-hand column shows, which is per agent: a
        conversation is where a thing is read, and the bill is the agent's.

        Called from whichever thread the turn is running on, which is why everything drawn
        from here goes through `_on_screen`.

        Args:
          agent: Whose turn said it.
          session: Which of that agent's conversations said it, or None for something the
            agent said rather than one of them -- a question put by a server that speaks for
            every conversation it holds. That one goes on the transcript of whichever of the
            agent's conversations is working, and on the one being read where none of them
            is, so that a turn which stopped to ask still reaches whoever is at the prompt.
          event: What was said.
        """
        # First, whatever else happens: showing a line raises once the interface has gone, and
        # what a watcher raises is swallowed, so accounting after it would be lost.
        for model, tokens in event.tokens.items():
            self._monitor.spend(agent.id, tokens, model=model)
        if event.kind == "took":
            # The agent saying a word put into its turn is now in front of it, which is the
            # one thing that makes a word said rather than posted.
            self._on_screen(self._took, agent.id, event.text)
            return
        if event.kind == "begins":
            self._monitor.begins(agent.id, agent.config.model)
            self._began[agent.id] = time.monotonic()
            if session is not None:
                # Which is what makes it a conversation a typed line may go into: one written
                # to a conversation between turns is answered on its own, outside the flow.
                self._working.add(session)
        elif event.kind == "ends":
            self._monitor.ends(agent.id)
            if session is not None:
                self._working.discard(session)
            # Whatever it was holding is not on its way anywhere now: the turn it was put
            # into is over, and it never said it had it.
            self._on_screen(self._ended_holding, agent.id)
            # The line opencode closes a message with: a filled square, two spaces, then the
            # parts separated by a middle dot.
            took = time.monotonic() - self._began.pop(agent.id, time.monotonic())
            # The line Claude Code closes a turn with, which says how long it worked.
            self._on_screen(
                self._part,
                session,
                f"[dim]{_WORKED} Worked for {took:.0f}s"
                f"{_DOT}{escape(short(agent.id))}[/]",
                packs=False,
            )
        elif event.kind == "tool" and self._details:
            # The tool on the bullet, what it came back with under it -- Claude Code's shape.
            named, _, about = escape(event.text).partition(" ")
            self._on_screen(
                self._part,
                session,
                f"[green]{_SAID}[/] {named}[dim]({about})[/]",
                packs=True,
            )
        elif event.kind == "reasoning" and self._details:
            self._on_screen(
                self._part,
                session,
                "\n".join(
                    f"[dim italic]{line}[/]" for line in escape(event.text).splitlines()
                ),
                packs=False,
            )
        elif event.kind == "asks":
            self._on_screen(
                self._asked_by,
                agent,
                session,
                f"[yellow]{_SAID}[/] {escape(event.text)}",
            )
        elif event.kind == "text":
            # The bullet on the first line, two spaces under it for the rest, which is how
            # Claude Code sets a message it has just written.
            said = escape(event.text).splitlines() or [""]
            self._on_screen(
                self._part,
                session,
                "\n".join(
                    [
                        f"[green]{_SAID}[/] {said[0]}",
                        *(f"  {line}" for line in said[1:]),
                    ]
                ),
                packs=False,
            )

    def _asked_by(
        self, agent: AgentBase, session: SessionBase | None, text: str
    ) -> None:
        """Puts a question where whoever is at the prompt will come across it.

        A question is the one thing an agent says that may not be any one conversation's: the
        server a codex or a kimi agent puts it through serves every conversation that agent
        holds, so it says which agent asked and no more. It goes on whichever of that agent's
        conversations is working, and on the one being read where none of them is -- either
        way somewhere it can be answered from, which is what a question is for.

        Args:
          agent: Who asked.
          session: Which of its conversations asked, or None where the agent asked.
          text: The question, as markup.
        """
        asked = session if session is not None else self._working_in(agent)
        # Written down so that what it will take for an answer goes under it rather than
        # wherever the person happens to be looking by then: the two are one question.
        self._asked_on = weakref.ref(asked) if asked is not None else None
        self._part(asked, text, packs=False)

    def _working_in(self, agent: AgentBase) -> SessionBase | None:
        """Which of one agent's conversations has a turn open, for a thing the agent said.

        Args:
          agent: The agent.

        Returns:
          The newest of its conversations that is working, or None where none of them is --
          which leaves what it said on whatever is being read. Only the conversations there
          are to read: the person's is this prompt, and is not one of them.
        """
        working = [
            session
            for who, session in self._conversations()
            if who is agent and session in self._working
        ]
        return working[-1] if working else None

    def _part(self, session: SessionBase | None, text: str, *, packs: bool) -> None:
        """Puts one part of a turn in the transcript, spaced as opencode spaces its own.

        A blank line goes between the parts, except between two that pack -- one-line tool
        rows run together, and everything else is set apart. Spaced per conversation: two of
        them talking at once would otherwise run each other's lines together.

        Args:
          session: Whose part it is, or None for one to show on whatever is being read.
          text: The part, as markup.
          packs: Whether this part is one that runs on from the one before it.
        """
        kept = self._keeping(session if session is not None else self._reading())
        if not (packs and kept.packed):
            self._into(session, "")
        kept.packed = packs
        self._into(session, text)

    def _background(self, work: Callable[[], int]) -> None:
        """Runs something off the event loop, showing what it says rather than dying of it.

        Args:
          work: What to do, answering with the status to report, if any.
        """

        def go() -> None:
            from hmz.agents import Stopped

            try:
                status = work()
            except SystemExit as stopped:  # argparse rejecting the line, not a crash
                status = int(stopped.code or 0)
            except Stopped:
                return  # asked for: esc already said the flow was stopping
            except Exception:  # noqa: BLE001 -- a flow fails any way it likes, and is shown
                with contextlib.suppress(RuntimeError):  # or the interface has gone
                    self.call_from_thread(
                        self.show, traceback.format_exc().strip(), "red"
                    )
                return
            if status:
                with contextlib.suppress(RuntimeError):
                    self.call_from_thread(self.show, f"— exited {status} —", "red")

        # A thread of our own rather than a worker: a worker is joined on the way out, and a
        # turn that is still thinking would hold the interpreter open behind a closed screen.
        threading.Thread(target=go, daemon=True).start()

    def _said(self, text: str) -> None:
        """Takes a line that is not a command, which is a task, an answer, or a word put in.

        With a flow chosen and not yet running, it is the task that starts it -- the way a
        first message to opencode is the thing it is asked to do, and the reason the flow
        this opens on is one that takes anything as a task. With one running, it is the
        answer to whatever the flow stopped to ask, or goes to the agent taking its turn --
        into the turn under way, or to the flow waiting to be told the next one.

        Args:
          text: What was said.
        """
        if self._asking is not None:
            self._said_by_you(text)
            self._answer = text
            self._answered.set()  # and the turn waiting on it carries on
        elif self._agents:
            self._interject(text)
        elif self._set_up:
            self._said_by_you(text)
            named = [part for runs in self._models for part in ("-a", runs.spec)]
            self._flow(["-f", self._flow_named, *named, text])
        else:
            self.show("hmz: no coding agent is installed here", "red")

    def _ask(self, agent: AgentBase, question: Question) -> str | None:
        """Puts a question a turn stopped on to whoever is at this prompt, and waits for them.

        Called from the turn's own thread, which is the one that waits: the agent has stopped
        working until this is answered. `/afk` is what says nobody is here to answer, and so
        is a flow that ends or is stopped while the question is still up -- neither leaves a
        turn waiting on a reply that is not coming.

        Asked of the agent that is asking rather than of whatever is running now, as
        :meth:`_listen` is, so that a flow on its way out cannot take the answer meant for
        the flow that replaced it.

        Args:
          agent: Whose turn stopped to ask.
          question: What the agent wants to know.

        Returns:
          What was typed, or None if nobody was there to type it.
        """
        if self._afk or agent.stopped or agent not in self._agents:
            return None
        # Cleared before the question goes up, so that an answer arriving between the two is
        # not cleared away with it.
        self._answered.clear()
        self._answer, self._asking = "", question
        with contextlib.suppress(RuntimeError):  # or the interface has gone
            self.call_from_thread(self._show_question, question)
        while not self._answered.wait(_REFRESH):
            # `/afk` while the question is up says so too, or saying you are away would
            # leave the turn waiting on the answer you had just declined to give.
            if self._afk or agent.stopped or agent not in self._agents:
                break
        self._asking = None
        return self._answer or None

    def _show_question(self, question: Question) -> None:
        """Shows what a question offers, under the question itself.

        The question is shown as the turn says it, like anything else the agent said. What is
        added here is what it will take for an answer, which only the one asking knows -- and
        it goes on the conversation the question went on, or the two would be read apart.

        Args:
          question: What the agent wants to know.
        """
        asked = self._asked_on() if self._asked_on is not None else None
        for option in question.options:
            self._into(asked, f"      [dim]· {escape(option)}[/dim]")
        self._into(asked, "   [dim]type an answer, or /afk to stop being asked[/dim]")

    @property
    def _set_up(self) -> bool:
        """Whether there is something for each of the flow's agents to run on.

        There is always a flow -- the interface opens on one -- so this is only ever short of
        an agent, which is a machine with no coding agent installed on it. A flow that asks
        for none is not short of anything: the person at this prompt is an agent it is handed
        rather than one anybody chooses, so a flow that talks only to them has everything it
        needs the moment it is chosen.
        """
        return bool(self._models) or not self._wanted

    def _interject(self, text: str) -> None:
        """Puts something in the queue for the flow, and sends it if nothing is in the way.

        Everything typed joins one queue, whether or not a turn is running: a line is a
        thing said, and things said go one at a time and in order. It is pinned above the
        prompt rather than written into the transcript until it goes -- it has not been said
        to anybody yet, and a transcript is what happened, which is what Claude Code does
        with a queued line too.

        Args:
          text: What to say.
        """
        with self._saying:
            self._queued.append(text)
        self._spoke.set()  # a flow between turns is waiting to be told something
        self._draw()  # rather than at the next tick: it was just typed
        self._hand_over()

    def _hand_over(self) -> None:
        """Puts the oldest waiting line into the conversation being read, one at a time.

        Into that one rather than into whichever agent happens to be working: a flow drives
        several agents and each of them holds as many conversations as it likes, so "the one
        that is working" is not something a line can be said to. The one being read is, and
        it is the one whose answer is on the screen.

        One at a time and never two: a backend given a second word while it is still
        swallowing the first runs the two together and answers once, so five lines typed in
        a row would come back as one reply. The next goes only once the turn has said it has
        this one, which is also the only point at which the two could not be run together.

        Nothing is sent between turns. A line has nowhere to go but the queue then -- writing
        it to a conversation that is not working would have it answered on its own, outside
        the flow -- so it waits for whichever turn starts next, and a running flow never
        drops one.
        """
        session = self._reading()
        if session is None or session not in self._working:
            return
        # The agent alongside its conversation: a word put in is pinned against whoever has
        # it, and it is that agent's own stream that will say it has been taken in.
        agent = next(
            (who for who, one in self._conversations() if one is session), None
        )
        if agent is None:
            return
        with self._saying:
            if any(who == agent.id for who, _ in self._given):
                return  # it is holding one already, and holds one at a time
            if not self._queued:
                return
            text = self._queued.pop(0)
            self._given.append((agent.id, text))
        self._draw()

        def put_in() -> int:
            # Off the event loop: this writes to the agent, and a large paste into a pipe the
            # interface itself is draining would otherwise deadlock the two.
            try:
                session.interject(text)
            except (NotImplementedError, RuntimeError, OSError) as error:
                self._on_screen(self._unreached, agent.id, text, str(error))
            except subprocess.CalledProcessError as refused:
                # A backend that refused it: codex drops a steer that named a turn already
                # over, and kimi answers one inside a 200. Either way it never went.
                self._on_screen(
                    self._unreached,
                    agent.id,
                    text,
                    refused.stderr or "the agent refused it",
                )
            return 0

        self._background(put_in)

    def _unreached(self, who: str, text: str, because: str) -> None:
        """Puts a word back at the head of the queue, the agent never having taken it.

        At the head rather than the end, and without trying the next one behind it: it was
        said before everything still waiting, and sending that one now would be sending it
        to the agent that just refused this.

        Args:
          who: The agent it was put to.
          text: The word.
          because: What the backend said about it.
        """
        with self._saying:
            if (who, text) in self._given:
                self._given.remove((who, text))
                self._queued.insert(0, text)
        self.show(f"hmz: {because}", "red")
        self._spoke.set()  # and whichever turn starts next takes it instead
        self._draw()

    def _took(self, who: str, text: str) -> None:
        """Takes a word off the pin, the agent having said it now has it.

        Args:
          who: The agent that said so.
          text: The word it said it has.
        """
        with self._saying:
            if (who, text) not in self._given:
                return  # somebody else's word, or one already written down
            self._given.remove((who, text))
        self._said_by_you(text)
        self._draw()
        self._hand_over()  # and the next one behind it goes now that this is through

    def _ended_holding(self, who: str) -> None:
        """Says what became of the words an agent was holding when its turn ended.

        The turn is over and it never said it had them, so they are neither waiting nor
        taken: they were put to it, and what it did with them is between it and the backend.
        Every backend but codex runs such a word as a turn of its own afterwards, and codex
        drops it -- which is more than this can tell from here, so it says what it knows.

        Args:
          who: The agent whose turn ended.
        """
        with self._saying:
            held = [text for agent, text in self._given if agent == who]
            self._given = [pair for pair in self._given if pair[0] != who]
        if not held:
            return
        for text in held:
            self._said_by_you(text)
        self.show(
            f"[dim]   put to {escape(short(who))}, which ended its turn without saying "
            f"it had {'them' if len(held) > 1 else 'it'}[/dim]"
        )
        self._draw()

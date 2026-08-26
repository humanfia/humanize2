"""humanize as a coding agent's own terminal, with a flow underneath instead of one agent.

Laid out the way Claude Code is, and no wider: a transcript the width of the terminal, an
editor under it between two rules, and a status line under that. Nothing sits beside them --
how the run is going is on `/status`, and `/flow` both chooses the loop and, a page along,
sets what each of its agents runs.

The transcript is a tab per agent, and one more where all of them appear together. A flow
drives several agents and each of them holds as many conversations as it likes; every agent's
lines interleaved is none of them readable, and a screen wiped every time a loop opened its
next conversation is a screen nobody can read back through. So each agent keeps a transcript
of its own, all of its conversations running on down it, and the tab this opens on is the one
that shows the lot -- which is where somebody watches a flow rather than an agent. tab and
shift+tab step between that one and whichever agents are working.

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

from hmz import telemetry
from hmz.runner import flow_and_agents
from hmz.settings import Settings

from .btw import AgentProgress, FlowSnapshot, Observation, compact, format_snapshot
from .complete import about, hinted, offered, takes
from .discover import installable, installed
from .history import History
from .monitor import Monitor, short, thousands
from .pick import EVERY as _EVERY
from .pick import (
    Adjusted,
    Adjusts,
    Chosen,
    Cycles,
    Drawn,
    Fallbacks,
    Flows,
    Flowverses,
    Held,
    Providers,
    Reports,
    Runs,
    Saved,
    Status,
    carries_on,
    config_of,
    opens_on,
    places_of,
    reads,
    settled,
)
from .selecting import Choices, Transcript
from .tally import Tally

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from pydantic import BaseModel

    from hmz.agents import AgentBase, Event, Question, SessionBase
    from hmz.flows import Place

#: What the editor understands, named as opencode names them, one step along: what answers
#: here is a flow rather than an agent, so opencode's `/agents` is `/flow`, and what a flow
#: runs on is an agent apiece rather than one model, so its `/models` is the page along from
#: it -- `/agents` being the ones saved to be imported there. `hmz anchor` is not here: it is
#: not a thing to do to a flow that is running, and it is a command line of its own. What a
#: run left behind is `/cycles`, which is where the runs of this directory are.
_OWN = (
    "flow",
    "btw",
    "flowverses",
    "agents",
    "providers",
    "fallback",
    "cycles",
    "settings",
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
    "/flow chooses the loop and what drives it.",
    "/providers holds the accounts they run as.",
)

#: How often the right-hand column and the status line are redrawn, in seconds.
_REFRESH = 0.5

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

#: How many transcripts are kept, and how many lines of each. One per agent and one for all
#: of them together, so a flow of ten agents is eleven -- and the ones before that are the
#: agents of flows that have already ended, which are kept until there are this many newer.
#: Two thousand lines is more of one than anybody reads back through, and about what a long
#: turn's tools and thinking come to.
_KEPT = 16
_LINES = 2000

#: How long a second ctrl+c has to arrive in for the two to be one gesture. Long enough to
#: read the line that says what the next press does and then press it, and short enough that
#: a press minutes later is a first press rather than half of one nobody remembers making.
_AGAIN = 3.0

#: The three steps one agent of a flow is configured in, in the order they are asked: which
#: coding agent takes its turns and as whom, which model it runs and at what effort, and --
#: only for a place the flow said may be pointed anywhere -- which machine its work lands on.
#: Each depends on the one before it: an account belongs to a backend, and a model belongs to
#: the CLI that runs it.
_WHO, _WHAT, _WHERE = 0, 1, 2

#: The flow the interface opens on, which is the one that is only talking to one agent.
_STARTS_ON = "chat"

#: How much live activity a side question may carry into its isolated context, and how many
#: side questions may have model turns open at once. Both are bounds on optional observation:
#: a day-long flow and a pasted row of questions must not grow the interface without limit.
_BTW_EVENTS = 80
_BTW_ACTIVE = 4


def _quiet_watch(
    _agent: AgentBase,
    _session: SessionBase | None,
    _event: Event,
) -> None:
    """Consumes a side agent's events so backend output stays out of the main transcript."""


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
    """What one transcript has to show, held against it rather than against the screen.

    One per agent, and one more for all of them together. Held rather than drawn once and
    forgotten because stepping to another agent draws that agent's from the top: a transcript
    is what that agent has done, and a screen that only ever appended would be every agent's
    lines shuffled into one another with no way of reading any of them back.

    Attributes:
      lines: What has been put in it, oldest first and held to the last `_LINES` of them, the
        ones before that falling off the front.
      unread: Whether it has said something since it was last read, which is what the line
        above the prompt marks an agent with.
      packed: Whether the last part shown was one the next may run on from. A thing about the
        transcript rather than about the screen: two agents talking at once would otherwise
        space each other's lines.
      spoke: Which agent said the last thing on it, so that the one where all of them appear
        together says who a line is from when that changes. "" on an agent's own, where
        there is only ever the one answer to it.
    """

    lines: deque[_Shown] = field(
        default_factory=lambda: deque[_Shown](maxlen=_LINES),
    )
    unread: bool = False
    packed: bool = False
    spoke: str = ""


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
        # How the run is going, which is where the flow is drawn. Not what stops a flow: a
        # key pressed to dismiss whatever is on the screen must not be the key that ends a
        # day's work, and esc is pressed to dismiss things everywhere else in this
        # interface. The editor takes it first while it is offering something.
        Binding("escape", "status", "status", show=False),
        # Round the transcripts: the one every agent is on, then whichever are working.
        # Priority, since tab and shift+tab are the screen's own way of moving the focus
        # about, and there is nowhere here for the focus to go.
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
        self._close_btw()
        self.exit()

    def _close_btw(self) -> None:
        """Closes the optional side sessions without touching any flow session."""
        with self._btw_lock:
            self._btw_closed = True
            self._btw_generation += 1
            held = [session for _, session in self._btw_active.values()]
            self._btw_active.clear()
            self._btw_running.clear()
        for session in held:
            with contextlib.suppress(Exception):
                session.close()

    def action_interrupt(self) -> None:
        """Takes back the nearest thing there is to take back, on a press or two or three.

        The half-written line first, if there is one, which is what ctrl+c does in every
        terminal there is and what nobody presses it twice for.

        With nothing typed it is the run, and it is asked twice: a flow is a day's work
        behind a key that is also pressed by mistake, so the first press says what the next
        one does and the second one does it. Every agent is told to take no further turn, so
        the turn running now is closed out and the loop ends rather than handing on.

        A third press does not wait for it. A flow that has been told to stop unwinds in its
        own time -- a loop sleeps off its round, a server is given its seconds -- and a third
        press closes every conversation still open under whatever turn it is in, which is the
        backend's process going. That is the last thing a key can do about a flow.

        With nothing running it is the interface, asked the same way: twice, because leaving
        is not what ctrl+c means anywhere else and a first press that left would be a run
        somebody ended while reaching to clear a line.
        """
        editor = self.query_one(Editor)
        if editor.text:
            editor.text = ""
            self._presses = 0
            return
        now = time.monotonic()
        # A press long enough after the last is the first of its own gesture: nobody
        # remembers pressing this two minutes ago, and the line that said what the next one
        # would do has been gone for most of that.
        self._presses = self._presses + 1 if now - self._pressed < _AGAIN else 1
        self._pressed = now
        if self._agents:
            self._interrupts()
        elif self._stopping:
            # A flow told to stop and not yet gone. However long ago it was told: this is
            # the one thing left that a key can do about it, and asking for it twice over
            # would be asking twice about a run that is already over.
            self._forces()
        elif self._presses > 1:
            self.action_quit()
        else:
            self.show("[dim]— press ctrl+c again to leave —[/dim]")
        self._draw()

    def _interrupts(self) -> None:
        """The first two presses at a flow that is running: say so, then stop it."""
        if self._presses < 2:  # noqa: PLR2004 -- the second press is what stops it
            self.show("[dim]— press ctrl+c again to stop the flow —[/dim]")
            return
        self.action_stop_flow()
        # Counted from nothing again, so that the press after this one is the one that does
        # not wait for the flow to unwind rather than the one that leaves.
        self._presses = 0

    def _forces(self) -> None:
        """The press after the one that stopped a flow, which does not wait for it to go.

        Telling an agent to stop closes its conversations, and a backend that took no notice
        of that is the reason there is a third press: every conversation still open is closed
        again, which is the backend's process going. What the flow gets back is a turn that
        failed, the same thing it would have got had the agent fallen over by itself.

        And the run reads as over from here, whatever is still unwinding behind it: nothing
        is left that a turn could still be running in, so nothing is left spinning at the
        person who has just asked twice for it to stop.
        """
        closing = [
            session
            for agent in self._stopping
            for session in agent.sessions
            if session in self._working
        ]
        self._presses = 0
        self._stopping = []
        if not closing:
            return
        self.show(
            f"[dim]— closing {len(closing)} conversation(s) under their turns —[/dim]"
        )
        # On this thread, as telling the flow to stop is: closing a conversation is closing
        # the process behind it, which is a second at the outside.
        for session in closing:
            with contextlib.suppress(Exception):  # a conversation already gone is gone
                session.close()
            self._working.discard(session)

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
        #: The task of the run in front of us and a bounded plain record of what its agent
        #: streams have said. `/btw` reads these once, as a snapshot; it never reaches into a
        #: flow's conversations for context, because doing that would make the side question a
        #: turn of the flow. The same lock holds the side sessions, since their threads add and
        #: remove them while the interface thread may close them on the way out.
        self._flow_task = ""
        self._btw_events: deque[Observation] = deque(maxlen=_BTW_EVENTS)
        self._btw_active: dict[int, tuple[AgentBase, SessionBase]] = {}
        self._btw_running: set[int] = set()
        self._btw_lock = threading.Lock()
        self._btw_serial = 0
        self._btw_generation = 0
        self._btw_closed = False
        #: Whether what a turn did on its way to an answer -- the tools it used, the thinking
        #: it did aloud, whatever it printed on its way past -- is shown, which `/details`
        #: toggles. Off, because a flow is watched to see where it has got to: what the
        #: agents said to each other and to you is that, and a tool row per file read is a
        #: transcript nobody is reading and the answer scrolled off the top of it.
        self._details = False
        #: Whether an agent may stop and ask, which `/afk` toggles. It may, until you say you
        #: are not there: a question nobody answers is a flow that has stopped.
        self._afk = False
        #: The question a turn has stopped on, if one has, and where its answer goes -- and
        #: which agent it was shown against, so that what it will take for an answer is shown
        #: under it rather than wherever the person is looking by the time it lands.
        self._asked_on: str | None = None
        self._asking: Question | None = None
        self._answer = ""
        self._answered = threading.Event()
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
        # What is installed here and what each of them says it runs, which is what a place
        # nothing was remembered for falls back on.
        backends = installed()
        if not self._models:
            self._models = self.settings.agents(
                self._flow_named,
                tuple(place.goals_default for place in self._wanted),
            ) or opens_on(
                backends,
                goals=self._wanted[0].goals_default if self._wanted else True,
            )
            # If the flow would not load, `_places_of` falls back to agents already in hand;
            # the remembered ones were not in hand on the first read.
            if not self._wanted and self._models:
                self._wanted = self._places_of(self._flow_named)
        self._models = settled(self._models, self._wanted, backends)
        #: What the flow itself is set up with, for a flow that says it can be set up at
        #: all: an instance of the model it declared, or None. Read back from what this
        #: workspace last ran, so a flow of many settings opens the way it was left.
        self._config = config or config_of(
            self._flow_named, self.settings.config(self._flow_named)
        )
        #: What has been typed here before, which the arrows walk. Read now rather than each
        #: time it is asked for: a run started here writes this project's own history into
        #: being, and what is being walked must not change under whoever is walking it.
        self.history = History()
        #: When each agent's turn started, for the line that closes it.
        self._began: dict[str, float] = {}
        #: What each transcript has to show: one per agent, under that agent's id, and one
        #: under `_EVERY` where all of them appear together. Kept by name rather than by the
        #: object, since an agent's conversations come and go under it -- a Ralph loop opens
        #: one a turn -- and what is read is the agent rather than whichever of them is open.
        self._kept: dict[str, _Kept] = {}
        #: Which transcript is being read: what the screen shows, and which agent a typed
        #: line is said to. The one they all appear on until somebody steps off it, that
        #: being where a flow is watched rather than one agent of it.
        self._attached: str = _EVERY
        #: When ctrl+c was last pressed, and how many times it has been pressed in a row, so
        #: that the second and third mean more than the first. `_AGAIN` is how long a press
        #: counts for.
        self._pressed = 0.0
        self._presses = 0
        #: The agents of a flow that has been told to stop and has not finished unwinding.
        #: A third ctrl+c closes their conversations under whatever turn is still open, which
        #: is the only thing left that a key can do about a flow already on its way out.
        self._stopping: list[AgentBase] = []
        #: The agents of the last run, which outlive it: their transcripts are still on the
        #: screen when the flow is over, so the diagram that reads one out is still about
        #: them. `_agents` is the running flow's and is let go of the moment it ends, so that
        #: the next thing typed starts something rather than being put to a flow that is gone.
        self._ran: list[AgentBase] = []
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
        from hmz.flows import Place

        # By the name it was chosen under, not by the file that name resolves to: a file may
        # hold several flows, and which of them was asked for is the half after the colon --
        # which resolving the name to a path throws away.
        places = places_of(flow)
        if places is not None:
            return places
        return tuple(
            Place(name="", person=False, moments=frozenset()) for _ in self._models
        )

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
        self._asks_about_reports()
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
        answer is left alone rather than retried -- `r` on the models is what asks again.
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
                self._models = opens_on(
                    installed(),
                    goals=self._wanted[0].goals_default if self._wanted else True,
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

        Only with `/details` on. What a backend writes on its way past is the working rather
        than the answer -- the same thing its tool rows and its thinking are -- and a flow
        watched to see where it has got to is one where all of that is in the way. The raw
        line is still retained in the bounded `/btw` snapshot when details are off.
        """
        if event.text.strip():
            # Flow-owned progress (for example, a Ralph round counter) is useful to `/btw`
            # even when `/details` keeps it out of the visible transcript.
            with self._btw_lock:
                self._btw_events.append(
                    Observation(
                        agent="",
                        kind="flow",
                        text=compact(event.text),
                        at=time.monotonic(),
                    )
                )
        if event.text.strip() and self._details:
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

    def _said_by_you(self, text: str, whose: str = "") -> None:
        """Puts something you said in the transcript, behind the `❯` Claude Code marks it with.

        Args:
          text: What was said.
          whose: The agent it was put to, where it went to one -- so that it lands on that
            agent's transcript and on the one they all appear on, as everything else that
            agent says does. A word put into a turn is part of that conversation, and would
            otherwise be on whichever screen happened to be up when the agent took it. "" for
            a line that went to nobody in particular: a command, the task that starts a flow,
            a line a flow that ended never took.
        """
        # What is read next starts its own part.
        self._keeping(whose or None).packed = False
        said = escape(text).splitlines() or [""]
        for line in (
            "",
            f"[dim]{_YOURS}[/] {said[0]}",
            *(f"  {one}" for one in said[1:]),
        ):
            self._into(whose or None, line)

    def show(self, text: str, style: str = "") -> None:
        """Puts a line in the transcript, on whichever one is being read.

        The interface's own lines go where you are looking: what you typed, what a command
        came back with, what went wrong. They are nobody's transcript in particular, and one
        that dropped them would be a screen where half of what you did never happened.

        Args:
          text: What to show, taken as markup when no style is given and as plain text
            otherwise -- so that a bracket an agent wrote stays a bracket.
          style: How to show it, as a Rich style, or "" to show it as it is.
        """
        body = text if style == "" else f"[{style}]{escape(text)}[/{style}]"
        self._into(None, body)

    def _into(self, whose: str | None, content: object, *, shrink: bool = True) -> None:
        """Keeps something on the transcripts it belongs on, and draws it if one is read.

        An agent's line goes on two: that agent's own, and the one where every agent's work
        appears together. Which is what makes the second a place to watch a flow from rather
        than a copy of one agent -- and what makes stepping onto an agent a transcript of
        that agent rather than the screen carrying on.

        Args:
          whose: The agent it is from, or None for the interface's own -- which belongs to
            whichever transcript is being read, since that is the one it was said over.
          content: What to draw, as markup or as something Rich renders.
          shrink: Whether to draw it to fit.
        """
        where = [_EVERY, whose] if whose else [self._attached]
        for one in where:
            kept = self._keeping(one)
            if one == _EVERY and whose and kept.spoke != whose:
                # Two agents working at once are two agents whose lines land here in the
                # order they were said, so the one being read from has to be said. Once, as
                # it changes: a name against every line is a column nobody is reading.
                kept.spoke = whose
                self._writes(one, _Shown("", shrink=True))
                said = f"[dim]{_RULE * 2} {escape(short(whose))}[/]"
                self._writes(one, _Shown(said, shrink=True))
            self._writes(one, _Shown(content, shrink))

    def _writes(self, whose: str, shown: _Shown) -> None:
        """Puts one line on one transcript, and on the screen where that one is read.

        Args:
          whose: Which transcript, as `_keeping` names them.
          shown: The line.
        """
        kept = self._keeping(whose)
        kept.lines.append(shown)
        if whose == self._attached:
            self.query_one("#transcript", Transcript).write(
                shown.content, shrink=shown.shrink
            )
        elif _EVERY not in (whose, self._attached):
            # Nothing is unread while every agent is being read: it went onto that transcript
            # too, and it was read there. Marking it would be marking every agent of the flow
            # as having something nobody has looked at, on the one screen that shows the lot.
            kept.unread = True  # and the line above the prompt says so until it is read

    def _keeping(self, whose: str | None) -> _Kept:
        """What is kept of one transcript, opening one the first time.

        Args:
          whose: The agent it is of, or `_EVERY` for the one they all appear on. None means
            the one being read, which is what the interface's own lines are said over.

        Returns:
          What it has to show, which is what stepping onto it draws.
        """
        key = self._attached if whose is None else whose
        if (kept := self._kept.get(key)) is not None:
            return kept
        kept = self._kept[key] = _Kept()
        # The oldest go first, and never the one being read, the one all of them are on, or
        # the one just opened: a machine that has run twenty flows would otherwise keep every
        # agent of all of them, and what is dropped this way is an agent no flow still holds.
        over = len(self._kept) - _KEPT
        dropping = [
            one for one in self._kept if one not in (_EVERY, key, self._attached)
        ]
        for gone in dropping[: max(over, 0)]:
            del self._kept[gone]
        return kept

    def _conversations(self) -> list[tuple[AgentBase, SessionBase]]:
        """Every conversation the flow has open, in the order the flow takes its agents.

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

    def _driven(self) -> list[AgentBase]:
        """The agents there are transcripts of, which is the run's or the last run's.

        The last run's once it is over, because its transcripts are still on the screen and
        still worth reading back: a run that ended is the one somebody wants to look at.
        Nothing that asks this can mistake one for a flow that is running -- what is working
        is asked of the conversations, and there are none of those once a run is over.

        Returns:
          One apiece, in the order the flow takes them, less the person -- who is talked to
          at this prompt rather than read.
        """
        from hmz.agents import HumanAgent

        held = self._agents or self._ran
        return [one for one in held if not isinstance(one, HumanAgent)]

    def _working_agents(self) -> list[str]:
        """Which of the flow's agents have a turn open, in the order the flow takes them.

        Returns:
          Their ids. These are the ones tab steps between: with ten agents going, what
          somebody is stepping between is the ones thinking.
        """
        return [
            agent.id
            for agent in self._driven()
            if any(session in self._working for session in agent.sessions)
        ]

    def _reading(self) -> AgentBase | None:
        """The agent being read, where one is rather than all of them.

        Returns:
          The agent, or None on the transcript they all appear on and for one whose flow is
          over -- the transcript stays up either way, there being nothing to say to it.
        """
        return next((one for one in self._driven() if one.id == self._attached), None)

    def _says_to(self) -> SessionBase | None:
        """Which conversation a typed line goes into, which is the one on the screen.

        The agent being read is what is being said to; of its conversations, the one with a
        turn open, since a line written to one between turns is answered on its own outside
        the flow. Where all of them are being read there is no one agent to have meant, so it
        is whichever has a turn open -- which is what the transcript is showing.

        Returns:
          The conversation, or None where there is none open to say it to yet.
        """
        agent = self._reading()
        if agent is not None:
            return self._working_in(agent)
        working = [one for _, one in self._conversations() if one in self._working]
        return working[0] if working else None

    def _now_reading(self, whose: str, *, stepped: bool = True) -> None:
        """Reads one of the transcripts there are, drawing it from the top.

        From the top, and not by carrying on where the screen was: what an agent has done is
        that agent's transcript, and a screen that only appended would be every agent's lines
        shuffled into one another. Stepping between an agent's own conversations is not this
        -- they are all one transcript, so a loop that opens one a turn goes on down the same
        screen rather than replacing it.

        Args:
          whose: Which transcript, as `_keeping` names them.
          stepped: Whether somebody asked for this, rather than what was being read having
            gone with the flow that held it.
        """
        if whose == self._attached:
            return  # already the one on the screen, so nothing has happened
        self._attached = whose
        kept = self._keeping(whose)
        kept.unread = False
        if whose == _EVERY:
            # Everything every agent has said is on this one, so reading it is reading all of
            # them: an agent left marked unread here would be marked for what is on the screen.
            for one in self._kept.values():
                one.unread = False
        agent = self._reading()
        shown = self.query_one("#transcript", Transcript)
        shown.clear()
        held = len(agent.sessions) if agent is not None else 0
        many = f"{_DOT}{held} conversations" if held > 1 else ""
        named = "every agent" if whose == _EVERY else f"{escape(short(whose))}{many}"
        shown.write(
            f"[dim]{_RULE} {'' if stepped else 'that flow has gone, now '}"
            f"reading {named} {_RULE}[/]"
        )
        for line in kept.lines:
            shown.write(line.content, shrink=line.shrink)

    def _unread(self, whose: str) -> bool:
        """Whether one transcript has something on it nobody has looked at.

        Args:
          whose: Which one, as `_keeping` names them.

        Returns:
          True if it has said something since it was last read.
        """
        kept = self._kept.get(whose)
        return kept is not None and kept.unread

    def _held(self) -> list[Held]:
        """How many conversations each of the flow's agents has, and which one is being read.

        Returns:
          One per agent the flow drives, in the order it takes them -- and nothing at all
          with no flow running, which is a line about what is set up rather than about what
          it is doing.
        """
        return [
            Held(
                many=len(agent.sessions),
                reading=agent.id == self._attached,
                unread=self._unread(agent.id),
                working=any(one in self._working for one in agent.sessions),
            )
            for agent in self._driven()
        ]

    def action_attach_next(self) -> None:
        """Reads the next agent that is working, which is what tab is for."""
        self._attach_by(1)

    def action_attach_previous(self) -> None:
        """Reads the one before it, which is what shift+tab is for."""
        self._attach_by(-1)

    def _ring(self) -> list[str]:
        """What tab steps round: the transcript all of them are on, then the ones working.

        The ones working rather than every agent the flow drives: with ten agents going,
        what somebody is stepping between is the ones thinking. Every agent there is can
        still be read, from the diagram on `/status`, which is where an agent that has
        stopped is picked out by name rather than stepped past.

        Returns:
          The transcripts to step round, the one they are all on first -- so that there is
          always the way back to watching the flow rather than one agent of it.
        """
        return [_EVERY, *self._working_agents()]

    def _attach_by(self, step: int) -> None:
        """Moves what is being read one step round the ring, either way.

        Args:
          step: How far, and which way.
        """
        ring = self._ring()
        # From where the one being read stands, and from the start where it is not on the
        # ring at all -- an agent that has stopped since it was stepped onto, which is left
        # up until somebody asks for something else.
        at = ring.index(self._attached) if self._attached in ring else 0
        self._now_reading(ring[(at + step) % len(ring)])
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
            left = f"[$text-muted]{_SPINNER[0]} waiting for you{_DOT}ctrl+c twice to stop[/]"
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
                f"[$text-muted]({time.monotonic() - since:.0f}s{_DOT}ctrl+c twice to stop)[/]"
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
        # Measured as drawn rather than as written: markup is not what takes up columns.
        # Textual's own, since these are Textual's markup and name its colours.
        room = self.size.width - 4 - Content.from_markup(left).cell_length
        keys = self._keys()
        while len(keys) > 1 and len(_DOT.join(keys)) > room:
            # The row is drawn against the right-hand edge, so what will not fit falls off
            # that end -- which is where the keys that change are. The ones at the front are
            # the ones that mean the same thing whenever they are pressed, so they are what
            # gives: a row that clipped `ctrl+c` to say `shift+enter newline` would be a row
            # holding the one key nobody has to be told about and losing the one they do.
            keys.pop(0)
        right = f"[$text-muted]{_DOT.join(keys)}[/]"
        gap = room - len(_DOT.join(keys))
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
        from hmz.flows import running

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
        than one that is not listed at all, and there is nowhere else to look them up. What
        ctrl+c would do next is what it is called by, since it is the one key here that
        means something different for having just been pressed.
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
        if len(self._ring()) > 1:
            # Only with somewhere to step: with nothing working there is the one transcript
            # every agent is on, and a key that lands back where it started is not a key.
            keys.append("tab agent")
        keys.append("/ commands")
        keys.append("shift+enter newline")
        keys.append("esc status")
        if self.query_one(Editor).text:
            keys.append("ctrl+c clear")
        elif self._counting():
            keys.append(
                "ctrl+c again to stop" if self._agents else "ctrl+c again to exit"
            )
        elif self._agents:
            keys.append("ctrl+c stop")
        elif self._stopping:
            keys.append("ctrl+c close them")
        else:
            keys.append("ctrl+c exit")
        return keys

    def _counting(self) -> bool:
        """Whether a ctrl+c has been pressed and the next one is still the second of it.

        Read where the keys are drawn, which is twice a second, so this is also where a
        gesture nobody finished is forgotten: a line saying what the next press does is
        wrong the moment that press would be a first press again.

        Returns:
          Whether the last press still stands.
        """
        if not self._presses:
            return False
        if time.monotonic() - self._pressed < _AGAIN:
            return True
        self._presses = 0
        return False

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
        self.show(
            f"hmz: {what} while a flow is running: ctrl+c twice stops it first", "red"
        )
        return True

    @work
    async def action_status(self) -> None:
        """Opens the sheet saying how the run is going, which is what esc is.

        Readable while a flow runs, unlike the two that choose something: it changes nothing
        about the run, so there is nothing for it to conflict with. The one thing it answers
        with is which transcript to read, the diagram being where an agent is picked out by
        name -- working or not, which is what tab is held to.
        """
        reading = await self.push_screen_wait(
            Status(
                self._flow_named,
                self._named_by,
                self._models,
                self._monitor,
                self._config,
                drawn=self._boxes(),
                reading=self._attached,
            )
        )
        if reading is not None:
            self._now_reading(reading)
            self._draw()

    def _boxes(self) -> list[Drawn]:
        """The agents of the run as the diagram draws them, in the order the flow takes them.

        Returns:
          One apiece, and nothing at all with no flow running -- which is a sheet about what
          is set up rather than about what it is doing.
        """
        named = self._named_by
        return [
            Drawn(
                who=agent.id,
                named=named[at] if at < len(named) else "",
                runs=self._models[at].spec if at < len(self._models) else "",
                working=any(one in self._working for one in agent.sessions),
                reading=agent.id == self._attached,
            )
            for at, agent in enumerate(self._driven())
        ]

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
        elif name == "btw":
            self.action_btw(" ".join(argv).strip())
        elif name == "flow":
            self.action_flow(argv[0] if argv else "")
        elif name == "agents":
            self.action_agents()
        elif name == "providers":
            self.action_providers()
        elif name == "fallback":
            self.action_fallback()
        elif name == "cycles":
            self.action_cycles()
        elif name == "flowverses":
            self.action_flowverses()
        elif name == "settings":
            self.action_settings()
        elif name == "status":
            self.action_status()
        elif name == "details":
            if (switched := self._switched(argv, now=self._details)) is None:
                return
            self._details = switched
            self.show(
                "[dim]showing the working: every tool call, all of the thinking, and "
                "whatever a backend prints on its way past[/dim]"
                if self._details
                else "[dim]showing what each turn said, and nothing of how it got "
                "there[/dim]"
            )
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
            telemetry.snag("unknown-command", length=len(name))
            self.show(f"hmz: no such command: /{name}", "red")

    def action_btw(self, question: str = "") -> None:
        """Answers a side question from a frozen flow snapshot.

        A side question must never become a steer. It is answered by a short-lived clone of
        one of the flow's coding agents, with read-only permissions and no flow skills, while
        the primary sessions continue on their own threads. The prompt contains the runtime
        observations collected by :meth:`_heard`, so the clone does not need to inspect or
        lock the primary conversation.

        Args:
          question: What to ask, without the ``/btw`` command name.
        """
        question = " ".join(question.split())
        if not question:
            self.show("hmz: usage: /btw <question>", "red")
            return
        if not self._agents:
            self.show("hmz: /btw needs a flow that is running", "red")
            return
        candidates = self._btw_candidates()
        if not candidates:
            self.show(
                "hmz: /btw needs a coding agent that supports read-only turns", "red"
            )
            return
        with self._btw_lock:
            if self._btw_closed:
                return
            if len(self._btw_running) >= _BTW_ACTIVE:
                self.show(
                    f"hmz: /btw already has {_BTW_ACTIVE} questions in progress", "red"
                )
                return
            self._btw_serial += 1
            request = self._btw_serial
            generation = self._btw_generation
            self._btw_running.add(request)
        try:
            snapshot = self._btw_snapshot()
            prompt = format_snapshot(snapshot, question)
        except Exception as why:  # noqa: BLE001 -- an observation failure must not break the UI
            with self._btw_lock:
                self._btw_running.discard(request)
            self.show(f"hmz: /btw could not read flow progress: {why}", "red")
            return
        self.show(f"[dim]btw: checking the flow for {escape(question)}…[/dim]")
        worker = threading.Thread(
            target=self._run_btw,
            args=(request, question, prompt, tuple(candidates), generation),
            daemon=True,
            name=f"humanize-btw-{request}",
        )
        try:
            worker.start()
        except RuntimeError as why:
            with self._btw_lock:
                self._btw_running.discard(request)
            self.show(f"hmz: /btw could not start: {why}", "red")

    def _btw_snapshot(self) -> FlowSnapshot:
        """Copies the current run into a prompt-sized, immutable observation."""
        from hmz.agents import HumanAgent

        shape = self._monitor.shape()
        driven = tuple(self._agents)
        named = self._named_by
        agents = tuple(
            (
                at,
                AgentProgress(
                    agent=agent.id,
                    model=agent.config.model,
                    turns=shape.turns.get(agent.id, 0),
                    working=agent.id in shape.working,
                ),
            )
            for at, agent in enumerate(driven)
            if not isinstance(agent, HumanAgent)
            if agent.id
        )
        handovers = tuple(
            sorted(
                (
                    sender,
                    receiver,
                    count,
                )
                for (sender, receiver), count in shape.handovers.items()
                if count > 0
            )
        )
        with self._btw_lock:
            observations = tuple(self._btw_events)
        with self._saying:
            waiting = len(self._queued) + len(self._given)
        moment = time.monotonic()
        ended = self._monitor.until
        elapsed = (ended if ended is not None else moment) - self._monitor.began
        spent = tuple(
            (entry.model, entry.tokens, entry.rate)
            for entry in self._monitor.spending(now=ended or moment)
        )
        # Keep the role separate from the stable id used by the monitor and handover records.
        labelled = tuple(
            AgentProgress(
                agent=item.agent,
                model=item.model,
                turns=item.turns,
                working=item.working,
                role=named[index] if index < len(named) else "",
            )
            for index, item in agents
        )
        return FlowSnapshot(
            flow=self._flowing(),
            task=self._flow_task,
            workspace=_where(),
            elapsed=elapsed,
            finished=ended is not None,
            agents=labelled,
            handovers=handovers,
            observations=observations,
            waiting=waiting,
            spent=spent,
            waiting_for_input=self._awaiting,
        )

    def _btw_candidates(self) -> list[AgentBase]:
        """Orders usable coding agents for a side question, without including the person."""
        from hmz.agents import HumanAgent

        reading = self._reading()
        ordered = ([reading] if reading is not None else []) + list(self._agents)
        candidates: list[AgentBase] = []
        for agent in ordered:
            if isinstance(agent, HumanAgent) or agent in candidates:
                continue
            candidates.append(agent)
        return candidates

    def _btw_clone(self, source: AgentBase, request: int) -> AgentBase:
        """Makes a read-only, skill-free agent that is invisible to the primary run."""
        from dataclasses import replace

        # `permission` is part of every AgentConfig, including backend-specific subclasses.
        # A backend that cannot express read-only raises here; the caller tries another agent
        # rather than silently running a side question with the flow's write permissions.
        settings: dict[str, object] = {"permission": "read-only", "goals": False}
        # Claude's optional allow-list can auto-approve a write even in a normal permission
        # mode. A side question has no reason to carry the flow's explicit tool grants.
        if hasattr(source.config, "allowed_tools"):
            settings["allowed_tools"] = ()
        config = replace(source.config, **settings)
        try:
            clone = source.clone(
                config=config,
                name=f"btw-{request}",
                skills=(),
            )
        except TypeError:
            # A third-party AgentBase written before the optional skills argument may still
            # implement clone(config=, name=). Clear its inherited skills after construction.
            clone = source.clone(config=config, name=f"btw-{request}")
            clone.loads(())
        # A watcher prevents command-backed backends from echoing the side answer to the
        # interface's captured stdout. It is intentionally not the primary app watcher.
        clone.watch(_quiet_watch)
        return clone

    def _btw_cwd(self, source: AgentBase) -> str | None:
        """Uses an already-open conversation's directory when one is available."""
        session = self._working_in(source)
        if session is None:
            return None
        try:
            return session.cwd
        except (OSError, RuntimeError, ValueError):
            return None

    def _run_btw(
        self,
        request: int,
        question: str,
        prompt: str,
        candidates: tuple[AgentBase, ...] = (),
        generation: int | None = None,
    ) -> None:
        """Runs one isolated side turn and posts only its final display event."""
        answer = ""
        failure = ""
        try:
            for source in candidates or tuple(self._btw_candidates()):
                with self._btw_lock:
                    if self._btw_closed or (
                        generation is not None and generation != self._btw_generation
                    ):
                        return
                side: AgentBase | None = None
                session: SessionBase | None = None
                try:
                    side = self._btw_clone(source, request)
                    cwd = self._btw_cwd(source)
                    session = side.new() if cwd is None else side.new(cwd)
                    with self._btw_lock:
                        if self._btw_closed or (
                            generation is not None
                            and generation != self._btw_generation
                        ):
                            session.close()
                            return
                        self._btw_active[request] = (side, session)
                    answered = session(prompt)
                    answer = str(answered or "").strip()
                    if answer:
                        break
                    failure = "the side agent returned no answer"
                except Exception as why:  # noqa: BLE001 -- a backend may fail independently
                    failure = str(why) or type(why).__name__
                finally:
                    if session is not None:
                        with contextlib.suppress(Exception):
                            session.close()
                    elif side is not None:
                        with contextlib.suppress(Exception):
                            side.stop()
                    with self._btw_lock:
                        held = self._btw_active.get(request)
                        if held is not None and held[1] is session:
                            self._btw_active.pop(request, None)
                if answer:
                    break
        finally:
            with self._btw_lock:
                self._btw_running.discard(request)
                closed = self._btw_closed or (
                    generation is not None and generation != self._btw_generation
                )
        if closed:
            return
        if answer:
            self._on_screen(self._btw_answer, question, answer)
        else:
            self._on_screen(
                self._btw_failed,
                question,
                failure or "no read-only coding agent is available",
            )

    def _btw_answer(self, question: str, answer: str) -> None:
        """Shows a completed side answer in the current transcript."""
        lines = escape(answer).splitlines() or [""]
        self._part(
            None,
            "\n".join(
                [
                    f"[cyan]{_SAID}[/] [dim]btw · {escape(question)}[/] {lines[0]}",
                    *(f"  {line}" for line in lines[1:]),
                ]
            ),
            packs=False,
        )
        self._draw()

    def _btw_failed(self, question: str, failure: str) -> None:
        """Reports a side-question failure without reporting it as a flow failure."""
        del question  # The command itself is already in the transcript.
        self.show(f"hmz: /btw: {failure}", "red")

    def action_clear(self) -> None:
        """Clears the screen, and nothing else.

        There is nothing else for it to clear. A turn carries no context across a cycle: a
        flow is handed agents that were made for that run and drops them at the end of it, so
        what is on screen is the whole of what starting over would have thrown away. What is
        running is left running, and what it has done so far is still beside it.

        The screen is one transcript, so what is cleared is that one: clearing every agent's
        would be `/clear` reaching into ones nobody was looking at.
        """
        kept = self._keeping(self._attached)
        kept.lines.clear()
        # And what it was in the middle of saying, which is gone with the lines it was said
        # against: the next part opens its own, and the next agent to speak on the one they
        # all appear on says which agent it is rather than running on from a name nobody can
        # see any more.
        kept.packed, kept.spoke = False, ""
        self.query_one("#transcript", Transcript).clear()
        self._welcome()  # a cleared screen is a screen just opened, and one opens with this
        self._draw()

    def action_stop_flow(self) -> None:
        """Stops the whole flow, not just the turn -- which is the second ctrl+c.

        Every agent is told to take no further turn, so the one running now is closed out and
        the loop driving it ends rather than handing on to the next agent. The agents are let
        go of here rather than when the flow's own thread notices, so that the next thing
        said starts something instead of being put to a flow that is on its way out -- and
        kept as the ones stopping, since a flow unwinds in its own time and the press after
        this one is the one that does not wait for it. Silent when nothing is running.
        """
        for agent in self._agents:
            agent.stop()
        if self._agents:
            self.show("[dim]— stopping the flow —[/dim]")
        # Held by identity, so that the run's own thread can say when it has finished
        # unwinding and nothing says it of a run that started since.
        self._agents, self._stopping = [], self._agents
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
        self._agents, self._stopping = [], []
        self._spoke.set()
        self._close_btw()

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
        # Lines typed at a flow that is no longer there to take them. Counted rather than
        # read: what they said is theirs, and how many of them there were is the signal.
        telemetry.snag("lines-never-sent", how_many=len(held) + len(given))
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
    async def action_flow(self, named: str = "", *, opening: int = 0) -> None:
        """Opens the flow menu: which flow runs, and what each of its agents is.

        One menu of two pages rather than a walk of a sheet per question. Nothing in it is
        applied until it is saved on the way out, so opening it to look at the flows and
        walking back out again leaves the interface exactly as ready to be typed at as it was.

        Not refused while a flow runs. The page that chooses one is shut then -- a flow is
        chosen in order to be started, and there is one going -- but the page its agents are
        set up on is open, that being where somebody halfway through a run finds out that an
        agent is thinking too little or is allowed too much.

        Args:
          named: A flow of your own, as a path, to open the menu already holding.
          opening: Which page to open on, counting from zero.
        """
        # Opened whether or not there is a backend to run one on: which flow to run is worth
        # reading either way, and the sheet an agent is set up on says for itself that there
        # is nothing installed to set it up as.
        agents = installed()
        unavailable = installable()
        agents.update(unavailable)
        running = bool(self._agents)
        if named and running:
            self.show("hmz: a flow is running; no choosing a flow", "red")
            return
        # What is in hand is what is in hand for the flow the interface is set up on. A menu
        # opened straight into another flow is handed none, and reads what that one was last
        # set up with here -- which is what turning to it would have read.
        holding = self._models if not named or named == self._flow_named else ()
        chosen = await self.push_screen_wait(
            Flows(
                named or self._flow_named,
                holding,
                self._config if holding else None,
                agents,
                self.settings.flows(),
                unavailable=frozenset(unavailable),
                running=running,
                opening=opening,
            )
        )
        if chosen is None:
            return  # walked out without saving, which changes nothing at all
        self._took_flow(chosen, running=running)

    def _took_flow(self, chosen: Chosen, *, running: bool) -> None:
        """Applies what the flow menu was saved with, and writes it down.

        Args:
          chosen: The flow, its agents, and how the flow itself is set up.
          running: Whether a flow was running when the menu opened, which is what decides
            between starting fresh and changing the agents under a run.
        """
        places = places_of(chosen.flow)
        same = (chosen.flow, list(chosen.agents), chosen.config) == (
            self._flow_named,
            self._models,
            self._config,
        )
        if not running and not same:
            # A flow is chosen in order to be run, so whatever is running stops: the interface
            # opens on one already, and a choice that quietly went to the back of the queue
            # behind it would read as no choice at all. Answering the same way twice is not a
            # choice, though, and must not end the conversation.
            self.action_stop_flow()
        self._flow_named, self._models = chosen.flow, list(chosen.agents)
        self._wanted = places if places is not None else self._places_of(chosen.flow)
        self._config = chosen.config
        self.settings.remember(
            chosen.flow,
            self._named_by,
            self._models,
            chosen.config.model_dump(mode="json")
            if chosen.config is not None
            else None,
        )
        if running:
            self._reconfigured()
        elif not same:
            self.show("[dim]say what to do, and the flow starts on it[/dim]")
        self._draw()

    def _reconfigured(self) -> None:
        """Sets the agents of a run that is going to what they have just been changed to.

        An agent is configured once and read from there on, so what a running one is doing now
        is what it was set up with, and what it is asked for next is what it is set up with by
        the time it is asked. So the ones whose CLI has not changed are set up where they
        stand: the turn under way finishes as it started -- a model does not think harder
        halfway through an answer -- and everything asked for after it is at the new model,
        effort, account, rung and machine.

        A CLI that has changed is not one of those. What drives a backend is the class the
        agent is, and the flow is holding the agents it was handed when it started; one of
        them cannot become another backend without becoming another object, which is a thing
        only starting the flow again does. So that one is written down and runs from the next
        time the flow is started.
        """
        from dataclasses import replace

        from hmz.agents import anchored

        for at, agent in enumerate(self._agents):
            if at >= len(self._models):
                break
            runs = self._models[at]
            cli, _, rest = runs.spec.partition("/")
            model, _, effort = rest.rpartition(":")
            if cli != agent.backend:
                self.show(
                    f"[dim]{escape(agent.id)} is {escape(cli)} from the next run; "
                    "an agent cannot become another backend under the flow holding it[/dim]"
                )
                continue
            try:
                machine = anchored(runs.anchor)
            except ValueError as why:  # a target that cannot be read is one to correct
                self.show(f"hmz: {escape(agent.id)}: {why}", "red")
                continue
            # Said to the agent rather than to a session: what a person changes here they
            # change about the agent, and every conversation it opens from now on is at it.
            agent.reconfigure(
                replace(
                    agent.config,
                    model=model,
                    effort=effort,
                    machine=machine,
                    provider=runs.provider,
                    goals=runs.goals,
                    web_search=runs.web_search,
                    **({"permission": runs.permission} if runs.permission else {}),
                )
            )
            self.show(
                f"[dim]{escape(agent.id)} is {escape(runs.spec)} "
                "from its next turn[/dim]"
            )

    def action_agents(self) -> None:
        """Opens the agents saved under a name, which is what `/agents` is for.

        Not the agents of the flow: those are the second page of `/flow`, and are what this
        run is driven by. These are the ones written down to be imported there -- the reviewer
        you always use, the cheap one you fan out across, the one on somebody's gateway -- and
        belong to no flow and no workspace at all.
        """
        self._saved_agents()

    @work
    async def _saved_agents(self) -> None:
        """Reads the saved agents, and says so where the menu was saved."""
        agents = installed()
        agents.update(installable())
        for one in await self.push_screen_wait(Saved(agents)) or ():
            self.show(one)

    @work
    async def _asks_about_reports(self) -> None:
        """Asks, once, whether humanize reports its own failures.

        Only where nobody has been asked yet, and only here: the interface is the one thing
        humanize has that has somebody at it. A headless run reports if this was answered yes
        and is silent otherwise -- silence is not consent, and a question nobody is there to
        answer is a run that has stopped.

        Left unanswered by esc, which is asked again next time rather than taken as a no. And
        what the interface knows about the machine is said here either way, so that a report
        made later carries it: registered rather than gathered, so nothing is looked at on a
        machine that reports nothing.
        """
        telemetry.about("machine", _machine)
        if telemetry.enabled() is not None:
            telemetry.start()
            return
        said = await self.push_screen_wait(Reports())
        if said is None:
            return  # asked again next time: walking away is not an answer
        telemetry.asked(enable_sentry=said == "on")
        self.show(
            "[dim]humanize reports what goes wrong; /settings turns it off[/dim]"
            if said == "on"
            else "[dim]humanize reports nothing; /settings turns it on[/dim]"
        )

    @work
    async def action_settings(self) -> None:
        """Opens what humanize remembers, which is what `/settings` is for.

        Two pages: what is true of this machine, and what is remembered about this directory.
        Not refused while a flow runs -- nothing on it changes what is running.
        """
        # What is written down rather than what is happening: the environment may answer for
        # one run, and a menu that showed that would be a menu offering to change a thing it
        # cannot. The sheet says so under the list where the two differ.
        #
        # Read again rather than off the interface's own `Settings`, which was made when it
        # opened: the first-start question writes through one of its own, so the long-lived
        # one would show a machine that has just answered as one nobody has asked.
        from hmz.settings import Settings

        written = Settings().enable_sentry
        profiling = self.settings.profiling
        said = await self.push_screen_wait(
            Adjusts(
                enable_sentry=written,
                overridden=telemetry.enabled() is not written,
                workspace=str(Path.cwd()),
                flow=self.settings.flow,
                agents=len(self.settings.agents(self.settings.flow)),
                flows=len(self.settings.flows()),
                profile=profiling,
            )
        )
        if said is None:
            return
        self._took_settings(said, written=written, profiling=profiling)

    def _took_settings(
        self,
        said: Adjusted,
        *,
        written: bool | None = None,
        profiling: bool = False,
    ) -> None:
        """Does what the settings menu was holding.

        Args:
          said: What it answered with.
          written: What was written down when it opened, so that a setting nobody moved is
            not written again.
          profiling: Whether this directory was already being profiled, for the same reason.
        """
        if said.enable_sentry is not None and said.enable_sentry != written:
            # Through the same road the first-start question takes, so that the answer is
            # written down, what was read is forgotten, and reporting starts or stops now
            # rather than at the next start.
            telemetry.asked(enable_sentry=said.enable_sentry)
            self.show(
                "[dim]humanize reports what goes wrong[/dim]"
                if said.enable_sentry
                else "[dim]humanize reports nothing[/dim]"
            )
        if said.profile != profiling:
            self.settings.profiles(on=said.profile)
            self.show(
                "[dim]a run here profiles the programs it starts; /cycles collects the "
                "trace[/dim]"
                if said.profile
                else "[dim]a run here is traced and not profiled[/dim]"
            )
        if said.forget and self.settings.forget():
            self.show(
                "[dim]what was remembered about this directory is forgotten[/dim]"
            )

    @work
    async def action_flowverses(self) -> None:
        """Opens the places flows come from, which is what `/flowverses` is for.

        Not which flow to run -- that is `/flow`, where the arrows step between these places
        and the list holds the one being read. This is the other question: what places there
        are, what one of them holds, and the three things that can happen to one. Not refused
        while a flow runs: a flowverse fetched now is a flowverse the next run may reach for,
        and nothing here touches the flow that is going.
        """
        for one in await self.push_screen_wait(Flowverses()) or ():
            self.show(one)

    @work
    async def action_cycles(self) -> None:
        """Opens the runs of this directory, which is what `/cycles` is for.

        Every run of a flow here, newest first: what it was, how it went, and what there is
        to do with it. Read while a flow runs -- what has already happened does not change
        under one -- but a run picked up is a flow started, so that half is refused while
        one is going, on the sheet where it was asked for.
        """
        said = await self.push_screen_wait(Cycles(running=bool(self._agents)))
        if said is None:
            return
        for one in said.said:
            self.show(one)
        if said.doing == carries_on and said.cycle is not None:
            self._carries_on(said.cycle)

    def _carries_on(self, cycle: Path) -> None:
        """Runs the flow of one run again, on what that run left behind.

        Which is a run of its own: a cycle is one run and is never reopened, so this is the
        flow started again with the state of the run being picked up, writing into a cycle of
        its own that says which one it came from.

        The flow, its agents and what it was asked to do all come from the run rather than
        from what the interface happens to be set up on: picking up a run means running what
        ran, and an agent swapped under it would be a different run wearing its name.

        Args:
          cycle: The run to pick up, by the directory it is written in.
        """
        from hmz.cycle import read

        ran = read(cycle)
        if ran is None:
            self.show(f"hmz: {escape(str(cycle))} is not a run", "red")
            return
        if self._mid_run("no picking a run up"):
            return
        # The person at the prompt is not one of the agents anybody chooses, so a flow that
        # talks to one wrote down an agent nothing on a command line names -- and the run
        # itself is what says which of them that was.
        drove = [one for one in ran.agents if not one.person]
        self._flow_named = ran.flow
        self._models = [
            Runs(
                f"{one.backend}/{one.model}:{one.effort}",
                permission=one.permission,
                provider=one.provider,
                goals=one.goals,
            )
            for one in drove
        ]
        self._wanted = self._places_of(ran.flow)
        self._config = config_of(ran.flow, self.settings.config(ran.flow))
        named = [part for runs in self._models for part in ("-a", runs.spec)]
        self.show(
            f"[dim]carrying on from {escape(ran.name)}: {escape(ran.flow)} on what that "
            "run left behind[/dim]"
        )
        self._flow(["-f", ran.flow, *named, ran.task], resume=cycle)

    @work
    async def action_fallback(self) -> None:
        """Opens where a turn goes when what was taking it cannot, which is `/fallback`.

        Its own menu rather than a row of the accounts, because half of it is not about
        accounts at all: an agent that has nowhere left to run falls back to a whole other
        agent, and that is written between the two rather than on either.

        Not refused while a flow runs, as the accounts are not: what is written down here is
        read by a turn that has failed, so a step added now is one the next failure walks.
        """
        agents = installed()
        agents.update(installable())
        for one in await self.push_screen_wait(Fallbacks(agents)) or ():
            self.show(one)

    @work
    async def action_providers(self) -> None:
        """Opens the accounts an agent may be run as, which is what `/providers` is for.

        Not refused while a flow runs. What it holds is not what is running: an agent reads
        the account it was configured with once, so one made or taken away now is one the next
        session sees. A login that takes the terminal does hold the rest of the interface up
        while it has it, which is what handing the terminal over means.
        """
        said = await self.push_screen_wait(Providers())
        for one in said or ():
            self.show(one)

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
        nothing else. An agent that works here and runs as this machine is signed in is left
        exactly as it was.

        Args:
          chosen: The agents the line named, in the order the flow takes them.

        Returns:
          The same agents, or one set up in place of any that was given a machine, a rung of
          what it may do, or an account to run as.

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
                and not runs.permission
                and not runs.provider
                and agent.config.goals is runs.goals
                and agent.config.web_search is runs.web_search
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
            # The config is frozen, so an agent that works elsewhere, allowed less than an
            # agent nobody asked about, or signed in as somebody else, is another agent at
            # the same model and effort -- which is what it is.
            moved.append(
                type(agent)(
                    replace(
                        agent.config,
                        machine=anchored(runs.anchor),
                        provider=runs.provider,
                        goals=runs.goals,
                        web_search=runs.web_search,
                        **({"permission": runs.permission} if runs.permission else {}),
                    )
                )
            )
        return moved

    def _flow(self, argv: list[str], resume: Path | None = None) -> None:
        """Starts a flow, keeping its agents so that a typed line can reach one.

        Args:
          argv: The command line, as `hmz exec` takes it.
          resume: The run to pick up from, for a flow that says it can be picked up, or None
            for one starting from whatever the last run of it here left -- which is what
            running a resumable flow again means.
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
            runner = Runner(path, chosen, self._config, resume=resume)
        except Exception as why:  # noqa: BLE001 -- a flow that will not load is a line to fix
            self.show(f"hmz: {why}", "red")
            return
        agents = list(runner.agents)
        self._agents = self._ran = agents
        with self._btw_lock:
            old_side_sessions = [session for _, session in self._btw_active.values()]
            self._btw_active.clear()
            self._btw_running.clear()
            self._flow_task = task
            self._btw_events.clear()
            self._btw_generation += 1
        for session in old_side_sessions:
            with contextlib.suppress(Exception):
                session.close()
        # Nothing is left of the flow before this one to press a key about, and what is
        # being read is one of its agents unless it was the transcript they all appear on.
        # Which is where a run is watched from, so it is where a run starts.
        self._stopping = []
        if self._attached != _EVERY:
            self._now_reading(_EVERY, stepped=False)
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
                if self._stopping is agents:
                    # Stopped by hand, and now finished unwinding: there is nothing left for
                    # the press that does not wait for it to reach.
                    self._stopping = []
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

    def _remember_btw(self, agent: AgentBase, event: Event) -> None:
        """Keeps a compact progress record for future side questions.

        Reasoning is intentionally omitted: a side question needs observable progress, not a
        second copy of private chain-of-thought. The event stream still reaches the ordinary
        transcript exactly as before.
        """
        # A stopped flow can take a moment to unwind while a new one is already up. Its old
        # watcher is still bound to this method, but its events must not become progress for
        # the new run.
        if self._agents and not any(agent is held for held in self._agents):
            return
        if event.kind not in {
            "begins",
            "ends",
            "failed",
            "asks",
            "tool",
            "text",
            "result",
        }:
            return
        text = (
            event.text.split("\n\n", 1)[0]
            if event.kind == "begins"
            else "turn ended"
            if event.kind == "ends"
            else event.text
        )
        text = compact(text)
        with self._btw_lock:
            self._btw_events.append(
                Observation(
                    agent=agent.id, kind=event.kind, text=text, at=time.monotonic()
                )
            )

    def _heard(
        self, agent: AgentBase, session: SessionBase | None, event: Event
    ) -> None:
        """Shows what a turn said, on the transcript of the agent that said it.

        And takes what it cost into what `/status` shows, which is per agent: an agent is
        what is read, and the bill is the agent's too.

        What is shown of a turn is what the turn was for unless `/details` says otherwise:
        the agent starting, what it said, and the agent stopping. The tools it used and the
        thinking it did aloud are how it got there, and a screen of them is a screen where
        the answer went past between two file reads. `/details` is what asks for all of it.

        Called from whichever thread the turn is running on, which is why everything drawn
        from here goes through `_on_screen`.

        Args:
          agent: Whose turn said it.
          session: Which of that agent's conversations said it, or None for something the
            agent said rather than one of them -- a question put by a server that speaks for
            every conversation it holds. Either way it is shown against the agent, all of
            whose conversations are the one transcript.
          event: What was said.
        """
        # First, whatever else happens: showing a line raises once the interface has gone, and
        # what a watcher raises is swallowed, so accounting after it would be lost.
        for model, tokens in event.tokens.items():
            self._monitor.spend(agent.id, tokens, model=model)
        self._remember_btw(agent, event)
        if event.kind == "took":
            # The agent saying a word put into its turn is now in front of it, which is the
            # one thing that makes a word said rather than posted.
            self._on_screen(self._took, agent.id, event.text)
            return
        whose = agent.id
        if event.kind == "begins":
            self._monitor.begins(agent.id, agent.config.model)
            self._began[agent.id] = time.monotonic()
            if session is not None:
                # Which is what makes it a conversation a typed line may go into: one written
                # to a conversation between turns is answered on its own, outside the flow.
                self._working.add(session)
            # A turn takes minutes and says nothing for most of them, so the line that says
            # one has started is the whole of what a flow looks like while it thinks. Which
            # of that agent's conversations, where it has more than one: a loop that opens
            # one a turn runs them all down the one transcript, and this is where each of
            # them begins.
            self._on_screen(
                self._part,
                whose,
                f"[dim]{_SAID} {escape(short(agent.id))} is working"
                f"{self._conversation(agent, session)}[/]",
                packs=False,
            )
        elif event.kind == "ends":
            self._monitor.ends(agent.id)
            if session is not None:
                self._working.discard(session)
            # Whatever it was holding is not on its way anywhere now: the turn it was put
            # into is over, and it never said it had it.
            self._on_screen(self._ended_holding, agent.id)
            took = time.monotonic() - self._began.pop(agent.id, time.monotonic())
            # The line Claude Code closes a turn with, which says how long it worked.
            self._on_screen(
                self._part,
                whose,
                f"[dim]{_WORKED} Worked for {took:.0f}s"
                f"{_DOT}{escape(short(agent.id))}[/]",
                packs=False,
            )
        elif event.kind == "tool" and self._details:
            # The tool on the bullet, what it came back with under it -- Claude Code's shape.
            named, _, about = escape(event.text).partition(" ")
            self._on_screen(
                self._part,
                whose,
                f"[green]{_SAID}[/] {named}[dim]({about})[/]",
                packs=True,
            )
        elif event.kind == "reasoning" and self._details:
            self._on_screen(
                self._part,
                whose,
                "\n".join(
                    f"[dim italic]{line}[/]" for line in escape(event.text).splitlines()
                ),
                packs=False,
            )
        elif event.kind == "asks":
            self._on_screen(
                self._asked_by,
                agent,
                f"[yellow]{_SAID}[/] {escape(event.text)}",
            )
        elif event.kind == "failed":
            self._on_screen(
                self._part,
                whose,
                f"[red]hmz: {escape(event.text)}[/]",
                packs=False,
            )
        elif event.kind == "text":
            # The bullet on the first line, two spaces under it for the rest, which is how
            # Claude Code sets a message it has just written.
            said = escape(event.text).splitlines() or [""]
            self._on_screen(
                self._part,
                whose,
                "\n".join(
                    [
                        f"[green]{_SAID}[/] {said[0]}",
                        *(f"  {line}" for line in said[1:]),
                    ]
                ),
                packs=False,
            )

    @staticmethod
    def _conversation(agent: AgentBase, session: SessionBase | None) -> str:
        """Which of an agent's conversations a turn is being taken in, where it has several.

        Args:
          agent: Whose turn it is.
          session: The conversation it is in, or None where the agent said it.

        Returns:
          Which one, counting from one, and nothing at all for an agent holding one -- there
          being nothing to tell it apart from.
        """
        held = agent.sessions
        if session is None or len(held) < 2:  # noqa: PLR2004 -- one is none to tell apart
            return ""
        at = next(
            (one for one, held_one in enumerate(held) if held_one is session), None
        )
        return "" if at is None else f"{_DOT}conversation {at + 1} of {len(held)}"

    def _asked_by(self, agent: AgentBase, text: str) -> None:
        """Puts a question where whoever is at the prompt will come across it.

        On that agent's own transcript and on the one they all appear on, as everything else
        it says goes: it is that agent's question whichever of its conversations put it, and
        the server a codex or a kimi agent puts one through serves every conversation it
        holds and so names none of them.

        Args:
          agent: Who asked.
          text: The question, as markup.
        """
        # Written down so that what it will take for an answer goes under it rather than
        # wherever the person happens to be looking by then: the two are one question.
        self._asked_on = agent.id
        self._part(agent.id, text, packs=False)

    def _working_in(self, agent: AgentBase) -> SessionBase | None:
        """Which of one agent's conversations has a turn open, for a line said to it.

        Args:
          agent: The agent.

        Returns:
          The newest of its conversations that is working, or None where none of them is,
          which is a line that waits for whichever turn starts next. Only the conversations
          there are to read: the person's is this prompt, and is not one of them.
        """
        working = [
            session
            for who, session in self._conversations()
            if who is agent and session in self._working
        ]
        return working[-1] if working else None

    def _part(self, whose: str | None, text: str, *, packs: bool) -> None:
        """Puts one part of a turn in the transcript, spaced as opencode spaces its own.

        A blank line goes between the parts, except between two that pack -- one-line tool
        rows run together, and everything else is set apart. Spaced per transcript: two
        agents talking at once would otherwise run each other's lines together.

        Args:
          whose: The agent whose part it is, or None for one to show on whatever is read.
          text: The part, as markup.
          packs: Whether this part is one that runs on from the one before it.
        """
        kept = self._keeping(whose)
        if not (packs and kept.packed):
            self._into(whose, "")
        kept.packed = packs
        self._into(whose, text)

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
            except Exception as why:  # noqa: BLE001 -- a flow fails how it likes, and is shown
                telemetry.crash(why, doing="a flow")
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
            # Typed a task and nothing at all happened, which is the worst of these: it is
            # somebody meeting humanize for the first time and getting a red line for it.
            telemetry.snag("nothing-started", because="no coding agent installed")
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
        it goes against the agent the question went against, or the two would be read apart.

        Args:
          question: What the agent wants to know.
        """
        asked = self._asked_on
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
        """Puts the oldest waiting line into the conversation on the screen, one at a time.

        Into the agent being read rather than into whichever happens to be working: a flow
        drives several, and a line said to the one that is not on the screen is a line said
        to the wrong agent. Of that agent's conversations it is the one with a turn open,
        since a line written to one between turns is answered on its own outside the flow.
        Where every agent is being read at once there is no one of them to have meant, so it
        is whichever has a turn open -- which is the one the screen is showing anyway.

        One at a time and never two: a backend given a second word while it is still
        swallowing the first runs the two together and answers once, so five lines typed in
        a row would come back as one reply. The next goes only once the turn has said it has
        this one, which is also the only point at which the two could not be run together.

        Nothing is sent between turns. A line has nowhere to go but the queue then -- writing
        it to a conversation that is not working would have it answered on its own, outside
        the flow -- so it waits for whichever turn starts next, and a running flow never
        drops one.
        """
        session = self._says_to()
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
        # How long the refusal was and nothing of what it said: `because` is a backend's own
        # stderr, which is the one thing a report may not carry.
        telemetry.snag("line-refused", said=len(because))
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
        self._said_by_you(text, who)
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


def _machine() -> dict[str, object]:
    """What the interface knows about this machine, for a report of something going wrong.

    Which coding agents are installed, which accounts exist and how each was signed in, what
    each backend would load as skills, and where flows come from. Names and counts only: an
    account's variables are named nowhere and its values are read nowhere, and a skill is its
    name and the CLI that would load it.

    Returns:
      The description, as plain values something can write out as YAML.
    """
    import platform

    from hmz import providers
    from hmz.agents.skills import skills
    from hmz.flows import flowverses

    return {
        "python": platform.python_version(),
        "system": platform.system(),
        "clis": sorted(installed()),
        "accounts": [
            {"cli": one.cli, "name": one.name or "as local", "way": one.way or "-"}
            for one in providers.providers()
        ],
        "skills": {
            cli: [one.name for one in skills(cli)]
            for cli in sorted(installed())
            if skills(cli)
        },
        "flowverses": [
            {"name": one.name, "fetched": one.fetched} for one in flowverses()
        ],
    }

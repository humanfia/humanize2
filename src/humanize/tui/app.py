"""humanize as a coding agent's own terminal, with a flow underneath instead of one agent.

Laid out the way opencode is, and no wider: a transcript, an editor under it, a status line
under that, and what the flow is doing beside them. Tab picks a flow the way opencode's tab
picks an agent, and `/agents` sets what each of that flow's agents runs.

It opens on the flow that is only talking to one agent, so that saying something is all it
takes to start. A flow is what you reach for once talking to one agent is not the shape of
the work, and nobody knows that before they have said anything.

The editor means both things at once: a line starting with `/` is a command, and any other
line is the task if nothing is running yet, or is said to the agent working right now.

Drawn in the terminal's own colours: every surface is the terminal's background and every
colour is one of the sixteen it already has a setting for, so nothing is read from it and
nothing is imposed on it.
"""

from __future__ import annotations

import contextlib
import functools
import os
import shlex
import sys
import threading
import time
import traceback
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from rich.markup import escape
from textual import events, on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.content import Content
from textual.message import Message
from textual.theme import Theme
from textual.widgets import OptionList, RichLog, Static, TextArea
from textual.widgets.option_list import Option

from humanize.cli import flow_and_agents

from .complete import about, offered, takes
from .discover import Model, installed
from .history import History
from .monitor import Monitor, short
from .pick import Flows, Models
from .settings import Settings
from .tally import Tally

if TYPE_CHECKING:
    from humanize.janus import AgentBase, Event, Question

#: What the editor understands, named as opencode names them, one step along: what answers
#: here is a flow rather than an agent, so opencode's `/agents` is `/flow`, and what a flow
#: runs on is an agent apiece rather than one model, so its `/models` is `/agents` -- which
#: asks once for each agent the flow drives. `hmz collect` and `hmz anchor` are not here:
#: neither is a thing to do to a flow that is running, and both are a command line of their
#: own.
_OWN = (
    "flow",
    "agents",
    "clear",
    "details",
    "afk",
    "export",
    "exit",
)

#: How often the right-hand column and the status line are redrawn, in seconds.
_REFRESH = 0.5


def _thousands(count: int) -> str:
    """Renders a token count short enough for a status line.

    Args:
      count: How many tokens.

    Returns:
      The count, abbreviated once it stops fitting.
    """
    if count < 1000:
        return str(count)
    if count < 1_000_000:
        return f"{count / 1000:.1f}k"
    return f"{count / 1_000_000:.2f}M"


#: How long a second ctrl+c still counts as the same one, in seconds.
_AGAIN = 2.0

#: The flow the interface opens on, which is the one that is only talking to one agent.
_STARTS_ON = "chat"

#: What it opens talking to, where the CLI it opens on runs it. The menu leads with the most
#: capable model a CLI has, which is the one to reach for rather than the one to spend before
#: anybody has asked for anything -- so what it starts on is named here instead.
_STARTS_AT = ("claude-opus-5", "gpt-5.6-sol", "kimi-code/k3")


def _starts_at(models: tuple[Model, ...]) -> str:
    """Which of a CLI's models the interface opens talking to.

    Args:
      models: What that CLI runs, in the order it is offered in.

    Returns:
      The one named as the one to start on, or the first it offers when none of them is.
    """
    named = {model.name for model in models}
    return next((at for at in _STARTS_AT if at in named), models[0].name)


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
        "input-selection-background": "ansi_bright_black",
        "input-selection-foreground": "ansi_bright_white",
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


class Editor(TextArea):
    """The prompt: multi-line, but enter sends rather than breaking the line."""

    BINDINGS: ClassVar = [
        Binding("enter", "send", "send", priority=True),
        Binding("ctrl+j", "newline", "newline", priority=True),
    ]

    class Sent(Message):
        """What was typed, now that it has been sent."""

        def __init__(self, text: str):
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

    async def _on_key(self, event: events.Key) -> None:
        """Gives tab and the arrows to the offers, but only while there are any.

        Bound here rather than on the application, and only when the list is showing: a key
        the offers are not using is the editor's, and a prompt of more than one line needs
        its arrows back. With nothing offered they walk what was typed here before, and only
        from the ends of what is being typed now -- up off the first line, down off the last
        -- so that a prompt of several lines is still moved around in. Tab is the offers'
        alone: stepping between flows is shift+tab, which nothing here wants.
        """
        listing = self.screen.query_one("#offers", OptionList)
        if not listing.has_class("offering"):
            if event.key in ("up", "down"):
                history = self.app.history  # type: ignore[attr-defined]
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
            listing.set_class(False, "offering")

    def take(self, whole: str) -> None:
        """Replaces the part being finished with what was offered for it.

        Args:
          whole: The offer, in full.
        """
        typed = self.text
        self.text = typed[: len(typed) - len(typed.split(" ")[-1])] + whole + " "
        self.move_cursor(self.document.end)


class Humanize(App[None]):
    """A transcript, an editor, a status line, and what the flow is doing beside them."""

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
    #transcript { width: 1fr; padding: 0; }
    .panel { margin-bottom: 1; }
    #side { width: 30; display: none; padding: 0 0 0 2; }
    #side.watching { display: block; }

    /* Above the prompt and unbordered, at most ten rows: what Claude Code offers a
       half-typed command in. The row under the cursor is coloured, not filled. */
    #offers { display: none; max-height: 10; padding: 0 2; background: $background;
              border: none; scrollbar-size: 0 0; }
    #offers.offering { display: block; }
    #offers > .option-list--option-highlighted {
        background: $background; color: $primary; text-style: none; }

    /* The prompt: a rule across, what you are typing behind a `❯`, a rule across. Which is
       how Claude Code draws its own -- no box, no bar, no shadow. */
    #above { height: 1; padding: 0 1; color: $text-muted; text-align: right; }
    .rule { height: 1; color: $text-muted; }
    #prompt { height: auto; background: $background; }
    #caret { width: 2; color: $text-muted; }
    #editor { height: auto; max-height: 10; border: none; padding: 0;
              background: $background; }
    #status { height: 1; padding: 0 2; color: $text-muted; }
    """

    BINDINGS: ClassVar = [
        Binding("ctrl+c", "interrupt", "interrupt", priority=True),
        # What the status line says while a flow runs, and what opencode's esc does there.
        # The editor takes esc first while it is offering something, and only then.
        Binding("escape", "stop_flow", "interrupt", show=False),
        Binding("shift+tab", "cycle_flow", "flow", priority=True),
    ]

    def action_quit(self) -> None:  # type: ignore[override]
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

    def __init__(self) -> None:
        """Initializes an interface holding no agents, because nothing is running yet."""
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
        #: The question a turn has stopped on, if one has, and where its answer goes.
        self._asking: Question | None = None
        self._answer = ""
        self._answered = threading.Event()
        #: When ctrl+c was last pressed, so that two of them in a row read as two.
        self._interrupted = 0.0
        #: The flow to run and what each of its agents runs, which start out as the flow that
        #: is only talking to one agent and the first agent there is to talk to. So the first
        #: thing you say starts something rather than being told to pick a flow first: a flow
        #: is what you reach for once talking to one agent is not the shape of the work, and
        #: nobody knows that before they have said anything.
        #:
        #: Not the hardest effort, which is what the picker's cursor starts on: that is the
        #: one to reach for, and this is the one to spend before anyone has asked for
        #: anything. `high` is an effort every model of every backend here takes.
        #: What this workspace was last set up to run, so that opening it again finds it
        #: that way rather than back at the default.
        self.settings = Settings()
        self._flow_named = self.settings.flow or _STARTS_ON
        self._models = self.settings.agents(self._flow_named) or [
            f"{backend}/{_starts_at(models)}:high"
            for backend, models in list(installed().items())[:1]
        ]
        #: What has been typed here before, which the arrows walk. Read now rather than each
        #: time it is asked for: a run started here writes this project's own history into
        #: being, and what is being walked must not change under whoever is walking it.
        self.history = History()
        #: When each agent's turn started, for the line that closes it.
        self._began: dict[str, float] = {}
        #: Whether the last thing shown was a part that the next one may run on from.
        self._packed = False
        #: Said while no turn was open, for whichever turn starts next to take. Written from
        #: the event loop and drained from whichever thread a flow runs on, so it is held
        #: under a lock: `a running flow never drops a line` is only true if nothing races.
        self._queued: list[str] = []
        self._saying = threading.Lock()
        #: Set when something is said, so a flow waiting to be told hears it at once rather
        #: than at the next tick, and whether a flow is waiting to be told at all.
        self._spoke = threading.Event()
        self._awaiting = False

    def compose(self) -> ComposeResult:
        """The transcript and what the flow is doing, the offers, the editor, the status."""
        with Horizontal():
            yield RichLog(id="transcript", wrap=True, markup=True)
            with Vertical(id="side"):
                yield Static(id="flow", classes="panel")
                yield Static(id="spend", classes="panel")
        yield OptionList(id="offers")
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
        # makes a flow watchable: janus tees each agent's streams to ours as they arrive.
        self.begin_capture_print(self)
        self._welcome()
        self._draw()
        self.set_interval(_REFRESH, self._draw)
        # The editor is the only thing to type at, so it is the only thing that takes focus:
        # a transcript or a list that could hold it would swallow the keystrokes meant for it.
        for elsewhere in self.query("#transcript, #offers"):
            elsewhere.can_focus = False
        self.query_one(Editor).focus()

    def _welcome(self) -> None:
        """The box Claude Code opens with, saying what this is set up to do instead.

        Its title rides in the top border and its corners are round, which is the one boxed
        thing on the screen: everything after it is text down the terminal.
        """
        from importlib.metadata import version

        # The transcript's own width, which is the screen less whatever it scrolls with.
        width = max(40, (self.query_one("#transcript", RichLog).size.width or 80) - 1)
        title = f" humanize v{version('humanize')} "
        agents = ", ".join(self._models) or "no coding agent installed here"
        self.show(f"[dim]╭──{title}{'─' * max(0, width - 5 - len(title))}╮[/]")
        for line in (
            f"{self._flow_named}{_DOT}{agents}",
            str(Path.cwd()),
        ):
            room = max(0, width - 4 - len(line))
            self.show(f"[dim]│[/] {escape(line)}{' ' * room} [dim]│[/]")
        self.show(f"[dim]╰{'─' * (width - 2)}╯[/]")

    def on_print(self, event: events.Print) -> None:
        """Puts something printed under this process into the transcript, as a barred block.

        Output is barred rather than indented because that is what opencode does with it:
        a command and what it said are one block, set apart from the words around them.
        """
        if event.text.strip():
            for line in escape(event.text.rstrip("\n")).splitlines():
                self.show(f"[dim]  {_CAME_BACK}  {line}[/]")

    def _said_by_you(self, text: str) -> None:
        """Puts something you said in the transcript, behind the `❯` Claude Code marks it with.

        Args:
          text: What was said.
        """
        self._packed = False  # what a turn says next starts its own part
        said = escape(text).splitlines() or [""]
        self.show("")
        self.show(f"[dim]{_YOURS}[/] {said[0]}")
        for line in said[1:]:
            self.show(f"  {line}")

    def show(self, text: str, style: str = "") -> None:
        """Puts a line in the transcript.

        Args:
          text: What to show, taken as markup when no style is given and as plain text
            otherwise -- so that a bracket an agent wrote stays a bracket.
          style: How to show it, as a Rich style, or "" to show it as it is.
        """
        body = text if style == "" else f"[{style}]{escape(text)}[/{style}]"
        self.query_one("#transcript", RichLog).write(body)

    @on(TextArea.Changed)
    @on(TextArea.SelectionChanged)
    def _offer(self) -> None:
        """Offers whatever the line being typed could be finished with.

        Reconsidered when the cursor moves as well as when the text does: an offer made at
        the end of a line does not still stand once the cursor is back in the middle of it.
        """
        editor = self.query_one(Editor)
        typed = editor.text
        at_end = editor.cursor_location == editor.document.end
        offers = offered(typed, _OWN) if at_end else []
        listing = self.query_one("#offers", OptionList)
        listing.clear_options()
        listing.set_class(bool(offers), "offering")
        if offers:
            # Name on the left and what it is for on the right, as opencode lists its own.
            # The bare name is kept as the option's id, since that is what replaces the text.
            # The name and what it takes on the left, what it is for on the right. The bare
            # name is the option's id, since that is what replaces the text: taking an offer
            # must not type the arguments in as well.
            listing.add_options(
                [
                    Option(
                        # Escaped: what a command takes is written in brackets, and a
                        # bracket left as it is would be read as markup and swallowed --
                        # which is what `[path]` did. Padded first, since the escaping adds
                        # characters that are not columns.
                        escape(f"{f'{offer} {takes(named)}'.rstrip():<19}")
                        + f"[dim]{escape(about(named))}[/dim]",
                        id=offer,
                    )
                    for offer, named in ((one, one.removeprefix("/")) for one in offers)
                ]
            )
            listing.highlighted = 0

    def _draw(self) -> None:
        """Redraws the right-hand column and the status line.

        Called on a timer, which keeps ticking while the interface is being taken down -- so
        there may be nothing left to draw on.
        """
        if not self.is_running:
            return
        graph = self._monitor.graph()
        self.query_one("#side").set_class(bool(self._agents or graph), "watching")
        self.query_one("#flow", Static).update(
            "\n".join(["[b]flow[/b]", *(graph or ["[dim]nothing yet[/dim]"])])
        )
        spending = self._monitor.spending()
        self.query_one("#spend", Static).update(
            "\n".join(
                ["[b]tokens[/b]"]
                + (
                    [
                        f"{escape(spend.model[:22])}\n"
                        f"  [dim]{_thousands(spend.tokens)}   {spend.rate:.0f}/s[/dim]"
                        for spend in spending
                    ]
                    or ["[dim]nothing spent yet[/dim]"]
                )
            )
        )
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
            named = ", ".join(short(who) for who in working) or self._flow_named
            left = (
                f"[$secondary]{bar}[/] {escape(named)}… "
                f"[$text-muted]({time.monotonic() - since:.0f}s{_DOT}esc to interrupt)[/]"
            )
        else:
            left = f"[$secondary]◉[/] {escape(self._flow_named)}"
        # Above the prompt on the right, where Claude Code says what it is running as.
        self.query_one("#above", Static).update(
            f"[$text-muted]{escape(', '.join(self._models) or 'no agent installed')}[/]"
            + (f"{_DOT}{_thousands(spent)} tokens{_DOT}{rate:.0f}/s" if spent else "")
        )
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

    def _switched(self, argv: list[str], now: bool) -> bool | None:
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
        keys = []
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
        keys.append("shift+tab flow")
        keys.append("/ commands")
        keys.append("ctrl+j newline")
        if self._agents:
            keys.append("esc stop")
        keys.append(
            "ctrl+c quit" if not self.query_one(Editor).text else "ctrl+c clear"
        )
        return keys

    def action_cycle_flow(self) -> None:
        """Moves to the next flow there is, without asking anything.

        Which is what shift+tab is for: the flows are a short list and stepping through them
        is quicker than opening a sheet to pick one. What each agent runs is carried over --
        a flow that drives more of them gets the same one again -- so a step is a step and
        not a form to fill in. `/flow` is still there for choosing one by name.
        """
        from humanize.flows import find, found
        from humanize.janus.runner import drives

        named = [name for _, name in found()]
        if not named or not self._models:
            self.show("hmz: no coding agent is installed here", "red")
            return
        at = named.index(self._flow_named) if self._flow_named in named else -1
        switching = named[(at + 1) % len(named)]
        try:
            named_by = drives(find(switching))
        except Exception as why:  # noqa: BLE001 -- a flow that will not load
            self.show(f"hmz: {why}", "red")
            return
        self.action_stop_flow()
        # As many agents as the flow drives, all running what the first one was running. If
        # this workspace has run this flow before, what it ran is what it runs again.
        self._flow_named = switching
        self._models = self.settings.agents(switching) or [self._models[0]] * len(
            named_by
        )
        self.settings.remember(switching, named_by, self._models)
        self._draw()

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
        elif name == "agents":
            self.action_agents()
        elif name == "details":
            if (switched := self._switched(argv, self._details)) is None:
                return
            self._details = switched
            shown = "shown" if self._details else "hidden"
            self.show(f"[dim]tool calls and thinking {shown}[/dim]")
        elif name == "afk":
            if (switched := self._switched(argv, self._afk)) is None:
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
        """
        self.query_one("#transcript", RichLog).clear()
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

    def _export(self) -> None:
        """Writes the transcript beside the trace files, as opencode writes its markdown."""
        import datetime

        stamp = datetime.datetime.now(datetime.UTC).strftime("%Y%m%dT%H%M%SZ")
        where = Path(".humanize") / f"{stamp}.session.md"
        where.parent.mkdir(parents=True, exist_ok=True)
        where.write_text(
            "\n".join(
                line.text for line in self.query_one("#transcript", RichLog).lines
            )
        )
        self.show(f"[dim]{where}[/dim]")

    @work
    async def action_flow(self, named: str = "") -> None:
        """Switches which flow runs, and then what each of its agents runs.

        The two are asked as one walk rather than as two dialogs: what each agent runs is
        asked next because a flow says for itself how many it drives, and esc off the first
        thing that asks is a step back to the flows -- since a flow chosen by mistake is what
        you would be walking back from.

        Args:
          named: A flow of your own, as a path. Left out, the ones humanize came with are
            listed instead -- a path is typed, since guessing which files below here are
            flows means reading all of them.
        """
        from humanize.flows import find
        from humanize.janus.runner import drives

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
                # What the flow calls each agent it drives, which is a name apiece where it
                # declared them as a named tuple and how many there are either way.
                wanted = drives(find(switching))
            except Exception as why:  # noqa: BLE001 -- a flow that will not load
                self.show(f"hmz: {why}", "red")
                return
            chosen = await self.push_screen_wait(Models(switching, wanted, agents))
            if chosen is not None:
                # A flow is chosen in order to be run, so whatever is running stops: the
                # interface opens on one already, and a choice that quietly went to the back
                # of the queue behind it would read as no choice at all. Answering the same
                # way twice is not a choice, though, and must not end the conversation.
                if (switching, list(chosen)) != (self._flow_named, self._models):
                    self.action_stop_flow()
                self._flow_named, self._models = switching, list(chosen)
                self.settings.remember(switching, wanted, self._models)
                self.show("[dim]say what to do, and the flow starts on it[/dim]")
                self._draw()
                return
            if named:
                return  # a flow of your own: there is no list to step back into
            # And otherwise round again, which is the step back off the leftmost column.

    def action_agents(self) -> None:
        """Sets what each of the flow's agents runs, which is what `/agents` is for.

        The flow itself is not asked for again, so esc is a way out rather than a step back
        into a list this did not come through.
        """
        self.action_flow(self._flow_named)

    def _take(self) -> list[str]:
        """Takes everything said while nobody was working, and leaves nothing behind.

        The queue is the interface's rather than any one agent's: a line is typed at the flow
        and reaches whichever agent asks for it first, which is what "a typed line reaches
        whoever has the turn" means. Both hooks drain it, and both drain it destructively, so
        a line is delivered once however it is asked for.

        Returns:
          What was said, oldest first, which is nothing when nothing was.
        """
        with self._saying:
            held, self._queued = self._queued, []
        return held

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
                    return "\n\n".join(held)
                self._spoke.wait(_REFRESH)
        finally:
            self._awaiting = False

    def _flow(self, argv: list[str]) -> None:
        """Starts a flow, keeping its agents so that a typed line can reach one.

        Args:
          argv: The command line, as `hmz exec` takes it.
        """
        from humanize.janus import Runner

        if self._agents:
            self.show("hmz: a flow is already running", "red")
            return
        try:
            path, agents, task = flow_and_agents(argv)
        except SystemExit:
            return  # argparse has already said what was wrong, and it went to the transcript
        self._agents = agents
        self._monitor = Monitor()
        # What the run costs is read from the logs the agents keep, which they write as they
        # go: a backend only says what a turn cost once the turn is over, and a turn is long.
        self._tally = Tally(agents, self._monitor)
        self._tally.watch()
        with self._saying:
            self._queued = []

        for agent in agents:
            agent.watch(self._heard)
            agent.waiting = self._take  # whichever turn starts next takes what was held
            # Bound to the agent, so that each of these answers about the flow that is
            # asking rather than about whichever flow is running by the time it is asked.
            agent.ask = functools.partial(self._ask, agent)
            agent.prompting = functools.partial(self._listen, agent)
        self._draw()

        # This run's, whatever is being watched by the time it ends.
        watching, tally = self._monitor, self._tally

        def drive() -> int:
            try:
                Runner(path, agents).run(task)
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
            return 0

        self._background(drive)

    def _heard(self, agent: AgentBase, event: Event) -> None:
        """Shows what a turn said, and takes it into what the right-hand column shows.

        Called from whichever thread the turn is running on.

        Args:
          agent: Whose turn said it.
          event: What was said.
        """
        # First, whatever else happens: showing a line raises once the interface has gone, and
        # what a watcher raises is swallowed, so accounting after it would be lost.
        for model, tokens in event.tokens.items():
            self._monitor.spend(agent.id, tokens, model=model)
        if event.kind == "begins":
            self._monitor.begins(agent.id, agent.config.model)
            self._began[agent.id] = time.monotonic()
        elif event.kind == "ends":
            self._monitor.ends(agent.id)
            # The line opencode closes a message with: a filled square, two spaces, then the
            # parts separated by a middle dot.
            took = time.monotonic() - self._began.pop(agent.id, time.monotonic())
            # The line Claude Code closes a turn with, which says how long it worked.
            self.call_from_thread(
                self._part,
                f"[dim]{_WORKED} Worked for {took:.0f}s"
                f"{_DOT}{escape(short(agent.id))}[/]",
                False,
            )
        elif event.kind == "tool" and self._details:
            # The tool on the bullet, what it came back with under it -- Claude Code's shape.
            named, _, about = escape(event.text).partition(" ")
            self.call_from_thread(
                self._part,
                f"[green]{_SAID}[/] {named}[dim]({about})[/]",
                True,
            )
        elif event.kind == "reasoning" and self._details:
            self.call_from_thread(
                self._part,
                "\n".join(
                    f"[dim italic]{line}[/]" for line in escape(event.text).splitlines()
                ),
                False,
            )
        elif event.kind == "asks":
            self.call_from_thread(
                self._part,
                f"[yellow]{_SAID}[/] {escape(event.text)}",
                False,
            )
        elif event.kind == "text":
            # The bullet on the first line, two spaces under it for the rest, which is how
            # Claude Code sets a message it has just written.
            said = escape(event.text).splitlines() or [""]
            self.call_from_thread(
                self._part,
                "\n".join(
                    [f"[green]{_SAID}[/] {said[0]}", *(f"  {l}" for l in said[1:])]
                ),
                False,
            )

    def _part(self, text: str, packs: bool) -> None:
        """Puts one part of a turn in the transcript, spaced as opencode spaces its own.

        A blank line goes between the parts, except between two that pack -- one-line tool
        rows run together, and everything else is set apart.

        Args:
          text: The part, as markup.
          packs: Whether this part is one that runs on from the one before it.
        """
        if not (packs and self._packed):
            self.show("")
        self._packed = packs
        self.show(text)

    def _background(self, work: Callable[[], int]) -> None:
        """Runs something off the event loop, showing what it says rather than dying of it.

        Args:
          work: What to do, answering with the status to report, if any.
        """

        def go() -> None:
            from humanize.janus import Stopped

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
            named = [part for model in self._models for part in ("-a", model)]
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
        added here is what it will take for an answer, which only the one asking knows.

        Args:
          question: What the agent wants to know.
        """
        for option in question.options:
            self.show(f"      [dim]· {escape(option)}[/dim]")
        self.show("   [dim]type an answer, or /afk to stop being asked[/dim]")

    @property
    def _set_up(self) -> bool:
        """Whether there is something for each of the flow's agents to run on.

        There is always a flow -- the interface opens on one -- so this is only ever short of
        an agent, which is a machine with no coding agent installed on it.
        """
        return bool(self._models)

    def _interject(self, text: str) -> None:
        """Says something to the agent working right now.

        Args:
          text: What to say.
        """
        working = set(self._monitor.now_working())
        sessions = [
            session
            for agent in self._agents
            if agent.id in working
            for session in agent.sessions
        ]
        self._said_by_you(text)
        if not sessions:
            # Between two turns, or inside a flow's own sleep. It is held rather than
            # written to a session, which between turns would answer it on its own, and it
            # goes into whichever turn starts next -- so a running flow never drops a line.
            with self._saying:
                self._queued.append(text)
            self._spoke.set()
            if not self._awaiting:
                # A flow waiting at the prompt is about to take this as the whole of its next
                # turn, so saying it was held would be saying so of every line ever typed.
                self.show("[dim]   held for the next turn[/dim]")
            return

        def put_in() -> int:
            # Off the event loop: this writes to the agent, and a large paste into a pipe the
            # interface itself is draining would otherwise deadlock the two.
            try:
                sessions[-1].interject(text)
            except (NotImplementedError, RuntimeError) as error:
                self.call_from_thread(self.show, f"hmz: {error}", "red")
            return 0

        self._background(put_in)

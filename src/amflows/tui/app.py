"""amflows as a coding agent's own terminal, with a flow underneath instead of one agent.

Laid out the way opencode is, and no wider: a transcript, an editor under it, a status line
under that, and what the flow is doing beside them. Nothing is chosen from a dialog -- a `/`
offers the commands, and a flag offers whatever it takes -- so there is one way to say a thing
and it is the way it is written down.

The editor means both things at once: a line starting with `/` is a command, and any other
line is said to the agent working right now.
"""

from __future__ import annotations

import shlex
import traceback
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from rich.markup import escape
from textual import events, on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widgets import OptionList, RichLog, Static, TextArea

from amflows.cli import COMMANDS, flow_and_agents

from .complete import flows, offered
from .monitor import Monitor, short

if TYPE_CHECKING:
    from amflows.janus import AgentBase, Event

#: What the editor understands beyond the commands the command line has.
_OWN = ("help", "clear", "quit")

#: How often the right-hand column and the status line are redrawn, in seconds.
_REFRESH = 0.5

#: How a tool call reads in the transcript, which is one compact row rather than a block.
_TOOL = "  [dim]⏺[/dim] "


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
        """Sends what is in the editor and empties it."""
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
        its arrows back.
        """
        listing = self.screen.query_one("#offers", OptionList)
        if not listing.has_class("offering"):
            return
        if event.key == "tab":
            event.prevent_default()
            event.stop()
            if listing.highlighted is not None:
                self.take(str(listing.get_option_at_index(listing.highlighted).prompt))
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


class Amflows(App[None]):
    """A transcript, an editor, a status line, and what the flow is doing beside them."""

    CSS = """
    Screen { background: $surface; }
    #transcript { width: 1fr; padding: 1 2 0 2; }
    .panel { margin-bottom: 1; }
    #side { width: 30; display: none; padding: 1 1 0 2; }
    #side.watching { display: block; }

    #offers { display: none; max-height: 8; border: none; padding: 0 2; background: $panel; }
    #offers.offering { display: block; }

    #editor { height: auto; max-height: 10; border: round $primary 60%; }
    #editor:focus { border: round $primary; }
    #status { height: 1; padding: 0 2; color: $text-muted; }
    """

    BINDINGS: ClassVar = [
        ("ctrl+c", "quit", "quit"),
        ("ctrl+l", "clear", "clear"),
    ]

    def __init__(self) -> None:
        """Initializes an interface holding no agents, because nothing is running yet."""
        super().__init__()
        #: The agents of the flow running now, which is who a typed line is said to.
        self._agents: list[AgentBase] = []
        #: What the flow has done so far, which is what the right-hand column shows.
        self._monitor = Monitor()

    def compose(self) -> ComposeResult:
        """The transcript and what the flow is doing, the offers, the editor, the status."""
        with Horizontal():
            yield RichLog(id="transcript", wrap=True, markup=True)
            with Vertical(id="side"):
                yield Static(id="flow", classes="panel")
                yield Static(id="spend", classes="panel")
        yield OptionList(id="offers")
        yield Editor(id="editor", show_line_numbers=False)
        yield Static(id="status")

    def on_mount(self) -> None:
        """Says what this understands, then waits to be told something."""
        # Everything printed anywhere under this process lands in the transcript, which is what
        # makes a flow watchable: janus tees each agent's streams to ours as they arrive.
        self.begin_capture_print(self)
        self.show("[b]amflows[/b]  [dim]a flow, and the agents running it[/dim]\n")
        self.action_help()
        self._draw()
        self.set_interval(_REFRESH, self._draw)
        # The editor is the only thing to type at, so it is the only thing that takes focus:
        # a transcript or a list that could hold it would swallow the keystrokes meant for it.
        for elsewhere in self.query("#transcript, #offers"):
            elsewhere.can_focus = False
        self.query_one(Editor).focus()
        # Found once, off the event loop, so that the first `/run -f` does not pay for a walk
        # of this directory between one keystroke and the next.
        self.run_worker(flows, thread=True)

    def on_print(self, event: events.Print) -> None:
        """Puts something printed under this process into the transcript."""
        if event.text.strip():
            self.show(event.text.rstrip("\n"), "dim" if event.stderr else "default")

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
        offers = offered(typed, (*COMMANDS, *_OWN)) if at_end else []
        listing = self.query_one("#offers", OptionList)
        listing.clear_options()
        listing.set_class(bool(offers), "offering")
        if offers:
            listing.add_options(offers)
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
        working = ", ".join(self._monitor.now_working())
        status = [f"[dim]{escape(str(Path.cwd()))}[/dim]"]
        if working:
            status.append(f"[b]▶[/b] {escape(working)}")
        if spent:
            status.append(f"[dim]{_thousands(spent)} tokens · {rate:.0f}/s[/dim]")
        self.query_one("#status", Static).update("   ".join(status), layout=False)

    def action_clear(self) -> None:
        """Empties the transcript, leaving whatever is running alone."""
        self.query_one("#transcript", RichLog).clear()

    def action_help(self) -> None:
        """Shows what the editor understands, which is the commands and everything else."""
        self.show(
            "  [dim]"
            + "  ".join(f"/{name}" for name in (*COMMANDS, *_OWN))
            + "[/dim]\n"
            "  [dim]tab takes what is offered · enter sends · ctrl+j breaks the line[/dim]\n"
            "  [dim]a line not starting with / is said to the agent working now[/dim]"
        )

    @on(Editor.Sent)
    def _sent(self, event: Editor.Sent) -> None:
        """Takes what was typed as a command, or as something to say to the agent."""
        line = event.text
        if not line.startswith("/"):
            self._interject(line)
            return
        self.show(f"\n[b]›[/b] {escape(line)}")
        name, _, rest = line[1:].partition(" ")
        try:
            argv = shlex.split(rest)
        except (
            ValueError
        ) as error:  # an unbalanced quote is a line to correct, not a crash
            self.show(f"amflows: {error}", "red")
            return
        if name == "quit":
            self.exit()
        elif name == "help":
            self.action_help()
        elif name == "clear":
            self.action_clear()
        elif name == "run":
            self._flow(argv)
        elif name in COMMANDS:
            self._background(lambda: COMMANDS[name][0](argv))
        else:
            self.show(f"amflows: no such command: /{name}", "red")

    def _flow(self, argv: list[str]) -> None:
        """Starts a flow, keeping its agents so that a typed line can reach one.

        Args:
          argv: The `run` command line, as `amflows run` takes it.
        """
        from amflows.janus import Runner

        if self._agents:
            self.show("amflows: a flow is already running", "red")
            return
        try:
            path, agents, task = flow_and_agents(argv)
        except SystemExit:
            return  # argparse has already said what was wrong, and it went to the transcript
        self._agents = agents
        self._monitor = Monitor()
        for agent in agents:
            agent.watch(self._heard)
        self._draw()

        def drive() -> int:
            try:
                Runner(path, agents).run(task)
            finally:
                self._agents = []
                self.call_from_thread(self.show, "[dim]— the flow is done —[/dim]")
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
            self.call_from_thread(self.show, f"\n[dim]{escape(short(agent.id))}[/dim]")
        elif event.kind == "ends":
            self._monitor.ends(agent.id)
        elif event.kind == "tool":
            self.call_from_thread(self.show, f"{_TOOL}{escape(event.text)}")
        elif event.kind == "reasoning":
            self.call_from_thread(self.show, event.text, "dim italic")
        elif event.kind == "text":
            self.call_from_thread(self.show, escape(event.text))

    def _background(self, work: Callable[[], int]) -> None:
        """Runs something off the event loop, showing what it says rather than dying of it.

        Args:
          work: What to do, answering with the status to report, if any.
        """

        def go() -> None:
            try:
                status = work()
            except SystemExit as stopped:  # argparse rejecting the line, not a crash
                status = int(stopped.code or 0)
            except Exception:  # noqa: BLE001 -- a flow fails any way it likes, and is shown
                self.call_from_thread(self.show, traceback.format_exc().strip(), "red")
                return
            if status:
                self.call_from_thread(self.show, f"— exited {status} —", "red")

        self.run_worker(go, thread=True, exit_on_error=False)

    def _interject(self, text: str) -> None:
        """Says something to the agent working right now.

        Args:
          text: What to say.
        """
        # Whoever has a turn open is who a typed line is for, and if nobody has, there is
        # nobody to tell: an agent between turns still holds a session that would take the
        # line without a word and say it back inside its own next turn.
        working = set(self._monitor.now_working())
        sessions = [
            session
            for agent in self._agents
            if agent.id in working
            for session in agent.sessions
        ]
        if not sessions:
            self.show("amflows: nothing is running to be told that", "red")
            return
        self.show(f"\n[b]›[/b] {escape(text)}")

        def put_in() -> int:
            # Off the event loop: this writes to the agent, and a large paste into a pipe the
            # interface itself is draining would otherwise deadlock the two.
            try:
                sessions[-1].interject(text)
            except (NotImplementedError, RuntimeError) as error:
                self.call_from_thread(self.show, f"amflows: {error}", "red")
            return 0

        self._background(put_in)

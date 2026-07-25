"""amflows as a coding agent's own terminal, with a flow underneath instead of one agent.

Laid out the way opencode is, because that is the thing this is: a transcript of the work,
a multi-line editor under it, and a status line under that. What is different is what is
running -- a flow driving several agents rather than one agent driving itself -- so the right
of the screen says which agent is working, who handed to whom, and what it is all costing.

The editor is both things at once: a line starting with `/` is a command, and any other line
is said to the agent working right now. A command named with nothing after it is filled in
rather than typed.
"""

from __future__ import annotations

import asyncio
import os
import shlex
import traceback
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from rich.markup import escape
from textual import events, on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widgets import RichLog, Static, TextArea

from amflows.cli import COMMANDS, flow_and_agents

from .form import Form, fields_for
from .monitor import Monitor, short

if TYPE_CHECKING:
    from amflows.janus import AgentBase, Event

#: What the editor understands, and the line `/help` shows each under. Every command of the
#: command line is among them, which is checked rather than remembered.
_HELP = (
    ("/run", "drive a flow — with nothing after it, fill one in"),
    ("/collect", "write what the agents left behind as a trace"),
    ("/anchor", "run an agent whose work lands on another machine"),
    ("/cd PATH", "work somewhere else"),
    ("/help  /clear  /quit", "this, empty the transcript, leave"),
    ("anything else", "say it to the agent working right now"),
)

#: How often the right-hand column and the status line are redrawn, in seconds.
_REFRESH = 0.5

#: How a tool call reads in the transcript, which is one compact row rather than a block.
_TOOL = "  [dim]⏺[/dim] "

#: Everything the editor completes: the commands of the command line and this one's own.
_COMPLETIONS = sorted(f"/{name}" for name in (*COMMANDS, "cd", "help", "clear", "quit"))


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
        Binding("tab", "complete", "complete", priority=True),
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

    def action_complete(self) -> None:
        """Takes the rest of the command being offered, if one is."""
        if rest := self.suggestion:
            self.insert(f"{rest} ")

    def update_suggestion(self) -> None:
        """Offers the rest of the command being typed, which the editor greys in for us.

        Called by the editor whenever the text changes; also called on a cursor that moved,
        because an offer is only ever made at the end of what is typed, where taking it would
        put it.
        """
        typed = self.text
        offered = (
            not typed.startswith("/")
            or " " in typed
            or "\n" in typed
            or self.cursor_location != self.document.end
        )
        self.suggestion = (
            ""
            if offered
            else next(
                (name[len(typed) :] for name in _COMPLETIONS if name.startswith(typed)),
                "",
            )
        )

    def watch_selection(self, *_: object) -> None:
        """Reconsiders the offer when the cursor moves, which the editor does not do itself.

        Without this, an offer made at the end of the line would still be shown after the
        cursor was moved back into the middle of it, and taking it would break the word.
        """
        self.update_suggestion()


class Amflows(App[None]):
    """A transcript, an editor, a status line, and what the flow is doing beside them."""

    CSS = """
    Screen { background: $surface; }
    #body { height: 1fr; }
    #left { width: 1fr; }
    #side { width: 30; display: none; padding: 1 1 0 2; }
    #side.watching { display: block; }

    #transcript {
        background: $surface;
        border: none;
        padding: 1 2 0 2;
        scrollbar-size-vertical: 1;
    }

    .panel { height: auto; margin-bottom: 1; }

    #editor {
        height: auto;
        max-height: 10;
        border: round $primary 60%;
        background: $surface;
        padding: 0 1;
    }
    #editor:focus { border: round $primary; }
    #status { height: 1; padding: 0 2; background: $surface; color: $text-muted; }
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
        """The transcript and what the flow is doing, the editor, then the status line."""
        with Horizontal(id="body"):
            with Vertical(id="left"):
                yield RichLog(
                    id="transcript",
                    wrap=True,
                    markup=True,
                    highlight=False,
                    auto_scroll=True,
                )
            with Vertical(id="side"):
                yield Static(id="flow", classes="panel")
                yield Static(id="spend", classes="panel")
        yield Editor(id="editor", soft_wrap=True, show_line_numbers=False)
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
        self.query_one(Editor).focus()

    def on_print(self, event: events.Print) -> None:
        """Puts something printed under this process into the transcript.

        Whatever an agent wrote is shown as the text it is: a closing bracket it happened to
        print is a bracket, not markup that would fail to parse and take this handler with it.
        """
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

    def _draw(self) -> None:
        """Redraws the right-hand column and the status line.

        Called on a timer, which keeps ticking while the interface is being taken down and
        while a sheet is up in front of it -- so there may be nothing left to draw on.
        """
        if not self.is_running or not self.query("#side"):
            return
        self.query_one("#side").set_class(
            bool(self._agents) or self._monitor.has_run(), "watching"
        )
        self.query_one("#flow", Static).update(
            "\n".join(
                ["[b]flow[/b]", *(self._monitor.graph() or ["[dim]nothing yet[/dim]"])]
            )
        )

        spending = self._monitor.spending()
        lines = ["[b]tokens[/b]"]
        lines += [
            f"{escape(spend.model[:22])}\n"
            f"  [dim]{_thousands(spend.tokens)}   {spend.rate:.0f}/s[/dim]"
            for spend in spending
        ] or ["[dim]nothing spent yet[/dim]"]
        self.query_one("#spend", Static).update("\n".join(lines))

        spent = sum(spend.tokens for spend in spending)
        rate = sum(spend.rate for spend in spending)
        working = ", ".join(self._monitor.now_working())
        status = [f"[dim]{escape(str(Path.cwd()))}[/dim]"]
        if working:
            status.append(f"[b]▶[/b] {escape(working)}")
        elif self._agents:
            status.append("[dim]…[/dim]")
        if spent:
            status.append(f"[dim]{_thousands(spent)} tokens · {rate:.0f}/s[/dim]")
        self.query_one("#status", Static).update("   ".join(status), layout=False)

    def action_clear(self) -> None:
        """Empties the transcript, leaving whatever is running alone."""
        self.query_one("#transcript", RichLog).clear()

    def action_help(self) -> None:
        """Shows what the editor understands."""
        for command, what in _HELP:
            self.show(f"  [b]{command}[/b]  [dim]{what}[/dim]")

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
        self._carry_out(name, argv)

    def _carry_out(self, name: str, argv: list[str]) -> None:
        """Carries out one slash command, filling it in first if it was given nothing.

        Args:
          name: The command, without its slash.
          argv: What followed it, split the way a shell would.
        """
        if name == "quit":
            self.exit()
        elif name == "help":
            self.action_help()
        elif name == "clear":
            self.action_clear()
        elif name == "cd":
            self._cd(argv)
        elif name not in COMMANDS:
            self.show(f"amflows: no such command: /{name}", "red")
        elif argv:
            self._start(name, argv)
        else:
            self._fill_in(name)

    @work
    async def _fill_in(self, name: str) -> None:
        """Asks for a command's arguments in a sheet, then carries it out.

        Args:
          name: The command to fill in.
        """
        fields = await asyncio.to_thread(fields_for, name)
        if (argv := await self.push_screen_wait(Form(name, fields))) is not None:
            self.show(f"[dim]/{name} {escape(shlex.join(argv))}[/dim]")
            self._start(name, argv)

    def _start(self, name: str, argv: list[str]) -> None:
        """Runs a command, which for a flow means keeping its agents to be talked to.

        Args:
          name: The command, as `amflows` spells it.
          argv: Its arguments.
        """
        if name == "run":
            self._flow(argv)
        else:
            self._background(lambda: COMMANDS[name][0](argv))

    def _cd(self, argv: list[str]) -> None:
        """Moves to another directory, which is where a flow started here will run."""
        try:
            os.chdir(Path(argv[0]).expanduser() if argv else Path.home())
        except OSError as error:
            self.show(f"amflows: {error}", "red")
            return
        self._draw()

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
        # First, and whatever else happens: showing a line raises once the interface has gone,
        # and what a watcher raises is swallowed, so accounting placed after it would be lost
        # for that event.
        for model, tokens in event.tokens.items():
            self._monitor.spend(agent.id, tokens, model=model)
        if event.kind == "begins":
            self._monitor.begins(agent.id, agent.config.model)
            self.call_from_thread(self.show, f"\n[dim]{escape(short(agent.id))}[/dim]")
        elif event.kind == "ends":
            self._monitor.ends(agent.id)
        elif event.kind == "tool":
            # A tool is a row rather than a block: what matters in a transcript is that one
            # was used and which, not the whole of what it was handed.
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
        # Whoever has a turn open is who a typed line is for. The last agent on the command
        # line may be sitting on a session of its own that is idle but still alive, and would
        # take the line silently and say it back in its own next turn.
        working = set(self._monitor.now_working())
        busy = [agent for agent in self._agents if agent.id in working]
        sessions = [
            session for agent in busy or self._agents for session in agent.sessions
        ]
        if not sessions:
            self.show("amflows: nothing is running to be told that", "red")
            return
        self.show(f"\n[b]›[/b] {escape(text)}")

        def put_in() -> int:
            # Off the event loop: this writes to the agent's stdin, and a large paste into a
            # pipe the interface itself is draining would otherwise deadlock the two.
            try:
                sessions[-1].interject(text)
            except (NotImplementedError, RuntimeError) as error:
                self.call_from_thread(self.show, f"amflows: {error}", "red")
            return 0

        self._background(put_in)

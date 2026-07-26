"""amflows as a coding agent's own terminal, with a flow underneath instead of one agent.

Laid out the way opencode is, and no wider: a transcript, an editor under it, a status line
under that, and what the flow is doing beside them. Tab picks a flow the way opencode's tab
picks an agent, and `/models` sets what each of that flow's agents runs.

The editor means both things at once: a line starting with `/` is a command, and any other
line is the task if nothing is running yet, or is said to the agent working right now.
"""

from __future__ import annotations

import contextlib
import shlex
import threading
import time
import traceback
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from rich.markup import escape
from rich.text import Text
from textual import events, on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widgets import OptionList, RichLog, Static, TextArea
from textual.widgets.option_list import Option

from amflows.cli import COMMANDS, flow_and_agents

from .complete import about, offered
from .discover import installed
from .monitor import Monitor, short
from .pick import Flows, Models

if TYPE_CHECKING:
    from amflows.janus import AgentBase, Event

#: What the editor understands beyond the commands the command line has, named as opencode
#: names them: its `/agents` switches which agent answers, and here that is which flow runs,
#: since a flow is what answers; its `/models` sets what that runs on, and a flow runs on one
#: model per agent it drives, so the same command asks once apiece.
_OWN = (
    "agents",
    "models",
    "new",
    "details",
    "thinking",
    "export",
    "help",
    "exit",
)

#: How often the right-hand column and the status line are redrawn, in seconds.
_REFRESH = 0.5

#: How many cells the bar opencode spins in its status line is wide. Blocks, not braille --
#: watching it run is what says so.
_BLOCKS = 8

#: What opencode draws a tool call with, read out of its own source: three spaces, then the
#: icon its renderer picks for that tool, then one space, then the label. There is no `⏺` in
#: opencode -- that glyph is another agent's -- and no per-tool checkmark.
_ICONS = {
    "bash": "$",
    "read": "→",
    "write": "←",
    "edit": "←",
    "glob": "✱",
    "grep": "✱",
    "webfetch": "%",
    "websearch": "◈",
    "task": "│",
}

#: What a tool amflows has never heard of is drawn with, as opencode draws its own unknowns.
_UNKNOWN = "⚙"

#: What is on screen before anything is typed, which is a wordmark and one tip.
_WORDMARK = (
    "█▀▀█ █▄ ▄█ █▀▀▀ █    █▀▀█ █   █ █▀▀▀",
    "█▄▄█ █ █ █ █▀▀  █    █  █ █ █ █ ▀▀▀█",
    "▀  ▀ ▀   ▀ ▀    ▀▀▀▀ ▀▀▀▀ ▀▀ ▀▀ ▀▀▀▀",
)
_TIP = "Press tab to pick a flow and the models it runs on, then say what it is to do"

#: The bar opencode puts down the left of a user's message, and the dot it separates the
#: parts of a summary line with.
_BAR = "┃"
_DOT = " · "


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
            if event.key == "tab":
                event.prevent_default()
                event.stop()
                self.app.action_agents()  # type: ignore[attr-defined]
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


class Amflows(App[None]):
    """A transcript, an editor, a status line, and what the flow is doing beside them."""

    CSS = """
    Screen { background: $surface; }
    #transcript { width: 1fr; padding: 1 2 0 2; }
    .panel { margin-bottom: 1; }
    #side { width: 30; display: none; padding: 1 1 0 2; }
    #side.watching { display: block; }

    /* Above the editor, barred down both sides and nowhere else, at most ten rows: what
       opencode draws its completions in. The row under the cursor is marked by its
       background alone, which is what an option list does anyway. */
    #offers { display: none; max-height: 10; margin: 0 2; padding: 0 1; background: $panel;
              border: none; scrollbar-size: 0 0;
              border-left: heavy $panel-lighten-2; border-right: heavy $panel-lighten-2; }
    #offers.offering { display: block; }

    /* Not a box: one bar down the left, the flow named inside it under what is being
       typed, and a capped shadow beneath -- which is how opencode draws its prompt. */
    #prompt { height: auto; margin: 0 2; background: $panel; padding: 1 2 0 2;
              border-left: heavy $primary 60%; }
    #prompt:focus-within { border-left: heavy $primary; }
    /* Bare: the bar around it is the prompt's, and a second one inside would be a box. */
    #editor { height: auto; max-height: 10; border: none; padding: 0; background: $panel; }
    #hint { height: 1; margin-top: 1; color: $text-muted; }
    #shadow { height: 1; margin: 0 2; color: $panel; }
    #status { height: 1; padding: 0 2; color: $text-muted; }
    """

    BINDINGS: ClassVar = [
        ("ctrl+c", "quit", "quit"),
        # What the status line says while a flow runs, and what opencode's esc does there.
        # The editor takes esc first while it is offering something, and only then.
        Binding("escape", "stop_flow", "interrupt", show=False),
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

    def __init__(self) -> None:
        """Initializes an interface holding no agents, because nothing is running yet."""
        super().__init__()
        #: The agents of the flow running now, which is who a typed line is said to.
        self._agents: list[AgentBase] = []
        #: What the flow has done so far, which is what the right-hand column shows.
        self._monitor = Monitor()
        #: Whether a tool call and whether the agent's thinking are shown, as opencode's
        #: `/details` and `/thinking` toggle them.
        self._details = True
        self._thinking = True
        #: The flow to run and what each of its agents runs. The first thing you say once
        #: both are set is the task, which is what starts it.
        self._flow_named = ""
        self._models: list[str] = []
        #: When each agent's turn started, for the line that closes it.
        self._began: dict[str, float] = {}
        #: Whether the last thing shown was a part that the next one may run on from.
        self._packed = False
        #: Said while no turn was open, for whichever turn starts next to take.
        self._queued: list[str] = []

    def compose(self) -> ComposeResult:
        """The transcript and what the flow is doing, the offers, the editor, the status."""
        with Horizontal():
            yield RichLog(id="transcript", wrap=True, markup=True)
            with Vertical(id="side"):
                yield Static(id="flow", classes="panel")
                yield Static(id="spend", classes="panel")
        yield OptionList(id="offers")
        with Vertical(id="prompt"):
            yield Editor(id="editor", show_line_numbers=False)
            yield Static(id="hint")
        yield Static(id="shadow")
        yield Static(id="status")

    def on_mount(self) -> None:
        """Says what this understands, then waits to be told something."""
        # Everything printed anywhere under this process lands in the transcript, which is what
        # makes a flow watchable: janus tees each agent's streams to ours as they arrive.
        self.begin_capture_print(self)
        # A wordmark and one tip, which is all opencode puts on screen before you type. The
        # commands are behind `/`, so listing them here would only be in the way.
        for row in _WORDMARK:
            self.show(f"[dim]{row}[/dim]")
        self.show(f"\n[yellow]●[/yellow] [b]Tip[/b] [dim]{_TIP}[/dim]\n")
        self._draw()
        self.set_interval(_REFRESH, self._draw)
        # The editor is the only thing to type at, so it is the only thing that takes focus:
        # a transcript or a list that could hold it would swallow the keystrokes meant for it.
        for elsewhere in self.query("#transcript, #offers"):
            elsewhere.can_focus = False
        self.query_one(Editor).focus()

    def on_print(self, event: events.Print) -> None:
        """Puts something printed under this process into the transcript, as a barred block.

        Output is barred rather than indented because that is what opencode does with it:
        a command and what it said are one block, set apart from the words around them.
        """
        if event.text.strip():
            for line in escape(event.text.rstrip("\n")).splitlines():
                self.show(f"[dim]{_BAR}[/dim]  [dim]{line}[/dim]")

    def _said_by_you(self, text: str) -> None:
        """Puts something you said in the transcript, down a bar as opencode draws it.

        Args:
          text: What was said.
        """
        self._packed = False  # what a turn says next starts its own part
        for line in ("", *escape(text).splitlines(), ""):
            self.show(f"[cyan]{_BAR}[/cyan]  {line}")

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
            # Name on the left and what it is for on the right, as opencode lists its own.
            # The bare name is kept as the option's id, since that is what replaces the text.
            listing.add_options(
                [
                    Option(
                        f"{offer:<12}[dim]{escape(about(offer.lstrip('/')))}[/dim]"
                        if about(offer.lstrip("/"))
                        else offer,
                        id=offer,
                    )
                    for offer in offers
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
        working = ", ".join(self._monitor.now_working())
        if working:
            at = int(time.monotonic() / _REFRESH) % (_BLOCKS * 2)
            at = at if at < _BLOCKS else _BLOCKS * 2 - 1 - at  # there and back again
            bar = "".join("■" if step == at else "⬝" for step in range(_BLOCKS))
            left = (
                f"[cyan]{bar}[/cyan]  {escape(working)}"
                f"   [bold]esc[/bold] [dim]interrupt[/dim]"
            )
        elif self._set_up and not self._agents:
            left = "[dim]waiting for a task[/dim]"
        else:
            left = f"[dim]{escape(str(Path.cwd()))}[/dim]"
        # Inside the prompt, what is set up to run: the flow and who runs it, as opencode
        # names the agent and model it would send to.
        self.query_one("#hint", Static).update(
            f"[cyan]{escape(self._flow_named or 'no flow')}[/cyan]"
            f"{_DOT}[dim]{escape(', '.join(self._models) or 'tab picks a flow')}[/dim]"
        )
        self.query_one("#shadow", Static).update(
            "╹" + "▀" * max(0, self.size.width - 1)
        )
        right = (
            f"[dim]{_thousands(spent)} tokens · {rate:.0f}/s[/dim]"
            if spent
            else "[bold]tab[/bold] [dim]flows[/dim]  [bold]/[/bold] [dim]commands[/dim]"
        )
        # Measured as drawn rather than as written: markup is not what takes up columns.
        gap = (
            self.size.width
            - 4
            - sum(Text.from_markup(end).cell_len for end in (left, right))
        )
        self.query_one("#status", Static).update(
            left + " " * max(2, gap) + right, layout=False
        )

    def action_help(self) -> None:
        """Shows what the editor understands, which is the commands and everything else."""
        self.show(
            "   [dim]"
            + "  ".join(f"/{name}" for name in (*COMMANDS, *_OWN) if about(name))
            + "[/dim]\n"
            "   [dim]tab picks a flow, or takes what is offered · enter sends · "
            "ctrl+j breaks the line[/dim]\n"
            "   [dim]the first thing you say is the task; anything after it goes to "
            "whoever has the turn[/dim]"
        )

    @on(Editor.Sent)
    def _sent(self, event: Editor.Sent) -> None:
        """Takes what was typed as a command, or as something to say to the agent."""
        line = event.text
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
            self.show(f"amflows: {error}", "red")
            return
        if name == "exit":
            self.action_quit()
        elif name == "help":
            self.action_help()
        elif name == "new":
            self.action_new()
        elif name == "agents":
            self.action_agents(argv[0] if argv else "")
        elif name == "models":
            self.action_models()
        elif name == "details":
            self._details = not self._details
            self.show(f"[dim]tool calls {'shown' if self._details else 'hidden'}[/dim]")
        elif name == "thinking":
            self._thinking = not self._thinking
            self.show(f"[dim]thinking {'shown' if self._thinking else 'hidden'}[/dim]")
        elif name == "export":
            self._export()
        elif name in COMMANDS and name != "run":
            self._background(lambda: COMMANDS[name][0](argv))
        else:
            self.show(f"amflows: no such command: /{name}", "red")

    def action_new(self) -> None:
        """Starts over: an empty transcript, no flow chosen, and nothing done."""
        self.action_stop_flow()
        self.query_one("#transcript", RichLog).clear()
        self._monitor = Monitor()
        self._models = []
        self._draw()

    def action_stop_flow(self) -> None:
        """Stops the whole flow, not just the turn -- which is what esc is for.

        Every agent is told to take no further turn, so the one running now is closed out and
        the loop driving it ends rather than handing on to the next agent. Silent when
        nothing is running: esc is pressed to dismiss things, and a complaint apiece would be
        in the way.
        """
        for agent in self._agents:
            agent.stop()
        if self._agents:
            self.show("[dim]— stopping the flow —[/dim]")

    def _export(self) -> None:
        """Writes the transcript beside the trace files, as opencode writes its markdown."""
        import datetime

        stamp = datetime.datetime.now(datetime.UTC).strftime("%Y%m%dT%H%M%SZ")
        where = Path(".amflows") / f"{stamp}.session.md"
        where.parent.mkdir(parents=True, exist_ok=True)
        where.write_text(
            "\n".join(
                line.text for line in self.query_one("#transcript", RichLog).lines
            )
        )
        self.show(f"[dim]{where}[/dim]")

    @work
    async def action_agents(self, named: str = "") -> None:
        """Switches which flow runs, as opencode's tab switches which agent answers.

        Args:
          named: A flow of your own, as a path. Left out, the ones amflows came with are
            listed instead -- a path is typed, since guessing which files below here are
            flows means reading all of them.
        """
        picked = named or await self.push_screen_wait(Flows(self._flow_named))
        if picked is None:
            return
        chosen = picked if isinstance(picked, str) else picked[0]
        self._flow_named = chosen
        # What each agent runs is asked next, since a flow says for itself how many it
        # drives. Its own worker, because a worker is what may put a screen up and wait.
        self._models = []
        self.action_models()

    @work
    async def action_models(self) -> None:
        """Sets what each of the flow's agents runs, which is what `/models` is for."""
        from amflows.janus.flows import find
        from amflows.janus.runner import drives

        if not self._flow_named:
            self.show("amflows: no flow yet — tab picks one", "red")
            return
        agents = installed()
        if not agents:
            self.show("amflows: no coding agent is installed here", "red")
            return
        try:
            wanted = drives(find(self._flow_named))
        except Exception as why:  # noqa: BLE001 -- a flow that will not load
            self.show(f"amflows: {why}", "red")
            return
        chosen = await self.push_screen_wait(Models(self._flow_named, wanted, agents))
        if chosen is None:
            return
        self._models = list(chosen)
        self.show("[dim]say what to do, and the flow starts on it[/dim]")
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
        self._queued = []

        def take() -> list[str]:
            held, self._queued = self._queued, []
            return held

        for agent in agents:
            agent.watch(self._heard)
            agent.waiting = take  # whichever turn starts next takes what was held
        self._draw()

        def drive() -> int:
            try:
                Runner(path, agents).run(task)
            finally:
                self._agents = []
                with contextlib.suppress(RuntimeError):
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
            self._began[agent.id] = time.monotonic()
        elif event.kind == "ends":
            self._monitor.ends(agent.id)
            # The line opencode closes a message with: a filled square, two spaces, then the
            # parts separated by a middle dot.
            took = time.monotonic() - self._began.pop(agent.id, time.monotonic())
            self.call_from_thread(
                self._part,
                f"   [dim]▣[/dim]  {escape(short(agent.id))}"
                f"{_DOT}{escape(agent.config.model)}{_DOT}{took:.1f}s",
                False,
            )
        elif event.kind == "tool" and self._details:
            icon = _ICONS.get(
                event.text.split()[0].lower() if event.text else "", _UNKNOWN
            )
            self.call_from_thread(
                self._part, f"   [dim]{icon}[/dim] {escape(event.text)}", True
            )
        elif event.kind == "reasoning" and self._thinking:
            self.call_from_thread(
                self._part,
                "\n".join(
                    f"   [dim italic]{line}[/dim italic]"
                    for line in escape(event.text).splitlines()
                ),
                False,
            )
        elif event.kind == "text":
            # Bare, indented three: opencode gives an assistant message no prefix at all.
            self.call_from_thread(
                self._part,
                "\n".join(f"   {line}" for line in escape(event.text).splitlines()),
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
            from amflows.janus import Stopped

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
        """Takes a line that is not a command, which is a task or a word put in.

        With a flow chosen and not yet running, it is the task that starts it -- the way a
        first message to opencode is the thing it is asked to do. With one running, it goes
        to the agent taking its turn.

        Args:
          text: What was said.
        """
        if self._agents:
            self._interject(text)
        elif self._set_up:
            self._said_by_you(text)
            self._flow(["-f", self._flow_named, "-a", ",".join(self._models), text])
        else:
            self.show("amflows: pick a flow first — tab does it", "red")

    @property
    def _set_up(self) -> bool:
        """Whether there is a flow to start and something for each agent to run on."""
        return bool(self._flow_named and self._models)

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
            self._queued.append(text)
            self.show("[dim]   held for the next turn[/dim]")
            return

        def put_in() -> int:
            # Off the event loop: this writes to the agent, and a large paste into a pipe the
            # interface itself is draining would otherwise deadlock the two.
            try:
                sessions[-1].interject(text)
            except (NotImplementedError, RuntimeError) as error:
                self.call_from_thread(self.show, f"amflows: {error}", "red")
            return 0

        self._background(put_in)

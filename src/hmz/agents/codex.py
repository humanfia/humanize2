"""Codex: every turn on the app server, which is the same binary its own client speaks to.

``codex exec`` runs a turn and stops, which leaves nowhere to put a later word: by the time
there is something to say to a turn, the process saying it has gone. ``codex app-server``
holds the thread instead, so a turn is a message on a conversation that is still running --
which is what ``turn/steer`` steers, and what ``thread/goal/set`` sets a goal on. Both are
features of the thread rather than flags of a command line, and neither is a word in a prompt.
"""

# A session and the agent holding it are two halves of one object declared in one
# file, which is what the underscore keeps out of the package rather than out of them.
# pyright: reportPrivateUsage=false

from __future__ import annotations

import contextlib
import itertools
import json
import os
import queue
import signal
import subprocess
import sys
import threading
import weakref
from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar, cast

from .base import AgentBase, SessionBase
from .config import PERMISSIONS, AgentConfig
from .event import Event, Failed, Question, Usage, say
from .hooks import EVERYWHERE, Moment, Occasion

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Mapping, Sequence

    from pydantic import BaseModel

#: `-c` keys this driver may take. They are process configuration of the app server, and
#: none of them is already a field of AgentConfig -- model, effort and permission are asked
#: elsewhere, and a second place for them would be two answers.
_OVERRIDE_KEYS = frozenset({"model_context_window", "model_auto_compact_token_limit"})

#: What the server calls a turn stopping to ask its user something. Every other request it
#: makes of a client is an approval, which an unattended flow does not stop for.
_ASKS = "item/tool/requestUserInput"


@dataclass
class _Running:
    """Which turn of which thread is under way, if one is.

    Written by the turn as the server names it and cleared when it ends, read by whoever wants
    to put a word in: a steer must name the thread and the turn it is for, and the server
    refuses one naming a turn that has already moved on.
    """

    thread: str | None = None
    turn: str | None = None
    #: The session's own book of words put into this turn, asked whenever one comes back
    #: around: the server holds every session of the agent, so the turn loop has no other way
    #: to know whose word it is reading.
    took: Callable[[str], str | None] | None = None
    #: Told what each request of this turn cost as the server says it, for the same reason:
    #: the server counts every thread it holds, and only the session knows whose this is.
    spends: Callable[[Usage], None] | None = None


#: What the server calls each of the ways it asks a client to approve something. All three are
#: answered where the agent is allowed to ask at all, and none of them ever arrives otherwise:
#: an approval policy of `never` is the server not asking.
_APPROVALS = (
    "item/commandExecution/requestApproval",
    "item/fileChange/requestApproval",
    "item/permissions/requestApproval",
)

#: What Codex is run under at each rung of the ladder, sent with every turn: a thread picked
#: back up does not carry the settings it was started with. Codex is the one backend here with
#: a sandbox of its own, so its rungs are the real thing rather than an approximation of one --
#: and the only rung that lets it ask for more is `auto`, which is the rung that means the
#: asking is granted. Everywhere else it is never asked, because a turn waiting on an approval
#: nobody is there to give is a flow that has stopped.
_PERMITTED = {
    "read-only": {"approvalPolicy": "never", "sandbox": "read-only"},
    "workspace-write": {"approvalPolicy": "never", "sandbox": "workspace-write"},
    "auto": {"approvalPolicy": "on-request", "sandbox": "workspace-write"},
    "bypass": {"approvalPolicy": "never", "sandbox": "danger-full-access"},
}

#: What each kind of token is called in the totals the server states. Cached input is counted
#: inside the input rather than beside it, so it is not a kind of its own here: adding it would
#: be counting the same tokens twice.
_KINDS = {"input": "inputTokens", "output": "outputTokens"}


def unattended(permission: str, service_tier: str = "default") -> dict[str, Any]:
    """What a turn is started with, at the rung the agent was configured for.

    Args:
      permission: One of :data:`hmz.agents.config.PERMISSIONS`.
      service_tier: The common provider service tier requested for this agent.

    Returns:
      The settings to send with the turn, and with the thread it runs on.
    """
    service = "priority" if service_tier == "fast" else "default"
    return {"serviceTier": service} | _PERMITTED.get(permission, _PERMITTED["bypass"])


#: What a Codex somebody else settled the rules for says when it will not run at the rung it
#: was asked for. An installation can be given requirements -- an enterprise policy delivered
#: with the account, a `requirements.toml` the platform the machine belongs to put there -- and
#: one that forbids the sandbox a rung is refuses the whole call rather than running it
#: tighter: `approval_policy = "never"` cannot be used because requirements do not allow
#: `sandbox_mode = "danger-full-access"`. Which is every turn of an agent nobody was asked
#: about failing on such a machine, since `bypass` is what one runs at.
_FORBIDDEN = "requirements do not allow"


def _rung(params: Mapping[str, Any]) -> str | None:
    """Which rung of the ladder a call's parameters are asking for.

    Args:
      params: What the call was made with.

    Returns:
      The rung they name, or None for a call that says nothing about what the agent may do.
    """
    return next(
        (
            rung
            for rung, settings in _PERMITTED.items()
            if all(params.get(key) == value for key, value in settings.items())
        ),
        None,
    )


def _tighter(permission: str) -> str:
    """The rung below one this machine's Codex will not take.

    Args:
      permission: The rung that was refused.

    Returns:
      The next rung down, and "" for the bottom of the ladder -- where a refusal is a machine
      that will not run an agent at all rather than one to be met halfway.
    """
    at = PERMISSIONS.index(permission) if permission in PERMISSIONS else 0
    return PERMISSIONS[at - 1] if at else ""


#: How long a server being taken down is given to go before it is left to the operating system,
#: and how long an idle thread is given to carry a goal on by itself before the goal is over.
_STOP_SECONDS = 5.0
_QUIET_SECONDS = 60.0

#: The items that are the agent talking rather than the agent doing something. They are shown
#: as they complete, there being no words in one before that; everything else is shown as it
#: starts, since watching a thing run is the point of showing it at all.
_TALKING = ("agentMessage", "reasoning")

#: The items that are not the agent working at all: what it was told, and what a hook dressed
#: that up with. Showing one would be showing the prompt back.
_OURS = ("userMessage", "hookPrompt")

#: What an item says about itself that says nothing about what the agent did: an id names it,
#: a status says how far along it is, and neither is worth a row of a transcript.
_NAMING = ("id", "itemId", "status", "threadId", "turnId", "type")

#: Where the words are in each kind of item, read off the schema the server generates for its
#: own protocol -- the field that says what the agent reached for, rather than the first one it
#: happens to serialise. An item of a kind that is not here is shown under whatever it does
#: name itself with: the server grows kinds, and a new one is still work being done.
_ABOUT = {
    "collabAgentToolCall": "tool",
    "commandExecution": "command",
    "dynamicToolCall": "tool",
    "fileChange": "changes",
    "imageGeneration": "revisedPrompt",
    "imageView": "path",
    "mcpToolCall": "tool",
    "plan": "text",
    "subAgentActivity": "agentPath",
    "webSearch": "query",
}

#: What the items every other backend also has are called there, so that one flow's transcript
#: reads as one transcript -- and so an interface picks the icon it picks for that tool anywhere
#: else. An item that is not here is shown under the name the server gave it.
_CALLED = {
    "collabAgentToolCall": "Task",
    "commandExecution": "Bash",
    "dynamicToolCall": "Task",
    "fileChange": "Edit",
    "imageView": "Read",
    "mcpToolCall": "Task",
    "webSearch": "WebSearch",
}


class _AppServer:
    """A `codex app-server` of our own, spoken to in JSON-RPC over its stdio."""

    def __init__(self, argv: list[str], env: Mapping[str, str] | None = None) -> None:
        """Starts the server and introduces this flow to it.

        Args:
          argv: The command that starts it, already wrapped for wherever its work is to land.
          env: The whole environment to start it in, which is this process's own less what the
            agent's provider hushes and plus what it sets, or None to inherit this one. The
            server is the agent's, so its account is the agent's too.

        Raises:
          subprocess.CalledProcessError: If it will not be introduced to, which is every turn
            it would have been asked for failing at the first one instead.
        """
        self._argv = argv
        #: Whose turns run here, so that what is teed can be what nobody is watching. Held
        #: weakly: the agent holds the server, and the finalizer that takes the server down is
        #: the agent's -- so a server holding its agent back would be an agent nothing could
        #: collect, and a `codex app-server` nothing would ever reap.
        self._held: list[weakref.ref[AgentBase]] = []
        self._stopping = threading.Lock()
        self._stopped = False
        self._proc = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            # Its log is nobody's: what a flow watches is the agent, which comes over stdout.
            stderr=subprocess.DEVNULL,
            encoding="utf-8",
            errors="replace",
            env=dict(env) if env else None,
            start_new_session=os.name != "nt",
        )
        self._pending = itertools.count(1)
        self._writing = threading.Lock()  # a line is written whole or not at all
        #: What each rung asked for actually runs at here, which is itself until this machine's
        #: Codex has refused it. Written the once, by the call that found out.
        self._instead: dict[str, str] = {}
        #: What each thread has spent so far, by kind, as the server counts it: a running
        #: total, so what one turn cost is the rise across it.
        self._counted: dict[str, Counter[str]] = {}
        self._messages: queue.Queue[dict[str, Any] | None] = queue.Queue()
        # Read from a thread of its own, so that a turn can wait on the server for a while
        # rather than only for as long as it takes.
        threading.Thread(target=self._pump, daemon=True).start()
        # One stream, shared by every session of the agent: a call is a write and the reads
        # up to its answer, and two of them interleaved would each take the other's messages.
        self._speaking = threading.Lock()
        # What this client calls itself on the wire, which the server records against every
        # session it opens. The project's own name, so that a thread found in Codex's logs
        # says what drove it rather than what the layer driving it was once called.
        self.call("initialize", {"clientInfo": {"name": "humanize", "version": "0"}})
        self._write({"jsonrpc": "2.0", "method": "initialized", "params": {}})

    @property
    def _agents(self) -> list[AgentBase]:
        """Whose turns run here, and still exist: an agent that has gone is not one to tell."""
        held = [one() for one in self._held]
        return [one for one in held if one is not None]

    def permitted(self, permission: str, service_tier: str) -> dict[str, Any]:
        """What a call of this server is told an agent at that rung may do.

        The rung asked for, until this machine's Codex has refused it: an installation given
        requirements that forbid the sandbox a rung is takes none of that rung's calls, and
        what it will take instead is remembered here -- so one refusal is the whole cost of
        finding out, rather than one per turn.

        Args:
          permission: One of :data:`hmz.agents.config.PERMISSIONS`.
          service_tier: The common provider service tier requested for this agent.

        Returns:
          The settings to send, at the loosest rung this Codex will take of the one asked for.
        """
        return unattended(self._instead.get(permission, permission), service_tier)

    def call(self, method: str, params: dict[str, Any]) -> Any:
        """Makes one call and reads until it is answered.

        A call naming a rung this machine's Codex will not take is made again a rung down: an
        installation whose requirements forbid full access refuses `bypass` outright, and the
        rung below is `auto` -- the same freedom with the asking turned back on, which this
        client grants. So a flow nobody was asked about goes on running unattended there.

        Args:
          method: The method to call.
          params: What to call it with.

        Returns:
          What the server answered with.

        Raises:
          subprocess.CalledProcessError: If it refused the call for anything but the rung it
            named, or stopped before answering.
        """
        while True:
            try:
                return self._called(method, params)
            except Failed as refused:
                if (instead := self._stepped(params, refused)) is None:
                    raise
                params = instead

    def _stepped(
        self, params: dict[str, Any], refused: Failed
    ) -> dict[str, Any] | None:
        """The same call a rung down, where Codex refused the rung this one named.

        Args:
          params: What the call was made with.
          refused: What the server said about it.

        Returns:
          Those parameters at the next rung down, or None where the refusal was about
          something else or there is no rung left below the one it named.
        """
        if _FORBIDDEN not in str(refused.stderr or ""):
            return None
        asked = _rung(params)
        if asked is None or not (instead := _tighter(asked)):
            return None
        # Every rung that was already running at the refused one runs at this one now: a
        # ladder walked down twice must not leave the first step pointing at the second.
        for rung, taken in list(self._instead.items()):
            if taken == asked:
                self._instead[rung] = instead
        self._instead[asked] = instead
        if not self._watched():
            # Where a turn's own words go when nothing is watching the agent, which is the one
            # place a line of ours belongs: something watching owns the screen.
            say(
                f"codex: this machine will not run an agent at {asked}, so it runs at"
                f" {instead}, where what it asks for is granted",
                sys.stderr,
            )
        return params | _PERMITTED[instead]

    def _called(self, method: str, params: dict[str, Any]) -> Any:
        """Makes that one call, exactly as it stands, and reads until it is answered.

        Args:
          method: The method to call.
          params: What to call it with.

        Returns:
          What the server answered with.

        Raises:
          subprocess.CalledProcessError: If it refused the call, or stopped before answering.
        """
        with self._speaking:
            ident = next(self._pending)
            self._write(
                {"jsonrpc": "2.0", "id": ident, "method": method, "params": params}
            )
            # An answer is a message with no method of its own: the server asks things of us
            # over the same stream, numbering its own calls, and one of those is not this one.
            while (message := self._read()) is None or not (
                message.get("id") == ident and "method" not in message
            ):
                pass
            return self._answer(message, "")

    def pursue(self, params: dict[str, Any]) -> str:
        """Starts a turn on a thread that has a goal, and reads until the goal is done with it.

        A goal is as many turns of the model as the objective takes, and Codex starts each one
        itself once the thread falls idle -- so an idle thread is where a goal carries on, not
        where it ends. What ends it is the goal leaving the state it was set in: met, or given
        up on for a budget it ran past. The thread falling idle after that is the last turn
        finishing what it was saying, which is the answer this returns.

        A turn can also end without the goal ever saying anything -- one refused by the model,
        or stopped before it began -- and Codex then carries nothing on. So an idle thread is
        waited on for a while rather than forever, and a goal that has gone quiet for that
        long is over whatever it still calls itself: a flow may lose a turn to this, and must
        not lose the loop it was running.

        Args:
          params: What to start the first turn with.

        Returns:
          The last thing the agent said, stripped.

        Raises:
          subprocess.CalledProcessError: If the turn was refused, or the server stopped.
        """
        with self._speaking:
            ident = next(self._pending)
            self._write(
                {
                    "jsonrpc": "2.0",
                    "id": ident,
                    "method": "turn/start",
                    "params": params,
                }
            )
            pursuing = (
                True  # a turn is only started here for a goal, which is set active
            )
            idle = False
            said = ""
            while (message := self._read(_QUIET_SECONDS if idle else None)) is not None:
                if message.get("id") == ident and "method" not in message:
                    self._answer(message, said)
                match message.get("method"):
                    case "item/completed":
                        item = message["params"]["item"]
                        if item.get("type") == "agentMessage":
                            said = item["text"]
                    case "thread/goal/updated":
                        pursuing = message["params"]["goal"]["status"] == "active"
                    case "thread/goal/cleared":
                        pursuing = False
                    case "thread/status/changed":
                        idle = message["params"]["status"]["type"] == "idle"
                    case _:  # every other method the server has is not this loop's
                        pass
                if idle and not pursuing:
                    break
            say(said, sys.stdout)  # where `codex exec` would have put the answer
            return said.strip()

    def turn(self, params: dict[str, Any], running: _Running) -> Iterator[Event]:
        """Runs one turn on a thread and says what the agent says as it says it.

        Args:
          params: What to start the turn with, naming the thread it is on.
          running: Told the turn's own id as the server names it, and told again when the turn
            is over -- which is what lets a word put in mid-turn say which turn it is for.

        Yields:
          What the agent said, and the answer it ended on.

        Raises:
          subprocess.CalledProcessError: If the turn was refused, failed, or was interrupted,
            or if the server stopped.
        """
        thread = params["threadId"]
        with self._speaking:
            ident = next(self._pending)
            self._write(
                {
                    "jsonrpc": "2.0",
                    "id": ident,
                    "method": "turn/start",
                    "params": params,
                }
            )
            said = ""
            # A thread falls idle the moment it is opened, and that idle is still in the
            # stream when a turn starts reading. A turn has not ended until it has begun.
            begun = False
            failed: str | None = None
            before = Counter(self._counted.get(thread) or Counter())
            costing = Usage()
            started: set[Any] = set()  # the items this turn has already shown
            try:
                while (message := self._read()) is not None:
                    if message.get("id") == ident and "method" not in message:
                        self._answer(message, said)
                    told: dict[str, Any] = message.get("params") or {}
                    # One server holds every session of the agent, and a turn one of them
                    # abandoned still says so on this stream. What is not this thread's is
                    # not this turn's.
                    if told.get("threadId") not in (None, thread):
                        continue
                    named_turn: dict[str, Any] = told.get("turn") or {}
                    if turn := told.get("turnId") or named_turn.get("id"):
                        running.turn = str(turn)
                        begun = True
                    match message.get("method"):
                        case "item/started" | "item/completed":
                            item: dict[str, Any] = told.get("item") or {}
                            kind = str(item.get("type") or "")
                            done = message["method"] == "item/completed"
                            # Shown once apiece: as it starts, a thing worth showing being a
                            # thing worth watching run, and otherwise as it completes -- the
                            # server need not have started everything it finishes. An item
                            # that names itself with nothing is not the item shown before it,
                            # so it is shown rather than taken for one already seen.
                            marked = item.get("id")
                            twice = done and marked is not None and marked in started
                            if marked is not None:
                                started.add(marked)
                            if kind == "userMessage" and not done and running.took:
                                # A word put into this turn, come back around: the server
                                # says so once the model has it, under the name it was sent
                                # with. Everything else on a `userMessage` is the turn's own
                                # prompt, which nobody is waiting to hear about.
                                words = running.took(str(item.get("clientId") or ""))
                                if words is not None:
                                    yield Event(kind="took", text=words)
                            elif kind == "agentMessage" and done:
                                said = str(item.get("text") or "")
                                yield Event(kind="text", text=said)
                            elif kind == "reasoning" and done:
                                # Reasoning is a list of parts rather than one text.
                                parts: list[Any] = (
                                    item.get("content") or item.get("summary") or []
                                )
                                thought = " ".join(str(part) for part in parts)
                                if thought.strip():
                                    yield Event(kind="reasoning", text=thought)
                            elif kind not in (*_TALKING, *_OURS) and not twice:
                                # Every other item is the agent reaching for something, and
                                # every one of them is shown: a turn spends its minutes here,
                                # and an item this has never heard of is still work being done
                                # rather than a silence to sit through.
                                named = item.get(_ABOUT.get(kind, ""))
                                if isinstance(named, list):
                                    # One entry per file changed: the paths are the words.
                                    listed = cast("list[Any]", named)
                                    named = " ".join(
                                        str(
                                            cast("dict[str, Any]", part).get(
                                                "path", part
                                            )
                                        )
                                        if isinstance(part, dict)
                                        else str(part)
                                        for part in listed
                                    )
                                about = str(named or "") or next(
                                    (
                                        value
                                        for name, value in item.items()
                                        if name not in _NAMING
                                        and isinstance(value, str)
                                        and value.strip()
                                    ),
                                    "",
                                )
                                yield Event(
                                    kind="tool",
                                    text=f"{_CALLED.get(kind, kind)} {about}".strip()[
                                        :120
                                    ],
                                )
                        case "thread/tokenUsage/updated":
                            # Sent as the turn spends it. `total` is the thread, every turn of
                            # it; `last` is the one request that just came back. Cached input
                            # is counted inside the input rather than beside it, so the input
                            # the server states is the whole of what went in -- and the two
                            # kinds together are the whole of what crossed the wire.
                            counted: dict[str, Any] = told.get("tokenUsage") or {}
                            usage: dict[str, Any] = counted.get("total") or {}
                            held = Counter(
                                {
                                    kind: int(usage.get(named) or 0)
                                    for kind, named in _KINDS.items()
                                    if usage.get(named)
                                }
                            )
                            if sum(held.values()):
                                risen = Usage(
                                    {
                                        kind: tokens
                                        for kind in set(held) | set(before)
                                        if (
                                            tokens := held[kind]
                                            - (self._counted.get(thread) or Counter())[
                                                kind
                                            ]
                                        )
                                        > 0
                                    }
                                )
                                self._counted[thread] = held
                                costing = costing + risen
                                if running.spends is not None:
                                    # As the turn spends it rather than once it is over: a
                                    # turn is minutes long, and a rate that only moved at the
                                    # end of one would stand still for all of them.
                                    running.spends(risen)
                        case "error":
                            failed = json.dumps(told.get("error"))
                        case "turn/completed":
                            turn_said = cast("dict[str, Any]", told.get("turn") or {})
                            if turn_said.get("status") not in (None, "completed"):
                                # A failed or interrupted turn is complete even when the
                                # server does not follow it with a separate idle notification.
                                failed = json.dumps(
                                    turn_said.get("error") or turn_said.get("status")
                                )
                                break
                            # Codex reports a reconnect attempt as an error notification even
                            # when a later sampling request completes this same turn.
                            failed = None
                        case "thread/status/changed" if (
                            begun and told["status"]["type"] == "idle"
                        ):
                            break
                        case _:  # the rest of the stream is not this turn's to show
                            pass
            finally:
                running.turn = None
            if failed is not None:
                raise Failed(1, self._argv, said, failed)
            # What the turn cost is the rise across it, charged to the model it ran on: the
            # server counts the thread, and a thread is every turn this session has taken.
            spent = sum((self._counted.get(thread) or Counter()).values()) - sum(
                before.values()
            )
            yield Event(
                kind="result",
                text=said.strip(),
                tokens={str(params.get("model") or "codex"): spent}
                if spent > 0
                else {},
                spent=costing,
            )

    def steer(self, thread: str, turn: str, text: str, ticket: str) -> None:
        """Says something to a turn that is already running.

        Written straight out rather than called: the turn holds the stream while it reads, and
        what the server answers a steer with is picked up by that same reader and passed over.

        Args:
          thread: The thread the turn is on.
          turn: The turn to steer, which the server refuses to confuse with any other.
          text: What to say.
          ticket: What the server is to name it by when it says the turn has it, which comes
            back on the `userMessage` item as its `clientId`.
        """
        self._write(
            {
                "jsonrpc": "2.0",
                "id": next(self._pending),
                "method": "turn/steer",
                "params": {
                    "threadId": thread,
                    "input": [{"type": "text", "text": text}],
                    "expectedTurnId": turn,
                    "clientUserMessageId": ticket,
                },
            }
        )

    def stop(self) -> None:
        """Takes the server and its children down, leaving its threads on disk."""
        with self._stopping:
            if self._stopped:
                return
            self._stopped = True
            if os.name == "nt":
                if self._proc.poll() is None:
                    self._proc.terminate()
                    try:
                        self._proc.wait(timeout=_STOP_SECONDS)
                    except subprocess.TimeoutExpired:
                        self._proc.kill()
                # Reaped rather than left: a flow that cycles through agents would otherwise
                # gather a zombie for each one it let go of.
                self._proc.wait()
                return

            # Provider wrappers and Codex share this dedicated group. Taking down the group
            # prevents a stopped flow from leaving either wrapper or server behind.
            with contextlib.suppress(ProcessLookupError):
                os.killpg(self._proc.pid, signal.SIGTERM)
            with contextlib.suppress(subprocess.TimeoutExpired):
                self._proc.wait(timeout=_STOP_SECONDS)
            with contextlib.suppress(ProcessLookupError):
                os.killpg(self._proc.pid, signal.SIGKILL)
            self._proc.wait()

    def _write(self, message: dict[str, Any]) -> None:
        """Puts one JSON-RPC message on the server's stdin.

        Args:
          message: The message to send.

        Raises:
          subprocess.CalledProcessError: If the server has stopped reading.
        """
        assert self._proc.stdin is not None  # noqa: S101
        try:
            with self._writing:
                self._proc.stdin.write(json.dumps(message) + "\n")
                self._proc.stdin.flush()
        except OSError as gone:
            raise Failed(1, self._argv, "", str(gone)) from gone

    def _pump(self) -> None:
        """Reads the server's whole stream, teeing the agent's words to ours as they arrive."""
        assert self._proc.stdout is not None  # noqa: S101
        for line in self._proc.stdout:
            message: dict[str, Any] = json.loads(line)
            if "id" in message and "method" in message:
                # Something asked of us. A request left unanswered stalls the turn holding the
                # stream -- and with it every session of the agent -- so every one of them is
                # answered. The turn asking its user something is put to that user; the rest
                # are approvals, and refusing is not the answer they wanted but is an answer.
                if message["method"] == _ASKS:
                    # On a thread of its own: asking waits on a person, and this one has the
                    # whole server's stream to keep reading meanwhile.
                    threading.Thread(
                        target=self._ask, args=(message,), daemon=True
                    ).start()
                    continue
                if message["method"] in _APPROVALS:
                    # On a thread of its own too: a hook is the flow's own code, and one that
                    # takes its time must not stop the stream every session is read from.
                    threading.Thread(
                        target=self._approve, args=(message,), daemon=True
                    ).start()
                    continue
                self._write(
                    {
                        "jsonrpc": "2.0",
                        "id": message["id"],
                        "error": {"code": -32601, "message": "a flow answers nothing"},
                    }
                )
                continue
            if (
                message.get("method") == "item/agentMessage/delta"
                and not self._watched()
            ):
                # So that a goal running for an hour stays as watchable as a turn that prints.
                say(message["params"]["delta"], sys.stderr, end="")
            self._messages.put(message)
        self._messages.put(None)  # it has stopped, and nothing more is coming

    def _approve(self, message: dict[str, Any]) -> None:
        """Grants something the agent asked to be allowed to do, unless a hook refuses.

        The server only asks at all at the rung that means the asking is granted, so this
        answers yes -- and the one place a refusal actually stops an agent doing something is
        the moment the backend waits on, which is this one. A hook hung on
        `PERMISSION_REQUEST` gets it first and may say no.

        The three requests take two shapes of answer: a decision for a command and for a file
        change, and the permissions themselves for a request to widen the sandbox -- where
        granting is handing back the profile it asked for, and refusing is handing back none.

        Args:
          message: The request, as read.
        """
        told: dict[str, Any] = message.get("params") or {}
        wanted: dict[str, Any] = told.get("permissions") or {}
        about = next(
            (
                str(value)
                for name, value in told.items()
                if name not in _NAMING and isinstance(value, str) and value.strip()
            ),
            "",
        )
        asking = (
            self._agents[0].hooks.fire(
                Occasion(
                    moment=Moment.PERMISSION_REQUEST,
                    agent=self._agents[0].id,
                    session=str(told.get("threadId") or ""),
                    tool=str(message["method"]).rsplit("/", 2)[-2],
                    about=about,
                    input=told,
                )
            )
            if self._agents
            else None
        )
        refused = asking is not None and asking.refused
        if message["method"] == _APPROVALS[2]:
            answer: dict[str, Any] = (
                {"permissions": {}}
                if refused
                else {"permissions": wanted, "scope": "turn"}
            )
        else:
            answer = {"decision": "decline" if refused else "accept"}
        self._write({"jsonrpc": "2.0", "id": message["id"], "result": answer})

    def _ask(self, message: dict[str, Any]) -> None:
        """Puts the questions a turn stopped on to whoever is driving the agent.

        The server takes an answer per question, keyed by the id it gave that question, and
        an answer is a list because a question may take more than one of its options. A
        question nobody is there to answer is answered with nothing, which the tool reads as
        having been skipped -- the turn goes on rather than waiting for a reply that is not
        coming.

        Args:
          message: The `item/tool/requestUserInput` request, as read.
        """
        told: dict[str, Any] = message.get("params") or {}
        answers: dict[str, dict[str, list[str]]] = {}
        questions: list[Any] = told.get("questions") or []
        for question in questions:
            labelled: list[str] = []
            for raw in cast("list[Any]", question.get("options") or []):
                option = cast("dict[str, Any]", raw)
                if isinstance(raw, dict) and option.get("label"):
                    labelled.append(str(option["label"]))
            offered = tuple(labelled)
            wanted = str(question.get("question") or question.get("header") or "")
            answer = (
                self._agents[0].asked(Question(text=wanted, options=offered))
                if (self._agents)
                else None
            )
            answers[str(question.get("id"))] = {"answers": [answer] if answer else []}
        self._write(
            {"jsonrpc": "2.0", "id": message["id"], "result": {"answers": answers}}
        )

    def _watched(self) -> bool:
        """Whether something is watching the agents this server runs turns for.

        A watcher is given each message whole as the turn says it, so teeing the pieces as
        well would show every message twice.

        Returns:
          Whether anything is watching.
        """
        return any(agent._watchers for agent in self._agents)

    def _read(self, timeout: float | None = None) -> dict[str, Any] | None:
        """Takes the next message the server sent.

        Args:
          timeout: How long to wait for one, or None to wait for as long as it takes.

        Returns:
          The message, or None if none arrived in the time given.

        Raises:
          subprocess.CalledProcessError: If the server stopped mid-turn.
        """
        try:
            message = self._messages.get(timeout=timeout)
        except queue.Empty:
            return None
        if message is None:
            self._messages.put(None)  # so that every later read finds it stopped too
            raise Failed(
                self._proc.wait(), self._argv, "", "app server stopped mid-turn"
            )
        return message

    def _answer(self, message: dict[str, Any], said: str) -> Any:
        """Unwraps one answer.

        Args:
          message: The answer read.
          said: Whatever the agent had said by then, which a failure carries as its output.

        Returns:
          The result the server sent.

        Raises:
          subprocess.CalledProcessError: If the server sent an error instead.
        """
        if (refused := message.get("error")) is not None:
            raise Failed(1, self._argv, said, json.dumps(refused))
        return message.get("result")


def _overrides(given: Sequence[tuple[str, str]]) -> tuple[tuple[str, str], ...]:
    """The app-server `-c` pairs, or a reason they cannot be taken.

    Args:
      given: What was asked for, as ``(key, value)`` in the order it was written.

    Returns:
      The same pairs, stripped, in that order.

    Raises:
      ValueError: If a key is not one of :data:`_OVERRIDE_KEYS`, is repeated, is not a
        positive integer, or the compact limit is not below the context window.
    """
    held: list[tuple[str, str]] = []
    seen: set[str] = set()
    for key, value in given:
        name, said = key.strip(), value.strip()
        if name not in _OVERRIDE_KEYS:
            raise ValueError(
                f"{name} is not a Codex override; expected "
                f"{', '.join(sorted(_OVERRIDE_KEYS))}"
            )
        if name in seen:
            raise ValueError(f"{name} was given twice")
        if not said.isdigit() or int(said) < 1:
            raise ValueError(f"{name} must be a positive integer, not {value!r}")
        seen.add(name)
        held.append((name, said))
    window = next(
        (int(said) for name, said in held if name == "model_context_window"), None
    )
    compact = next(
        (int(said) for name, said in held if name == "model_auto_compact_token_limit"),
        None,
    )
    if window is not None and compact is not None and compact >= window:
        raise ValueError(
            "model_auto_compact_token_limit must be below model_context_window"
        )
    return tuple(held)


@dataclass(frozen=True, kw_only=True)
class CodexAgentConfig(AgentConfig):
    """What Codex is configured with: the common model and effort, and its app-server `-c`.

    `overrides` is only the keys Codex treats as process configuration and that
    :class:`AgentConfig` does not already name. They are this agent's, so two Codex agents
    of one flow may take different windows, and neither writes the user's `config.toml`.
    """

    overrides: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        super().__post_init__()
        object.__setattr__(self, "overrides", _overrides(self.overrides))


class CodexSession(SessionBase):
    """A Codex conversation, held as a thread by the app server the agent runs.

    Every turn goes to the server rather than to a `codex exec` of its own, which is what
    leaves the turn somewhere to be talked to: the thread is still there, still running, so
    :meth:`interject` steers the turn under way instead of waiting for the next one.
    """

    _agent: CodexAgent  # every turn is run on the app server this agent holds

    #: `outputSchema` is the server's own: a turn started with one is constrained to answer
    #: in it, so the shape is asked for where the turn is started rather than in the prompt.
    shapes: ClassVar[bool] = True

    def __init__(
        self, agent: AgentBase, cwd: str | os.PathLike[str] | None = None
    ) -> None:
        """Initializes a session holding no thread yet.

        Args:
          agent: The agent whose config every turn of this session runs at.
          cwd: The directory this conversation works in, as for `SessionBase`.
        """
        super().__init__(agent, cwd)
        #: The turn under way, which is what a word put in has to name.
        self._running = _Running()

    @property
    def named(self) -> str | None:
        """The thread this session is, which the server names before the turn starts."""
        return self._id or self._running.thread

    def _stream(
        self, prompt: str, *, schema: type[BaseModel] | None = None
    ) -> Iterator[Event]:
        """Sends one turn to the server, saying what the agent says as it says it.

        Args:
          prompt: The input prompt for this turn.
          schema: The shape to answer in, which is a setting of the turn here: the server
            takes it as `outputSchema` and holds the last message to it.

        Yields:
          What the agent said, in the order it said it.

        Raises:
          subprocess.CalledProcessError: If the turn was refused, or the server stopped.
        """
        with self._lock:  # a conversation is a sequence: one turn at a time
            thread = self._thread()
            # Known before the turn starts, so a word put in has a thread to name even though
            # the session is only opened once the turn has landed. The book goes with it: the
            # server reads every session's stream, and only this one knows what it put in.
            self._running.thread = thread
            self._running.took = self.took
            self._running.spends = self._spends
            said = ""
            spent: Mapping[str, int] = {}
            costing = Usage()
            for event in self._agent.server.turn(
                {
                    "threadId": thread,
                    "input": [{"type": "text", "text": prompt}],
                    "model": self._agent.config.model,
                    "effort": self.effort,
                    **(
                        {"outputSchema": schema.model_json_schema()}
                        if schema is not None
                        else {}
                    ),
                    **self._agent.server.permitted(
                        self._agent.config.permission,
                        self._agent.config.service_tier,
                    ),
                },
                self._running,
            ):
                if event.kind == "result":
                    said, spent, costing = event.text, event.tokens, event.spent
                    continue
                if not self._agent._watchers:
                    # On stderr, where every other backend puts its progress: a turn nobody
                    # can watch is a flow that reads as hung for as long as the turn takes.
                    # Something watching the agent shows the turn itself, and would then be
                    # showing it twice.
                    say(event.text, sys.stderr)
                yield event
            if not self._agent._watchers:
                # Where `codex exec` would have put the answer. Something watching the agent
                # has had it already, as the turn said it.
                say(said, sys.stdout)
            self._adopt(thread)  # a turn has landed, so the session is open
            yield Event(kind="result", text=said, tokens=spent, spent=costing)

    def interject(self, text: str) -> None:
        """Steers the turn under way, which the server takes into the turn it is running.

        Args:
          text: What to say to the agent.

        The server takes it and answers at once, and that answer is not the agent having
        heard: it says only that the word is bound to the turn. What says the model has it is
        the `userMessage` item the turn plays back, which is a `took` event.

        Raises:
          RuntimeError: If no turn is running, so there is none for the server to steer.
        """
        running = self._running
        if running.turn is None or running.thread is None:
            raise RuntimeError("no turn is running to be talked to")
        ticket = self.steering(text)
        try:
            self._agent.server.steer(running.thread, running.turn, text, ticket)
        except BaseException:
            self.took(ticket)
            raise

    def _thread(self) -> str:
        """The thread this session is, started or picked back up as needed.

        Returns:
          The thread's id, which is also the session's.
        """
        server = self._agent.server
        rung = server.permitted(
            self._agent.config.permission, self._agent.config.service_tier
        )
        if (thread := self._id) is None:
            return str(
                server.call(
                    "thread/start",
                    {
                        "cwd": self._workspace(),
                        "model": self._agent.config.model,
                        **rung,
                    },
                )["thread"]["id"]
            )
        # Said again on the way back in: a thread picked up is picked up under the settings it
        # was left with, and this session's rung is what its agent is configured for now.
        server.call("thread/resume", {"threadId": thread, **rung})
        return thread

    def _pursue(self, objective: str) -> str:
        """Runs the turn under a goal of Codex's own, which its runtime steers until it is met.

        Args:
          objective: What the agent is to have achieved before it stops.

        Returns:
          The agent's response once it stops, stripped.

        Raises:
          subprocess.CalledProcessError: If any of the calls a goal is made of is refused,
            leaving the session unopened so that the next call retries it.
        """
        with self._lock:  # a conversation is a sequence: one turn at a time
            server = self._agent.server
            config = self._agent.config
            thread = self._thread()
            server.call("thread/goal/set", {"threadId": thread, "objective": objective})
            answer = server.pursue(
                {
                    "threadId": thread,
                    "input": [{"type": "text", "text": objective}],
                    "model": config.model,
                    "effort": self.effort,
                    **server.permitted(config.permission, config.service_tier),
                }
            )
            self._adopt(thread)
            return answer


class CodexAgent(AgentBase):
    """Codex, driven over the app server so that a turn can be steered while it runs.

    Every moment a turn passes through, and one more: at the rung where the agent may ask for
    more than it has, the server asks and waits for the answer -- so that is the one place a
    hook here can say no to something and have the agent hear it. At every other rung it is
    never asked, and a hook hung on that moment never fires.
    """

    moments: ClassVar[frozenset[Moment]] = EVERYWHERE | {Moment.PERMISSION_REQUEST}

    service_tiers = ("default", "fast")

    #: codex keeps itself going toward an objective, which is what `pursue` reaches for.
    pursues: ClassVar[bool] = True

    def __init__(self, config: AgentConfig, *, name: str | None = None) -> None:
        """Initializes an agent whose app server is not running yet.

        Args:
          config: The model and effort every session of this agent runs at.
          name: What to call this agent, defaulting to one nothing else answers to.
        """
        super().__init__(config, name=name)
        self._server: _AppServer | None = None
        #: Which account the server up now was started as, so that an agent which has fallen
        #: back starts another rather than going on talking to one signed in as somebody else.
        self._server_as = ""
        self._serving = threading.Lock()

    def disable_goals(self) -> None:
        """Disables both ``pursue`` and Codex's goal tools for this agent.

        The feature is selected when the app server starts, so a running server cannot be
        changed underneath sessions it already holds.

        Raises:
          RuntimeError: If this agent's app server has already started with goals enabled.
        """
        with self._serving:
            if self._server is not None and self.goals_enabled:
                raise RuntimeError(
                    f"{self.id}: goals must be disabled before its first turn"
                )
            super().disable_goals()

    @property
    def server(self) -> _AppServer:
        """The app server this agent's turns run on, started the first time one is needed.

        One per agent rather than one per session, so a flow that drops a session a turn does
        not start a server a turn; it is taken down when the agent is collected, or at exit for
        one held to the end. An anchored agent starts it through coganchor, which leaves the
        server here, holding the thread, and its work on the target -- the same split ``codex
        exec`` runs under. A flow that never sets a goal never starts one.
        """
        with (
            self._serving
        ):  # two sessions of one agent share the server rather than start two
            if self._server is not None and self._server_as != self.node().name:
                # Started as an account this agent has since left. Let go of rather than
                # taken down: a turn on another thread may still be talking to it, and it is
                # stopped by its own finalizer when the agent is collected either way.
                self._server, self._server_as = None, ""
            if self._server is None:
                argv = ["codex", "app-server"]
                if not self.goals_enabled:
                    # Per server rather than in config, so this flow changes no other Codex
                    # session belonging to the user.
                    argv += ["--disable", "goals"]
                # Said in both directions rather than only when it is off: Codex searches
                # nothing until it is asked to, so an agent that may search the web has to
                # say so here for `web_search` to mean on every backend what it says.
                argv += [
                    "-c",
                    f"tools.web_search={'true' if self.config.web_search else 'false'}",
                ]
                argv += ["--stdio"]
                for key, value in getattr(self.config, "overrides", ()):
                    # The same `-c` Codex's own client takes, scoped to this server: a
                    # window asked for here is this agent's, and the user's config.toml is
                    # left exactly as it was.
                    argv += ["-c", f"{key}={value}"]
                # Read before the environment is built out of it: a fallback landing
                # between the two reads would name the account this server is *not* signed
                # into, and a server that believes it is already elsewhere is one nothing ever
                # starts again.
                account = self.node().name
                self._server = _AppServer(self.spawned(argv), self._environ())
                self._server_as = account
                self._server._held.append(weakref.ref(self))
                # Held by the finalizer alone, which is what takes the server down: when the
                # agent is collected, and at exit for one held to the end.
                weakref.finalize(self, self._server.stop)
            return self._server

    def stop(self) -> None:
        """Takes no further turn, and takes down the server the turn under way is waiting on."""
        super().stop()
        self._down()

    def _down(self) -> None:
        """Takes down the server this agent holds, if it is holding one."""
        if self._server is not None:
            self._server.stop()
            self._server = None

    def new(self, cwd: str | os.PathLike[str] | None = None) -> CodexSession:
        """Opens a new Codex session, in the directory it is given or in this one."""
        return CodexSession(self, cwd)

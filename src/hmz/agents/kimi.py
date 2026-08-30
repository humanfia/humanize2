"""Kimi Code: the app server it serves itself from, where a session is more than its prompts.

``kimi --prompt`` takes a prompt and nothing else. A ``/goal`` written into one is text the model
reads rather than a goal its runtime keeps, there is no flag for swarm mode, the effort an agent
is configured with has nowhere to go, and a turn already running has nowhere to be talked to.
``kimi web`` is the same binary serving the sessions its own browser client drives, and there
all four are things done to the session a turn is submitted to.
"""

# A session and the agent holding it are two halves of one object declared in one
# file, which is what the underscore keeps out of the package rather than out of them.
# pyright: reportPrivateUsage=false

from __future__ import annotations

import collections
import contextlib
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import weakref
from collections import Counter
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar, cast

from websockets.exceptions import WebSocketException
from websockets.sync.client import ClientConnection, connect

from .base import AgentBase, SessionBase
from .config import AgentConfig
from .event import Event, Failed, Question, Usage, say

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

    from pydantic import BaseModel

#: The one line `kimi web` prints once it is listening, and the only place the port it took --
#: asked for as 0, so that two flows on one machine cannot collide -- and its token are said.
_LISTENING = re.compile(r"^Kimi server: (\S+)/#token=(\S+)$")

#: What an effort is prefixed with to ask for swarm mode: `max` and `swarmmax` are the same
#: thinking, run as one agent and as a fleet of them.
SWARM = "swarm"


@dataclass
class _Running:
    """The turn under way, if one is: which session it is in, and what it is running at.

    Written as the turn opens and cleared when it is over, read by whoever wants to put a word
    in. A prompt sent to a session that is working is queued rather than run, and steering it
    is what moves it into the turn already running instead of leaving it for the next one.
    """

    session: str | None = None
    config: dict[str, Any] = field(default_factory=dict[str, Any])


#: How often a running turn is asked whether it is still running, how long one call may take,
#: and how long a daemon being taken down is given to go before it is left to the system.
_POLL_SECONDS = 1.0
_CALL_SECONDS = 60.0
_STOP_SECONDS = 5.0

#: Event-capable daemons need polling only as recovery while the model is thinking.
_RECOVERY_SECONDS = 10.0

#: What each frame the daemon names says is worth reading back off it: whether spending may
#: have moved, and whether a question may be waiting to be answered. REST stays authoritative
#: for both -- these only say which of those reads is worth the shared daemon's time, and a
#: frame listed here is one the reader wakes for at once. A frame under no name here means
#: both and is coalesced instead: the daemon streams a running command's output and a tool
#: call's arguments a chunk at a time, and a reader woken per chunk would spend the daemon
#: every session of the agent shares on one session's `cat`.
_MEANS = {
    "tool.call.started": (False, False),
    "prompt.started": (False, False),
    "goal.updated": (False, False),
    "turn.step.completed": (True, False),
    "event.question.requested": (False, True),
    "event.approval.requested": (False, True),
    "error": (True, True),
}


def _update(socket: ClientConnection, deadline: float) -> dict[str, Any]:
    """Read one bounded event frame, refusing malformed or stalled event streams."""
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError
    message = json.loads(socket.recv(timeout=remaining))
    if not isinstance(message, dict):
        raise TypeError("Kimi event frames must be objects")
    return cast("dict[str, Any]", message)


class _Updates:
    """Wake a session reader when its official daemon has something new to read.

    REST remains authoritative for history, spending, questions and goals. A refused
    subscription or a lost connection returns to polling without resubmitting a prompt.
    It also says *which* of those authoritative reads is due: one daemon serves every
    session of its agent, so a reader that asked it all four questions on every wake would
    be spending the shared daemon's time on answers nothing had changed.
    """

    def __init__(self, base: str, token: str, session: str) -> None:
        self._session = session
        self._socket: ClientConnection | None = None
        self._contexts = contextlib.ExitStack()
        self.ended = False
        #: Whether a question may be waiting to be answered, and whether spending may have
        #: moved. True to begin with and true again whenever this listener stops carrying
        #: events: what is not being told is asked for, which is the polling this backend
        #: ran on before there were notifications at all.
        self.questioned = True
        self.stepped = True
        try:
            socket = self._contexts.enter_context(
                connect(
                    base.replace("http:", "ws:", 1) + "/ws",
                    additional_headers={"Authorization": f"Bearer {token}"},
                    proxy=None,
                    compression=None,
                    ping_interval=None,
                    open_timeout=1,
                    # A full notification queue can delay its close handshake; REST has
                    # already settled the turn, so disposing this listener needs little grace.
                    close_timeout=0.1,
                )
            )
            self._socket = socket
            socket.send(
                json.dumps(
                    {
                        "type": "subscribe",
                        "id": "hmz",
                        "payload": {"session_ids": [session]},
                    }
                )
            )
            deadline = time.monotonic() + 1
            while True:
                message = _update(socket, deadline)
                if message.get("type") == "ack" and message.get("id") == "hmz":
                    if message.get("code") != 0:
                        self.close()
                    break
        except (OSError, WebSocketException, ValueError, TypeError):
            self.close()

    def wait(self, *, settled: bool) -> None:
        """Wait for progress, falling back to ordinary polling after a disconnect."""
        socket = self._socket
        if socket is None:
            # Nothing is being told, so everything is asked: this is the plain polling the
            # backend ran on before there were notifications, and it asks the daemon the
            # whole set every time round.
            self.questioned = self.stepped = True
            time.sleep(_POLL_SECONDS)
            return
        # Keep the extra REST read after completion, without its polling delay once the
        # daemon has confirmed that this turn's final events have been published.
        if settled and self.ended:
            return
        started = time.monotonic()
        deadline = started + (_POLL_SECONDS if settled else _RECOVERY_SECONDS)
        told = False  # whether the daemon said anything at all before the deadline
        try:
            while True:
                message = _update(socket, deadline)
                if message.get("type") == "ping":
                    payload = message.get("payload")
                    if not isinstance(payload, dict) or not isinstance(
                        nonce := cast("dict[str, Any]", payload).get("nonce"), str
                    ):
                        self.close()
                        return
                    socket.send(
                        json.dumps({"type": "pong", "payload": {"nonce": nonce}})
                    )
                    continue
                if message.get("session_id") != self._session:
                    continue
                told = True  # a heartbeat says the daemon is there, not that this turn moved
                kind = message.get("type")
                payload = message.get("payload", {})
                if not isinstance(payload, dict):
                    self.close()
                    return
                main = cast("dict[str, Any]", payload).get("agentId", "main") == "main"
                if kind in ("assistant.delta", "thinking.delta"):
                    # Preserve the old display cadence during long streaming messages,
                    # coalescing token notifications into at most one history read/second.
                    deadline = min(deadline, started + _POLL_SECONDS)
                elif kind == "turn.started":
                    # An agent beginning is not yet anything to read back: what it goes on
                    # to do is, and that arrives under its own name.
                    if main:
                        self.ended = False
                elif kind == "turn.ended":
                    if main:
                        self.ended = True
                    self.stepped = True
                    return
                elif (means := _MEANS.get(str(kind))) is not None:
                    self.stepped = self.stepped or means[0]
                    self.questioned = self.questioned or means[1]
                    return
                else:
                    # Everything else this session is told is progress, whatever the daemon
                    # calls it: a list of the frames worth waking for is a list that goes
                    # stale, and a question arriving under a name written down before the
                    # daemon had it would be a turn that stopped to ask and was never read
                    # again. So it is read back -- at the cadence a stream of them can
                    # afford, which is the one the streamed text already goes at.
                    self.stepped = self.questioned = True
                    deadline = min(deadline, started + _POLL_SECONDS)
        except TimeoutError:
            # Silence for as long as that is a listener that may have missed something, so
            # the reader goes back to asking the daemon everything. A deadline reached with
            # frames still arriving is not silence: it is the coalescing above, and what
            # those frames meant has already been said.
            if not told:
                self.questioned = self.stepped = True
            return  # Event delivery is never the only way to finish.
        except (OSError, WebSocketException, ValueError, TypeError):
            self.close()

    def close(self) -> None:
        """Release the subscription, including a partially completed handshake."""
        # Said before the socket goes, so that a reader still in its turn asks the daemon
        # everything from here on rather than trusting a listener that has stopped.
        self.questioned = self.stepped = True
        if self._socket is not None:
            self._socket = None
            with contextlib.suppress(OSError, WebSocketException):
                self._contexts.close()


#: What the daemon counts a session's spending in, and what each of those is here. Every kind
#: of token counts: what a rate is measuring is the traffic, and a cache read crosses the wire
#: like anything else.
_KINDS = {
    "input": "input_tokens",
    "output": "output_tokens",
    "cache_read": "cache_read_tokens",
    "cache_write": "cache_creation_tokens",
}

#: What each kind of block a message is written in reads as. A block of a kind that is not here
#: is not shown: an image is not a line of a transcript.
_BLOCKS = {"text": "text", "thinking": "reasoning", "tool_use": "tool"}

#: How each rung of the ladder is set on a Kimi session. The daemon takes one of `yolo`,
#: `manual` and `auto`, and plan mode beside it. `manual` is the one that is never used: it
#: asks, and a flow running unattended has nobody to answer -- so an agent that is to change
#: nothing is put in plan mode instead, which is Kimi's own way of saying work it out and do
#: none of it. There is no sandbox here, so `workspace-write` and `auto` are the same setting: it
#: is told to answer its own approvals, and nothing confines where it answers them.
_PERMITTED = {
    "read-only": {"permission_mode": "auto", "plan_mode": True},
    "workspace-write": {"permission_mode": "auto", "plan_mode": False},
    "auto": {"permission_mode": "auto", "plan_mode": False},
    "bypass": {"permission_mode": "yolo", "plan_mode": False},
}


class _AppServer:
    """A `kimi web` daemon of our own, and the calls one turn of a session is made of."""

    def __init__(self, argv: list[str], env: Mapping[str, str] | None = None) -> None:
        """Starts the daemon and waits for it to say where it is listening.

        Args:
          argv: The command that starts it, already wrapped for wherever its work is to land.
          env: The whole environment to start it in, which is this process's own less what the
            agent's provider hushes and plus what it sets, or None to inherit this one. The
            daemon is the agent's, so its account is the agent's too.

        Raises:
          subprocess.CalledProcessError: If it stops without ever saying, which would leave a
            flow waiting on a server that is not there. Reported as a failed turn, because it
            is the turn that starts it that has nowhere to run.
        """
        self._argv = argv
        self._stopping = threading.Lock()
        self._stopped = False
        self._proc = subprocess.Popen(
            argv,
            # Its log is nobody's to read; what is wanted from it is the one line below.
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            encoding="utf-8",
            errors="replace",
            env=dict(env) if env else None,
            start_new_session=os.name != "nt",
        )
        assert self._proc.stdout is not None  # noqa: S101
        for line in self._proc.stdout:
            if (listening := _LISTENING.match(line.strip())) is not None:
                self._base = f"{listening[1]}/api/v1"
                self._token = listening[2]
                break
        else:
            raise Failed(
                self._proc.wait(), argv, "", f"{argv[0]} stopped without listening"
            )
        # A pipe nobody drains stops the daemon writing to it, so the rest of the log is read
        # and dropped rather than left to fill.
        threading.Thread(
            target=collections.deque, args=(self._proc.stdout, 0), daemon=True
        ).start()

    def call(self, method: str, path: str, body: Any = None) -> Any:
        """Makes one call to the daemon.

        Args:
          method: The HTTP method to make it with.
          path: The path under the daemon's API root.
          body: What to send as JSON, or None to send nothing.

        Returns:
          What the daemon answered with, unwrapped from its envelope.

        Raises:
          subprocess.CalledProcessError: If it refuses the call or cannot be reached, which is
            a failed turn however it failed -- reported the way every other backend reports one,
            so that a flow catches turns rather than transports.
        """
        # The address is the one this process just watched its own server announce, so the
        # scheme is http and the host is loopback whatever the audit rule fears.
        request = urllib.request.Request(  # noqa: S310
            self._base + path,
            data=None if body is None else json.dumps(body).encode(),
            method=method,
            headers={
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=_CALL_SECONDS) as response:  # noqa: S310
                said: dict[str, Any] = json.load(response)
        except urllib.error.HTTPError as refused:
            raise Failed(
                refused.code, self._argv, "", refused.read().decode(errors="replace")
            ) from refused
        except OSError as unreachable:  # a daemon that died, or a call that timed out
            raise Failed(1, self._argv, "", str(unreachable)) from unreachable
        # A refusal arrives inside a 200: a word steered into a turn that has already ended
        # comes back as `{"code": 40402, "msg": ...}` with the status still OK. Read as an
        # answer, that is a word which never landed reading as one that did.
        if said.get("code"):
            raise Failed(
                1, self._argv, "", f"{path}: {said.get('msg') or said['code']}"
            )
        return said.get("data")

    def stop(self) -> None:
        """Takes the daemon and its children down, leaving its sessions on disk."""
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
                self._proc.wait()
                return

            # Provider wrappers and Kimi share this dedicated group. Taking down the group
            # prevents a stopped flow from leaving either wrapper or daemon behind.
            with contextlib.suppress(ProcessLookupError):
                os.killpg(self._proc.pid, signal.SIGTERM)
            with contextlib.suppress(subprocess.TimeoutExpired):
                self._proc.wait(timeout=_STOP_SECONDS)
            with contextlib.suppress(ProcessLookupError):
                os.killpg(self._proc.pid, signal.SIGKILL)
            self._proc.wait()


@dataclass(frozen=True, kw_only=True)
class KimiCodeCLIAgentConfig(AgentConfig):
    """What Kimi Code is configured with: the common model, and an effort that says width too.

    Attributes:
      effort: How hard to think, in Kimi's own wording, optionally prefixed `swarm` to run
        every turn as a fleet of subagents rather than as one agent -- `max` and `swarmmax` are
        the same thinking at either width.
    """


class KimiCodeCLISession(SessionBase):
    """A Kimi Code conversation, held by the app server and named by it as it opens.

    The id is the server's, handed out before the turn rather than read back out of a resume
    hint, so a second agent working alongside cannot be resumed by mistake.
    """

    _agent: KimiCodeCLIAgent  # every turn is submitted to the server this agent holds

    def __init__(
        self, agent: AgentBase, cwd: str | os.PathLike[str] | None = None
    ) -> None:
        """Initializes a session running nothing yet.

        Args:
          agent: The agent whose config every turn of this session runs at.
          cwd: The directory this conversation works in, as for `SessionBase`.
        """
        super().__init__(agent, cwd)
        #: The turn under way, which is what a word put in is steered into.
        self._running = _Running()
        #: What this session has cost so far, by kind, as the daemon counts it: a running
        #: total for the whole conversation, so what one turn cost is the rise across it.
        self._counted: Counter[str] = Counter()

    @property
    def named(self) -> str | None:
        """The session the daemon holds, which it names as the turn opens it."""
        return self._id or self._running.session

    def interject(self, text: str) -> None:
        """Puts a word into the turn already running, rather than into the next one.

        A prompt sent to a session that is working is queued, and would be answered as a turn
        of its own once this one ended. Steering moves it into the turn that is running, which
        is what makes it a word put in rather than a turn queued behind.

        Args:
          text: What to say to the agent.

        Raises:
          RuntimeError: If no turn is running, so there is none to steer it into.
          subprocess.CalledProcessError: If the daemon refuses either call.
        """
        running = self._running
        if running.session is None:
            raise RuntimeError("no turn is running to be talked to")
        # Named by its own words: Kimi mints a fresh id for a steered prompt, so the id it
        # answers with is not the one it took, and the words are what both ends have.
        self.steering(text, ticket=text)
        server = self._agent.server
        queued = server.call(
            "POST",
            f"/sessions/{running.session}/prompts",
            {"content": [{"type": "text", "text": text}], **running.config},
        )
        try:
            server.call(
                "POST",
                f"/sessions/{running.session}/prompts:steer",
                {"prompt_ids": [queued["prompt_id"]]},
            )
        except BaseException:
            self.unsteered(text)  # nothing is coming back for a word that never went in
            raise

    def _stream(
        self,
        prompt: str,
        *,
        schema: type[BaseModel] | None = None,  # noqa: ARG002
    ) -> Iterator[Event]:
        """Sends one turn, opening the session on the first call and resuming it after.

        The daemon answers a turn whole, but it writes the turn down as it goes: what the
        agent said is read back as it is written, which is what makes the turn watchable.

        A shape is not a setting of a turn here -- the daemon takes a prompt and nothing
        else about the answer -- so a turn asked for one has already been asked in the
        prompt, which is what :attr:`SessionBase.shapes` says of this backend.
        """
        yield from self._submit(prompt, goal=False)

    def _asked(self, session: str) -> None:
        """Answers whatever the turn has stopped to ask, if it has stopped to ask anything.

        The daemon holds a question until it is answered and the turn waits on it, so a poll
        that only read messages would read a session that never moves again. An answer is
        matched to one of the options where it names one, since a question that offered them
        need not take anything else; a question nobody is there to answer is skipped, which
        the tool reads as an answer and carries on from.

        Args:
          session: The session the turn is running in.
        """
        server = self._agent.server
        held = server.call("GET", f"/sessions/{session}/questions?status=pending")
        # A list or a list under `items`, depending on the daemon: what is wanted is the
        # questions, and a daemon that has none of them has nothing to answer either.
        waiting: list[Any] = (
            cast("dict[str, Any]", held).get("items") or []
            if isinstance(held, dict)
            else held or []
        )
        for raw in waiting:
            pending = cast("dict[str, Any]", raw)
            if not pending.get("question_id"):
                continue  # not a question, whatever else the daemon answered with
            answers: dict[str, dict[str, Any]] = {}
            for asked in cast("list[Any]", pending.get("questions") or []):
                question = cast("dict[str, Any]", asked)
                offers: list[Any] = question.get("options") or []
                options = {
                    str(cast("dict[str, Any]", option).get("label", "")).lower(): cast(
                        "dict[str, Any]", option
                    ).get("id")
                    for option in offers
                    if isinstance(option, dict)
                }
                said = self._agent.asked(
                    Question(
                        text=str(
                            question.get("question") or question.get("header") or ""
                        ),
                        options=tuple(
                            str(cast("dict[str, Any]", option)["label"])
                            for option in offers
                            if isinstance(option, dict)
                            and cast("dict[str, Any]", option).get("label")
                        ),
                    )
                )
                if said is None:
                    answers[str(question["id"])] = {"kind": "skipped"}
                elif (chosen := options.get(said.strip().lower())) is not None:
                    answers[str(question["id"])] = {
                        "kind": "single",
                        "option_id": chosen,
                    }
                else:
                    answers[str(question["id"])] = {"kind": "other", "text": said}
            server.call(
                "POST",
                f"/sessions/{session}/questions/{pending['question_id']}",
                {"answers": answers},
            )

    def _counting(self, server: _AppServer, session: str) -> Usage:
        """What this session has spent since the last time it was asked.

        The daemon counts the whole conversation, so what has been spent since is the rise
        across it. Told to the meters as it is read, which is what a rate taken while the turn
        is still running is made of.

        Args:
          server: The daemon holding the session.
          session: The session to ask about.

        Returns:
          The rise since the last reading, by kind, which is nothing at all where it has not
          moved.

        Raises:
          subprocess.CalledProcessError: If the daemon will not say, which is not a failed
            turn: what a run costs is worth nothing at the price of the run.
        """
        held = server.call("GET", f"/sessions/{session}")
        usage: dict[str, Any] = (
            cast("dict[str, Any]", held).get("usage") or {}
            if isinstance(held, dict)
            else {}
        )
        counted = Counter(
            {
                kind: int(usage.get(named) or 0)
                for kind, named in _KINDS.items()
                if usage.get(named)
            }
        )
        risen = Usage(
            {
                kind: tokens
                for kind in set(counted) | set(self._counted)
                if (tokens := counted[kind] - self._counted[kind]) > 0
            }
        )
        self._counted = counted
        self._spends(risen)
        return risen

    def _pursue(self, objective: str) -> str:
        """Runs the turn under a goal of Kimi's own, which its runtime steers until it is met.

        The objective is the prompt as well as the goal, which is what ``/goal`` does: the
        agent is told what to do, and the runtime is told what it is for.

        Returns:
          The agent's response once the goal is done with, stripped.
        """
        said = ""
        for event in self._submit(objective, goal=True):
            # Told to whoever is watching, since a goal does not run through `stream`: it is
            # one prompt and as many turns of the model as the objective takes.
            self._agent._heard(event)
            if event.kind == "result":
                said = event.text
        return said.strip()

    def _submit(self, prompt: str, *, goal: bool) -> Iterator[Event]:
        """Runs one turn, saying what the agent says as it says it.

        A goal-driven turn is many turns of the model, and it is over when the session falls
        idle rather than when the first of them ends. The session is asked whether it is still
        running before its messages are read, so that nothing said between the two is missed.

        Args:
          prompt: The input prompt for this turn, which is the objective as well when it is
            a goal the session is being set.
          goal: Whether to set the prompt as the session's goal before sending it.

        Yields:
          What the agent said, in the order it said it, and the answer it ended on.

        Raises:
          subprocess.CalledProcessError: If the daemon refuses any of the calls a turn is made
            of, leaving the session unopened so that the next call retries the turn.
        """
        effort = self.effort
        turn: dict[str, Any] = {
            "model": self._agent.config.model,
            "thinking": effort.removeprefix(SWARM),
            "swarm_mode": effort.startswith(SWARM),
            # What it may do without being asked, which for an unattended flow is everything:
            # a flow watches its agent rather than answering it, as humanize' own flows do.
            **_PERMITTED.get(self._agent.config.permission, _PERMITTED["bypass"]),
        }
        updates: _Updates | None = None
        with self._lock:  # a conversation is a sequence: one turn at a time
            # A turn that failed is as over as one that landed: neither leaves
            # anything for a word to be steered into.
            try:
                server = self._agent.server
                # A session of its own per attempt while this one is unopened: an opening turn that
                # failed leaves the daemon holding a conversation nothing landed in, and resuming
                # that one would be resuming a turn that never happened.
                if (session := self._id) is None:
                    session = server.call(
                        "POST", "/sessions", {"metadata": {"cwd": self._workspace()}}
                    )["id"]
                server.call(
                    "POST",
                    f"/sessions/{session}/profile",
                    {
                        "agent_config": turn
                        | ({"goal_objective": prompt} if goal else {})
                    },
                )
                updates = _Updates(server._base, server._token, session)
                # Said before the prompt goes in, so that a word put in has a session to be
                # steered into from the moment there is a turn to interrupt.
                self._running = _Running(session=session, config=turn)
                since = server.call(
                    "POST",
                    f"/sessions/{session}/prompts",
                    {"content": [{"type": "text", "text": prompt}], **turn},
                )["user_message_id"]
                answer = ""
                shown: dict[
                    str, int
                ] = {}  # how much of each message has been passed on
                settled = False
                costing = Usage()  # what this turn has come to, added up as it goes
                # When each of the two authoritative readings was last made, so that a turn
                # told nothing about either still makes them at the cadence it made them at
                # before there were notifications at all. What the daemon says brings one
                # forward; nothing the daemon says can put one off.
                read_at = {"asked": 0.0, "counted": 0.0}

                def due(what: str, *, told: bool) -> bool:
                    if not told and time.monotonic() - read_at[what] < _POLL_SECONDS:
                        return False
                    read_at[what] = time.monotonic()
                    return True

                while True:
                    # First of all: a turn that has stopped to ask waits on the answer, so a
                    # poll that only read messages would be reading a session that has
                    # stopped moving. A daemon that cannot be asked is not a failed turn.
                    # Asked at once when the daemon has said there may be something to
                    # answer, and a second apart when it has not: one daemon serves every
                    # session of the agent, and asking it per notification what it has
                    # already said it has none of is the one cost here that buys nothing.
                    # Taken off the book before the reading rather than after, so that a
                    # question raised while it runs is a question read next time round
                    # rather than one this turn waits on forever; a reading that failed
                    # puts it back.
                    if due("asked", told=updates.questioned):
                        updates.questioned = False
                        try:
                            self._asked(session)
                        except subprocess.CalledProcessError:
                            updates.questioned = True
                    busy = server.call("GET", f"/sessions/{session}/status")["busy"]
                    # What it has come to so far, asked for each time round rather than once
                    # at the end: a turn is minutes long, and a rate that only moved when one
                    # ended would stand still for all of them. A daemon that will not say is
                    # not a failed turn. Spending moves a step at a time, so it is read when
                    # a step has landed -- and what a skipped reading would have added is
                    # still in the total, which is read once more as the turn settles.
                    if due("counted", told=updates.stepped):
                        updates.stepped = False
                        try:
                            costing = costing + self._counting(server, session)
                        except subprocess.CalledProcessError:
                            updates.stepped = True
                    if goal and not busy:
                        # A goal runs through the quiet between its turns: Kimi starts the next one
                        # itself once the session falls still, so a session that has stopped is a
                        # goal that has stopped only when the goal is no longer being pursued.
                        pursued = server.call("GET", f"/sessions/{session}/goal")
                        busy = pursued is not None and pursued["status"] == "active"
                    said = server.call(
                        "GET", f"/sessions/{session}/messages?after_id={since}"
                    )["items"]
                    # A message is readable while it is still being written, so the turn is read
                    # again from its own first message every poll rather than once: a message put
                    # aside as seen would be the one the agent had only started saying. Newest
                    # first, and a turn reads forwards; what has been passed on is not passed on
                    # twice.
                    for message in reversed(said):
                        if message["role"] != "assistant":
                            # A word put into the turn, spliced into the conversation at the
                            # step that takes it in: that splice is the agent saying it has
                            # it, and is the only thing here that is not the agent talking.
                            # Read as one, it would show your own words back as the agent's.
                            if message["id"] not in shown:
                                shown[message["id"]] = len(message["content"])
                                words = "".join(
                                    block.get("text") or ""
                                    for block in message["content"]
                                    if block.get("type") == "text"
                                )
                                if self.took(words) is not None:
                                    yield Event(kind="took", text=words)
                            continue
                        for block in message["content"][shown.get(message["id"], 0) :]:
                            kind = _BLOCKS.get(str(block.get("type")))
                            # A tool is named by what it is; everything else is what it says,
                            # which a block keeps under its own name -- text under `text`.
                            words = str(
                                (
                                    block.get("tool_name")
                                    if kind == "tool"
                                    else block.get(str(block.get("type")))
                                )
                                or ""
                            )
                            if kind is None or not words.strip():
                                continue
                            if not self._agent._watchers:
                                # On stderr, where every other backend puts its progress: a
                                # turn nobody can watch is a flow that reads as hung for as
                                # long as the turn takes. Something watching the agent shows
                                # the turn itself, and would then be showing it twice.
                                say(words, sys.stderr)
                            yield Event(kind=kind, text=words)
                        shown[message["id"]] = len(message["content"])
                    # And the answer is taken fresh each time, so that it is what the agent ended
                    # up saying rather than what it had said when it was first readable.
                    for (
                        message
                    ) in said:  # newest first: the last thing said that has any words
                        text = "".join(
                            block["text"]
                            for block in message["content"]
                            if block["type"] == "text"
                        )
                        if message["role"] == "assistant" and text:
                            answer = text
                            break
                    if settled:
                        # Taken note of before it is passed on: a turn that landed is a session
                        # this agent opened, whether or not there is anywhere left to say so.
                        self._adopt(session)
                        if not self._agent._watchers:
                            # Where the CLI would have put the response. Something watching
                            # the agent has had it already, as the turn said it.
                            say(answer, sys.stdout)
                        # What the turn cost: the daemon counts the whole session, so what
                        # this turn spent is the rise across it, added up as the turn went.
                        # Asked once more here and never at the cost of the answer -- a turn
                        # that landed has landed, whatever the daemon then says it came to.
                        with contextlib.suppress(subprocess.CalledProcessError):
                            costing = costing + self._counting(server, session)
                        spent = (
                            {self._agent.config.model: int(costing.total)}
                            if costing.total > 0
                            else {}
                        )
                        yield Event(
                            kind="result",
                            text=answer.strip(),
                            tokens=spent,
                            spent=costing,
                        )
                        return
                    # A session says it has stopped before the last thing it said can be read
                    # back, so what it said is read once more after it stops rather than at the
                    # moment it does -- otherwise a turn returns everything but its answer.
                    settled = not busy
                    updates.wait(settled=settled)

            finally:
                if updates is not None:
                    updates.close()
                self._running = _Running()


class KimiCodeCLIAgent(AgentBase):
    """Kimi Code, driven through an app server of its own so a whole session is settable."""

    #: Kimi keeps itself going toward an objective, which is what `pursue` reaches for.
    pursues: ClassVar[bool] = True

    def __init__(self, config: AgentConfig, *, name: str | None = None) -> None:
        """Initializes an agent whose server is not running yet.

        Args:
          config: The model and effort every session of this agent runs at.
          name: What to call this agent, defaulting to one nothing else answers to.
        """
        super().__init__(config, name=name)
        self._server: _AppServer | None = None
        #: Which account the daemon up now was started as: an agent that has fallen back
        #: starts another rather than going on submitting turns as somebody else.
        self._server_as = ""
        self._serving = threading.Lock()

    @property
    def server(self) -> _AppServer:
        """The daemon this agent's turns are submitted to, started the first time it is asked for.

        One per agent rather than one per session, so that a flow dropping a session a turn
        does not start a server a turn; it is taken down when the agent is collected, or at
        exit for one held to the end. An anchored agent starts it through coganchor, which
        leaves the server here, holding the conversation, and its work on the target -- the
        same split the CLI ran under.
        """
        with (
            self._serving
        ):  # two sessions of one agent share the server rather than start two
            if self._server is not None and self._server_as != self.node().name:
                # Started as an account this agent has since left. Let go of rather than
                # taken down: a turn on another thread may still be talking to it, and its
                # own finalizer stops it when the agent is collected either way.
                self._server, self._server_as = None, ""
            if self._server is None:
                argv = [
                    "kimi",
                    "web",
                    "--no-open",
                    "--port",
                    "0",
                    "--log-level",
                    "error",
                ]
                # Read before the environment is built out of it: a fallback landing
                # between the two reads would name the account this server is *not* signed
                # into, and a server that believes it is already elsewhere is one nothing ever
                # starts again.
                account = self.node().name
                self._server = _AppServer(self.spawned(argv), self._environ())
                self._server_as = account
                # Held by the finalizer alone, which is what takes the daemon down: when the
                # agent is collected, and at exit for one held to the end.
                weakref.finalize(self, self._server.stop)
            return self._server

    def stop(self) -> None:
        """Takes no further turn, and takes down the server the turn under way is waiting on."""
        super().stop()
        if self._server is not None:
            self._server.stop()
            self._server = None

    def new(self, cwd: str | os.PathLike[str] | None = None) -> KimiCodeCLISession:
        """Opens a new Kimi session, in the directory it is given or in this one."""
        return KimiCodeCLISession(self, cwd)

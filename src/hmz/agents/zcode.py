"""ZCode: a session held open on one `zcode app-server --stdio`, and every turn sent to it.

Its command line will run a turn -- `zcode --prompt` answers with one JSON object, session id
and all -- and cannot be told which model to run it on or how hard to think. Both of those are
settings of the configuration file whoever is at this machine already has, so a turn driven
that way is a turn on whatever that file names, and a model chosen where the agents are chosen
would be a setting that lies. The app server takes both per session, which is why a turn goes
there instead: `session/create` names the model, the thought level and the rung, and what comes
back is the turn as it happens rather than a summary once it is over.

The protocol is ZCode's own rather than JSON-RPC. The four frames are the familiar ones -- a
call, a notification, an answer, a refusal -- and a `jsonrpc` on any of them is refused
outright, so this speaks it as it is. The server also asks things of its client: what the
runtime may do, whether a high-risk tool is allowed, what to answer a question with. Every one
of those is answered, because a request left hanging stops the turn waiting behind it.
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
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar, cast

from .base import AgentBase, SessionBase
from .config import AgentConfig
from .event import Event, Failed, Question, Usage, say
from .hooks import EVERYWHERE, Moment, Occasion

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

    from pydantic import BaseModel

#: How long a server being taken down is given to go before it is left to the operating system.
_STOP_SECONDS = 5.0

#: What ZCode is run in at each rung of the ladder. `plan` refuses an edit and refuses a command
#: it reads as high-risk, and lets it look at anything; `edit` may change the workspace and asks
#: about none of it; `build` -- the mode its own terminal opens in -- asks before a tool with
#: side effects and waits for the answer, which is what makes it the rung where a hook hung on
#: `PERMISSION_REQUEST` has something to refuse; and `yolo` asks nothing at all.
#:
#: Its own `auto` is not the `auto` here and is nobody's rung: its permission service answers
#: `mode.auto.unimplemented` to every tool in that mode -- `Auto mode is reserved but not
#: implemented yet` -- so an agent run at it would be an agent allowed to do nothing.
_PERMITTED = {
    "read-only": "plan",
    "workspace-write": "edit",
    "auto": "build",
    "bypass": "yolo",
}

#: The modes in which what the agent asks for is granted. ZCode asks in three of the four --
#: `edit` and `build` both stop at a high-risk tool and wait -- and a rung is what says whether
#: the answer is yes: an agent allowed no more than its workspace is not one that gets a
#: `rm -rf` by asking twice. `yolo` is here because it is granted rather than asked, and is
#: never the mode a request arrives under.
_GRANTS = ("build", "yolo")

#: The two tools ZCode reaches outside the workspace with, and so the two an agent that may not
#: search the web is denied. Denied at the session rather than in anybody's settings file: two
#: agents of one flow may be told different things, and neither is a reason to change what the
#: person at this machine has configured.
_WEB = ("WebFetch", "WebSearch")

#: What each kind of token is called in the counts the server states. Reasoning and the cached
#: part of the input are counted inside these two rather than beside them -- the server's own
#: `totalTokens` is the input and the output added up -- so a third kind here would be counting
#: some of the same tokens twice.
_KINDS = {"input": "inputTokens", "output": "outputTokens"}

#: What the client is told the runtime may do. The one answer that is not a default is about
#: ZCode's own file search: turning it off would take `find` and `grep` away from an agent
#: inside its workspace, which is not what anybody means by running one unattended.
_PREFERENCES = {"nativeSearchEnhancementsEnabled": True}

#: What the server asks its client before it will open a session at all, and gives up on after
#: fifteen seconds.
_RUNTIME = "session/requestRuntimePreferences"

#: What the server calls the client requests that are somebody's to answer rather than the
#: runtime's own: an approval, and a question the agent stopped on.
_APPROVAL = "interaction/requestPermission"
_ASKS = "interaction/requestUserInput"

#: What a session's own stream is delivered as. The other kind replays for a web client that
#: may have missed some; a turn read here is read as it happens and misses nothing.
_DELIVERY = "desktop-continuous"

#: Where the words are in each tool's arguments, so that a row of a transcript says what the
#: agent reached for rather than the first field that happens to serialise. A tool that is not
#: here is shown under whatever string it does name itself with.
_ABOUT = {
    "Bash": "description",
    "Edit": "file_path",
    "Read": "file_path",
    "Skill": "skill",
    "Task": "description",
    "WebFetch": "url",
    "Write": "file_path",
}

#: What a payload of `session.updated` has to carry to be one model's answer rather than one of
#: the several other things that arrive under that name.
_ANSWERED = ("stopReason", "usage")


@dataclass
class _Held:
    """What one session of this agent runs, and what the server holding it has been told.

    Attributes:
      spends: Told what each request of the turn cost as it lands, so that a rate read while a
        turn is still running has something to move on.
      model: What this session is to run now, which its agent's config says.
      effort: The same, for the thought level.
      mode: The same, for the rung.
      told: The three of them as the server was last told them, so that a turn at the settings
        of the one before it says none of them again -- each is a call, and a call is a
        round trip.
    """

    spends: Any = None
    model: str = ""
    effort: str = ""
    mode: str = ""
    told: tuple[str, str, str] | None = None


class _AppServer:
    """A `zcode app-server` of our own, spoken to in the ZCode protocol over its stdio."""

    def __init__(self, argv: list[str], env: Mapping[str, str] | None = None) -> None:
        """Starts the server.

        Nothing is said to introduce this client: the protocol has no handshake, and the first
        call a turn makes is the one that opens its session.

        Args:
          argv: The command that starts it, already wrapped for wherever its work is to land.
          env: The whole environment to start it in, which is this process's own less what the
            agent's provider hushes and plus what it sets, or None to inherit this one. The
            server is the agent's, so its account is the agent's too.
        """
        self._argv = argv
        #: Whose turns run here, so that a hook has an agent to fire on and a question somebody
        #: to be put to. Held weakly, as codex's is and for the same reason: the agent holds
        #: the server and the finalizer that takes it down is the agent's, so a server holding
        #: its agent back would be an agent nothing could collect.
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
        #: Which sessions this server is holding and what each is allowed, so that one opened
        #: on a server since let go of is picked back up rather than talked to as though it
        #: were still here -- and so that an approval it asks about is answered as the rung
        #: that session runs at, rather than as the loosest one any session of the agent has.
        self.sessions: dict[str, str] = {}
        self._messages: queue.Queue[dict[str, Any] | None] = queue.Queue()
        # Read from a thread of its own, so that a turn can wait on the server for a while
        # rather than only for as long as it takes to answer.
        threading.Thread(target=self._pump, daemon=True).start()
        # One stream, shared by every session of the agent: a call is a write and the reads up
        # to its answer, and two of them interleaved would each take the other's messages.
        self._speaking = threading.Lock()

    @property
    def _agents(self) -> list[AgentBase]:
        """Whose turns run here, and still exist: an agent that has gone is not one to tell."""
        held = [one() for one in self._held]
        return [one for one in held if one is not None]

    def call(self, method: str, params: dict[str, Any]) -> Any:
        """Makes one call and reads until it is answered.

        Args:
          method: The method to call.
          params: What to call it with.

        Returns:
          What the server answered with.

        Raises:
          subprocess.CalledProcessError: If it refused the call, or stopped before answering.
        """
        with self._speaking:
            return self._called(method, params)

    def _called(self, method: str, params: dict[str, Any]) -> Any:
        """Makes that call with the stream already held, and reads until it is answered.

        Args:
          method: The method to call.
          params: What to call it with.

        Returns:
          What the server answered with.

        Raises:
          subprocess.CalledProcessError: If it refused the call, or stopped before answering.
        """
        ident = next(self._pending)
        self._write({"id": ident, "method": method, "params": params})
        # An answer is a frame with no method of its own: the server asks things of us over the
        # same stream, numbering its own calls, and one of those is not this one.
        while (message := self._read()) is None or not (
            message.get("id") == ident and "method" not in message
        ):
            pass
        return self._answer(message, "")

    def open(self, workspace: str, held: _Held, *, searches: bool) -> str:
        """Opens a session, at the settings the agent it is for is configured with.

        Args:
          workspace: The directory the session works in.
          held: What it is to run, which is remembered so a turn at the same settings says
            nothing again.
          searches: Whether the agent may reach the web.

        Returns:
          The session's id, which ZCode gives it before any turn has run.

        Raises:
          subprocess.CalledProcessError: If the server refused to open one.
        """
        with self._speaking:
            opened = self._called(
                "session/create",
                {
                    "workspace": _workspace(workspace),
                    "model": {
                        "providerId": _provider(held.model),
                        "modelId": _model(held.model),
                    },
                    "thoughtLevel": held.effort,
                    "mode": held.mode,
                    # A title is a turn of its own on the lite model, and nothing here reads
                    # one: a session is named by the flow that opened it.
                    "titleGenerationEnabled": False,
                    **({} if searches else {"toolDenylist": list(_WEB)}),
                },
            )
            session = str(opened["session"]["sessionId"])
            self._called(
                "session/subscribe", {"sessionId": session, "deliveryKind": _DELIVERY}
            )
        # Everything a settling would say was said in the call that opened it.
        held.told = (held.model, held.effort, held.mode)
        self.sessions[session] = held.mode
        return session

    def settle(self, session: str, held: _Held) -> None:
        """Says what has changed since the last turn of this session, and nothing else.

        An agent's effort is a setting anybody may reach for between turns, and its model moves
        when it falls back onto another account. Both are said again where they have moved and
        left alone where they have not, since each of them is a call.

        Args:
          session: The session to settle.
          held: What it is to run now, against what it was last told.

        Raises:
          subprocess.CalledProcessError: If the server refused any of it.
        """
        with self._speaking:
            for method, params in _settling(session, held):
                self._called(method, params)
        self.sessions[session] = held.mode

    def resume(
        self, session: str, workspace: str, held: _Held, *, searches: bool
    ) -> None:
        """Picks a session back up on a server that did not open it.

        Which is a server started since, because the agent fell back onto another account: the
        conversation is ZCode's own and outlives the process that was holding it. What does not
        outlive it is the model the turns ran on -- the server materialises that from the
        client and keeps it in memory -- so ZCode says on the way back in that the session's
        model is gone, and refuses the first turn sent to it. That refusal is left to happen
        where it can be read, rather than guessed at here.

        Args:
          session: The session to pick up.
          workspace: The directory it works in.
          held: What it is to run.
          searches: Whether the agent may reach the web.

        Raises:
          subprocess.CalledProcessError: If the server refused to pick it up.
        """
        with self._speaking:
            self._called(
                "session/resume",
                {
                    "sessionId": session,
                    "workspace": _workspace(workspace),
                    "thoughtLevel": held.effort,
                    **({} if searches else {"toolDenylist": list(_WEB)}),
                },
            )
            self._called(
                "session/subscribe", {"sessionId": session, "deliveryKind": _DELIVERY}
            )
            for method, params in _settling(session, held, again=True):
                self._called(method, params)
        self.sessions[session] = held.mode

    def turn(self, session: str, prompt: str, held: _Held) -> Iterator[Event]:
        """Sends one turn and says what the agent says as it says it.

        Args:
          session: The session to send it to.
          prompt: The input prompt for this turn.
          held: Whose turn it is, told what each request of it cost as that request lands.

        Yields:
          What the agent said, and the answer it ended on.

        Raises:
          subprocess.CalledProcessError: If the turn was refused or failed, or the server
            stopped while it was running.
        """
        with self._speaking:
            self._called("session/send", {"sessionId": session, "content": prompt})
            yield from self._reading(session, held)

    def pursue(self, session: str, objective: str, held: _Held) -> str:
        """Sets a goal of ZCode's own and lets the turn it starts run to the end.

        Args:
          session: The session to set it on.
          objective: What the agent is to have achieved before it stops.
          held: Whose goal it is, told what each request of it cost.

        Returns:
          What ZCode said once the goal stopped.

        Raises:
          subprocess.CalledProcessError: If the goal was refused, or the turn under it failed.
        """
        with self._speaking:
            answered: dict[str, Any] = self._called(
                "session/goal",
                {"sessionId": session, "action": "set", "objective": objective},
            )
            said = str(answered.get("response") or "")
            if not answered.get("startedTurn"):
                # A goal recorded rather than run: `plan` is the rung where ZCode writes the
                # objective down and waits to be let out of it, which is that rung meaning what
                # it says rather than a goal that failed.
                return said.strip()
            watched = self._watched()
            for event in self._reading(session, held):
                if event.kind == "result":
                    return event.text or said.strip()
                if not watched:
                    # A goal runs for as long as it takes to be met, and nothing above this
                    # yields while it does. So its own words are the only sign it is running.
                    say(event.text, sys.stderr)
            return said.strip()

    def _watched(self) -> bool:
        """Whether something is watching the agents this server runs turns for.

        A watcher is given each message whole as the turn says it, so teeing the pieces as well
        would show every message twice.

        Returns:
          Whether anything is watching.
        """
        return any(agent._watchers for agent in self._agents)

    def _reading(self, session: str, held: _Held) -> Iterator[Event]:
        """Reads one turn's events off the stream, from the one now running to its last.

        Args:
          session: Whose events these are. One server holds every session of the agent, and a
            turn on another of them is still on this stream: what is not this session's is not
            this turn's.
          held: Whose turn it is, told what each request cost as it lands.

        Yields:
          What the agent said, and the answer it ended on.

        Raises:
          subprocess.CalledProcessError: If the turn failed, or the server stopped mid-turn.
        """
        said = ""
        saying = _Saying()
        costing = Usage()
        counted = 0
        while (message := self._read()) is not None:
            told: dict[str, Any] = message.get("params") or {}
            if message.get("method") != "session/event":
                continue
            if told.get("sessionId") != session:
                continue
            payload: dict[str, Any] = told.get("payload") or {}
            match told.get("type"):
                case "model.streaming":
                    yield from saying.streamed(payload)
                case "session.updated" if all(name in payload for name in _ANSWERED):
                    marked = str(payload.get("assistantMessageId") or "")
                    # The whole message as the server has it, which is what was streamed plus
                    # whatever arrived in no delta at all.
                    for event in saying.ended(
                        marked, str(payload.get("content") or "")
                    ):
                        if event.kind == "text":
                            said = event.text
                        yield event
                    spent = _spent(cast("dict[str, Any]", payload.get("usage") or {}))
                    counted += int(spent.total)
                    costing = costing + spent
                    if held.spends is not None and spent.total:
                        # As the turn spends it rather than once it is over: a turn is minutes
                        # long, and a rate that only moved at the end of one would stand still
                        # for all of them.
                        held.spends(spent)
                case "turn.failed":
                    raise Failed(1, self._argv, said, json.dumps(payload))
                case "turn.completed":
                    # What the whole turn cost, which is what the server adds up rather than
                    # what this saw: a request whose event arrived after the turn's own would
                    # otherwise be a turn that cost less than it did.
                    whole = _spent(cast("dict[str, Any]", payload.get("usage") or {}))
                    owed = Usage(
                        {
                            kind: short
                            for kind in whole
                            if (short := whole[kind] - costing.get(kind, 0.0)) > 0
                        }
                    )
                    if held.spends is not None and owed.total:
                        # Settling up rather than another turn's worth of spending: what this
                        # adds is what the turn's own total says was spent and no event of it
                        # carried.
                        held.spends(owed, turn=False)
                    said = str(payload.get("response") or said)
                    total = max(counted, int(whole.total))
                    yield Event(
                        kind="result",
                        text=said.strip(),
                        tokens={held.model: total} if total > 0 else {},
                        spent=whole if whole.total else costing,
                    )
                    return
                case _:  # the rest of the stream is not this turn's to show
                    pass
        raise Failed(
            self._proc.poll() or 1, self._argv, said, "app server stopped mid-turn"
        )

    def stop(self) -> None:
        """Takes the server and its children down, leaving its sessions on disk."""
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
            # Provider wrappers and the server share this dedicated group. Taking down the
            # group stops a stopped flow leaving either of them behind.
            with contextlib.suppress(ProcessLookupError):
                os.killpg(self._proc.pid, signal.SIGTERM)
            with contextlib.suppress(subprocess.TimeoutExpired):
                self._proc.wait(timeout=_STOP_SECONDS)
            with contextlib.suppress(ProcessLookupError):
                os.killpg(self._proc.pid, signal.SIGKILL)
            self._proc.wait()

    def _write(self, message: dict[str, Any]) -> None:
        """Puts one frame on the server's stdin.

        Args:
          message: The frame to send.

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
        """Reads the server's whole stream, answering what it asks of us as it arrives."""
        assert self._proc.stdout is not None  # noqa: S101
        for line in self._proc.stdout:
            if not line.strip():
                continue
            try:
                message: dict[str, Any] = json.loads(line)
            except ValueError:
                continue  # not ours: whatever the runtime put on its own stdout
            if "id" in message and "method" in message:
                # Something asked of us. A request left unanswered stalls the turn holding the
                # stream -- and with it every session of the agent -- so every one of them is
                # answered, on a thread of its own where the answer is somebody's rather than
                # this client's: a hook is the flow's own code, and asking waits on a person.
                if message["method"] in (_APPROVAL, _ASKS):
                    threading.Thread(
                        target=self._asked, args=(message,), daemon=True
                    ).start()
                    continue
                # What the runtime may do is the one of these with an answer of ours. The rest
                # are the desktop app's -- headers for a server it signed into, a browser it
                # holds -- and nothing here has any of them; answering with nothing is a client
                # that has none rather than a request the turn behind it waits on forever.
                self._write(
                    {
                        "id": message["id"],
                        "result": _PREFERENCES if message["method"] == _RUNTIME else {},
                    }
                )
                continue
            self._messages.put(message)
        self._messages.put(None)  # it has stopped, and nothing more is coming

    def _asked(self, message: dict[str, Any]) -> None:
        """Answers the one kind of request that is somebody's rather than the runtime's.

        An approval is granted, since the server only asks at all at a rung that means the
        asking is granted -- and a hook hung on `PERMISSION_REQUEST` gets it first and may say
        no, which is the one moment a refusal actually stops this agent doing something.

        A question is put to whoever is driving the agent and then declined either way: ZCode
        takes an answer to one over a channel its own terminal holds and this does not, so what
        reaches the model is the refusal and its reason -- the person's own words where there
        was somebody to say them, and that nobody was there where there was not. The turn goes
        on rather than waiting for a reply that is not coming.

        Args:
          message: The request, as read.
        """
        told: dict[str, Any] = message.get("params") or {}
        agents = self._agents
        if message["method"] == _APPROVAL:
            mode = self.sessions.get(str(told.get("sessionId") or ""), "")
            if mode not in _GRANTS:
                # A rung below the one that means the asking is granted. Refused here rather
                # than put to a hook: what a hook may do at that moment is say no, and no is
                # what this rung already says.
                self._write(
                    {
                        "id": message["id"],
                        "result": {
                            "decision": "deny",
                            "reason": f"the agent is allowed no more than {mode} mode",
                        },
                    }
                )
                return
            asking = (
                agents[0].hooks.fire(
                    Occasion(
                        moment=Moment.PERMISSION_REQUEST,
                        agent=agents[0].id,
                        session=str(told.get("sessionId") or ""),
                        tool=str(told.get("toolName") or ""),
                        about=str(told.get("reason") or ""),
                        input=told,
                    )
                )
                if agents
                else None
            )
            answer = (
                {"decision": "deny", "reason": asking.because or "refused by a hook"}
                if asking is not None and asking.refused
                else {"decision": "allow", "reason": "run unattended"}
            )
            self._write({"id": message["id"], "result": answer})
            return
        said: list[str] = []
        for raw in cast("list[Any]", told.get("questions") or []):
            question = cast("dict[str, Any]", raw)
            offered = tuple(
                str(cast("dict[str, Any]", one).get("label") or "")
                for one in cast("list[Any]", question.get("options") or [])
                if isinstance(one, dict)
            )
            wanted = str(question.get("question") or question.get("header") or "")
            answered = (
                agents[0].asked(Question(text=wanted, options=offered))
                if agents
                else None
            )
            if answered:
                said.append(f"{wanted} {answered}".strip())
        self._write(
            {
                "id": message["id"],
                "result": {
                    "decision": "deny",
                    "reason": "; ".join(said) or "nobody is here to answer",
                },
            }
        )

    def _read(self) -> dict[str, Any] | None:
        """Takes the next frame the server sent.

        Returns:
          The frame, which is never None in practice: the queue only holds what was read.

        Raises:
          subprocess.CalledProcessError: If the server stopped mid-turn.
        """
        message = self._messages.get()
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
          subprocess.CalledProcessError: If the server sent a refusal instead.
        """
        if (refused := message.get("error")) is not None:
            raise Failed(1, self._argv, said, json.dumps(refused))
        return message.get("result")


def _workspace(where: str) -> dict[str, str]:
    """How the directory a session works in is named, which ZCode wants twice.

    Args:
      where: The directory.

    Returns:
      The path, and the key a workspace is remembered under -- the same thing here, since a
      directory is what identifies one and nothing else about it is ours to name.
    """
    return {"workspacePath": where, "workspaceKey": where}


def _provider(model: str) -> str:
    """Which of ZCode's providers serves a model, out of the pair a model here is written as.

    Args:
      model: The model, as `provider/id`.

    Returns:
      The provider, or "" for a model written without one -- which ZCode refuses, where it
      says so rather than here.
    """
    provider, _, _ = model.partition("/")
    return provider


def _model(model: str) -> str:
    """The model itself, out of that pair.

    Args:
      model: The model, as `provider/id`.

    Returns:
      What the provider calls it, which may carry slashes of its own.
    """
    _, _, named = model.partition("/")
    return named or model


def _settling(
    session: str, held: _Held, *, again: bool = False
) -> list[tuple[str, dict[str, Any]]]:
    """The calls that put a session back at the settings its agent is configured with now.

    Args:
      session: The session to settle.
      held: What it is to run, against what it was last told.
      again: Whether every one of them is to be said whether it moved or not, which is what a
        session picked back up on another server needs: nothing there was ever told any of it.

    Returns:
      One `(method, params)` per setting that has to be said, in the order to say them.
    """
    told: tuple[str | None, str | None, str | None] = (
        (None, None, None) if again or held.told is None else held.told
    )
    calls: list[tuple[str, dict[str, Any]]] = []
    if held.model != told[0]:
        calls.append(
            (
                "session/setModel",
                {
                    "sessionId": session,
                    "model": {
                        "providerId": _provider(held.model),
                        "modelId": _model(held.model),
                    },
                    # This agent's model is this agent's. Persisting it would make one flow's
                    # choice the default of whatever the person at this machine opens next.
                    "persistAsWorkspaceLastUsed": False,
                },
            )
        )
    if held.effort != told[1]:
        calls.append(
            (
                "session/setThoughtLevel",
                {
                    "sessionId": session,
                    "thoughtLevel": held.effort,
                    "persistAsWorkspaceLastUsed": False,
                },
            )
        )
    if held.mode != told[2]:
        calls.append(("session/setMode", {"sessionId": session, "mode": held.mode}))
    held.told = (held.model, held.effort, held.mode)
    return calls


class _Saying:
    """What one model's answer has said so far, and what of it has been shown.

    The words arrive a fragment at a time and are worth one row of a transcript rather than
    fifty, so they are gathered here and said whole -- at the moment the agent reaches for
    something, since what it said before reaching is what says why it reached, and again when
    the answer ends. What has already been shown is remembered so that the end of a message
    says only the part of it nobody has seen.
    """

    def __init__(self) -> None:
        """Initializes a reading in which nothing has been said yet."""
        #: What has been thought and what has been said, by the message each belongs to, and
        #: how much of the words have been shown.
        self._thinking: dict[str, str] = {}
        self._words: dict[str, str] = {}
        self._shown: dict[str, int] = {}
        #: Which message is being streamed, because the event that ends one does not name it:
        #: what has just come back is what the pieces before it were pieces of.
        self._latest = ""

    def streamed(self, payload: dict[str, Any]) -> Iterator[Event]:
        """Reads one piece of a model's answer, and says what that piece is worth showing.

        Args:
          payload: The `model.streaming` payload, as read.

        Yields:
          The reasoning and the words that led up to a tool call, and then the call itself.
        """
        marked = str(payload.get("assistantMessageId") or "")
        self._latest = marked or self._latest
        match payload.get("kind"):
            case "reasoning_delta":
                self._thinking[marked] = self._thinking.get(marked, "") + str(
                    payload.get("delta") or ""
                )
            case "text_delta":
                self._words[marked] = self._words.get(marked, "") + str(
                    payload.get("delta") or ""
                )
            case "tool_call":
                yield from self._upto(marked, self._words.get(marked, ""))
                called = str(payload.get("toolName") or "tool")
                given = cast("dict[str, Any]", payload.get("input") or {})
                about = str(given.get(_ABOUT.get(called, ""), "") or "") or next(
                    (
                        value
                        for value in given.values()
                        if isinstance(value, str) and value.strip()
                    ),
                    "",
                )
                yield Event(kind="tool", text=f"{called} {about}".strip()[:120])
            case _:  # the pieces of a tool's arguments on the way to the call itself
                pass

    def ended(self, marked: str, content: str) -> Iterator[Event]:
        """Says whatever of one message has not been said, now that it has ended.

        Args:
          marked: The message that ended, or "" for the event that names none -- which is the
            one the server ends every message with, so the one being streamed is the one meant.
          content: The whole of it, as the server has it -- which is the deltas put back
            together, and is what a model that streamed nothing said in one piece.

        Yields:
          The reasoning and the words nobody has seen yet.
        """
        marked = marked or self._latest
        yield from self._upto(marked, content or self._words.get(marked, ""))
        self._thinking.pop(marked, None)
        self._words.pop(marked, None)
        self._shown.pop(marked, None)

    def _upto(self, marked: str, words: str) -> Iterator[Event]:
        """Says one message as far as it has got, and remembers how far that was.

        Args:
          marked: The message.
          words: The whole of what it has said so far.

        Yields:
          What it thought, the once, and the words beyond the ones already shown.
        """
        if thought := self._thinking.pop(marked, "").strip():
            yield Event(kind="reasoning", text=thought)
        rest = words[self._shown.get(marked, 0) :]
        self._shown[marked] = len(words)
        if said := rest.strip():
            yield Event(kind="text", text=said)


def _spent(counted: dict[str, Any]) -> Usage:
    """What one request of a turn cost, by the kind each token went on.

    Args:
      counted: The `usage` the server stated, as read.

    Returns:
      What it spent, which is nothing at all for a count that says nothing.
    """
    return Usage(
        {
            kind: float(counted.get(named) or 0)
            for kind, named in _KINDS.items()
            if counted.get(named)
        }
    )


@dataclass(frozen=True, kw_only=True)
class ZcodeAgentConfig(AgentConfig):
    """What ZCode is configured with: the common model and effort, and nothing else.

    The model is written as ZCode writes it, `provider/id`, since a model here belongs to the
    provider serving it and the app server is asked for the pair.
    """


class ZcodeSession(SessionBase):
    """A ZCode conversation, held as a session by the app server its agent runs.

    The session is ZCode's own and outlives this process, but the model it runs on does not:
    the server materialises that when the session is opened and keeps it in memory. So a
    conversation carries on for as long as the server holding it does, and one picked back up
    on a server started since -- which is what a fallback onto another account leaves behind --
    is refused by ZCode with its own reason for it.
    """

    _agent: ZcodeAgent  # every turn is run on the app server this agent holds

    def __init__(
        self, agent: AgentBase, cwd: str | os.PathLike[str] | None = None
    ) -> None:
        """Initializes a session holding no ZCode session yet.

        Args:
          agent: The agent whose config every turn of this session runs at.
          cwd: The directory this conversation works in, as for `SessionBase`.
        """
        super().__init__(agent, cwd)
        #: What the server has been told this session runs, and what its turns cost.
        self._held = _Held(spends=self._spends)
        #: The session ZCode named, known before the turn it was opened for has landed.
        self._opening: str | None = None

    @property
    def named(self) -> str | None:
        """The ZCode session this is, which the server names before the turn starts."""
        return self._id or self._opening

    def _stream(
        self, prompt: str, *, schema: type[BaseModel] | None = None
    ) -> Iterator[Event]:
        """Sends one turn to the server, saying what the agent says as it says it.

        Args:
          prompt: The input prompt for this turn.
          schema: The shape to answer in, already asked for in the prompt: the protocol has no
            way of holding a turn to one.

        Yields:
          What the agent said, in the order it said it.

        Raises:
          subprocess.CalledProcessError: If the turn was refused or failed, or the server
            stopped while it was running.
        """
        del schema  # asked for in the prompt, since ZCode has no setting for it
        with self._lock:  # a conversation is a sequence: one turn at a time
            server = self._agent.server
            session = self._session(server)
            said = ""
            spent: Mapping[str, int] = {}
            costing = Usage()
            for event in server.turn(session, prompt, self._held):
                if event.kind == "result":
                    said, spent, costing = event.text, event.tokens, event.spent
                    continue
                if not self._agent._watchers:
                    # On stderr, where every other backend puts its progress: a turn nobody can
                    # watch is a flow that reads as hung for as long as the turn takes.
                    say(event.text, sys.stderr)
                yield event
            if not self._agent._watchers:
                say(said, sys.stdout)
            self._adopt(session)  # a turn has landed, so the session is open
            yield Event(kind="result", text=said, tokens=spent, spent=costing)

    def _pursue(self, objective: str) -> str:
        """Runs the turn under a goal of ZCode's own, which it steers until it is met.

        Args:
          objective: What the agent is to have achieved before it stops.

        Returns:
          What ZCode said once the goal stopped, stripped.

        Raises:
          subprocess.CalledProcessError: If any of the calls a goal is made of is refused,
            leaving the session unopened so that the next call retries it.
        """
        with self._lock:  # a conversation is a sequence: one turn at a time
            server = self._agent.server
            session = self._session(server)
            said = server.pursue(session, objective, self._held)
            self._adopt(session)
            return said

    def _session(self, server: _AppServer) -> str:
        """The ZCode session this is, opened or settled as needed.

        Args:
          server: The app server this agent's turns run on now.

        Returns:
          The session's id.

        Raises:
          subprocess.CalledProcessError: If the server refused to open or pick one up.
        """
        config = self._agent.config
        self._held.model = config.model
        self._held.effort = self.effort
        self._held.mode = _PERMITTED.get(config.permission, _PERMITTED["bypass"])
        searches = config.web_search
        if (session := self.named) is None:
            self._opening = server.open(
                self._workspace(), self._held, searches=searches
            )
            return self._opening
        if session not in server.sessions:
            server.resume(session, self._workspace(), self._held, searches=searches)
            return session
        server.settle(session, self._held)
        return session


class ZcodeAgent(AgentBase):
    """ZCode, driven over its own app server so that a turn can name what it runs on.

    Every moment a turn passes through, and one more: at the rungs where the agent may ask for
    more than it has, the server asks and waits for the answer -- so that is the one place a
    hook here can say no to something and have the agent hear it. At `bypass` it is never
    asked, and a hook hung on that moment never fires.
    """

    moments: ClassVar[frozenset[Moment]] = EVERYWHERE | {Moment.PERMISSION_REQUEST}

    #: ZCode keeps itself going toward an objective, which is what `pursue` reaches for.
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

    @property
    def server(self) -> _AppServer:
        """The app server this agent's turns run on, started the first time one is needed.

        One per agent rather than one per session, so a flow that drops a session a turn does
        not start a server a turn; it is taken down when the agent is collected, or at exit for
        one held to the end. An anchored agent starts it through coganchor, which leaves the
        server here, holding the session, and its work on the target.
        """
        with (
            self._serving
        ):  # two sessions of one agent share the server rather than start two
            if self._server is not None and self._server_as != self.node().name:
                # Started as an account this agent has since left. Let go of rather than taken
                # down: a turn on another thread may still be talking to it, and it is stopped
                # by its own finalizer when the agent is collected either way.
                self._server, self._server_as = None, ""
            if self._server is None:
                # Read before the environment is built out of it: a fallback landing between
                # the two reads would name the account this server is *not* signed into.
                account = self.node().name
                argv = ["zcode", "app-server", "--stdio"]
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

    def new(self, cwd: str | os.PathLike[str] | None = None) -> ZcodeSession:
        """Opens a new ZCode session, in the directory it is given or in this one."""
        return ZcodeSession(self, cwd)

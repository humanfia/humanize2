"""Any CLI that speaks the Agent Client Protocol, driven as one of these.

The protocol is the whole of what is known about such a backend: humanize is handed a command
to run and speaks JSON-RPC to it over its own stdin and stdout, one message a line. That is
enough to hold a conversation -- `session/new` opens one, `session/prompt` takes a turn, and
the agent says what it is doing in `session/update` notifications while the turn runs.

It is not enough to know anything else. ACP says nothing about which models an agent runs or
how hard it can be asked to think, so neither is offered: the agent runs as whoever installed
it configured it. What it does say is that a client is asked to permit each tool call, and
nobody is at a prompt here -- so every request is granted, by the *kind* of the option rather
than by its id, which is the agent's own to name.
"""

from __future__ import annotations

import json
import subprocess
import threading
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar, cast

from .base import AgentBase, SessionBase
from .config import AgentConfig
from .event import Event

if TYPE_CHECKING:
    import os
    from collections.abc import Iterator

    from pydantic import BaseModel

#: The version of the protocol this speaks, as an integer. Sent on the way in; an agent that
#: answers with another is answering about itself, not refusing.
_VERSION = 1

#: What this client can do, which is nothing beyond being talked to. A client that says it
#: reads files or holds terminals is a client the agent will ask to do those things, and the
#: agent already has a machine of its own to do them on. Saying so keeps the only inbound
#: request `session/request_permission`.
_CAPABILITIES = {
    "fs": {"readTextFile": False, "writeTextFile": False},
    "terminal": False,
}

#: How a tool call is permitted, best first. The kind rather than the id: an id is the agent's
#: own word -- one calls it `proceed_once`, another `allow-once` -- and a client that matched
#: on those would work with the agent it was written against and no other.
_GRANTS = ("allow_always", "allow_once")

#: What each thing said in a turn reads as, by the name ACP gives that kind of update.
_SAYS = {"agent_message_chunk": "text", "agent_thought_chunk": "reasoning"}

#: The reasons a turn can end. The first two are a turn that answered; the rest are one that
#: did not, and a flow told otherwise would be running on an answer nobody gave.
_ANSWERED = ("end_turn", "max_tokens")

#: What ACP says a backend runs and how hard it thinks, which is nothing at all. One of each
#: is offered so that an agent can be configured; both are the agent's own to know.
UNSAID = "as configured"


class _Stopped(Exception):  # noqa: N818 -- not an error of ours: the agent went away
    """The agent went away while something was waiting on it."""


@dataclass
class AcpConnection:
    """One ACP agent, running, and the conversation this client holds with it.

    A process rather than a command per turn: the protocol is a session opened once and
    prompted many times, and the agent is what holds the session.
    """

    argv: list[str]
    environ: dict[str, str] | None = None
    cwd: str | None = None
    proc: subprocess.Popen[str] | None = None
    #: What each request is waiting for, by the id it was sent under, and the lock that keeps
    #: two threads from writing half a line each.
    answers: dict[int, Any] = field(default_factory=dict[int, Any])
    landed: threading.Condition = field(default_factory=threading.Condition)
    writing: threading.Lock = field(default_factory=threading.Lock)
    said: list[dict[str, Any]] = field(default_factory=list[dict[str, Any]])
    at: int = 0

    def start(self) -> None:
        """Spawns the agent, if it is not already up."""
        if self.proc is not None:
            return
        self.proc = subprocess.Popen(
            self.argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
            errors="replace",
            env=self.environ,
            cwd=self.cwd,
        )

    def send(self, method: str, params: dict[str, Any]) -> int:
        """Writes one request and answers with the id it went under.

        Args:
          method: What to ask for.
          params: What to ask it with.

        Returns:
          The id the answer will come back under.

        Raises:
          _Stopped: If the agent is not there to be told.
        """
        with self.writing:
            self.at += 1
            at = self.at
            self._write(
                {"jsonrpc": "2.0", "id": at, "method": method, "params": params}
            )
        return at

    def notify(self, method: str, params: dict[str, Any]) -> None:
        """Writes one notification, which is a message nothing answers."""
        with self.writing:
            self._write({"jsonrpc": "2.0", "method": method, "params": params})

    def reply(self, at: object, result: dict[str, Any]) -> None:
        """Answers something the agent asked us."""
        with self.writing:
            self._write({"jsonrpc": "2.0", "id": at, "result": result})

    def refuse(self, at: object, why: str) -> None:
        """Tells the agent this client does not offer what it asked for.

        Args:
          at: The id it asked under.
          why: What to say, which goes back as the message of a `method not found`.
        """
        with self.writing:
            self._write(
                {
                    "jsonrpc": "2.0",
                    "id": at,
                    "error": {"code": -32601, "message": why},
                }
            )

    def _write(self, message: dict[str, Any]) -> None:
        """Puts one message on the agent's stdin, whole and on one line.

        Raises:
          _Stopped: If there is nothing listening.
        """
        proc = self.proc
        if proc is None or proc.stdin is None:
            raise _Stopped("the agent is not running")
        try:
            # Compact and on one line: the framing is the newline, so a message written with
            # any in it would be read as several.
            proc.stdin.write(json.dumps(message) + "\n")
            proc.stdin.flush()
        except (OSError, ValueError) as gone:
            raise _Stopped("the agent is no longer listening") from gone

    def read(self) -> dict[str, Any] | None:
        """The next message the agent wrote, or None once it has stopped writing."""
        proc = self.proc
        if proc is None or proc.stdout is None:
            return None
        for line in proc.stdout:
            if not line.strip():
                continue
            try:
                said: object = json.loads(line)
            except ValueError:
                continue  # a line of something else, which stdout should not carry
            if isinstance(said, dict):
                return cast("dict[str, Any]", said)
        return None

    def stop(self) -> None:
        """Ends the agent, which is what was holding the conversation open."""
        proc, self.proc = self.proc, None
        if proc is None:
            return
        with contextlib_suppress():
            if proc.stdin is not None:
                proc.stdin.close()
        try:
            proc.wait(timeout=1)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        with contextlib_suppress():
            if proc.stdout is not None:
                proc.stdout.close()
        with contextlib_suppress():
            if proc.stderr is not None:
                proc.stderr.close()


class contextlib_suppress:  # noqa: N801 -- a tiny stand-in, kept local
    """Swallows the errors a descriptor being closed twice raises."""

    def __enter__(self) -> None:
        return None

    def __exit__(self, kind: object, value: object, traceback: object) -> bool:
        return isinstance(value, (OSError, ValueError))


class AcpSession(SessionBase):
    """One ACP conversation, held open on the agent this client spawned.

    The process is the session: ACP opens one with `session/new` and takes as many turns on it
    as it is asked for, so the agent stays up between them rather than being run again.
    """

    #: The protocol has no way of holding a turn to a shape, so one asked for is asked for in
    #: the prompt, as it is for every other backend without a setting for it.
    shapes: ClassVar[bool] = False

    def __init__(
        self, agent: AgentBase, cwd: str | os.PathLike[str] | None = None
    ) -> None:
        """Initializes a session with no agent running yet.

        Args:
          agent: The agent whose command every turn of this session is run against.
          cwd: The directory this conversation works in, as for `SessionBase`.
        """
        super().__init__(agent, cwd)
        self._link: AcpConnection | None = None

    def _connection(self) -> AcpConnection:
        """The agent, started and initialized and holding a session, made on first use.

        Returns:
          The connection, with `session/new` already answered.

        Raises:
          subprocess.CalledProcessError: If the agent will not start, will not speak the
            protocol, or refuses to open a session.
        """
        if self._link is not None:
            return self._link
        agent = cast("AcpAgent", self._agent)
        argv = self._agent.spawned(list(agent.command), self.cwd)
        link = AcpConnection(
            argv=argv,
            environ=self._environ(),
            cwd=None if self._agent.anchor is not None else self._workspace(),
        )
        try:
            link.start()
            self._settle(
                link,
                link.send(
                    "initialize",
                    {
                        "protocolVersion": _VERSION,
                        "clientCapabilities": _CAPABILITIES,
                        "clientInfo": {"name": "humanize", "version": "1"},
                    },
                ),
            )
            opened = self._settle(
                link,
                link.send(
                    "session/new",
                    {
                        # Absolute, which the protocol requires, and the one the session works in.
                        "cwd": self._workspace(),
                        # Required even when there are none of them.
                        "mcpServers": [],
                    },
                ),
            )
        except _Stopped as gone:
            link.stop()
            raise subprocess.CalledProcessError(1, argv, "", str(gone)) from gone
        except ValueError as refused:
            link.stop()
            raise subprocess.CalledProcessError(1, argv, "", str(refused)) from refused
        self._adopt(str(opened.get("sessionId") or ""))
        self._link = link
        return link

    def _settle(self, link: AcpConnection, at: int) -> dict[str, Any]:
        """Waits for one request to be answered, serving whatever is asked on the way.

        The client has to keep answering while its own request is outstanding: an agent asks
        for permission in the middle of the turn it was told to take, and a client that only
        read its own answer would deadlock against it.

        Args:
          link: The agent.
          at: The id the request went under.

        Returns:
          What it answered with.

        Raises:
          _Stopped: If the agent stopped before answering.
          ValueError: If it answered with an error.
        """
        for event in self._serving(link, at):
            del event  # nothing is shown from here: the turn is what is watched
        answered = link.answers.pop(at)
        if isinstance(answered, Exception):
            raise answered
        return cast("dict[str, Any]", answered)

    def _serving(self, link: AcpConnection, at: int) -> Iterator[Event]:
        """Reads until one request is answered, saying what the agent says on the way.

        Args:
          link: The agent.
          at: The id being waited for.

        Yields:
          What the agent said while it worked.

        Raises:
          _Stopped: If the agent stopped before answering.
        """
        while True:
            message = link.read()
            if message is None:
                link.answers[at] = _Stopped("the agent stopped before it answered")
                raise cast("_Stopped", link.answers[at])
            if "method" in message:
                yield from self._asked(link, message)
                continue
            if message.get("id") != at:
                continue  # an answer to something else, which nothing here is waiting on
            if (failed := message.get("error")) is not None:
                link.answers[at] = ValueError(json.dumps(failed))
            else:
                link.answers[at] = message.get("result") or {}
            return

    def _asked(self, link: AcpConnection, message: dict[str, Any]) -> Iterator[Event]:
        """Answers something the agent said or asked, and says what is worth showing.

        Args:
          link: The agent.
          message: What it sent.

        Yields:
          What it said, for a notification that is the agent talking.
        """
        method = str(message.get("method") or "")
        params = cast("dict[str, Any]", message.get("params") or {})
        if method == "session/update":
            yield from self._told(cast("dict[str, Any]", params.get("update") or {}))
            return
        if "id" not in message:
            return  # a notification of some other kind: nothing to answer, nothing to show
        if method == "session/request_permission":
            link.reply(message["id"], {"outcome": self._permits(params)})
            return
        # Everything else is a thing this client said it could not do, and an agent asking
        # anyway is told so in the protocol's own words rather than left waiting.
        link.refuse(message["id"], f"{method} is not offered")

    def _permits(self, params: dict[str, Any]) -> dict[str, Any]:
        """Grants a tool call, by the kind of the option rather than by its name.

        Args:
          params: What was asked, which carries the options the agent offers.

        Returns:
          The outcome to answer with, which is the chosen option or a refusal where the agent
          offered nothing that would allow it.
        """
        offered = [
            cast("dict[str, Any]", one)
            for one in cast("list[Any]", params.get("options") or [])
            if isinstance(one, dict)
        ]
        for kind in _GRANTS:
            for one in offered:
                if one.get("kind") == kind:
                    return {"outcome": "selected", "optionId": str(one.get("optionId"))}
        # Nothing that grants it: the turn is not ours to hang, so it is answered rather than
        # left, and the agent decides what a refusal means to it.
        if offered:
            return {"outcome": "selected", "optionId": str(offered[0].get("optionId"))}
        return {"outcome": "cancelled"}

    def _told(self, update: dict[str, Any]) -> Iterator[Event]:
        """Reads one `session/update`, whose variant names itself and is flattened beside it.

        Args:
          update: The update, as read.

        Yields:
          What it said, which is nothing for one that moved a state along.
        """
        kind = str(update.get("sessionUpdate") or "")
        if kind == "tool_call":
            named = str(update.get("title") or update.get("kind") or "tool")
            yield Event(kind="tool", text=named[:120])
        elif (says := _SAYS.get(kind)) is not None:
            content = cast("dict[str, Any]", update.get("content") or {})
            if words := str(content.get("text") or ""):
                yield Event(kind=says, text=words)

    def _stream(
        self, prompt: str, *, schema: type[BaseModel] | None = None
    ) -> Iterator[Event]:
        """Takes one turn on the session, saying what the agent says as it says it.

        Args:
          prompt: The input prompt for this turn.
          schema: Unused here: the protocol has no way of holding a turn to a shape, so one
            was asked for in the prompt before this was called.

        Yields:
          What the agent said, and the answer it ended on.

        Raises:
          subprocess.CalledProcessError: If the agent went away, refused, or ended the turn
            on a reason that is not an answer.
        """
        del schema
        link = self._connection()
        said: list[str] = []
        try:
            at = link.send(
                "session/prompt",
                {
                    "sessionId": self.id,
                    "prompt": [{"type": "text", "text": prompt}],
                },
            )
            for event in self._serving(link, at):
                if event.kind == "text":
                    said.append(event.text)
                yield event
            answered = link.answers.pop(at)
        except _Stopped as gone:
            link.stop()
            self._link = None
            raise subprocess.CalledProcessError(
                1, list(cast("AcpAgent", self._agent).command), "".join(said), str(gone)
            ) from gone
        if isinstance(answered, Exception):
            raise subprocess.CalledProcessError(
                1,
                list(cast("AcpAgent", self._agent).command),
                "".join(said),
                str(answered),
            )
        why = str(cast("dict[str, Any]", answered).get("stopReason") or "")
        if why not in _ANSWERED:
            raise subprocess.CalledProcessError(
                1,
                list(cast("AcpAgent", self._agent).command),
                "".join(said),
                f"the turn ended on {why}",
            )
        yield Event(kind="result", text="".join(said).strip())

    def interject(self, text: str) -> None:
        """Says something to the turn already running, which ACP has no way of doing.

        Args:
          text: What would have been said.

        Raises:
          NotImplementedError: Always. Steering is an extension each agent spells its own
            way, and a client that guessed at one would be talking to itself.
        """
        del text
        raise NotImplementedError(
            "the agent client protocol has no way to steer a turn"
        )

    def _shut(self) -> None:
        """Ends the agent, which is what was holding the conversation open."""
        link, self._link = self._link, None
        if link is not None:
            link.stop()


@dataclass(frozen=True, kw_only=True)
class AcpAgentConfig(AgentConfig):
    """What an ACP agent is configured with, which is which CLI it is and little else.

    Attributes:
      cli: The name the CLI was added under, which is what an `-a` calls it.
      command: What to run to start it, or nothing to look it up by name.
    """

    cli: str = ""
    command: tuple[str, ...] = ()


class AcpAgent(AgentBase):
    """A CLI of your own that speaks the Agent Client Protocol."""

    @property
    def backend(self) -> str:
        """The name this CLI was added under, rather than one read off the class.

        Every other backend here is one class apiece, so the class says which it drives. This
        one class drives every CLI anybody adds, so the name is a setting instead.
        """
        held = getattr(self.config, "cli", "") or "acp"
        return str(held)

    @property
    def command(self) -> tuple[str, ...]:
        """What to run to start this agent.

        Returns:
          The command, as it was given when the CLI was added.

        Raises:
          ValueError: If nothing says how to start it, which is a CLI that was never added.
        """
        from hmz import backends

        given = tuple(getattr(self.config, "command", ()) or ())
        if given:
            return given
        found = backends.speaking().get(self.backend)
        if not found:
            raise ValueError(
                f"{self.backend}: no command to start it with; add it with `hmz acp add`"
            )
        return found

    def new(self, cwd: str | os.PathLike[str] | None = None) -> AcpSession:
        """Opens a new conversation, in the directory it is given or in this one."""
        return AcpSession(self, cwd)

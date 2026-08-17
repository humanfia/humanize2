"""Callbacks of the flow's own, handed to a coding agent as tools it may reach for.

A flow drives an agent by saying things to it. This is the other direction: a function the
flow wrote, put in front of the agent as a tool, so that the agent reaching for it is the
flow's own code running -- in the flow's process, with the flow's variables, on the flow's
thread pool -- and what that code answers is what the agent reads back.

Which is what makes an agent able to call a flow. A tool whose callback is
`lambda said: load("official/rlar")(agents, said["task"])` is an agent that can start a loop
of its own and wait for what it comes to, and nothing about that is written into any backend.

The road between the two is the Model Context Protocol, because that is the one way every one
of these CLIs already takes a tool it was not shipped with. It is spoken here rather than
through a client library for the reason `hmz.coganchor` speaks its own protocol here: what is
needed is four methods of a JSON-RPC subset over a pipe, in a process that is threaded rather
than asynchronous, and every library for it is written the other way round. What a backend is
handed is a command to run -- `hmz tools --at <socket>` -- which relays that pipe to this
process. The callback therefore runs where the flow is, which is the whole point: a tool that
ran anywhere else would be a subprocess and not a callback.

What is offered is the agent's rather than one conversation's. A CLI is told about its tools
where it is started, and some of these are started once per agent and hold every conversation
of it, so the tools are the agent's and a conversation says which of them it is adding. Two
conversations offering a tool of one name are offering one tool.
"""

from __future__ import annotations

import json
import socket
import tempfile
import threading
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping

    from pydantic import BaseModel

__all__ = ["PROTOCOL", "Tool", "Toolbox", "serve"]

#: The version of the protocol this speaks, which is what a client is answered with. The
#: revision every one of these CLIs shipped against; a client asking for another is answered
#: with this one, which is what the protocol says to do.
PROTOCOL = "2025-06-18"

#: What the server calls itself where a client asks.
_WHOSE = "humanize"

#: How long a socket that nothing has connected to is waited on before the thread serving it
#: looks again at whether it has been closed. A number rather than a blocking accept, so that
#: taking a toolbox down does not need the socket poked to wake it.
_LOOKING = 0.2

#: What a JSON-RPC error is answered with, by the code the protocol gives each.
_NO_METHOD, _BAD_PARAMS = -32601, -32602


@dataclass(frozen=True, slots=True)
class Tool:
    """One callback of the flow's, as the agent is offered it.

    Attributes:
      name: What the agent calls it, which is what it must be told to use. A tool named for
        what it does is a tool a model reaches for at the right moment.
      about: What it is for, said to the model. This is the whole of what the model knows
        about when to use it, so it is a sentence rather than a label.
      takes: The shape of what it is called with, as a pydantic model, or None for a tool
        that takes nothing. The model is the whole of what the agent is told: its fields,
        their types, which are required and the description each was declared with are
        already in it, so nothing about the arguments is said twice.
      call: What to run when the agent reaches for it. It is given the arguments -- the model
        where one was declared, and nothing at all where none was -- and what it answers is
        put in front of the agent as text. It runs on the thread serving the tool call, which
        is not the thread the flow is on: a callback that touches what the flow is touching
        answers for that itself.
    """

    name: str
    about: str
    call: Callable[..., Any]
    takes: type[BaseModel] | None = None

    def schema(self) -> dict[str, Any]:
        """What the agent is told this tool takes, as the JSON Schema the protocol wants.

        Returns:
          The model's own schema, or the schema of a tool that takes nothing.
        """
        if self.takes is None:
            return {"type": "object", "properties": {}}
        return self.takes.model_json_schema()

    def called(self, given: Mapping[str, Any]) -> str:
        """Runs the callback and says what it answered, in words the agent can read.

        Args:
          given: What the agent called it with.

        Returns:
          What the callback answered, as text. A callback that answers with nothing is a tool
          that did something rather than one that failed, and says so.

        Raises:
          Exception: Whatever the callback raised, which is answered to the agent as the tool
            having failed rather than as the turn having failed: a flow must not end because
            a model called one of its tools wrongly.
        """
        said = self.call() if self.takes is None else self.call(self.takes(**given))
        if said is None:
            return "done"
        return said if isinstance(said, str) else json.dumps(said, default=str)


class Toolbox:
    """The callbacks one agent's conversations are offering, served over a socket.

    Held by the agent rather than by a session, for the reason its hooks are: a CLI is told
    about its tools where it is started, and the backends that hold one process for every
    conversation of an agent would otherwise have to be told twice.

    Nothing is started until something is offered: an agent whose flow hands it no callbacks
    has no socket, no thread and no bridge, and its turns are the turns they always were.
    """

    def __init__(self) -> None:
        """Initializes a toolbox nothing has been put in and nothing is serving."""
        #: What each conversation is offering, by the id of the conversation: a session that
        #: stops offering something takes it away, and one that never offered anything is not
        #: in here at all.
        self._held: dict[int, tuple[Tool, ...]] = {}
        self._lock = threading.RLock()
        self._at: str = ""
        self._sock: socket.socket | None = None
        self._serving: threading.Thread | None = None
        self._closed = threading.Event()
        self._where: tempfile.TemporaryDirectory[str] | None = None

    def offers(self, whose: int, tools: Iterable[Tool]) -> None:
        """Says which callbacks one conversation is putting in front of the agent.

        Args:
          whose: Which conversation, by a number nothing else answers to.
          tools: The callbacks, or nothing at all to take back whatever it was offering.
        """
        held = tuple(tools)
        with self._lock:
            if held:
                self._held[whose] = held
            else:
                self._held.pop(whose, None)

    def offered(self) -> tuple[Tool, ...]:
        """Every callback in front of the agent now, one per name.

        Returns:
          The tools, in the order the conversations offering them were opened. Two
          conversations offering a tool of one name are offering one tool, the agent having
          one list.
        """
        with self._lock:
            found: dict[str, Tool] = {}
            for tools in self._held.values():
                for one in tools:
                    found.setdefault(one.name, one)
            return tuple(found.values())

    def empty(self) -> bool:
        """Whether nothing is being offered, which is an agent with no tools of the flow's."""
        with self._lock:
            return not self._held

    def address(self) -> str:
        """Where this toolbox is reached, starting it if nothing has yet.

        Returns:
          The path of the socket it serves on, which is under a directory of its own so that
          nothing else on the machine can name it.
        """
        with self._lock:
            if self._sock is not None:
                return self._at
            # A toolbox served again after it was closed is one an agent went on being
            # offered callbacks through: the thread that was looking would otherwise see the
            # old answer and stop before it had taken anything.
            self._closed.clear()
            self._where = tempfile.TemporaryDirectory(
                prefix="humanize-tools-", ignore_cleanup_errors=True
            )
            # Inside a directory this user alone may enter: a socket is a way into this
            # process, and one anybody could connect to is a way in for anybody.
            where = Path(self._where.name)
            where.chmod(0o700)
            self._at = str(where / "tools.sock")
            self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self._sock.bind(self._at)
            self._sock.listen(8)
            self._sock.settimeout(_LOOKING)
            self._serving = threading.Thread(
                target=self._accepts, name="humanize-tools", daemon=True
            )
            self._serving.start()
            return self._at

    def command(self) -> list[str]:
        """What a coding agent is told to run to reach these callbacks.

        Returns:
          The bridge, as argv: it relays the pipe its CLI speaks the protocol over to the
          socket this is served on, so that the callback runs in this process.
        """
        import sys

        return [sys.executable, "-m", "hmz", "tools", "--at", self.address()]

    def config(self, named: str = _WHOSE) -> dict[str, Any]:
        """These callbacks as the entry a CLI's own MCP configuration holds.

        Args:
          named: What the server is called there, which is what the agent's tools are
            prefixed with wherever a backend prefixes them.

        Returns:
          The mapping every one of these CLIs reads a stdio server out of.
        """
        argv = self.command()
        return {
            "mcpServers": {
                named: {"type": "stdio", "command": argv[0], "args": argv[1:]}
            }
        }

    def close(self) -> None:
        """Stops serving, and takes the socket away. Doing it twice does it once."""
        self._closed.set()
        with self._lock:
            sock, self._sock = self._sock, None
            where, self._where = self._where, None
        if sock is not None:
            sock.close()
        if where is not None:
            where.cleanup()

    def _accepts(self) -> None:
        """Takes each connection and serves it on a thread of its own, until this is closed."""
        while not self._closed.is_set():
            sock = self._sock
            if sock is None:
                return
            try:
                held, _from = sock.accept()
            except TimeoutError:
                continue
            except OSError:
                return  # closed under us, which is what closing does
            threading.Thread(
                target=self._serves, args=(held,), name="humanize-tool", daemon=True
            ).start()

    def _serves(self, held: socket.socket) -> None:
        """Answers one client for as long as it is connected.

        Args:
          held: The connection.
        """
        with held, held.makefile("rwb") as stream:
            for line in stream:
                answer = serve(line.decode("utf-8", "replace"), self.offered)
                if answer is None:
                    continue  # a notification, which is not answered
                stream.write((json.dumps(answer) + "\n").encode())
                stream.flush()


@dataclass(frozen=True, slots=True)
class _Refused(Exception):  # noqa: N818  -- what it is, not what went wrong
    """One call that could not be made, as the error to answer it with."""

    code: int
    said: str = field(default="")


def serve(line: str, offered: Callable[[], tuple[Tool, ...]]) -> dict[str, Any] | None:
    """Answers one line of the protocol, which is one JSON-RPC message.

    Written as a function of the line so that what the protocol says is one thing to read and
    one thing to test, whatever is carrying it.

    Args:
      line: The message, as it was written.
      offered: What the tools are now, asked afresh per message: a conversation may offer
        another between two turns, and a list read once would be the list it had then.

    Returns:
      What to answer with, or None for a notification and for a line that is not a message at
      all -- neither is answered, the protocol having nowhere to put the answer.
    """
    try:
        held: object = json.loads(line)
    except ValueError:
        return None
    if not isinstance(held, dict):
        return None
    said = cast("dict[str, Any]", held)
    if "method" not in said:
        return None
    marked = said.get("id")
    method = str(said.get("method") or "")
    given = cast("dict[str, Any]", said.get("params") or {})
    if marked is None:
        return (
            None  # a notification: `initialized`, `cancelled`, and whatever comes next
        )
    try:
        return {
            "jsonrpc": "2.0",
            "id": marked,
            "result": _answers(method, given, offered),
        }
    except _Refused as refused:
        return {
            "jsonrpc": "2.0",
            "id": marked,
            "error": {"code": refused.code, "message": refused.said},
        }


def _answers(
    method: str, given: dict[str, Any], offered: Callable[[], tuple[Tool, ...]]
) -> dict[str, Any]:
    """What one call is answered with.

    Args:
      method: What was asked for.
      given: What it was asked with.
      offered: What the tools are now.

    Returns:
      The result.

    Raises:
      _Refused: If nothing here answers that method, or the call names no tool there is.
    """
    if method == "initialize":
        return {
            "protocolVersion": PROTOCOL,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": _WHOSE, "version": "0.1.0"},
        }
    if method == "ping":
        return {}
    if method == "tools/list":
        return {
            "tools": [
                {
                    "name": one.name,
                    "description": one.about,
                    "inputSchema": one.schema(),
                }
                for one in offered()
            ]
        }
    if method != "tools/call":
        raise _Refused(_NO_METHOD, f"{method} is not something humanize serves")
    named = str(given.get("name") or "")
    tool = next((one for one in offered() if one.name == named), None)
    if tool is None:
        raise _Refused(_BAD_PARAMS, f"there is no tool called {named!r}")
    try:
        said = tool.called(cast("dict[str, Any]", given.get("arguments") or {}))
    except Exception as why:  # noqa: BLE001 -- the model's mistake, not the flow's failure
        # Answered as the tool having failed rather than raised out of the turn: a flow must
        # not end because a model called one of its tools wrongly, and the model reading what
        # went wrong is a model that can call it again correctly.
        return {
            "content": [{"type": "text", "text": _plainly(why)}],
            "isError": True,
        }
    return {"content": [{"type": "text", "text": said}], "isError": False}


def _plainly(why: BaseException) -> str:
    """What a callback that raised said, as the agent is told it.

    Args:
      why: What was raised.

    Returns:
      The exception in one line, with its type where its message says nothing -- a
      `KeyError('task')` on its own is a line nobody can act on.
    """
    said = str(why).strip() or traceback.format_exception_only(why)[-1].strip()
    return f"{type(why).__name__}: {said}" if said != type(why).__name__ else said

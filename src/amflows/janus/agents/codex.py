"""Codex: ``codex exec`` for a turn, and the app server behind ``/goal`` for a goal.

``codex exec`` runs a turn and stops. A goal is a setting of the thread rather than a word in
the prompt -- ``/goal`` is what the interactive client calls ``thread/goal/set`` from -- and
``codex app-server`` is the same binary serving that client, so it is where a flow reaches the
same feature from.
"""

from __future__ import annotations

import contextlib
import json
import queue
import re
import subprocess
import sys
import threading
import weakref
from dataclasses import dataclass
from typing import Any

from .base import AgentBase, CommandSessionBase, say
from .config import AgentConfig

_SESSION_ID = re.compile(r"^session id: (\S+)$", re.MULTILINE)

#: How long a server being taken down is given to go before it is left to the operating system,
#: and how long an idle thread is given to carry a goal on by itself before the goal is over.
_STOP_SECONDS = 5.0
_QUIET_SECONDS = 60.0


class _AppServer:
    """A `codex app-server` of our own, spoken to in JSON-RPC over its stdio."""

    def __init__(self, argv: list[str]):
        """Starts the server and introduces this flow to it.

        Args:
          argv: The command that starts it, already wrapped for wherever its work is to land.

        Raises:
          subprocess.CalledProcessError: If it will not be introduced to, which is every turn
            it would have been asked for failing at the first one instead.
        """
        self._argv = argv
        self._proc = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            # Its log is nobody's: what a flow watches is the agent, which comes over stdout.
            stderr=subprocess.DEVNULL,
            encoding="utf-8",
            errors="replace",
        )
        self._pending = 0
        self._messages: queue.Queue[dict[str, Any] | None] = queue.Queue()
        # Read from a thread of its own, so that a turn can wait on the server for a while
        # rather than only for as long as it takes.
        threading.Thread(target=self._pump, daemon=True).start()
        # One stream, shared by every session of the agent: a call is a write and the reads
        # up to its answer, and two of them interleaved would each take the other's messages.
        self._speaking = threading.Lock()
        self.call("initialize", {"clientInfo": {"name": "janus", "version": "0"}})
        self._write({"jsonrpc": "2.0", "method": "initialized", "params": {}})

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
            self._pending += 1
            ident = self._pending
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
            self._pending += 1
            ident = self._pending
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
                if idle and not pursuing:
                    break
            say(said, sys.stdout)  # where `codex exec` would have put the answer
            return said.strip()

    def stop(self) -> None:
        """Takes the server down, leaving the threads it held on disk."""
        self._proc.terminate()
        # Reaped rather than left: a flow that cycles through agents would otherwise gather a
        # zombie for each one it let go of.
        with contextlib.suppress(subprocess.TimeoutExpired):
            self._proc.wait(timeout=_STOP_SECONDS)

    def _write(self, message: dict[str, Any]) -> None:
        """Puts one JSON-RPC message on the server's stdin.

        Args:
          message: The message to send.

        Raises:
          subprocess.CalledProcessError: If the server has stopped reading.
        """
        assert self._proc.stdin is not None
        try:
            self._proc.stdin.write(json.dumps(message) + "\n")
            self._proc.stdin.flush()
        except OSError as gone:
            raise subprocess.CalledProcessError(1, self._argv, "", str(gone)) from gone

    def _pump(self) -> None:
        """Reads the server's whole stream, teeing the agent's words to ours as they arrive."""
        assert self._proc.stdout is not None
        for line in self._proc.stdout:
            message: dict[str, Any] = json.loads(line)
            if message.get("method") == "item/agentMessage/delta":
                # So that a goal running for an hour stays as watchable as a turn that prints.
                say(message["params"]["delta"], sys.stderr, end="")
            self._messages.put(message)
        self._messages.put(None)  # it has stopped, and nothing more is coming

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
            raise subprocess.CalledProcessError(
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
            raise subprocess.CalledProcessError(
                1, self._argv, said, json.dumps(refused)
            )
        return message.get("result")


@dataclass(frozen=True, kw_only=True)
class CodexAgentConfig(AgentConfig):
    """What Codex is configured with: the common model and effort, and nothing else."""


class CodexSession(CommandSessionBase):
    """A Codex conversation, addressed by the id ``codex exec`` announces before it starts work.

    Codex has no way to pin the id up front and ``resume --last`` takes whichever session in
    this directory is newest, so the id is read back from the first turn instead.
    """

    _agent: CodexAgent  # a goal is run on the app server this agent holds

    def _turn(self, prompt: str) -> tuple[list[str], str | None]:
        """Builds ``codex exec [resume <id>]`` with the prompt on stdin."""
        resume = ["resume", self._id] if self._id else []
        return (
            [
                "codex",
                "exec",
                *resume,
                "--dangerously-bypass-approvals-and-sandbox",
                "--skip-git-repo-check",
                "--model",
                self._agent.config.model,
                "-c",
                f'model_reasoning_effort="{self._agent.config.effort}"',
                "-c",
                'service_tier="default"',
                "-",  # take the prompt from stdin
            ],
            prompt,
        )

    def _read_session_id(self, transcript: str) -> str:
        """Reads ``session id: <uuid>`` out of the header Codex prints before it starts work.

        Raises:
          RuntimeError: If the header is missing, which means the id cannot be resumed.
        """
        match = _SESSION_ID.search(transcript)
        if match is None:
            raise RuntimeError("codex exec printed no session id")
        return match.group(1)

    def pursue(self, objective: str) -> str:
        """Runs the turn under a goal of Codex's own, which its runtime steers until it is met.

        The thread is the session either way -- one opened here is the one ``codex exec resume``
        goes on with -- so a flow may set a goal on a session it has been running turns in, and
        run turns in one it has set a goal on.

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
            if (thread := self._id) is None:
                thread = server.call(
                    "thread/start",
                    {
                        "cwd": self._workspace(),
                        "model": config.model,
                        # What `codex exec` is run with here: a flow watches its agent rather
                        # than answering it.
                        "approvalPolicy": "never",
                        "sandbox": "danger-full-access",
                        "serviceTier": "default",
                    },
                )["thread"]["id"]
            else:
                # A session that has been running turns is one the server has never held, and
                # a goal is set on a thread it is holding.
                server.call("thread/resume", {"threadId": thread})
            server.call("thread/goal/set", {"threadId": thread, "objective": objective})
            answer = server.pursue(
                {
                    "threadId": thread,
                    "input": [{"type": "text", "text": objective}],
                    "model": config.model,
                    "effort": config.effort,
                }
            )
            self._adopt(thread)
            return answer


class CodexAgent(AgentBase):
    """Codex, which takes the prompt on stdin and the effort via ``model_reasoning_effort``."""

    def __init__(self, config: AgentConfig, *, name: str | None = None):
        """Initializes an agent whose app server is not running yet.

        Args:
          config: The model and effort every session of this agent runs at.
          name: What to call this agent, defaulting to one nothing else answers to.
        """
        super().__init__(config, name=name)
        self._server: _AppServer | None = None
        self._serving = threading.Lock()

    @property
    def server(self) -> _AppServer:
        """The app server this agent's goals run on, started the first time one is asked for.

        One per agent rather than one per session, so a flow that drops a session a turn does
        not start a server a turn; it is taken down when the agent is collected, or at exit for
        one held to the end. An anchored agent starts it through coganchor, which leaves the
        server here, holding the thread, and its work on the target -- the same split ``codex
        exec`` runs under. A flow that never sets a goal never starts one.
        """
        with (
            self._serving
        ):  # two sessions of one agent share the server rather than start two
            if self._server is None:
                argv = ["codex", "app-server", "--stdio"]
                if (anchor := self.anchor) is not None:
                    argv = anchor.command(argv)
                self._server = _AppServer(argv)
                # Held by the finalizer alone, which is what takes the server down: when the
                # agent is collected, and at exit for one held to the end.
                weakref.finalize(self, self._server.stop)
            return self._server

    def launch(self) -> CodexSession:
        """Creates a new Codex session."""
        return CodexSession(self)

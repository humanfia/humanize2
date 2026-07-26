"""Kimi Code: the app server it serves itself from, where a session is more than its prompts.

``kimi --prompt`` takes a prompt and nothing else. A ``/goal`` written into one is text the model
reads rather than a goal its runtime keeps, there is no flag for swarm mode, the effort an agent
is configured with has nowhere to go, and a turn already running has nowhere to be talked to.
``kimi web`` is the same binary serving the sessions its own browser client drives, and there
all four are things done to the session a turn is submitted to.
"""

from __future__ import annotations

import collections
import contextlib
import json
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import weakref
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from .base import AgentBase, Event, SessionBase, say
from .config import AgentConfig

#: The one line `kimi web` prints once it is listening, and the only place the port it took --
#: asked for as 0, so that two flows on one machine cannot collide -- and its token are said.
_LISTENING = re.compile(r"^Kimi server: (\S+)/#token=(\S+)$")

#: What an effort is prefixed with to ask for swarm mode: `max` and `swarmmax` are the same
#: thinking, run as one agent and as a fleet of them.
_SWARM = "swarm"


@dataclass
class _Running:
    """The turn under way, if one is: which session it is in, and what it is running at.

    Written as the turn opens and cleared when it is over, read by whoever wants to put a word
    in. A prompt sent to a session that is working is queued rather than run, and steering it
    is what moves it into the turn already running instead of leaving it for the next one.
    """

    session: str | None = None
    config: dict[str, Any] = field(default_factory=dict)


#: How often a running turn is asked whether it is still running, how long one call may take,
#: and how long a daemon being taken down is given to go before it is left to the system.
_POLL_SECONDS = 1.0
_CALL_SECONDS = 60.0
_STOP_SECONDS = 5.0


class _AppServer:
    """A `kimi web` daemon of our own, and the calls one turn of a session is made of."""

    def __init__(self, argv: list[str]):
        """Starts the daemon and waits for it to say where it is listening.

        Args:
          argv: The command that starts it, already wrapped for wherever its work is to land.

        Raises:
          subprocess.CalledProcessError: If it stops without ever saying, which would leave a
            flow waiting on a server that is not there. Reported as a failed turn, because it
            is the turn that starts it that has nowhere to run.
        """
        self._argv = argv
        self._proc = subprocess.Popen(
            argv,
            # Its log is nobody's to read; what is wanted from it is the one line below.
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            encoding="utf-8",
            errors="replace",
        )
        assert self._proc.stdout is not None
        for line in self._proc.stdout:
            if (listening := _LISTENING.match(line.strip())) is not None:
                self._base = f"{listening[1]}/api/v1"
                self._token = listening[2]
                break
        else:
            raise subprocess.CalledProcessError(
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
        request = urllib.request.Request(
            self._base + path,
            data=None if body is None else json.dumps(body).encode(),
            method=method,
            headers={
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=_CALL_SECONDS) as response:
                return json.load(response)["data"]
        except urllib.error.HTTPError as refused:
            raise subprocess.CalledProcessError(
                refused.code, self._argv, "", refused.read().decode(errors="replace")
            ) from refused
        except OSError as unreachable:  # a daemon that died, or a call that timed out
            raise subprocess.CalledProcessError(
                1, self._argv, "", str(unreachable)
            ) from unreachable

    def stop(self) -> None:
        """Takes the daemon down, leaving the sessions it held on disk."""
        self._proc.terminate()
        # Reaped rather than left: a flow that cycles through agents would otherwise gather a
        # zombie for each one it let go of.
        with contextlib.suppress(subprocess.TimeoutExpired):
            self._proc.wait(timeout=_STOP_SECONDS)


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

    def __init__(self, agent: AgentBase):
        """Initializes a session running nothing yet.

        Args:
          agent: The agent whose config every turn of this session runs at.
        """
        super().__init__(agent)
        #: The turn under way, which is what a word put in is steered into.
        self._running = _Running()

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
        server = self._agent.server
        queued = server.call(
            "POST",
            f"/sessions/{running.session}/prompts",
            {"content": [{"type": "text", "text": text}], **running.config},
        )
        server.call(
            "POST",
            f"/sessions/{running.session}/prompts:steer",
            {"prompt_ids": [queued["prompt_id"]]},
        )

    def _stream(self, prompt: str) -> Iterator[Event]:
        """Sends one turn, opening the session on the first call and resuming it after.

        The server answers a turn whole, so a turn has one thing to say and says it at the end.
        What the agent wrote on the way is teed as it arrives, the way it always was.
        """
        yield Event(kind="result", text=self._submit(prompt, goal=False))

    def pursue(self, objective: str) -> str:
        """Runs the turn under a goal of Kimi's own, which its runtime steers until it is met.

        The objective is the prompt as well as the goal, which is what ``/goal`` does: the
        agent is told what to do, and the runtime is told what it is for.
        """
        return self._submit(objective, goal=True)

    def _submit(self, prompt: str, *, goal: bool) -> str:
        """Runs one turn, teeing what the agent says as it says it.

        A goal-driven turn is many turns of the model, and it is over when the session falls
        idle rather than when the first of them ends. The session is asked whether it is still
        running before its messages are read, so that nothing said between the two is missed.

        Args:
          prompt: The input prompt for this turn, which is the objective as well when it is
            a goal the session is being set.
          goal: Whether to set the prompt as the session's goal before sending it.

        Returns:
          The response generated by the agent, stripped.

        Raises:
          subprocess.CalledProcessError: If the daemon refuses any of the calls a turn is made
            of, leaving the session unopened so that the next call retries the turn.
        """
        effort = self._agent.config.effort
        turn: dict[str, Any] = {
            "model": self._agent.config.model,
            "thinking": effort.removeprefix(_SWARM),
            # A flow watches its agent rather than answering it, as the flows amflows comes with do.
            "permission_mode": "auto",
            "plan_mode": False,
            "swarm_mode": effort.startswith(_SWARM),
        }
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
                while True:
                    busy = server.call("GET", f"/sessions/{session}/status")["busy"]
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
                        for block in message["content"][shown.get(message["id"], 0) :]:
                            if block["type"] == "tool_use":
                                say(block["tool_name"], sys.stderr)
                            elif block["type"] == "text":
                                say(block["text"], sys.stderr)
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
                        say(
                            answer, sys.stdout
                        )  # where the CLI would have put the response
                        return answer.strip()
                    # A session says it has stopped before the last thing it said can be read
                    # back, so what it said is read once more after it stops rather than at the
                    # moment it does -- otherwise a turn returns everything but its answer.
                    settled = not busy
                    time.sleep(_POLL_SECONDS)

            finally:
                self._running = _Running()


class KimiCodeCLIAgent(AgentBase):
    """Kimi Code, driven through an app server of its own so a whole session is settable."""

    def __init__(self, config: AgentConfig, *, name: str | None = None):
        """Initializes an agent whose server is not running yet.

        Args:
          config: The model and effort every session of this agent runs at.
          name: What to call this agent, defaulting to one nothing else answers to.
        """
        super().__init__(config, name=name)
        self._server: _AppServer | None = None
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
                if (anchor := self.anchor) is not None:
                    argv = anchor.command(argv)
                self._server = _AppServer(argv)
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

    def launch(self) -> KimiCodeCLISession:
        """Creates a new Kimi Code session."""
        return KimiCodeCLISession(self)

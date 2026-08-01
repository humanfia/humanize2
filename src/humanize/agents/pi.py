"""pi: one ``pi --mode rpc`` held open, spoken to in JSON a line at a time.

``pi -p`` runs a turn and stops, which leaves nowhere to put a later word and no way to move
the thinking level once a session is going. ``pi --mode rpc`` is the same binary headless: the
session stands, turns are commands written to its stdin, and what it says comes back as the
same events its print mode writes. Steering a running turn, changing the effort mid-session
and asking what the session has spent are all commands there, and none of them is a flag.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from .base import AgentBase, StreamSessionBase
from .config import AgentConfig
from .event import Event, Question, Usage

if TYPE_CHECKING:
    import os
    from collections.abc import Iterator

#: What each kind of thing pi says a turn did reads as. A message is a list of parts and pi
#: says each of them twice -- once as it starts and once with the whole of it -- so only the
#: ends are read: they are the only ones that carry any words.
_PARTS = {"text_end": "text", "thinking_end": "reasoning", "toolcall_end": "tool"}

#: The ways an extension may stop a turn to ask the person at the prompt something. The rest
#: of what one may put on the screen -- a notice, a status, a widget -- is told rather than
#: asked, and pi waits on none of it.
_ASKS = ("select", "confirm", "input", "editor")

#: What pi offers for a question that is a yes or a no, so that it reads as a question
#: wherever it is shown rather than as one with nothing to answer it with.
_YES_NO = ("yes", "no")

#: What each kind of token is called in the usage pi reports on every message. Reasoning is
#: counted inside the output rather than beside it, which is why it is not a kind of its own.
_KINDS = {
    "input": "input",
    "output": "output",
    "cache_read": "cacheRead",
    "cache_write": "cacheWrite",
}

#: The tools of pi's own that change something rather than look at something, which is the
#: whole of what an agent that may change nothing is refused. pi has no permission gate and no
#: sandbox -- what it takes is which tools to load -- so `read-only` is the only rung it can be
#: held to, and the three above it are one and the same agent.
_CHANGING = ("bash", "edit", "write")


def _about(called: dict[str, Any]) -> str:
    """What a tool was called with, as the one line a row of a transcript has room for.

    Args:
      called: The tool's arguments, as pi sent them.

    Returns:
      The first thing in it that is words -- the command, the path, the query -- or "".
    """
    return next(
        (
            str(value)
            for value in called.values()
            if isinstance(value, str) and value.strip()
        ),
        "",
    )


@dataclass(frozen=True, kw_only=True)
class PiAgentConfig(AgentConfig):
    """What pi is configured with: the common model and effort, and nothing else.

    The model is written as pi writes it, `provider/id` -- `openai-codex/gpt-5.5` -- since a
    model here belongs to the provider that serves it and pi is asked for the pair.
    """


class PiSession(StreamSessionBase):
    """A pi conversation, addressed by an id chosen up front.

    Pinning beats ``--continue``, which resumes whichever session in this directory is newest:
    a second agent working alongside would steal the resume. The process stands for the life
    of the session rather than the length of a turn, which is what the RPC mode buys: the
    turns of one conversation are commands written to a pi that is already there, and so is
    anything said to it while a turn is running.
    """

    def __init__(
        self, agent: AgentBase, cwd: str | os.PathLike[str] | None = None
    ) -> None:
        """Initializes a session that has spent nothing yet.

        Args:
          agent: The agent whose config every turn of this session runs at.
          cwd: The directory this conversation works in, as for `SessionBase`.
        """
        super().__init__(agent, cwd)
        #: The id pi says this session has, taken only once a turn has landed in it.
        self._named: str | None = None
        #: What the agent has said so far in the turn now running, and what went wrong with
        #: it if anything did. Both are cleared as the turn's answer is given.
        self._said = ""
        self._failed: str | None = None
        #: What the turn now running has cost, added up as pi reports each request: as one
        #: number for the model it ran on, and by the kind each token went on.
        self._spent = 0
        self._costing = Usage()
        #: What the process now up was last told to think at, so that a flow moving the
        #: effort mid-session is told to pi rather than left on the flag it was started with.
        self._at: str | None = None

    @property
    def named(self) -> str | None:
        """What pi calls this conversation, which is the id it was opened with."""
        return self._id or self._named

    def _command(self) -> list[str]:
        """Builds the ``pi --mode rpc`` that reads commands on stdin and says events on stdout.

        Opens the session while it is unopened and resumes it once it has an id -- pi takes
        the same flag for both, making the session it is given when there is none. Which is
        what an anchored session needs: its process ends with each turn, so the next one has a
        conversation to rejoin.
        """
        # A fresh id per attempt: an opening turn that failed may still have left pi holding
        # the session it was given, and retrying under that one would resume a turn that never
        # happened.
        pinned = self._id or str(uuid.uuid4())
        self._named = pinned
        argv = [
            "pi",
            "--mode",
            "rpc",
            "--model",
            self._agent.config.model,
            "--thinking",
            self.effort,
            "--session-id",
            pinned,
        ]
        if self._agent.config.permission == "read-only":
            # Not a mode it is put in but tools it is not given: an agent without the three
            # that change anything is one that can only look, which is the rung asked for.
            argv += ["--exclude-tools", ",".join(_CHANGING)]
        return argv

    def _write(self, text: str, ticket: str = "") -> str:
        """Renders one thing to say as the `prompt` command pi reads it as.

        Args:
          text: What to say.
          ticket: What to name the command by, or "" to leave it unnamed -- pi answers a
            command under the name it was sent with, and the turn's own prompt needs none:
            the turn beginning is what says that one landed.

        Returns:
          The line, newline included.
        """
        said: dict[str, Any] = {"type": "prompt", "message": text}
        if ticket:
            said["id"] = ticket
        line = json.dumps(said) + "\n"
        if self._at is not None and self._at != self.effort:
            # How hard to think is a command here rather than a flag to restart under: pi
            # takes it on the session it is already holding, so a flow that moves the effort
            # is answered by telling it, ahead of the prompt the new effort is for.
            self._at = self.effort
            line = (
                json.dumps({"type": "set_thinking_level", "level": self._at})
                + "\n"
                + line
            )
        return line

    def interject(self, text: str) -> None:
        """Steers the turn under way, which pi takes into the turn it is running.

        Written rather than said: pi answers a whole agent run with one `agent_settled`,
        however many things it was told along the way, so a word put in is not a turn owed an
        answer of its own. What says the model has it is the user message pi splices into the
        conversation as it takes it in, which is a `took` event.

        Args:
          text: What to say to the agent.

        Raises:
          RuntimeError: If no process is up to hear it, which is a session no turn has opened.
        """
        if self._proc is None or self._proc.poll() is not None:
            raise RuntimeError("no turn is running to be talked to")
        # Named by its own words: pi splices a steered message into the conversation as the
        # user saying it, and the words are what both ends have to go on.
        self.steering(text, ticket=text)
        try:
            self._send(json.dumps({"type": "steer", "message": text}) + "\n")
        except BaseException:
            self.unsteered(text)  # nothing is coming back for a word that never went in
            raise

    def _restarted(self) -> None:
        """Forgets the turn the last process was in the middle of, which this one is not."""
        self._said, self._failed, self._spent, self._costing = "", None, 0, Usage()
        self._at = self.effort

    def _read(self, line: str) -> Iterator[Event]:
        """Reads one event pi wrote, as the things it says the agent did.

        Args:
          line: The line, as written.

        Yields:
          What it said, which is nothing for a line saying nothing worth showing: a fragment
          of a message still being written, a tool's result coming back, or an answer to a
          command nobody is waiting on.
        """
        try:
            said: dict[str, Any] = json.loads(line)
        except json.JSONDecodeError:
            return  # not ours: pi prints the odd plain line among the JSON
        match said.get("type"):
            case "session":
                # Noted, not taken: this is said before anything can go wrong, and a session
                # is only opened by a turn that lands in it.
                self._named = str(said.get("id") or "") or self._named
            case "response" if said.get("success") is False:
                # A command pi would not take. The one that matters is the prompt: a turn that
                # was never started is a failed turn, and there is no `agent_settled` coming.
                if said.get("command") == "prompt":
                    yield Event(
                        kind="failed", text=str(said.get("error") or "the turn failed")
                    )
            case "extension_ui_request":
                self._answer(said)
            case "message_update":
                yield from self._part(
                    cast("dict[str, Any]", said.get("assistantMessageEvent") or {})
                )
            case "message_start":
                # A word put into the turn, come back around: pi splices it into the
                # conversation at the step that takes it in, and that splice is the agent
                # saying it has it. The turn's own prompt arrives the same way and was never
                # put into anything, so it is not on the book and says nothing here.
                message: dict[str, Any] = said.get("message") or {}
                if message.get("role") == "user":
                    words = "".join(
                        str(cast("dict[str, Any]", part).get("text") or "")
                        for part in cast("list[Any]", message.get("content") or [])
                        if isinstance(part, dict)
                    )
                    if self.took(words) is not None:
                        yield Event(kind="took", text=words)
            case "message_end":
                self._message(cast("dict[str, Any]", said.get("message") or {}))
            case "agent_settled":
                # The whole of the run pi was told to make, the words put into it included:
                # it says this once it has stopped and has nothing queued behind.
                yield self._answered()
            case _:  # every other event is a step of a turn already read another way
                pass

    def _part(self, event: dict[str, Any]) -> Iterator[Event]:
        """Reads one part of a message pi has finished writing.

        Args:
          event: The `assistantMessageEvent`, as read.

        Yields:
          What the agent said or reached for, and nothing for a part still being written.
        """
        kind = _PARTS.get(str(event.get("type") or ""))
        if kind is None:
            return
        if kind == "tool":
            called: dict[str, Any] = event.get("toolCall") or {}
            arguments: dict[str, Any] = called.get("arguments") or {}
            # The name and what it was called on, which is what a tool call reads as:
            # `bash echo hi`, `read src/x.py`. Only what will fit on a row.
            yield Event(
                kind="tool",
                text=f"{called.get('name') or 'tool'} {_about(arguments)}".strip()[
                    :120
                ],
            )
            return
        if (words := str(event.get("content") or "")).strip():
            yield Event(kind=kind, text=words)

    def _message(self, message: dict[str, Any]) -> None:
        """Takes what one request to the model came to, as it comes back.

        pi answers a prompt with as many requests as the work takes, and says what each of
        them cost as it lands -- so a turn's spending is known while the turn is still
        running rather than once it is over. What it said last is the answer the turn ends
        on, and what it complained of last is why it did not.

        Args:
          message: The message just finished, as read.
        """
        if message.get("role") != "assistant":
            return
        usage: dict[str, Any] = message.get("usage") or {}
        # Every kind of token counts: what a rate is measuring is the traffic, and a cache
        # read crosses the wire like anything else. Told as it lands rather than once the run
        # is over, since that is what a rate read while the turn runs is made of.
        counted = Usage(
            {
                kind: float(usage.get(named) or 0)
                for kind, named in _KINDS.items()
                if usage.get(named)
            }
        )
        self._spent += int(counted.total)
        self._costing = self._costing + counted
        self._spends(counted)
        self._failed = (
            str(message["errorMessage"]) if message.get("errorMessage") else None
        )
        words = "".join(
            str(cast("dict[str, Any]", part).get("text") or "")
            for part in cast("list[Any]", message.get("content") or [])
            if isinstance(part, dict)
            and cast("dict[str, Any]", part).get("type") == "text"
        )
        if words.strip():
            self._said = words

    def _answered(self) -> Event:
        """The turn's answer, and what it cost, once pi has gone quiet.

        Returns:
          The `result` the turn ends on, or the `failed` that closes it the other way: a run
          whose last request came back as an error and left nothing to answer with did not
          land, and a loop fed that error would be running on it as the work of the turn.
        """
        said, failed, spent, turn = self._said, self._failed, self._spent, self._costing
        self._said, self._failed, self._spent, self._costing = "", None, 0, Usage()
        tokens = {self._agent.config.model: spent} if spent > 0 else {}
        if failed is not None and not said:
            return Event(kind="failed", text=failed, tokens=tokens, spent=turn)
        if self._named is not None:
            self._adopt(self._named)  # a turn has landed, so the session is open
        return Event(kind="result", text=said.strip(), tokens=tokens, spent=turn)

    def _answer(self, said: dict[str, Any]) -> None:
        """Answers something an extension of pi's stopped the turn to ask.

        pi waits on the answer, so one left unanswered is a turn that never ends. A question
        nobody is there to answer is cancelled, which pi reads as the person having walked
        away from it and carries on from.

        Args:
          said: The `extension_ui_request`, as read.
        """
        method = str(said.get("method") or "")
        if method not in _ASKS:
            return  # told rather than asked: a notice, a status, a widget, a title
        offers: list[Any] = said.get("options") or []
        answer = self._agent.asked(
            Question(
                text=str(said.get("title") or said.get("message") or ""),
                options=tuple(str(one) for one in offers)
                if method == "select"
                else (_YES_NO if method == "confirm" else ()),
            )
        )
        if answer is None:
            self._send(
                json.dumps(
                    {
                        "type": "extension_ui_response",
                        "id": said.get("id"),
                        "cancelled": True,
                    }
                )
                + "\n"
            )
            return
        answered: dict[str, Any] = {
            "type": "extension_ui_response",
            "id": said.get("id"),
        }
        if method == "confirm":
            answered["confirmed"] = answer.strip().lower() not in ("no", "n", "false")
        else:
            answered["value"] = answer
        self._send(json.dumps(answered) + "\n")


class PiAgent(AgentBase):
    """pi, driven over its RPC protocol so a turn can be talked to while it runs.

    Every moment here is one read off the turn itself: pi asks nothing of a client before it
    reaches for a tool, so there is no permission for a hook to be hung on.
    """

    def new(self, cwd: str | os.PathLike[str] | None = None) -> PiSession:
        """Opens a new pi session, in the directory it is given or in this one."""
        return PiSession(self, cwd)

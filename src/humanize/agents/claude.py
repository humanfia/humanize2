"""Claude Code: one ``claude --print`` held open, spoken to in JSON a line at a time."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar, cast

from .base import AgentBase, StreamSessionBase
from .config import AgentConfig
from .event import Event, Question
from .hooks import EVERYWHERE, Moment
from .skills import leaving

if TYPE_CHECKING:
    from collections.abc import Iterator

#: The tool Claude reaches for when it wants a person rather than a file. Its input is a list
#: of questions and its answer is that same input with the answers written into it, which is
#: what the permission prompt of an interactive Claude fills in.
_ASKS = "AskUserQuestion"


def _about(called: dict[str, Any]) -> str:
    """What a tool was called with, as the one line a row of a transcript has room for.

    Args:
      called: The tool's input, as Claude sent it.

    Returns:
      The first thing in it that is words -- the path, the command, the query -- or "".
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
class ClaudeCodeAgentConfig(AgentConfig):
    """What Claude Code is configured with: the common model and effort, and nothing else."""


class ClaudeCodeSession(StreamSessionBase):
    """A Claude Code conversation, addressed by an id chosen up front.

    Pinning beats ``--continue``, which resumes whichever session in this directory is newest:
    a second agent working alongside would steal the resume.

    The process stands for the life of the session rather than the length of a turn, which is
    what streaming input buys: the turns of one conversation are lines written to a Claude that
    is already there, and so is anything said to it while a turn is running.
    """

    #: `--json-schema` is Claude's own: it validates the answer against the schema before it
    #: hands it back, so a turn asked for a shape answers in it or does not answer.
    shapes: ClassVar[bool] = True

    def __init__(self, agent: AgentBase) -> None:
        """Initializes a session that has spent nothing yet.

        Args:
          agent: The agent whose config every turn of this session runs at.
        """
        super().__init__(agent)
        #: What each model has cost so far, as Claude counts it: a running total per process.
        self._counted: dict[str, int] = {}
        #: The id Claude says this session has, taken only once a turn has landed in it.
        self._named: str | None = None

    @property
    def named(self) -> str | None:
        """What Claude called this session, which it says on the first line it writes."""
        return self._id or self._named

    def _command(self) -> list[str]:
        """Builds the ``claude --print`` that reads turns from stdin and says events on stdout.

        Opens the session while it is unopened and resumes it once it has an id, which is what
        an anchored session needs: its process ends with each turn, so the next one has a
        conversation to rejoin. An unanchored session opens once and stays open.
        """
        # A fresh id per attempt: an opening turn that failed may still have left Claude holding
        # the id it was given, and retrying under that one would collide forever.
        pinned = self._id or str(uuid.uuid4())
        argv = [
            "claude",
            "--print",
            "--input-format",
            "stream-json",
            "--output-format",
            "stream-json",
            "--verbose",
            "--resume" if self._id else "--session-id",
            pinned,
            "--dangerously-skip-permissions",
            "--model",
            self._agent.config.model,
            "--effort",
            self._agent.config.effort,
        ]
        if self._shaping is not None:
            # Claude validates the answer against this itself, so a turn that lands has
            # answered in the shape: what comes back is the object, and nothing else.
            argv += ["--json-schema", json.dumps(self._shaping.model_json_schema())]
        if off := leaving(
            self._agent.backend, self._agent.config.skills, self._workspace()
        ):
            # A skill is a tool call, and `Skill(<name>)` is that call written as a rule: the
            # agent is refused every skill it was not given. It is still told they exist --
            # Claude lists what is installed, and no flag takes one off that list -- so this
            # is a skill it cannot use rather than one it never hears of.
            argv += ["--disallowedTools", ",".join(f"Skill({one})" for one in off)]
        return argv

    def _write(self, text: str, ticket: str = "") -> str:
        """Renders one thing to say as the user message Claude reads it as.

        A word put into a turn carries a `uuid`, which is what Claude names it by in the
        `command_lifecycle` lines it answers with -- so a turn told three things says which
        of them it has taken in, one at a time. Without one it says nothing at all, and a
        word put in would only ever be as good as the write that sent it.

        Args:
          text: What to say.
          ticket: The uuid to name it by, or "" for a turn's own prompt: the turn beginning
            is what says that one landed.

        Returns:
          The line, newline included.
        """
        said: dict[str, Any] = {
            "type": "user",
            "message": {
                "role": "user",
                "content": [{"type": "text", "text": text}],
            },
        }
        if ticket:
            said["uuid"] = ticket
        return json.dumps(said) + "\n"

    def _restarted(self) -> None:
        """Forgets what the last process had spent, which the new one has not counted."""
        self._counted = {}

    def _spent(self, said: dict[str, Any]) -> dict[str, int]:
        """What the turn just ending cost, as tokens per model.

        Claude reports each model's usage as a running total for the session, so what this
        turn cost is the rise since the last one. Every kind of token counts: what a rate is
        measuring is the traffic, and a cache read crosses the wire like anything else.

        Args:
          said: The `result` event, as read.

        Returns:
          Tokens spent per model since the previous turn, models that did not move omitted.
        """
        spent: dict[str, int] = {}
        used: dict[str, Any] = said.get("modelUsage") or {}
        for model, usage in used.items():
            total = sum(
                int(usage.get(kind) or 0)
                for kind in (
                    "inputTokens",
                    "outputTokens",
                    "cacheReadInputTokens",
                    "cacheCreationInputTokens",
                )
            )
            if (risen := total - self._counted.get(model, 0)) > 0:
                spent[model] = risen
            self._counted[model] = total
        return spent

    def _read(self, line: str) -> Iterator[Event]:
        """Reads one event Claude wrote, as the things it says the agent did.

        A message carries a list of parts, and thinking, speaking and reaching for a tool can
        all be in the same one -- so every part is read, not the first that says anything.

        Args:
          line: The line, as written.

        Yields:
          What it said, which is nothing for a line saying nothing worth showing: a partial
          chunk, a tool's result coming back, or something a later Claude has added.
        """
        try:
            said: dict[str, Any] = json.loads(line)
        except json.JSONDecodeError:
            return  # not ours: Claude prints the odd plain line among the JSON
        if said.get("type") == "control_request":
            # Claude waits on the answer, so one left unanswered is a turn that never ends.
            self._answer(said)
        elif said.get("type") == "command_lifecycle":
            # What Claude answers a word put into a turn with, under the uuid it was sent
            # with: `queued` the moment it has been read off stdin, `started` once it is in
            # front of the model, `completed` when its answer is done. Only `started` is the
            # agent having heard -- the other two are the pipe and the answer.
            if said.get("state") == "started":
                words = self.took(str(said.get("command_uuid") or ""))
                if words is not None:
                    yield Event(kind="took", text=words)
        elif said.get("type") == "system" and said.get("session_id"):
            # Noted, not taken: this is the first line out, said before anything can go
            # wrong, and a session is only opened by a turn that lands in it.
            self._named = str(said["session_id"])
        elif said.get("type") == "result":
            if said.get("is_error"):
                # `subtype` reads "success" even here, so this flag is the whole of it. The
                # text is Claude explaining itself, which is a diagnostic and not an answer.
                yield Event(
                    kind="failed",
                    text=str(said.get("result") or "the turn failed"),
                    tokens=self._spent(said),
                )
                return
            if self._named is not None:
                self._adopt(self._named)  # a turn has landed, so the session is open
            yield Event(
                kind="result",
                text=str(said.get("result") or ""),
                tokens=self._spent(said),
            )
        elif said.get("type") == "assistant":
            for part in said.get("message", {}).get("content", []):
                if part.get("type") == "text" and part.get("text", "").strip():
                    yield Event(kind="text", text=part["text"])
                elif (
                    part.get("type") == "thinking" and part.get("thinking", "").strip()
                ):
                    yield Event(kind="reasoning", text=part["thinking"])
                elif part.get("type") == "tool_use":
                    # The name and what it was called on, which is what a tool call reads
                    # as: `Read src/x.py`, `Bash git status`. Only what will fit on a row.
                    called: dict[str, Any] = part.get("input") or {}
                    yield Event(
                        kind="tool",
                        text=f"{part.get('name') or 'tool'} {_about(called)}".strip()[
                            :120
                        ],
                    )

    def _answer(self, said: dict[str, Any]) -> None:
        """Answers something Claude asked of us over the same stream the turn is read from.

        Only one kind is worth putting to a person: the tool Claude uses to ask one. Every
        other request is a permission, and a flow watches its agent rather than gating it --
        so those are allowed with the input they came with, unless something hung on
        `PermissionRequest` says otherwise. That is the one moment where a refusal actually
        stops the agent doing something, because it is the one the backend waits on. A
        question nobody is there to answer is refused, which Claude reads as the tool having
        been declined and carries on from, rather than waiting on a reply that is not coming.

        Args:
          said: The `control_request`, as read.
        """
        asked: dict[str, Any] = said.get("request") or {}
        called: dict[str, Any] = asked.get("input") or {}
        answers: dict[str, str] = {}
        tool = str(asked.get("tool_name") or "")
        if tool != _ASKS:
            asking = self._fire(
                Moment.PERMISSION_REQUEST,
                tool=tool,
                about=_about(called),
                called=called,
            )
            if asking.refused:
                self._reply(
                    said,
                    {
                        "behavior": "deny",
                        "message": asking.because or f"{tool} was refused",
                    },
                )
                return
        else:
            for raw in cast("list[Any]", called.get("questions") or []):
                question = cast("dict[str, Any]", raw)
                wanted = str(question.get("question") or question.get("header") or "")
                offers: list[Any] = question.get("options") or []
                offered = tuple(
                    str(cast("dict[str, Any]", option)["label"])
                    for option in offers
                    if isinstance(option, dict)
                    and cast("dict[str, Any]", option).get("label")
                )
                answer = self._agent.asked(Question(text=wanted, options=offered))
                if answer is None:
                    self._reply(said, {"behavior": "deny", "message": "nobody to ask"})
                    return
                answers[wanted] = answer
        self._reply(
            said,
            {
                "behavior": "allow",
                "updatedInput": {**called, "answers": answers} if answers else called,
            },
        )

    def _reply(self, said: dict[str, Any], answer: dict[str, Any]) -> None:
        """Writes one answer back to Claude, against the request it answers.

        Args:
          said: The `control_request` being answered.
          answer: What to answer it with.
        """
        self._send(
            json.dumps(
                {
                    "type": "control_response",
                    "response": {
                        "subtype": "success",
                        "request_id": said.get("request_id"),
                        "response": answer,
                    },
                }
            )
            + "\n"
        )

    def _pursue(self, objective: str) -> str:
        """Runs the turn as Claude Code's own ``/goal``, which print mode expands like any other.

        Claude keeps the session going itself, by refusing to stop while the objective is
        unmet, so the turn is over only once it has been reached or given up on.
        """
        return self(f"/goal {objective}")


class ClaudeCodeAgent(AgentBase):
    """Claude Code, driven over its streaming JSON protocol so a turn can be talked to."""

    #: Every moment a turn passes through, and one more: Claude asks before it uses a tool,
    #: over the same stream the turn is read from, and waits for the answer. So this is the
    #: one backend here where a hook can say no to something and have the agent hear it.
    moments: ClassVar[frozenset[Moment]] = EVERYWHERE | {Moment.PERMISSION_REQUEST}

    def new(self) -> ClaudeCodeSession:
        """Opens a new Claude Code session."""
        return ClaudeCodeSession(self)

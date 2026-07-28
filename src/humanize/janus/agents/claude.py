"""Claude Code: one ``claude --print`` held open, spoken to in JSON a line at a time."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from .base import AgentBase, Event, Question, StreamSessionBase
from .config import AgentConfig

if TYPE_CHECKING:
    from collections.abc import Iterator

#: The tool Claude reaches for when it wants a person rather than a file. Its input is a list
#: of questions and its answer is that same input with the answers written into it, which is
#: what the permission prompt of an interactive Claude fills in.
_ASKS = "AskUserQuestion"


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
        return [
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

    def _write(self, text: str) -> str:
        """Renders one thing to say as the user message Claude reads it as."""
        return (
            json.dumps(
                {
                    "type": "user",
                    "message": {
                        "role": "user",
                        "content": [{"type": "text", "text": text}],
                    },
                }
            )
            + "\n"
        )

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
                    about = next(
                        (
                            str(value)
                            for value in called.values()
                            if isinstance(value, str) and value.strip()
                        ),
                        "",
                    )
                    yield Event(
                        kind="tool",
                        text=f"{part.get('name') or 'tool'} {about}".strip()[:120],
                    )

    def _answer(self, said: dict[str, Any]) -> None:
        """Answers something Claude asked of us over the same stream the turn is read from.

        Only one kind is worth putting to a person: the tool Claude uses to ask one. Every
        other request is a permission, and a flow watches its agent rather than gating it --
        so those are allowed with the input they came with. A question nobody is there to
        answer is refused, which Claude reads as the tool having been declined and carries
        on from, rather than waiting on a reply that is not coming.

        Args:
          said: The `control_request`, as read.
        """
        asked: dict[str, Any] = said.get("request") or {}
        called: dict[str, Any] = asked.get("input") or {}
        answers: dict[str, str] = {}
        if asked.get("tool_name") == _ASKS:
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

    def new(self) -> ClaudeCodeSession:
        """Opens a new Claude Code session."""
        return ClaudeCodeSession(self)

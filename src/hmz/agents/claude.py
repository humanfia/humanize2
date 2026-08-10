"""Claude Code: one ``claude --print`` held open, spoken to in JSON a line at a time."""

from __future__ import annotations

import json
import uuid
from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar, cast

from .base import AgentBase, StreamSessionBase
from .config import AgentConfig
from .event import Event, Question, Usage
from .hooks import EVERYWHERE, Moment

if TYPE_CHECKING:
    import os
    from collections.abc import Iterator

#: The tool Claude reaches for when it wants a person rather than a file. Its input is a list
#: of questions and its answer is that same input with the answers written into it, which is
#: what the permission prompt of an interactive Claude fills in.
_ASKS = "AskUserQuestion"

#: Noninteractive orchestration tools that can move work beyond the ordinary turn HMZ owns.
#: An agent whose goals are disabled remains able to use its ordinary permission-bound tools,
#: but cannot escape into a hidden goal, subagent, wakeup, or cron lifecycle.
_CONTINUATION_TOOLS = (
    "Agent",
    "ScheduleWakeup",
    "CronCreate",
    "CronDelete",
    "CronList",
)

_ALLOWED_TOOLS_MAX = 32

_ALLOWED_TOOL_RULE_MAX_CHARS = 4096

#: Reasons that leave an answer unfinished even when a broken intermediary labels the result
#: `success`. Claude normally keeps its own agent loop going for these rather than returning
#: them as the result of the whole turn.
_UNFINISHED = frozenset(
    {
        "max_tokens",
        "model_context_window_exceeded",
        "pause_turn",
        "tool_deferred",
        "tool_use",
    }
)

#: What Claude calls each rung of the ladder. Its own four modes line up with them, and one of
#: them is even called the same thing: `plan` is an agent that works everything out and changes
#: nothing, `acceptEdits` is one that may change what it is working on without asking, Claude's
#: own `auto` is one whose requests are answered for it, and `bypassPermissions` is the
#: permission system switched off -- which is what `--dangerously-skip-permissions` has always
#: meant here, and is spelled that way still because that flag is the one Claude documents.
_PERMITTED = {
    "read-only": "plan",
    "workspace-write": "acceptEdits",
    "auto": "auto",
}

#: What each kind of token is called on the total Claude states at the end of a turn, and what
#: it is called on the message each request answered with. The same kinds either way, under
#: the two spellings Claude uses for them.
_KINDS = {
    "input": "inputTokens",
    "output": "outputTokens",
    "cache_read": "cacheReadInputTokens",
    "cache_write": "cacheCreationInputTokens",
}
_AS_IT_GOES = {
    "input": "input_tokens",
    "output": "output_tokens",
    "cache_read": "cache_read_input_tokens",
    "cache_write": "cache_creation_input_tokens",
}


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


def _result_failure(said: dict[str, Any]) -> str | None:
    """Explains why a Claude result did not finish its turn, or says that it did.

    A turn held to a shape ends the one way that otherwise reads as unfinished: the last
    thing the model did was call `StructuredOutput`, so the result says `stop_reason:
    tool_use` -- and says the object beside it, which is the answer. So a result carrying
    one is a turn that finished, however it stopped.
    """
    reason: str | None = None
    shaped = said.get("structured_output") is not None
    if said.get("is_error"):
        reason = "the turn failed"
    elif (subtype := said.get("subtype")) not in (None, "success"):
        reason = f"Claude ended the turn with {subtype}"
    elif (terminal := said.get("terminal_reason")) not in (None, "completed"):
        reason = f"Claude ended the turn with {terminal}"
    elif not shaped and (stopped := said.get("stop_reason")) in _UNFINISHED:
        reason = f"Claude stopped with {stopped} before completing the turn"
    if reason is None:
        return None

    if result := said.get("result"):
        return str(result)
    errors = cast("list[Any]", said.get("errors") or [])
    if errors:
        return "; ".join(str(error) for error in errors)
    return reason


@dataclass(frozen=True, kw_only=True)
class ClaudeCodeAgentConfig(AgentConfig):
    """The common settings plus exact Claude-native tool allow rules."""

    allowed_tools: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        super().__post_init__()
        if (
            len(self.allowed_tools) > _ALLOWED_TOOLS_MAX
            or self.allowed_tools != tuple(sorted(set(self.allowed_tools)))
            or any(
                not rule or len(rule) > _ALLOWED_TOOL_RULE_MAX_CHARS or "," in rule
                for rule in self.allowed_tools
            )
        ):
            raise ValueError("allowed_tools must be unique sorted Claude tool rules")


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

    def __init__(
        self, agent: AgentBase, cwd: str | os.PathLike[str] | None = None
    ) -> None:
        """Initializes a session that has spent nothing yet.

        Args:
          agent: The agent whose config every turn of this session runs at.
          cwd: The directory this conversation works in, as for `SessionBase`.
        """
        super().__init__(agent, cwd)
        #: What each model has cost so far, by kind, as Claude counts it: a running total per
        #: process, so what a turn cost is the rise across it.
        self._counted: dict[str, Counter[str]] = {}
        #: What the turn now running has already been counted as spending, from the messages
        #: it answered with -- so that the total it states at the end adds only the rest --
        #: and what each of those messages last said it had cost.
        self._fed: Counter[str] = Counter()
        self._seen: dict[str, Counter[str]] = {}
        #: What the process now up was started to think at, so that a flow moving the effort
        #: mid-session is answered by starting one that thinks at the new one.
        self._at: str | None = None
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
            *(
                ["--permission-mode", mode]
                if (mode := _PERMITTED.get(self._agent.config.permission))
                else ["--dangerously-skip-permissions"]
            ),
            "--settings",
            json.dumps(
                {"fastMode": self._agent.config.service_tier == "fast"},
                separators=(",", ":"),
            ),
            "--model",
            self._agent.config.model,
            "--effort",
            self.effort,
        ]
        if self._shaping is not None:
            # Claude validates the answer against this itself, so a turn that lands has
            # answered in the shape: what comes back is the object, and nothing else.
            argv += ["--json-schema", json.dumps(self._shaping.model_json_schema())]
        if not self._agent.goals_enabled:
            # A tool call is a tool call, and `--disallowedTools` is that call written as a
            # rule: an agent whose goals were switched off is refused the ones that would
            # carry work past the turn humanize is holding -- a subagent of its own, a
            # wakeup, anything on the scheduler. Everything else it may reach for is what its
            # permission rung says it may, exactly as before.
            argv += ["--disallowedTools", ",".join(_CONTINUATION_TOOLS)]
        allowed_tools = getattr(self._agent.config, "allowed_tools", ())
        if allowed_tools:
            argv += ["--allowedTools", ",".join(allowed_tools)]
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
        self._counted, self._fed, self._seen = {}, Counter(), {}
        self._at = self.effort

    def _stale(self) -> bool:
        """Whether the process up was started to think at something this turn is not.

        `--effort` is an argument of the process, so a flow that moves it mid-session is
        answered by ending this one and resuming the conversation in a process started at the
        new one -- exactly as asking for a shape is.
        """
        return self._at is not None and self._at != self.effort

    def _spent(self, said: dict[str, Any]) -> tuple[dict[str, int], Usage]:
        """What the turn just ending cost, per model and by the kind it went on.

        Claude reports each model's usage as a running total for the session, so what this
        turn cost is the rise since the last one. Every kind of token counts: what a rate is
        measuring is the traffic, and a cache read crosses the wire like anything else.

        Args:
          said: The `result` event, as read.

        Returns:
          Tokens spent per model since the previous turn, models that did not move omitted,
          and the same spending by kind.
        """
        spent: dict[str, int] = {}
        risen: Counter[str] = Counter()
        used: dict[str, Any] = said.get("modelUsage") or {}
        for model, usage in used.items():
            counted = Counter(
                {
                    kind: int(usage.get(named) or 0)
                    for kind, named in _KINDS.items()
                    if usage.get(named)
                }
            )
            before = self._counted.get(model) or Counter()
            moved = Counter(
                {
                    kind: tokens
                    for kind in set(counted) | set(before)
                    if (tokens := counted[kind] - before[kind]) > 0
                }
            )
            if total := sum(moved.values()):
                spent[model] = total
            risen.update(moved)
            self._counted[model] = counted
        return spent, Usage(risen)

    def _live(self, said: dict[str, Any]) -> None:
        """Takes what one request to the model came to, as its answer arrives.

        Claude says what each of them cost on the message it produced, which is where a rate
        read while the turn is still running comes from -- the `result` at the end of the turn
        is minutes away, and a rate that only moved there would stand still for all of them.
        What the result then states is the whole of the turn, so only the shortfall is added.

        Args:
          said: The `assistant` event, as read.
        """
        message: dict[str, Any] = said.get("message") or {}
        usage: dict[str, Any] = message.get("usage") or {}
        # Claude says the same message twice -- once for the thinking in it and once for the
        # words -- and states the whole of what that request cost both times. So what one of
        # these adds is the rise on the message it names, not the figure on it.
        named = str(message.get("id") or "")
        counted: Counter[str] = Counter(
            {
                kind: int(usage.get(spelled) or 0)
                for kind, spelled in _AS_IT_GOES.items()
                if usage.get(spelled)
            }
        )
        before = self._seen.get(named) or Counter()
        risen = Usage(
            {
                kind: tokens
                for kind in set(counted) | set(before)
                if (tokens := counted[kind] - before[kind]) > 0
            }
        )
        self._seen[named] = counted
        if risen.total:
            self._fed.update(risen)
            self._spends(risen)

    def _settle(self, risen: Usage) -> None:
        """Adds whatever the turn's own total says was spent beyond what was counted live.

        Args:
          risen: What the turn cost, by kind, as the `result` states it.
        """
        owed = Usage(
            {
                kind: tokens
                for kind in set(risen) | set(self._fed)
                if (tokens := risen.get(kind, 0.0) - self._fed[kind]) > 0
            }
        )
        self._fed, self._seen = Counter(), {}
        # Not a turn of the model: the requests it is settling up for have each been counted
        # already, and counting this as one more would put a turn in the average that never
        # happened.
        self._spends(owed, turn=False)

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
            if failure := _result_failure(said):
                # Claude has emitted `subtype: success` with `is_error: true`, so neither
                # field is sufficient alone. The remaining reasons also guard a malformed
                # success result that arrives while Claude is still asking to use a tool.
                tokens, risen = self._spent(said)
                self._settle(risen)
                yield Event(
                    kind="failed",
                    text=failure,
                    tokens=tokens,
                    spent=risen,
                )
                return
            if self._named is not None:
                self._adopt(self._named)  # a turn has landed, so the session is open
            tokens, risen = self._spent(said)
            self._settle(risen)
            yield Event(
                kind="result",
                text=str(said.get("result") or ""),
                tokens=tokens,
                spent=risen,
            )
        elif said.get("type") == "assistant":
            self._live(said)
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

        An agent that may change nothing is the exception: a permission is a request to do
        something, and granting one under `read-only` would be handing back the rung the flow
        asked for. Claude in plan mode asks rather than acts, and the answer here is no.

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
            if self._agent.config.permission == "read-only":
                self._reply(
                    said,
                    {"behavior": "deny", "message": f"{tool} would change something"},
                )
                return
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

    service_tiers = ("default", "fast")

    #: Every moment a turn passes through, and one more: Claude asks before it uses a tool,
    #: over the same stream the turn is read from, and waits for the answer. So this is the
    #: one backend here where a hook can say no to something and have the agent hear it.
    moments: ClassVar[frozenset[Moment]] = EVERYWHERE | {Moment.PERMISSION_REQUEST}

    #: Claude keeps itself going toward an objective, which is what `pursue` reaches for.
    pursues: ClassVar[bool] = True

    def new(self, cwd: str | os.PathLike[str] | None = None) -> ClaudeCodeSession:
        """Opens a new Claude Code session, in the directory it is given or in this one."""
        return ClaudeCodeSession(self, cwd)

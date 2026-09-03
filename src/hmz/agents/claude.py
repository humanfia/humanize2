"""Claude Code: one ``claude --print`` held open, spoken to in JSON a line at a time."""

from __future__ import annotations

import functools
import json
import shutil
import subprocess
import uuid
from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar, cast

from .base import AgentBase, StreamSessionBase
from .config import AgentConfig
from .event import Event, Failed, Question, Usage
from .hooks import EVERYWHERE, SUBAGENTS, Moment

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

#: The tools that reach the web, by the names Claude calls them. Both, because searching and
#: fetching are one question here: an agent told not to search the web that went on reading
#: whatever page it liked would be answering the same question the other way.
_WEB_TOOLS = ("WebSearch", "WebFetch")

#: The tools Claude starts an agent of its own with. A turn that reaches for one of these has
#: agents under it rather than a tool running, which is worth saying as what it is: the id the
#: call was made under is what pairs the one that started with the result that ends it.
_FLEET = ("Task", "Agent")

_ALLOWED_TOOLS_MAX = 32

_ALLOWED_TOOL_RULE_MAX_CHARS = 4096
_FORK_SECONDS = 30.0

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

#: That fourth mode under the name Claude says it back by. It is not in the mapping above
#: because the flag is what a turn asks for it with, and this is what the first line out calls
#: the same rung once the turn is running at it -- which is the only way to find out that it
#: is not: an account can be given managed settings, and one carrying
#: `disableBypassPermissionsMode` does not refuse the command line the way a Codex given
#: requirements refuses such a call. It starts the turn at `default` instead, where every edit
#: is declined, the model says it could not do the work, and the turn ends successfully having
#: changed nothing.
_UNCHECKED = "bypassPermissions"

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


@functools.lru_cache(maxsize=8)
def _native_fork_ready(binary: str | None = None) -> bool:
    """Whether the installed Claude CLI advertises prompt-free session forking."""
    binary = binary or shutil.which("claude")
    if binary is None:
        return False
    try:
        result = subprocess.run(
            [binary, "--help"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    text = f"{result.stdout}\n{result.stderr}"
    if "--fork-session" in text and "--session-id" in text:
        return True
    # Test doubles and third-party wrappers may not implement --help. Their native operation
    # remains the source of truth, while a real Claude help page has a recognizable usage.
    return result.returncode == 0 and not any(
        marker in text for marker in ("Usage:", "Options:")
    )


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

    #: `--mcp-config` takes a server on the command line, so a flow's own callbacks reach
    #: this turn without anything of the person at this machine's being written.
    takes_tools: ClassVar[bool] = True

    #: `--resume <parent> --fork-session --session-id <child>` is Claude's native fork: it
    #: branches a conversation in place without a prompt, so the child keeps the parent's
    #: prefix for the provider's cache. A fork is eager and prompt-free here.
    forks: ClassVar[bool] = True

    @classmethod
    def native_ready(cls) -> bool:
        """Whether this installation exposes Claude's native fork flags."""
        return _native_fork_ready(shutil.which("claude"))

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
        #: The agents this turn has started of its own, by the id of the call that started
        #: each: Claude ends one by answering that call, and what comes back names no tool,
        #: so what it was is remembered here until it does.
        self._fleet: dict[str, str] = {}
        #: Which of the flow's own callbacks the process now up was told about, by the names
        #: it was told them under, so that a session whose offer changes between two turns is
        #: answered by starting one that was told what this turn is offering.
        self._offering: tuple[str, ...] | None = None
        #: What the command line just built said they were, read once while it was built and
        #: kept for the process it starts. Read once rather than twice: an offer landing from
        #: a sibling session between the two reads would be written down as a name the process
        #: was told about when the process was told nothing at all, and never asked again.
        self._telling: tuple[str, ...] = ()
        #: The `set_permission_mode` this process was asked to step down by, until Claude has
        #: answered it: a rung refused twice is a turn that would go on quietly doing nothing,
        #: which is the whole of what asking a second time is here to stop.
        self._stepping: str = ""

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
            *self._session_args(),
        ]

    def _session_args(self) -> list[str]:
        """The settings a process is started with, off the config in force for this session.

        A forked child reads them off its frozen fork context rather than off the agent, so
        that reconfiguring the parent afterwards does not change the child -- and the fork
        command itself is built from the same frozen values, so the branch carries them.

        Returns:
          The permission, tier, model, effort, tool rules and MCP config, as argv.
        """
        context = self._fork_context
        if context is None:
            config = self._agent.config
            model, effort = self._agent.config.model, self.effort
            permission = self._agent.config.permission
            service_tier = self._agent.config.service_tier
            goals = self._agent.goals_enabled
            web_search = self._agent.config.web_search
        else:
            config = self._frozen_config
            model, effort = context.model, context.effort
            permission, service_tier = context.permission, context.service_tier
            goals, web_search = context.goals, context.web_search
        argv = [
            *(
                ["--permission-mode", mode]
                if (mode := _PERMITTED.get(permission))
                else ["--dangerously-skip-permissions"]
            ),
            "--settings",
            json.dumps({"fastMode": service_tier == "fast"}, separators=(",", ":")),
            "--model",
            model,
            "--effort",
            effort,
        ]
        if self._shaping is not None:
            # Claude validates the answer against this itself, so a turn that lands has
            # answered in the shape: what comes back is the object, and nothing else.
            argv += ["--json-schema", json.dumps(self._shaping.model_json_schema())]
        # A tool call is a tool call, and `--disallowedTools` is that call written as a rule.
        # Two things are said with it and the flag takes one list, so they are one list: an
        # agent whose goals were switched off is refused the tools that would carry work past
        # the turn humanize is holding -- a subagent of its own, a wakeup, anything on the
        # scheduler -- and one told not to search the web is refused the two that reach it.
        # Everything else it may reach for is what its permission rung says it may.
        denied: list[str] = []
        if not goals:
            denied += _CONTINUATION_TOOLS
        if not web_search:
            denied += _WEB_TOOLS
        if denied:
            argv += ["--disallowedTools", ",".join(denied)]
        allowed_tools = getattr(config, "allowed_tools", ())
        if allowed_tools:
            argv += ["--allowedTools", ",".join(allowed_tools)]
        # Read once and kept, so that what the process is recorded as having been told is
        # what this line actually tells it.
        self._telling = self._offered()
        if self._telling:
            # The flow's own callbacks, as the one thing Claude takes a tool it was not
            # shipped with on: a server on the command line rather than a line written into
            # anybody's settings file. Added to whatever the person at this machine has
            # configured rather than replacing it -- `--strict-mcp-config` would take their
            # own servers away for the length of this flow, which is not this flow's to do.
            argv += [
                "--mcp-config",
                json.dumps(self._toolbox().config(), separators=(",", ":")),
            ]
        return argv

    def _permission(self) -> str:
        """The permission rung frozen for this child, or the live agent rung otherwise."""
        if self._fork_context is not None:
            return self._fork_context.permission
        return self._agent.config.permission

    def _fork_command(self, parent_id: str, child_id: str) -> list[str]:
        """The one-time native fork: resume the parent and branch it into a named child.

        Args:
          parent_id: The parent conversation, as Claude logged it.
          child_id: The child the branch is to become, chosen up front.

        Returns:
          The command, which must not be sent a user prompt: the fork is done by the flags.
        """
        return [
            "claude",
            "--print",
            "--input-format",
            "stream-json",
            "--output-format",
            "stream-json",
            "--verbose",
            "--resume",
            parent_id,
            "--fork-session",
            "--session-id",
            child_id,
            *self._session_args(),
        ]

    def _fork(self, *, parent_id: str, last_turn_id: str | None) -> str:
        """Performs Claude's native fork eagerly, without sending a prompt.

        The branch is made by the flags alone; the child id is adopted before any turn, and
        later child turns resume it with an ordinary ``--resume <child-id>``.

        Args:
          parent_id: The parent conversation to branch.
          last_turn_id: Refused: Claude forks the whole conversation, with no boundary.

        Returns:
          The child's id, which the child adopts.

        Raises:
          NotImplementedError: For a non-None boundary, which Claude cannot express.
          subprocess.CalledProcessError: If the fork could not be made.
        """
        if last_turn_id is not None:
            raise NotImplementedError(
                "Claude forks the whole conversation; it has no intermediate boundary"
            )
        child_id = str(uuid.uuid4())
        argv = self._spawned(self._fork_command(parent_id, child_id))
        with subprocess.Popen(
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            env=self._environ(),
            cwd=(
                None
                if (
                    self._fork_context.anchor
                    if self._fork_context is not None
                    else self._agent.anchor
                )
                is not None
                else self._workspace()
            ),
        ) as proc:
            assert proc.stdout is not None  # noqa: S101
            assert proc.stderr is not None  # noqa: S101
            assert proc.stdin is not None  # noqa: S101
            try:
                # An empty input closes stdin without a prompt. Calling communicate after a
                # manual close would make Python flush the already-closed pipe a second time.
                stdout, stderr = proc.communicate(input="", timeout=_FORK_SECONDS)
            except subprocess.TimeoutExpired as timed:
                proc.kill()
                stdout, stderr = proc.communicate()
                raise Failed(
                    124,
                    argv,
                    stdout or "",
                    f"Claude native fork timed out after {_FORK_SECONDS:g}s: {stderr or ''}",
                ) from timed
            status = proc.returncode
        if status != 0:
            if self._agent.cycle is not None:
                self._agent.cycle.fork_lost(
                    self._agent,
                    parent_id,
                    last_turn_id,
                    provider=(
                        self._fork_context.provider
                        if self._fork_context is not None
                        else None
                    ),
                )
            raise Failed(status or 1, argv, stdout or "", stderr or "")
        return child_id

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
        # And whatever was under the turn the last process was taking: it went with it.
        self._fleet = {}
        self._at = self.effort
        self._offering = self._telling
        # And the rung, which each process is granted or refused for itself: nothing is carried
        # over from the last one, whose account may not even be this one's.
        self._stepping = ""

    def _offered(self) -> tuple[str, ...]:
        """What a Claude started now would be told the flow's own callbacks are.

        Returns:
          The name of every callback in front of the agent, sorted, so that a flow which
          builds its list afresh before each turn is offering the same thing each time.
          Names rather than everything a tool says: a name is what a tool is here -- two
          conversations offering one name are offering one tool -- and building every
          argument schema again before every turn to catch a reworded sentence would cost
          each turn more than the sentence is worth.
        """
        return tuple(sorted(one.name for one in self._toolbox().offered()))

    def _validate_fork_boundary(self, last_turn_id: str | None) -> None:
        """Claude's native fork has no intermediate turn boundary."""
        if last_turn_id is not None:
            raise NotImplementedError(
                "Claude forks the whole conversation; it has no intermediate boundary"
            )

    def _stale(self) -> bool:
        """Whether the process up was started for something this turn is no longer.

        `--effort` is an argument of the process, so a flow that moves it mid-session is
        answered by ending this one and resuming the conversation in a process started at the
        new one -- exactly as asking for a shape is. So is `--mcp-config`: Claude reads what
        an MCP server has when it starts it and holds that list for the life of the process,
        so a flow that changes which callbacks it offers between two turns is answered the
        same way. What is compared is the list the process was actually told, not whether it
        was told anything: a tool swapped for another is one the model has never heard of and
        one it can still reach for and be told is not there.
        """
        if self._at is not None and self._at != self.effort:
            return True
        return self._offering is not None and self._offering != self._offered()

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
        elif said.get("type") == "control_response" and self._stepping:
            # Claude answering the one thing this session ever asks of it: the step below.
            answer: dict[str, Any] = said.get("response") or {}
            if answer.get("request_id") == self._stepping:
                self._stepping = ""
                if answer.get("subtype") == "success":
                    yield Event(
                        kind="tool",
                        text="claude: this account will not run an agent at bypass, so it"
                        " runs at auto, where the account's own rules still apply",
                    )
                else:
                    # A rung refused twice. The turn is still at `default`, where every edit
                    # is declined and the answer at the end says the work is done -- so this
                    # is the turn's failure rather than something to carry on past.
                    yield Event(
                        kind="failed",
                        text=str(
                            answer.get("error")
                            or "Claude would not run this turn at auto either"
                        ),
                    )
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
            if said.get("subtype") == "init":
                # The one line that says what the turn *started* at. Claude says the mode
                # again on every `status` line once one has been set, and reading one of
                # those as the answer to this would have the session asking for the same
                # rung again for as long as the turn ran.
                yield from self._stepped(str(said.get("permissionMode") or ""))
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
                    named = str(part.get("name") or "tool")
                    said_as = f"{named} {_about(called)}".strip()[:120]
                    if named in _FLEET:
                        marked = str(part.get("id") or "")
                        self._fleet[marked] = said_as
                        yield Event(kind="subagent", text=said_as, whose=marked)
                        continue
                    yield Event(kind="tool", text=said_as)
        elif said.get("type") == "user":
            # A tool answering, which is the only thing said back to Claude on this stream
            # that is worth reading: one of them is an agent of its own having finished.
            for part in said.get("message", {}).get("content", []):
                if part.get("type") != "tool_result":
                    continue
                marked = str(part.get("tool_use_id") or "")
                if was := self._fleet.pop(marked, ""):
                    yield Event(kind="subagent-ends", text=was, whose=marked)

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
            if self._permission() == "read-only":
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

    def _stepped(self, granted: str) -> Iterator[Event]:
        """Asks again a rung down, where this account will not start the turn at the one asked.

        The mode the first line out says the turn is *running* at, rather than the one the
        command line asked for: an account whose managed settings forbid `bypassPermissions`
        runs the turn at `default` and says so only here, and a turn left there reaches for a
        tool, is declined, and ends by saying it could not -- successfully. So one running
        lower than it was told to is asked for again over the same stream the turn is read
        from, which lands while the model is still being asked the first question: the answer
        to that is a round trip away, and this is a line already written.

        The rung below `bypass` is `auto`, where Claude decides for itself under the account's
        own rules rather than having the deciding switched off -- so a flow nobody was asked
        about goes on running unattended here, though not with everything granted: a tool the
        account's `permissions.ask` or `permissions.deny` covers is still declined, and in
        print mode declined without anybody being asked. A step up from doing nothing at all,
        and not the same as `bypass`. Every other rung is asked for as a mode Claude grants,
        so one of those
        coming back changed is an account that will not run this agent as it was configured,
        and what is under it is not a rung but a promotion: an agent told it may change
        nothing is not handed the workspace for having been refused. That one is a failed turn.

        Args:
          granted: What Claude says the turn is running at, or "" for a line that does not say.

        Yields:
          The turn's failure, where the rung asked for cannot be met halfway.
        """
        wanted = _PERMITTED.get(self._agent.config.permission, _UNCHECKED)
        if granted in ("", wanted):
            return
        if wanted != _UNCHECKED:
            yield Event(
                kind="failed",
                text=f"this account will not run an agent at"
                f" {self._agent.config.permission}: Claude runs the turn at {granted}",
            )
            return
        self._stepping = str(uuid.uuid4())
        self._send(
            json.dumps(
                {
                    "type": "control_request",
                    "request_id": self._stepping,
                    "request": {
                        "subtype": "set_permission_mode",
                        "mode": _PERMITTED["auto"],
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

    #: Every moment a turn passes through, and three more: Claude asks before it uses a tool,
    #: over the same stream the turn is read from, and waits for the answer -- so this is the
    #: one backend here where a hook can say no to something and have the agent hear it -- and
    #: it says on the same stream when it starts an agent of its own and when that one is done.
    moments: ClassVar[frozenset[Moment]] = (
        EVERYWHERE | SUBAGENTS | {Moment.PERMISSION_REQUEST}
    )

    #: Claude keeps itself going toward an objective, which is what `pursue` reaches for.
    pursues: ClassVar[bool] = True

    def new(self, cwd: str | os.PathLike[str] | None = None) -> ClaudeCodeSession:
        """Opens a new Claude Code session, in the directory it is given or in this one."""
        return ClaudeCodeSession(self, cwd)

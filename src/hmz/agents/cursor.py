"""Cursor Agent: one run of `cursor-agent --print` per turn, read as the NDJSON it answers in.

Its command line says the whole of what an agent is configured with -- which model, how hard
it thinks, what it may reach for, which chat to carry on -- so a turn is one run of it rather
than a conversation held open on a server.

How hard it thinks is not a flag. Cursor's models are parameterized, and the rung is written
into the model the turn is asked for: `claude-opus-4-8[effort=high]`, which is the spelling
its own `--help` documents. Asking to be served quickly is the same bracket, as `fast=true`,
which is why this backend can express a service tier at all. A model named with a bracket
already is taken exactly as it was written: a flow that spelled out its own parameters meant
them.

What `--output-format stream-json` writes on stdout is a protocol rather than the agent
talking: one JSON object a line, tagged by `type`, opening on the `system` line that names the
chat and ending on the `result` that carries the answer. Nothing in it says what the turn
cost -- Cursor reports a duration and no tokens -- so a run of this spends what its account
says it spent and this says nothing about it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar, cast

from .base import AgentBase, CommandSessionBase
from .config import AgentConfig
from .event import Event, Failed
from .hooks import EVERYWHERE, SUBAGENTS, Moment

if TYPE_CHECKING:
    import os
    from collections.abc import Iterator

#: What the CLI is installed as. Its installer writes two names and this is the one that can
#: only be this CLI: `agent` is a name anything on a machine could have taken.
_COMMAND = "cursor-agent"

#: What a turn is run as at each rung of the ladder, in Cursor's own vocabulary. `plan` is the
#: mode it documents as read-only -- it analyses and proposes and changes nothing; `--sandbox
#: enabled` is its own sandbox, which is what stops a command at the edge of the workspace;
#: `--auto-review` is its server-side classifier, which runs the safe calls itself; and
#: `--force` is Run Everything, which is what an unattended flow has always run its agents at.
_PERMITTED = {
    "read-only": ("--mode", "plan"),
    "workspace-write": ("--force", "--sandbox", "enabled"),
    "auto": ("--auto-review",),
    "bypass": ("--force", "--sandbox", "disabled"),
}

#: The tools it starts a fleet of its own with, by the names its stream calls them. A turn
#: that reaches for one of these is a turn with agents under it, which is worth showing as
#: what it is rather than as another tool call.
_SUBAGENTS = ("task", "subagent", "explore", "agent")

#: How much of a tool call fits on a row of a transcript.
_ROOM = 120


def _about(given: dict[str, Any]) -> str:
    """What a tool was called with, as the one line a row of a transcript has room for.

    Args:
      given: The tool call's arguments, as Cursor sent them.

    Returns:
      The first thing in it that is words -- the path, the command, the query -- or "".
    """
    return next(
        (
            str(value)
            for value in given.values()
            if isinstance(value, str) and value.strip()
        ),
        "",
    )


def _called(said: dict[str, Any]) -> tuple[str, str]:
    """One tool call, as what was reached for and what with.

    Cursor names the tool by the key of the one object under `tool_call` -- `readToolCall`,
    `shellToolCall` -- and puts what it was called with under `args` inside it.

    Args:
      said: The `tool_call` line, as read.

    Returns:
      The tool's name and the one line about what it was called with.
    """
    call = cast("dict[str, Any]", said.get("tool_call") or {})
    named = next(iter(call), "tool")
    inside = cast("dict[str, Any]", call.get(named) or {})
    given = cast("dict[str, Any]", inside.get("args") or {})
    return named.removesuffix("ToolCall") or "tool", _about(given)


def parameterized(model: str, effort: str, *, fast: bool) -> str:
    """One model as Cursor is asked for it, with the rung and the tier written into it.

    Cursor's models take their parameters in brackets after the name, which is where how hard
    it thinks and how quickly it is served both go. A model already written with a bracket is
    left exactly as it is: a flow that spelled out `claude-opus-4-8[context=1m,effort=high]`
    said what it meant, and a second bracket would be a model Cursor refuses.

    Args:
      model: The model, as the agent was configured with it.
      effort: How hard it is to think, or "" to leave the model at its own default.
      fast: Whether to ask for the faster service.

    Returns:
      What to put after `--model`.
    """
    if "[" in model:
        return model
    said = [f"effort={effort}" for _ in range(1) if effort]
    said += [f"fast={'true' if fast else 'false'}"]
    return f"{model}[{','.join(said)}]"


class CursorSession(CommandSessionBase):
    """A Cursor chat, resumed by the id its first turn reported.

    The id is minted by `cursor-agent` as the chat opens and stated on the first line it
    writes, so it is read back out of the turn that opened it and given to every turn after --
    which is what keeps the conversation one conversation rather than a new one per run.
    """

    #: What it writes on stdout is the turn as events rather than the agent talking.
    protocol: ClassVar[bool] = True

    def __init__(
        self, agent: AgentBase, cwd: str | os.PathLike[str] | None = None
    ) -> None:
        """Initializes a session that has run no turn yet.

        Args:
          agent: The agent whose config every turn of this session runs at.
          cwd: The directory this conversation works in, as for `SessionBase`.
        """
        super().__init__(agent, cwd)
        #: What the agent has said so far in the turn now running, and what went wrong with it
        #: if anything did. Cursor states each complete message once, between tool calls.
        self._said: list[str] = []
        self._failed: str | None = None
        #: Which tool calls have been shown, a call being stated twice -- once as it starts
        #: and once as it comes back -- and a row per status being a transcript of statuses.
        self._shown: set[str] = set()

    def _turn(self, prompt: str) -> tuple[list[str], str | None]:
        """Builds the `cursor-agent --print` one turn is.

        Args:
          prompt: The input prompt for this turn.

        Returns:
          The command, and None because the prompt is inside it: Cursor takes it as an
          argument and reads nothing off a piped stdin.
        """
        self._said, self._failed, self._shown = [], None, set()
        argv = [
            _COMMAND,
            "--print",
            "--output-format",
            "stream-json",
            "--model",
            parameterized(
                self._agent.config.model,
                self.effort,
                fast=self._agent.config.service_tier == "fast",
            ),
            # The workspace it works in is a session's rather than a run's, and Cursor takes
            # it as a flag rather than reading the directory it was started in.
            "--workspace",
            self.cwd,
            # It asks before it trusts a workspace it has not seen, and there is nobody at a
            # headless turn to answer: a turn that waited on that would be a flow that stopped.
            "--trust",
            *_PERMITTED[self._agent.config.permission],
        ]
        if self._id is not None:
            # Written onto the flag: its own argument is optional -- `--resume` with nothing
            # after it means the latest chat -- so a value given separately would be read as
            # the prompt.
            argv.append(f"--resume={self._id}")
        # After `--`, so that a prompt opening with a dash is a prompt rather than a flag.
        return [*argv, "--", prompt], None

    def _reads(self, line: str, *, error: bool) -> Iterator[Event]:
        """Reads one line Cursor wrote, as the things it says the agent did.

        Args:
          line: The line, as written.
          error: Whether it came from stderr, which is its own warnings rather than the turn
            -- kept for a failed turn's diagnostic and shown nowhere.

        Yields:
          What it said, which is nothing for a line saying nothing worth showing.
        """
        if error:
            return
        try:
            said: dict[str, Any] = json.loads(line)
        except json.JSONDecodeError:
            return  # not ours: it prints the odd plain line among the JSON
        kind = str(said.get("type") or "")
        if kind == "system" and said.get("session_id"):
            # Noted, not taken: this is the first line out, said before anything can go
            # wrong, and a chat is only opened by a turn that lands in it.
            self._named = str(said["session_id"])
        elif kind == "assistant":
            message = cast("dict[str, Any]", said.get("message") or {})
            for raw in cast("list[Any]", message.get("content") or []):
                part = cast("dict[str, Any]", raw)
                if part.get("type") == "text" and str(part.get("text") or "").strip():
                    self._said.append(str(part["text"]))
                    yield Event(kind="text", text=str(part["text"]))
        elif kind == "tool_call" and said.get("subtype") == "started":
            marked = str(said.get("call_id") or "")
            if marked in self._shown:
                return
            self._shown.add(marked)
            named, about = _called(said)
            if named.lower() in _SUBAGENTS:
                # A fleet of its own rather than another tool: what is under this turn is
                # agents, and whatever is watching draws them as agents.
                yield Event(
                    kind="subagent",
                    text=f"{named} {about}".strip()[:_ROOM],
                    whose=marked,
                )
                return
            yield Event(kind="tool", text=f"{named} {about}".strip()[:_ROOM])
        elif kind == "tool_call" and said.get("subtype") == "completed":
            named, about = _called(said)
            if named.lower() in _SUBAGENTS:
                yield Event(
                    kind="subagent-ends",
                    text=f"{named} {about}".strip()[:_ROOM],
                    whose=str(said.get("call_id") or ""),
                )
        elif kind == "result":
            if said.get("is_error") or said.get("subtype") not in (None, "success"):
                self._failed = str(said.get("result") or "") or json.dumps(said)
            elif said.get("result"):
                # What it answers with is the whole of the turn, stated again at the end. It
                # is what the messages already came to, so it stands in for them rather than
                # being added to them.
                self._said = [str(said["result"])]

    def _result(self, transcript: str) -> Event:
        """The turn's answer, out of the lines it wrote.

        Args:
          transcript: The whole of stdout, already read line by line.

        Returns:
          The `result` the turn ends on.

        Raises:
          subprocess.CalledProcessError: If the turn failed. Cursor says so on the line it
            ends on as well as in its exit status, and a loop fed that as an answer would be
            running on it as the work of the turn.
        """
        said = "".join(self._said)
        if self._failed is not None:
            raise Failed(1, [_COMMAND], said, self._failed)
        if not transcript.strip():
            raise Failed(1, [_COMMAND], "", f"{_COMMAND} said nothing at all")
        return Event(kind="result", text=said.strip())

    def _read_session_id(self, transcript: str) -> str:
        """Reads back the chat Cursor opened, which the line it opens on names.

        Args:
          transcript: Everything the turn printed.

        Returns:
          The chat's id.

        Raises:
          ValueError: If nothing the turn wrote names one, which is a turn that landed
            somewhere nobody can find again.
        """
        for line in transcript.splitlines():
            try:
                said: object = json.loads(line)
            except ValueError:
                continue
            if isinstance(said, dict) and (
                named := cast("dict[str, Any]", said).get("session_id")
            ):
                return str(named)
        raise ValueError(f"{_COMMAND} named no chat")


@dataclass(frozen=True, kw_only=True)
class CursorAgentConfig(AgentConfig):
    """What Cursor Agent is configured with: the common model and effort, and nothing else.

    The model is written as Cursor writes it -- a name out of its own catalogue, which
    `cursor-agent --list-models` prints -- with or without the bracket its parameterized
    models take. Written with one, the bracket is what the turn asks for and the effort
    beside it is left alone.
    """


class CursorAgent(AgentBase):
    """Cursor Agent, driven through its own command line, one run per turn."""

    #: Its models take `fast=true` in the bracket their parameters go in, which is the same
    #: thing every other backend here calls a service tier.
    service_tiers = ("default", "fast")

    #: Every moment a turn passes through, and the two about a fleet: its stream says when a
    #: turn starts an agent of its own and when that one has come back.
    moments: ClassVar[frozenset[Moment]] = EVERYWHERE | SUBAGENTS

    def new(self, cwd: str | os.PathLike[str] | None = None) -> CursorSession:
        """Opens a new Cursor chat, in the directory it is given or in this one."""
        return CursorSession(self, cwd)

"""opencode: one ``opencode run`` per turn, reading the JSON it answers in.

Its command line says everything an agent is configured with -- the model, the variant that is
its reasoning effort, the session to carry on, the directory to work in -- so a turn is one run
of it rather than a conversation held open on a server. What it writes on stdout with
``--format json`` is a protocol rather than the agent talking: the events of the turn, one per
line, which is where the session it opened, what it reached for and what it spent all are.

mimocode is the same program under another name, and is driven from here: what differs is what
the command is called and which of its own variables it takes.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar, cast

from .base import AgentBase, CommandSessionBase
from .config import AgentConfig
from .event import Event

if TYPE_CHECKING:
    from collections.abc import Iterator

#: What each kind of event reads as. A step beginning or ending is the turn's own plumbing,
#: and is read for what it cost rather than shown.
_SAYS = {"text": "text", "reasoning": "reasoning"}

#: What the tokens of one step are called, and what each of them is here. `reasoning` is
#: counted beside the output rather than inside it, so it is a kind of its own; the cache
#: counts arrive under `cache` rather than beside these.
_COUNTED = ("input", "output", "reasoning")
_CACHED = ("read", "write")


class OpencodeSession(CommandSessionBase):
    """An opencode conversation, resumed by the id the first turn's events name it with.

    The id is minted by opencode as the session opens, so it is read back out of the turn that
    opened it and given to every turn after -- which is what keeps the conversation one
    conversation rather than a new one per run.
    """

    #: What it writes on stdout is the turn as events rather than the agent talking.
    protocol: ClassVar[bool] = True

    #: The command this backend is installed as, which is the only thing mimocode differs by
    #: on the way in.
    command: ClassVar[str] = "opencode"

    def __init__(self, agent: AgentBase) -> None:
        """Initializes a session that has run no turn yet.

        Args:
          agent: The agent whose config every turn of this session runs at.
        """
        super().__init__(agent)
        #: What the agent has said so far in the turn now running, and what went wrong with
        #: it if anything did.
        self._said = ""
        self._failed: str | None = None
        #: What the turn now running has cost, added up as each step of it comes back, and
        #: which parts of it have already been shown -- a part is written once here, but a
        #: turn that saw it twice would show it twice.
        self._spent = 0
        self._shown: set[str] = set()

    def _turn(self, prompt: str) -> tuple[list[str], str | None]:
        """Builds the ``opencode run`` one turn is, and hands it the prompt on stdin.

        On stdin rather than as an argument: a prompt is a paragraph and may open with a dash,
        neither of which belongs on a command line.

        Args:
          prompt: The input prompt for this turn.

        Returns:
          The command and the prompt to write to it.
        """
        self._said, self._failed, self._spent, self._shown = "", None, 0, set()
        argv = [
            type(self).command,
            "run",
            "--format",
            "json",
            "--dir",
            self._workspace(),
            "--model",
            self._agent.config.model,
            "--variant",
            self._agent.config.effort,
        ]
        if self._id is not None:
            argv += ["--session", self._id]
        argv += self._unattended()
        return argv, prompt

    def _unattended(self) -> list[str]:
        """What tells this backend that nobody is there to answer it.

        A flow watches its agent rather than gating it, as humanize' own flows do, and a turn
        waiting on an approval nobody is there to give is a flow that has stopped.
        """
        return ["--auto"]

    def _reads(self, line: str, *, error: bool) -> Iterator[Event]:
        """Reads one event opencode wrote, as the things it says the agent did.

        Args:
          line: The line, as written.
          error: Whether it came from stderr, which is opencode's own log rather than the
            turn -- kept for a failed turn's diagnostic and shown nowhere.

        Yields:
          What it said, which is nothing for a line saying nothing worth showing.
        """
        if error:
            return
        try:
            said: dict[str, Any] = json.loads(line)
        except json.JSONDecodeError:
            return  # not ours: the odd plain line among the JSON
        part: dict[str, Any] = said.get("part") or {}
        kind = str(said.get("type") or "")
        if kind == "error":
            failed: dict[str, Any] = said.get("error") or {}
            self._failed = json.dumps(failed) if failed else "the turn failed"
        elif kind == "step_finish":
            self._spent += self._cost(cast("dict[str, Any]", part.get("tokens") or {}))
        elif kind == "tool_use":
            yield from self._tool(part)
        elif (says := _SAYS.get(kind)) is not None:
            words = str(part.get("text") or "")
            marked = str(part.get("id") or "")
            if not words.strip() or (marked and marked in self._shown):
                return  # a part already shown is not the agent saying it twice
            self._shown.add(marked)
            if says == "text":
                # The last thing it says is what the turn answers with; the reasoning on the
                # way there is shown and nothing more.
                self._said = words
            yield Event(kind=says, text=words)

    def _tool(self, part: dict[str, Any]) -> Iterator[Event]:
        """Reads one tool call, as the one line a row of a transcript has room for.

        Args:
          part: The `tool` part, as read.

        Yields:
          What it reached for and what with, once per call.
        """
        marked = str(part.get("id") or "")
        if marked and marked in self._shown:
            return
        self._shown.add(marked)
        state: dict[str, Any] = part.get("state") or {}
        called: dict[str, Any] = state.get("input") or {}
        about = str(state.get("title") or "") or next(
            (
                str(value)
                for value in called.values()
                if isinstance(value, str) and value.strip()
            ),
            "",
        )
        yield Event(
            kind="tool", text=f"{part.get('tool') or 'tool'} {about}".strip()[:120]
        )

    def _cost(self, counted: dict[str, Any]) -> int:
        """What one step of a turn cost, all told.

        Every kind of token counts: what a rate is measuring is the traffic, and a cache read
        crosses the wire like anything else. Reasoning is counted beside the output here
        rather than inside it, which is why it is added rather than left out.

        Args:
          counted: The step's `tokens`, as read.

        Returns:
          The tokens that step spent.
        """
        cached: dict[str, Any] = counted.get("cache") or {}
        return sum(int(counted.get(name) or 0) for name in _COUNTED) + sum(
            int(cached.get(name) or 0) for name in _CACHED
        )

    def _result(self, transcript: str) -> Event:
        """The turn's answer, and what it cost, out of the events it wrote.

        Args:
          transcript: The whole of stdout, already read event by event.

        Returns:
          The `result` the turn ends on.

        Raises:
          subprocess.CalledProcessError: If the turn failed. opencode leaves nonzero for the
            times it could not start at all and says everything else in its events, so a
            model that refused and a turn that said nothing whatever both come back as an
            exit of zero -- and a loop fed either as an answer would be running on it as the
            work of the turn.
        """
        said, failed, spent = self._said, self._failed, self._spent
        if failed is not None:
            raise subprocess.CalledProcessError(1, [type(self).command], said, failed)
        if not transcript.strip():
            raise subprocess.CalledProcessError(
                1, [type(self).command], "", f"{type(self).command} said nothing at all"
            )
        return Event(
            kind="result",
            text=said.strip(),
            tokens={self._agent.config.model: spent} if spent > 0 else {},
        )

    def _read_session_id(self, transcript: str) -> str:
        """Reads back the session opencode opened, which every event of the turn names.

        Args:
          transcript: Everything the turn printed.

        Returns:
          The session's id.

        Raises:
          ValueError: If nothing the turn wrote names one, which is a turn that landed
            somewhere nobody can find again.
        """
        for line in transcript.splitlines():
            try:
                said: object = json.loads(line)
            except ValueError:
                continue
            if not isinstance(said, dict):
                continue
            if named := cast("dict[str, Any]", said).get("sessionID"):
                return str(named)
        raise ValueError(f"{type(self).command} named no session")


@dataclass(frozen=True, kw_only=True)
class OpencodeAgentConfig(AgentConfig):
    """What opencode is configured with: the common model and effort, and nothing else.

    The model is written as opencode writes it, `provider/id` -- `opencode/big-pickle` --
    since a model here belongs to the provider that serves it and opencode is asked for the
    pair.
    """


class OpencodeAgent(AgentBase):
    """opencode, driven through its own command line, one run per turn."""

    def new(self) -> OpencodeSession:
        """Opens a new opencode session."""
        return OpencodeSession(self)

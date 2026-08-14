"""grok: one run of `grok -p` per turn, reading the stream of JSON it answers in.

Its command line says the whole of what an agent is configured with -- the model, how hard to
think, the session to carry on, what it may reach for -- so a turn is one run of it rather
than a conversation held open on a server. What it writes on stdout with
`--output-format streaming-json` is a protocol rather than the agent talking: one JSON object
a line, tagged by `type`, ending on the `end` that names the session and says what it cost.

The prompt goes on the command line because that is the only way in: Grok Build does not read
a piped stdin as the prompt, and the two other ways it offers are a JSON literal and a file.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar, cast

from .base import AgentBase, CommandSessionBase
from .config import AgentConfig
from .event import Event, Failed, Usage

if TYPE_CHECKING:
    import os
    from collections.abc import Iterator

#: What the CLI is installed as.
_COMMAND = "grok"

#: What a turn at each rung of the ladder is given, by the tool ids Grok Build calls its own.
#: An allowlist for the rung that may change nothing, since that is the only way to be sure a
#: tool cannot run at all; a denylist above it, where what is taken away is the reaching
#: outside the workspace. `--yolo` carries the rest: a flow watches its agent rather than
#: gating it, and a turn waiting on an approval nobody is there to give is a flow that stopped.
_ONLY = {"read-only": ("read_file", "grep", "list_dir")}
_WITHHELD = {"workspace-write": ("web_search", "web_fetch")}

#: And the same two where the reaching outside the workspace is refused on its own
#: rather than as a rung: an agent told not to search the web is refused them at every
#: rung, and one whose rung already refuses them is not refused them twice.
_WEB_TOOLS = ("web_search", "web_fetch")

#: What each kind of line reads as. A tool call that is only being updated is not shown
#: again: it was shown when it started, and a row per status is a transcript of statuses.
_SAYS = {"text": "text", "thought": "reasoning"}


class GrokBuildSession(CommandSessionBase):
    """A Grok Build conversation, resumed by the id its first turn reported.

    The id is minted by `grok` as the session opens and reported on the line the turn ends on,
    so it is read back out of the turn that opened it and given to every turn after -- which
    is what keeps the conversation one conversation rather than a new one per run. Asked for
    rather than chosen: `-s` takes an id, but refuses one already in use, and a flow that
    reopened a session it had already run would fail on its second turn.
    """

    #: What it writes on stdout is the turn as events rather than the agent talking.
    protocol: ClassVar[bool] = True

    #: `--json-schema` is a setting of the run: the answer comes back validated by the agent
    #: itself rather than asked for in the prompt.
    shapes: ClassVar[bool] = True

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
        #: if anything did. The text arrives in chunks, so the answer is what they come to.
        self._said: list[str] = []
        self._failed: str | None = None
        #: What the turn now running has cost, added up as each response of it comes back, and
        #: the tool calls already shown -- a call is shown as it starts and updated after.
        self._costing = Usage()
        self._shown: set[str] = set()

    def _turn(self, prompt: str) -> tuple[list[str], str | None]:
        """Builds the `grok -p` one turn is.

        Args:
          prompt: The input prompt for this turn.

        Returns:
          The command, and None because the prompt is inside it: Grok Build does not read a
          piped stdin as the prompt.
        """
        self._said, self._failed, self._shown = [], None, set()
        self._costing = Usage()
        argv = [
            _COMMAND,
            "--output-format",
            "streaming-json",
            "--model",
            self._agent.config.model,
            "--effort",
            self.effort,
            # Everything the rung leaves is approved without being asked.
            "--yolo",
        ]
        permission = self._agent.config.permission
        if only := _ONLY.get(permission):
            argv += ["--tools", ",".join(only)]
        withheld = list(_WITHHELD.get(permission, ()))
        if not self._agent.config.web_search:
            withheld += [one for one in _WEB_TOOLS if one not in withheld]
        if withheld:
            argv += ["--disallowed-tools", ",".join(withheld)]
        if (schema := self._shaping) is not None:
            argv += ["--json-schema", json.dumps(schema.model_json_schema())]
        if self._id is not None:
            argv += ["--resume", self._id]
        # Written onto the flag rather than after it: a prompt is a paragraph and may open
        # with a dash, and a value given with an `=` is a value whatever it starts with.
        return [*argv, f"--single={prompt}"], None

    def _reads(self, line: str, *, error: bool) -> Iterator[Event]:
        """Reads one line Grok Build wrote, as the things it says the agent did.

        Args:
          line: The line, as written.
          error: Whether it came from stderr, which is its own log rather than the turn --
            kept for a failed turn's diagnostic and shown nowhere.

        Yields:
          What it said, which is nothing for a line saying nothing worth showing.
        """
        if error:
            return
        try:
            said: dict[str, Any] = json.loads(line)
        except json.JSONDecodeError:
            return  # not ours: the odd plain line among the JSON
        kind = str(said.get("type") or "")
        if kind == "error":
            self._failed = str(said.get("message") or "") or json.dumps(said)
        elif kind == "tool_call":
            marked = str(said.get("toolCallId") or "")
            if marked not in self._shown:
                self._shown.add(marked)
                yield Event(kind="tool", text=_called(said))
        elif kind == "usage":
            # Told as each response lands rather than once the run is over, which is what a
            # rate read while the turn is still running is made of. The line the turn ends on
            # carries the same spending added up, so only these are counted.
            self._costing = self._costing + self._cost(
                cast("dict[str, Any]", said.get("usage") or {})
            )
        elif (says := _SAYS.get(kind)) is not None:
            words = str(said.get("data") or "")
            if words:
                if says == "text":
                    self._said.append(words)
                yield Event(kind=says, text=words)

    def _cost(self, counted: dict[str, Any]) -> Usage:
        """What one response cost, by the kind each token went on.

        Every kind counts: what a rate is measuring is the traffic, and a cache read crosses
        the wire like anything else. The input count is the uncached part alone here, which is
        why the two cache counts are added rather than folded into it.

        Args:
          counted: A `usage`, as read.

        Returns:
          What it spent.
        """
        return Usage(
            {
                name: float(counted.get(name) or 0)
                for name in (
                    "input_tokens",
                    "output_tokens",
                    "cache_read_input_tokens",
                    "cache_creation_input_tokens",
                    "reasoning_tokens",
                )
                if counted.get(name)
            }
        )

    def _result(self, transcript: str) -> Event:
        """The turn's answer, and what it cost, out of the lines it wrote.

        Args:
          transcript: The whole of stdout, already read line by line.

        Returns:
          The `result` the turn ends on.

        Raises:
          subprocess.CalledProcessError: If the turn failed. Grok Build says so on a line of
            its own as well as in its exit status, and a loop fed that as an answer would be
            running on it as the work of the turn.
        """
        said = "".join(self._said)
        if self._failed is not None:
            raise Failed(1, [_COMMAND], said, self._failed)
        if not transcript.strip():
            raise Failed(1, [_COMMAND], "", f"{_COMMAND} said nothing at all")
        spent = int(self._costing.total)
        return Event(
            kind="result",
            text=said.strip(),
            tokens={self._agent.config.model: spent} if spent > 0 else {},
            spent=self._costing,
        )

    def _read_session_id(self, transcript: str) -> str:
        """Reads back the session Grok Build opened, which the line it ends on names.

        Only that line: the stream has no preamble, so the id is not there to be read until
        the turn is over.

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
            if isinstance(said, dict) and (
                named := cast("dict[str, Any]", said).get("sessionId")
            ):
                return str(named)
        raise ValueError(f"{_COMMAND} named no session")


def _called(said: dict[str, Any]) -> str:
    """One tool call as the one line a row of a transcript has room for.

    Args:
      said: The `tool_call` line, as read.

    Returns:
      What it reached for and what with.
    """
    given: dict[str, Any] = said.get("rawInput") or {}
    about = str(said.get("title") or "") or next(
        (
            str(value)
            for value in given.values()
            if isinstance(value, str) and value.strip()
        ),
        "",
    )
    named = said.get("toolName") or said.get("kind") or "tool"
    return f"{named} {about}".strip()[:120]


@dataclass(frozen=True, kw_only=True)
class GrokBuildAgentConfig(AgentConfig):
    """What Grok Build is configured with: the common model and effort, and nothing else.

    The model is written as Grok Build writes it, which is a name out of its own catalogue --
    `grok models` is what lists them.
    """


class GrokBuildAgent(AgentBase):
    """Grok Build, driven through its own command line, one run per turn."""

    def new(self, cwd: str | os.PathLike[str] | None = None) -> GrokBuildSession:
        """Opens a new Grok Build session, in the directory it is given or in this one."""
        return GrokBuildSession(self, cwd)

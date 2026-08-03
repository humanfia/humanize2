"""qwen: one run of `qwen` per turn, reading the stream of JSON it answers in.

Its command line says everything an agent is configured with except how hard to think -- the
model, the session to carry on, what it may do without being asked -- so a turn is one run of
it rather than a conversation held open on a server. What it writes on stdout with
`--output-format stream-json` is a protocol rather than the agent talking: one JSON object a
line, the session it opened and the answer it ended on among them.

How hard it thinks is the one setting with no flag. It is a setting of the CLI's own
`settings.json`, and the run is pointed at a file of ours through `QWEN_CODE_SYSTEM_SETTINGS_PATH`
rather than having it written into the user's -- two agents of one flow may think at two
efforts, and neither is a reason to change what the person who started the flow has configured.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, cast

from .base import AgentBase, CommandSessionBase
from .config import AgentConfig
from .event import Event, Usage

if TYPE_CHECKING:
    import os
    from collections.abc import Iterator

#: What the CLI is installed as, and the variable that points one run at a settings file of
#: ours. The system layer rather than the user's own: it is read for this process only, and
#: what it says outranks the file the person who started the flow has configured.
_COMMAND = "qwen"
_SETTINGS = "QWEN_CODE_SYSTEM_SETTINGS_PATH"

#: The tools a turn is not given at each rung of the ladder, by the names Qwen Code calls
#: them. A rung is said as refusals because the flag that carries the rest is the approval
#: mode: what the agent may not do is taken away, and everything left is approved without
#: being asked -- a run per turn has nobody to answer it.
_WITHHELD = {
    "read-only": ("edit", "write_file", "notebook_edit", "run_shell_command"),
    "workspace-write": ("web_fetch",),
    "auto": (),
    "bypass": (),
}

#: What each kind of thing said reads as. `assistant` carries the agent talking and the tools
#: it reached for in the one message; `result` is the turn's own answer and is read for what
#: it cost rather than shown twice.
_SAYS = {"text": "text", "thinking": "reasoning"}

#: Where the settings files that say how hard to think are kept, one per effort there is.
#: One directory for the process rather than one per session: a flow that opens a session a
#: turn would otherwise leave a directory behind for every turn it ran, and what is in these
#: files is the effort and nothing else -- so two sessions at one effort are one file.
_EFFORTS: dict[str, Path] = {}


def _thinking(effort: str) -> Path:
    """The settings file a turn at one effort is run against, written once.

    Qwen Code has no flag for how hard to think: it is a setting of its own `settings.json`,
    so a run is pointed at a file of ours instead of having it written into the user's. The
    system layer, which is the one that outranks what they have configured.

    Args:
      effort: How hard the turn is to think, as Qwen Code words it.

    Returns:
      The file's path.
    """
    held = _EFFORTS.get(effort)
    if held is None:
        # Kept for as long as the process runs: a turn reads it as it starts, and every later
        # turn at this effort reads the same one.
        where = Path(tempfile.mkdtemp(prefix="hmz-qwen-"))
        held = where / "settings.json"
        held.write_text(
            json.dumps({"model": {"reasoningEffort": effort}}), encoding="utf-8"
        )
        _EFFORTS[effort] = held
    return held


class QwenCodeSession(CommandSessionBase):
    """A Qwen Code conversation, resumed by the id its first turn reported.

    The id is minted by `qwen` as the session opens, so it is read back out of the turn that
    opened it and given to every turn after -- which is what keeps the conversation one
    conversation rather than a new one per run. Asked for rather than chosen: `--session-id`
    takes one, but refuses an id that has been used before, and a flow that reopens a session
    it has already run is a flow that would fail on the second turn.
    """

    #: What it writes on stdout is the turn as events rather than the agent talking.
    protocol: ClassVar[bool] = True

    #: `--json-schema` is a setting of the run: the turn is held to the shape by a tool of the
    #: CLI's own making rather than by being asked for it in the prompt.
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
        #: What the agent has said so far in the turn now running, and what it answered with.
        #: The answer is the `result` record rather than the last thing said: a turn that ends
        #: on a tool has still answered.
        self._said = ""
        self._failed: str | None = None
        #: What the turn now running has cost, and which parts of it have been shown -- one
        #: message is said once, and a stream that repeats it would show it twice.
        self._costing = Usage()
        self._shown: set[str] = set()

    def _turn(self, prompt: str) -> tuple[list[str], str | None]:
        """Builds the `qwen` one turn is, and hands it the prompt on stdin.

        On stdin rather than as an argument: a prompt is a paragraph and may open with a dash,
        neither of which belongs on a command line. Qwen Code takes what is on stdin as the
        prompt when it is given none of its own, which is what makes the turn headless.

        Args:
          prompt: The input prompt for this turn.

        Returns:
          The command and the prompt to write to it.
        """
        self._said, self._failed, self._shown = "", None, set()
        self._costing = Usage()
        argv = [
            _COMMAND,
            "--output-format",
            "stream-json",
            "--model",
            self._agent.config.model,
            # Everything the rung leaves is approved without being asked: a flow watches its
            # agent rather than gating it, and a turn waiting on an approval nobody is there
            # to give is a flow that has stopped.
            "--approval-mode",
            "yolo",
        ]
        withheld = _WITHHELD.get(self._agent.config.permission, ())
        if withheld:
            argv += ["--exclude-tools", ",".join(withheld)]
        if (schema := self._shaping) is not None:
            # The shape as the CLI takes it: a JSON literal on the command line, which it
            # holds the last message to rather than asking the model to keep to.
            argv += ["--json-schema", json.dumps(schema.model_json_schema())]
        # The first turn opens the conversation and every later one resumes it by the id that
        # first turn reported.
        argv += ["--resume", self._id] if self._id is not None else []
        return argv, prompt

    def _environment(self) -> dict[str, str]:
        """What the turn runs with, plus the settings file that says how hard to think.

        Written once per session and pointed at rather than written into the user's own
        settings: two agents of one flow may be run at two efforts, and neither is a reason to
        change what the person who started the flow has configured. The system layer, because
        that is the one that outranks what they have configured.
        """
        return {**super()._environment(), _SETTINGS: str(_thinking(self.effort))}

    def _reads(self, line: str, *, error: bool) -> Iterator[Event]:
        """Reads one record Qwen Code wrote, as the things it says the agent did.

        Args:
          line: The line, as written.
          error: Whether it came from stderr, which is the CLI's own log rather than the turn
            -- kept for a failed turn's diagnostic and shown nowhere.

        Yields:
          What it said, which is nothing for a record saying nothing worth showing.
        """
        if error:
            return
        try:
            said: dict[str, Any] = json.loads(line)
        except json.JSONDecodeError:
            return  # not ours: the odd plain line among the JSON
        kind = str(said.get("type") or "")
        if kind == "assistant":
            yield from self._message(cast("dict[str, Any]", said.get("message") or {}))
        elif kind == "result":
            # The turn's own answer, which is what it ends on. Held rather than shown: the
            # agent already said these words as it said them.
            self._said = str(said.get("result") or "")
            self._costing = self._costing + self._cost(
                cast("dict[str, Any]", said.get("usage") or {})
            )
            if said.get("is_error"):
                failed: dict[str, Any] = said.get("error") or {}
                self._failed = str(failed.get("message") or "") or json.dumps(said)

    def _message(self, message: dict[str, Any]) -> Iterator[Event]:
        """Reads one message the model produced, which is text and tools together.

        Args:
          message: The `message` of an `assistant` record, as read.

        Yields:
          What it said and what it reached for, each part once.
        """
        marked = str(message.get("id") or "")
        # Counted where it is reported: a message carries the usage of the request that
        # produced it, so a turn of several is the sum of them rather than the last one.
        self._costing = self._costing + self._cost(
            cast("dict[str, Any]", message.get("usage") or {})
        )
        # A message said twice is the stream repeating itself rather than the agent saying it
        # again -- but only an id tells them apart, so one that names itself with nothing is
        # shown rather than taken for the last one.
        if marked:
            if marked in self._shown:
                return
            self._shown.add(marked)
        for one in cast("list[Any]", message.get("content") or []):
            if not isinstance(one, dict):
                continue
            part = cast("dict[str, Any]", one)
            kind = str(part.get("type") or "")
            if kind == "tool_use":
                yield Event(kind="tool", text=_called(part))
            elif (says := _SAYS.get(kind)) is not None:
                words = str(part.get("text") or part.get("thinking") or "")
                if words.strip():
                    yield Event(kind=says, text=words)

    def _cost(self, counted: dict[str, Any]) -> Usage:
        """What one request cost, by the kind each token went on.

        Every kind counts: what a rate is measuring is the traffic, and a cache read crosses
        the wire like anything else.

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
                    "thoughts_tokens",
                )
                if counted.get(name)
            }
        )

    def _result(self, transcript: str) -> Event:
        """The turn's answer, and what it cost, out of the records it wrote.

        Args:
          transcript: The whole of stdout, already read record by record.

        Returns:
          The `result` the turn ends on.

        Raises:
            subprocess.CalledProcessError: If the turn failed. Qwen Code says so in its own
              records as well as in its exit status -- a model that refused comes back as an
              exit of zero -- and a loop fed that as an answer would be running on it as the
              work of the turn.
        """
        if self._failed is not None:
            raise subprocess.CalledProcessError(1, [_COMMAND], self._said, self._failed)
        if not transcript.strip():
            raise subprocess.CalledProcessError(
                1, [_COMMAND], "", f"{_COMMAND} said nothing at all"
            )
        spent = int(self._costing.total)
        return Event(
            kind="result",
            text=self._said.strip(),
            tokens={self._agent.config.model: spent} if spent > 0 else {},
            spent=self._costing,
        )

    def _read_session_id(self, transcript: str) -> str:
        """Reads back the session Qwen Code opened, which every record of the turn names.

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
                named := cast("dict[str, Any]", said).get("session_id")
            ):
                return str(named)
        raise ValueError(f"{_COMMAND} named no session")


def _called(part: dict[str, Any]) -> str:
    """One tool call as the one line a row of a transcript has room for.

    Args:
      part: The `tool_use` block, as read.

    Returns:
      What it reached for and what with.
    """
    given: dict[str, Any] = part.get("input") or {}
    about = next(
        (
            str(value)
            for value in given.values()
            if isinstance(value, str) and value.strip()
        ),
        "",
    )
    return f"{part.get('name') or 'tool'} {about}".strip()[:120]


@dataclass(frozen=True, kw_only=True)
class QwenCodeAgentConfig(AgentConfig):
    """What Qwen Code is configured with: the common model and effort, and nothing else.

    The model is written as Qwen Code writes it, which is the id its endpoint serves -- it is
    an OpenAI-compatible client, so what it runs is what the account behind it offers.
    """


class QwenCodeAgent(AgentBase):
    """Qwen Code, driven through its own command line, one run per turn."""

    def new(self, cwd: str | os.PathLike[str] | None = None) -> QwenCodeSession:
        """Opens a new Qwen Code session, in the directory it is given or in this one."""
        return QwenCodeSession(self, cwd)

"""Antigravity CLI held across ordinary turns through its official NDJSON protocol.

Slash commands and shaped turns use finite commands, preserving the CLI's print-mode
behavior. Native cumulative usage follows the conversation across both transports and
process restarts; each result here reports only its own turn's cost.
"""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, cast

from ._inputs import snapshot
from .base import AgentBase, CommandSessionBase, SessionBase, StreamSessionBase
from .config import AgentConfig
from .event import Event, Failed, Usage

if TYPE_CHECKING:
    from collections.abc import Iterator

    from pydantic import BaseModel

#: What the CLI is installed as. The tarball calls the file `antigravity` and the installer
#: puts it down under this name, which is what a command line reaches for.
_COMMAND = "agy"

#: The rungs it can actually be run at. There is one switch -- approve everything, or ask --
#: and nobody is there to be asked, so a rung it cannot express is refused where the agent is
#: made rather than silently run as something else.
_TAKES = ("auto", "bypass")

#: What a step says it is doing, as the one line a row of a transcript has room for.
_THINKING = "THINKING"


def _native(
    cwd: Path, environment: dict[str, str], args: tuple[str, ...] = ()
) -> bytes | None:
    """Fingerprints native customizations, including inherited external skill roots.

    Runtime databases, caches and logs are not configuration inputs. Missing roots are
    included so installing a new native skill between turns restarts the held process.
    """
    home = Path(environment.get("HOME") or Path.home())
    directory = "antigravity-cli"
    extra: list[Path] = []
    for index, argument in enumerate(args):
        name, separator, value = argument.partition("=")
        if name not in ("--app_data_dir", "--add-dir"):
            continue
        if not separator and index + 1 < len(args):
            value = args[index + 1]
        if not value:
            # A flag with nothing after it names nothing. Left as it was rather than taken
            # as "": an empty data directory is `~/.gemini` itself, which is the whole of
            # that home walked and read every turn instead of the one directory under it.
            continue
        if name == "--app_data_dir":
            directory = value
        else:
            extra.append(cwd / Path(value).expanduser())
    native = (home / ".gemini" / directory).resolve()
    roots = {home / ".gemini/config", native}
    ancestors = (cwd, *cwd.parents, *extra)
    roots.update(parent / ".agents" for parent in ancestors)
    roots.update(parent / ".agent" for parent in ancestors)
    paths = {
        parent / name
        for parent in (*ancestors, home / ".gemini")
        for name in ("AGENTS.md", "GEMINI.md")
    }
    files = ("settings.json", "config.json", "mcp_config.json", "hooks.json")
    directories = ("skills", "plugins", "agents", "rules", "workflows")
    for root in roots:
        paths.update(root / name for name in (*files, *directories))
    paths.add(native / "builtin")
    pending = [
        root / name for root in roots for name in ("skills.json", "plugins.json")
    ]
    seen: set[Path] = set()
    repository = next(
        (parent for parent in ancestors if (parent / ".git").exists()), cwd
    )
    while pending:
        path = pending.pop()
        if path in seen:
            continue
        seen.add(path)
        paths.add(path)
        try:
            raw: object = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            continue
        except (OSError, UnicodeError, ValueError):
            return None
        if not isinstance(raw, dict):
            return None
        config = cast("dict[str, Any]", raw)
        for kind in ("entries", "inherits"):
            entries = config.get(kind, [])
            if not isinstance(entries, list):
                return None
            for entry in cast("list[object]", entries):
                if not isinstance(entry, dict):
                    return None
                value = cast("dict[str, Any]", entry).get("path")
                if not isinstance(value, str):
                    return None
                target = repository / Path(value).expanduser()
                paths.add(target)
                if kind == "inherits":
                    pending.append(target)
    return snapshot(paths)


class AntigravityCLISession(StreamSessionBase):
    """An Antigravity conversation, resumed by the id its first turn reported.

    The id is minted by `agy` as the conversation opens and named on the line the stream opens
    with, so it is read back out of the turn that opened it and given to every turn after --
    it takes no id of its own choosing.
    """

    #: What it writes on stdout is the turn as events rather than the agent talking.
    protocol: ClassVar[bool] = True

    #: `--json-schema` is a setting of the run: the answer comes back under `structured_output`
    #: rather than being asked for in the prompt.
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
        #: What the agent answered with, and what went wrong with it if anything did.
        self._said = ""
        self._failed: str | None = None
        #: What the turn now running has cost, which it reports once, at the end.
        self._costing = Usage()
        self._previous = Usage()
        self._announced: str | None = None
        self._launched: tuple[object, ...] | None = None
        self._requested: tuple[object, ...] = ()

    def _stream(
        self, prompt: str, *, schema: type[BaseModel] | None = None
    ) -> Iterator[Event]:
        """Keeps ordinary turns warm and preserves print-only command behavior."""
        with self._lock:
            try:
                if schema is not None or prompt.lstrip().startswith("/"):
                    self._shut()
                    yield from CommandSessionBase._stream(  # noqa: SLF001 -- shared transport
                        cast("CommandSessionBase", self), prompt, schema=schema
                    )
                else:
                    self._requested = self._settings()
                    yield from super()._stream(prompt)
            except BaseException:
                self._shut()
                if self._id is None:
                    self._previous = Usage()
                raise

    def _command(self) -> list[str]:
        """Starts the official stream driver without a finite --print prompt."""
        argv, _ = self._turn("")
        return [*argv[:-2], "--input-format", "stream-json"]

    def _settings(self) -> tuple[object, ...]:
        """Remembers the configuration and resources read when the CLI starts."""
        environment = self._environ() or dict(os.environ)
        provider = self._agent.node()
        native = _native(Path(self.cwd), environment, provider.args)
        return (
            self._agent.config,
            self.effort,
            self._carrying(),
            self._tools,
            environment,
            provider,
            snapshot({Path(target) for _, target in provider.swaps()}),
            native if native is not None else object(),
        )

    def _stale(self) -> bool:
        """Restarts before changed native or flow inputs can become stale."""
        return self._launched is not None and self._launched != self._requested

    def _restarted(self) -> None:
        """Records process inputs; native usage survives --conversation resumes."""
        self._launched = self._requested

    def _write(self, text: str, ticket: str = "") -> str:
        """Encodes one prompt in Antigravity's event-tagged NDJSON format."""
        del ticket
        return json.dumps({"event": "user", "message": {"content": text}}) + "\n"

    def interject(self, text: str) -> None:
        """Keeps steering unsupported: the native protocol has no receipt ticket."""
        SessionBase.interject(self, text)

    def _read(self, line: str) -> Iterator[Event]:
        """Reads one native event and commits its conversation only on success."""
        try:
            raw: object = json.loads(line)
        except ValueError:
            return
        if not isinstance(raw, dict):
            return
        said = cast("dict[str, Any]", raw)
        yield from self._record(said)
        if named := said.get("conversation_id"):
            self._announced = str(named)
        if said.get("event") == "result":
            result = self._result(line)
            if self._id is None:
                self._adopt(self._announced or self._read_session_id(line))
            yield result

    def _turn(self, prompt: str) -> tuple[list[str], str | None]:
        """Builds the `agy -p` one turn is.

        Args:
          prompt: The input prompt for this turn.

        Returns:
          The command, and None because the prompt is inside it: Antigravity CLI reads no
          prompt off stdin.
        """
        self._said, self._failed = "", None
        self._costing = Usage()
        self._announced = None
        argv = [
            _COMMAND,
            "--output-format",
            "stream-json",
            "--model",
            self._agent.config.model,
            # Project selection can replace the CLI's initial cwd with a scratch directory.
            # Keep this session's workspace explicit, beside any provider-supplied roots.
            "--add-dir",
            self.cwd,
            # Nobody is there to answer it: a flow watches its agent rather than gating it.
            "--dangerously-skip-permissions",
        ]
        # And no `--effort`: how hard to think is part of the model here. Antigravity lists
        # `gemini-3.7-flash-high`, `-medium` and `-low` as three models, and refuses the flag
        # beside every model it lists -- as `conflicts with --effort` where the name carries
        # one that differs, and as `--effort is not supported for model` where the name
        # carries none. The effort is chosen by choosing the model.
        if (schema := self._shaping) is not None:
            argv += ["--json-schema", json.dumps(schema.model_json_schema())]
        if self._id is not None:
            argv += ["--conversation", self._id]
        # Its flags are Go's, which take the next word whatever it starts with, so a prompt
        # opening with a dash is still a prompt.
        return [*argv, "--print", prompt], None

    def _reads(self, line: str, *, error: bool) -> Iterator[Event]:
        """Reads one line Antigravity CLI wrote, as the things it says the agent did.

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
            raw: object = json.loads(line)
        except ValueError:
            return
        if isinstance(raw, dict):
            yield from self._record(cast("dict[str, Any]", raw))

    def _record(self, said: dict[str, Any]) -> Iterator[Event]:
        """Shares native event parsing between persistent and finite transports."""
        kind = str(said.get("event") or "")
        # The payload sits under a key of the event's own name rather than beside it.
        told = cast("dict[str, Any]", said.get(kind) or {})
        if kind == "step_update":
            yield from self._step(told)
        elif kind == "result":
            self._said = str(told.get("response") or "")
            if self._shaping is not None and "structured_output" in told:
                # Display text includes rejected finish calls and native tool metadata.
                # Only the final structured value is the answer to the requested schema.
                self._said = json.dumps(told["structured_output"])
            cumulative = self._cost(cast("dict[str, Any]", told.get("usage") or {}))
            self._costing = Usage(
                {
                    name: max(0.0, value - self._previous.get(name, 0.0))
                    for name, value in cumulative.items()
                }
            )
            # Local commands such as /help report zeros, without resetting the resumed
            # conversation's cumulative usage. Omitted counters retain their baseline.
            self._previous = Usage({**self._previous, **cumulative})
            # It says how the run ended in a word rather than only in its exit status, and a
            # run that was cancelled or refused is not a turn that landed.
            status = str(told.get("status") or "")
            if failed := str(told.get("error") or ""):
                self._failed = failed
            elif status and status != "SUCCESS":
                self._failed = status

    def _step(self, told: dict[str, Any]) -> Iterator[Event]:
        """Reads one step of the turn, which is a piece of an answer or a tool going by.

        Args:
          told: The `step_update` payload, as read.

        Yields:
          What that step said, which is nothing for one that only moved a state along.
        """
        if words := str(told.get("text_delta") or ""):
            kind = (
                "reasoning" if str(told.get("step_type") or "") == _THINKING else "text"
            )
            yield Event(kind=kind, text=words)
            return
        # A tool is shown as it starts rather than once per state it passes through.
        named = str(told.get("tool_name") or "")
        if named and str(told.get("state") or "") != "DONE":
            about: dict[str, Any] = told.get("tool_info") or {}
            first = next(
                (
                    str(value)
                    for value in about.values()
                    if isinstance(value, str) and value.strip()
                ),
                "",
            )
            yield Event(kind="tool", text=f"{named} {first}".strip()[:120])

    def _cost(self, counted: dict[str, Any]) -> Usage:
        """What the turn cost, by the kind each token went on.

        Args:
          counted: The `usage`, as read.

        Returns:
          What it spent.
        """
        return Usage(
            {
                name: float(counted.get(name) or 0)
                for name in (
                    "input_tokens",
                    "output_tokens",
                    "thinking_tokens",
                    "cache_read_tokens",
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
          subprocess.CalledProcessError: If the turn failed, which it says in a word of its own
            as well as in its exit status.
        """
        if self._failed is not None:
            raise Failed(1, [_COMMAND], self._said, self._failed)
        if not transcript.strip():
            raise Failed(1, [_COMMAND], "", f"{_COMMAND} said nothing at all")
        spent = int(self._costing.total)
        return Event(
            kind="result",
            text=self._said.strip(),
            tokens={self._agent.config.model: spent} if spent > 0 else {},
            spent=self._costing,
        )

    def _read_session_id(self, transcript: str) -> str:
        """Reads back the conversation it opened, which the line it opens with names.

        Args:
          transcript: Everything the turn printed.

        Returns:
          The conversation's id.

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
            held = cast("dict[str, Any]", said)
            # Named at the top of the line it opens with, and again inside the one it ends on.
            named = held.get("conversation_id") or cast(
                "dict[str, Any]", held.get("result") or {}
            ).get("conversation_id")
            if named:
                return str(named)
        raise ValueError(f"{_COMMAND} named no conversation")


@dataclass(frozen=True, kw_only=True)
class AntigravityCLIAgentConfig(AgentConfig):
    """What Antigravity CLI is configured with: the common model and effort, and nothing else.

    The model is written as `agy models` lists it, which is a slug of its own -- and the
    effort is part of that slug, `gemini-3.7-flash-low` being that model at that effort. So
    the effort here is what a model was chosen at rather than something the CLI is told: it
    refuses the flag beside every model it lists.
    """


class AntigravityCLIAgent(AgentBase):
    """Antigravity CLI, driven through its own persistent stream-json protocol."""

    def __init__(self, config: AgentConfig, *, name: str | None = None) -> None:
        """Makes the agent, refusing a rung this backend has no way of running at.

        Args:
          config: What its turns run at.
          name: What the flow calls it, or None for one of its own.

        Raises:
          ValueError: If it was configured to be allowed less than everything. Antigravity CLI
            has one switch -- approve every tool, or stop and ask -- and nobody is at a prompt
            to be asked, so a rung it cannot express is said here rather than quietly run as
            the rung above it.
        """
        if config.permission not in _TAKES:
            raise ValueError(
                f"{_COMMAND} runs at {' or '.join(_TAKES)} only, "
                f"not {config.permission}: it has no way of being allowed less"
            )
        super().__init__(config, name=name)

    def new(self, cwd: str | os.PathLike[str] | None = None) -> AntigravityCLISession:
        """Opens a new Antigravity conversation, in the directory it is given or in this one."""
        return AntigravityCLISession(self, cwd)

"""DeepSeek Harness, driven through its Python SDK."""

# A session and the agent holding it are two halves of one object declared here.
# pyright: reportPrivateUsage=false

from __future__ import annotations

import contextlib
import importlib
import importlib.resources
import io
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
import weakref
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, Protocol, Self, cast

import yaml

from .base import AgentBase, SessionBase
from .config import AgentConfig
from .event import Event, Usage, say

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Mapping

    from pydantic import BaseModel

__all__ = ["DshAgent", "DshAgentConfig", "DshSession"]

_EFFORTS = ("max", "high", "off")
_EFFORT_ENV = "HMZ_DSH_EFFORT"
_REQUEST_SECONDS = 180.0
_API_KEY_ENV = "DEEPSEEK_API_KEY"
_BASE_URL_ENV = "DEEPSEEK_BASE_URL"
_REF = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_EXTRA = (
    "DeepSeek Harness is not installed in this Python environment; install humanize "
    "with its dsh extra: pip install 'hmz[dsh]'"
)
_KEY_REQUIRED = (
    "DeepSeek Harness only supports API-key login and needs a DeepSeek API key. Save one "
    "in dsh under Settings -> Models; in hmz, open /agents, switch to dsh, press ctrl+n, "
    "and create a key account; or set DEEPSEEK_API_KEY before starting hmz."
)
_GOAL = "Use create_goal to pursue this objective until it is complete:\n\n{}"


class _Subscription(Protocol):
    """The part of an SDK notification subscription used by a turn."""

    def __enter__(self) -> Self: ...

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None: ...

    def next(self) -> object: ...


class _Client(Protocol):
    """The low-level public SDK calls used to stream one session."""

    def subscribe_session_notifications(self, session_id: str) -> _Subscription: ...

    def session_prompt(
        self,
        session_id: str,
        content_blocks: list[dict[str, Any]],
        *,
        notification_subscription: _Subscription,
    ) -> str: ...


class _Harness(Protocol):
    """A running SDK harness and its low-level client."""

    client: _Client

    def start(self) -> None: ...

    def close(self) -> None: ...


class _ObjectLoader(Protocol):
    """The typed part of PyYAML's loader used by duplicate-key validation."""

    def construct_object(
        self,
        node: yaml.Node,
        deep: bool = False,  # noqa: FBT001, FBT002 -- mirrors PyYAML's method
    ) -> object: ...


@dataclass(frozen=True, kw_only=True)
class DshAgentConfig(AgentConfig):
    """The model and effort every DeepSeek Harness session runs at."""


class DshAgent(AgentBase):
    """A DeepSeek Harness agent using the bundled SDK runtime."""

    #: The official goal service keeps the session working until its objective is complete.
    pursues: ClassVar[bool] = True

    def __init__(self, config: DshAgentConfig, *, name: str | None = None) -> None:
        super().__init__(config, name=name)

    def new(self, cwd: str | os.PathLike[str] | None = None) -> DshSession:
        """Opens an SDK session, which stays unopened until its first turn."""
        return DshSession(self, cwd)


class DshSession(SessionBase):
    """One durable DeepSeek Harness conversation."""

    def __init__(
        self, agent: DshAgent, cwd: str | os.PathLike[str] | None = None
    ) -> None:
        super().__init__(agent, cwd)
        self._harness: _Harness | None = None
        self._runtime_effort: str | None = None
        self._attempt_id: str | None = None
        self._reaper: weakref.finalize[..., Any] | None = None

    @property
    def named(self) -> str | None:
        """The durable id, including the one whose opening turn is still running."""
        return super().named or self._attempt_id

    def _stream(
        self, prompt: str, *, schema: type[BaseModel] | None = None
    ) -> Iterator[Event]:
        """Runs one SDK turn and maps its session notifications as they arrive."""
        del schema  # SessionBase has already put unsupported shapes in the prompt.
        self._validate()
        session_id = self._id or f"session-{uuid.uuid4().hex}"
        self._attempt_id = session_id
        answer = ""
        costing = Usage()
        reason: Mapping[str, Any] | None = None
        streamed: set[tuple[object, object, str]] = set()
        anchored = self._agent.anchor is not None

        try:
            self._require_key(session_id)
            harness = self._running()
            with harness.client.subscribe_session_notifications(
                session_id
            ) as subscribed:
                message_id = harness.client.session_prompt(
                    session_id,
                    [{"type": "text", "text": prompt}],
                    notification_subscription=subscribed,
                )
                received = False
                while True:
                    method, payload = _notification(subscribed.next())
                    if not received:
                        if not _receipt(method, payload, session_id, message_id):
                            continue
                        received = True
                    if (
                        method == "session.event"
                        and payload.get("sessionId") == session_id
                    ):
                        event = _mapping(payload.get("event"))
                        data = _mapping(event.get("data"))
                        kind = event.get("type")
                        if kind == "assistant/chunk":
                            chunk = _mapping(data.get("chunk"))
                            block = str(chunk.get("type") or "")
                            event_kind = {
                                "text-delta": "text",
                                "reasoning-delta": "reasoning",
                            }.get(block)
                            text = chunk.get("text")
                            if (
                                event_kind is not None
                                and isinstance(text, str)
                                and text
                            ):
                                streamed.add(
                                    (data.get("turn"), data.get("step"), event_kind)
                                )
                                yield self._shows(Event(kind=event_kind, text=text))
                        elif kind == "assistant/message":
                            message = _mapping(data.get("message"))
                            content = message.get("content", data.get("content"))
                            blocks = (
                                cast("list[object]", content)
                                if isinstance(content, list)
                                else []
                            )
                            parts: list[str] = []
                            for raw in blocks:
                                block = _mapping(raw)
                                block_kind = block.get("type")
                                text = block.get("text")
                                if block_kind == "text" and isinstance(text, str):
                                    parts.append(text)
                                event_kind = (
                                    block_kind
                                    if block_kind in ("text", "reasoning")
                                    else None
                                )
                                key = (data.get("turn"), data.get("step"), event_kind)
                                if (
                                    event_kind is not None
                                    and isinstance(text, str)
                                    and text
                                    and key not in streamed
                                ):
                                    yield self._shows(Event(kind=event_kind, text=text))
                            answer = "".join(parts)
                            usage = _usage(data.get("usage"))
                            if usage.total:
                                self._spends(usage)
                                costing = costing + usage
                        elif kind == "tool/call":
                            name = str(data.get("name") or "tool")
                            about = str(data.get("arguments") or "")
                            yield self._shows(
                                Event(kind="tool", text=f"{name} {about}".rstrip())
                            )
                        elif kind == "turn/end":
                            reason = _mapping(data.get("reason"))
                    elif (
                        method == "session.status"
                        and payload.get("sessionId") == session_id
                        and payload.get("status") == "idle"
                    ):
                        break

            _require_completed(session_id, answer, reason)
            self._adopt(session_id)
            tokens = int(costing.total)
            result = Event(
                kind="result",
                text=answer,
                tokens={self._agent.config.model: tokens} if tokens else {},
                spent=costing,
            )
            if not self._agent._watchers:
                say(result.text, sys.stdout)
            yield result
        except subprocess.CalledProcessError as refused:
            self._shut()
            yield self._shows(Event(kind="failed", text=_diagnostic(refused)))
            raise
        except (ModuleNotFoundError, ValueError):
            self._shut()
            raise
        except Exception as why:
            self._shut()
            refused = subprocess.CalledProcessError(
                1, ["dsh", session_id], output=answer, stderr=str(why)
            )
            yield self._shows(Event(kind="failed", text=_diagnostic(refused)))
            raise refused from why
        finally:
            self._attempt_id = None
            if anchored:
                # Coganchor reconciles the mirror when the supervised process exits.
                self._shut()

    def _shows(self, event: Event) -> Event:
        """Shows an event on an unwatched run and returns it for the stream."""
        if not self._agent._watchers:
            say(event.text, sys.stderr)
        return event

    def _pursue(self, objective: str) -> str:
        """Runs the objective through Harness's persisted same-session goal service."""
        return self(_GOAL.format(objective))

    def _validate(self) -> None:
        """Refuses settings the SDK cannot faithfully apply."""
        if self.effort not in _EFFORTS:
            expected = ", ".join(_EFFORTS)
            raise ValueError(
                f"unsupported dsh effort {self.effort!r}; expected {expected}"
            )
        if self._agent.config.permission != "bypass":
            raise ValueError(
                "dsh exposes no per-session sandbox or approval controls; "
                "permission must be 'bypass'"
            )
        if self._agent.config.skills is not None:
            raise ValueError("dsh does not support selecting skills per agent")

    def _require_key(self, session_id: str) -> None:
        """Refuses an explicitly selected account that cannot authenticate dsh."""
        provider = self._agent.provider
        if provider is None:
            return
        key = provider.env.get(_API_KEY_ENV, "")
        if provider.way != "key" or not key.strip():
            raise subprocess.CalledProcessError(
                1, ["dsh", session_id], output="", stderr=_KEY_REQUIRED
            )

    def _running(self) -> _Harness:
        """Returns a runtime initialized for this session's current effort."""
        effort = self.effort
        if self._harness is not None and self._runtime_effort != effort:
            self._shut()
        if self._harness is not None:
            return self._harness

        harness_type = _harness_type()
        where = self._workspace()
        launch = self._agent.spawned(list(_runtime_args()), self.cwd)
        hushed = sorted(self._agent.hushed())
        if hushed:
            env = shutil.which("env")
            if env is None:
                raise FileNotFoundError(
                    "env is required to isolate dsh provider credentials"
                )
            launch = [env, *(part for name in hushed for part in ("-u", name)), *launch]
        environment = (
            _native_dsh_environment(Path(where))
            if self._agent.provider is None
            else dict(self._agent.environment())
        )
        environment[_EFFORT_ENV] = effort
        harness = harness_type(
            provider="deepseek-official",
            model=self._agent.config.model,
            cwd=where,
            runtime_cwd=where,
            session_root=str(_dsh_home() / "sessions"),
            cordis=str(
                importlib.resources.files("hmz.agents").joinpath("dsh.cordis.yml")
            ),
            env=environment,
            launch_args_override=tuple(launch),
            request_timeout_seconds=_REQUEST_SECONDS,
        )
        try:
            harness.start()
        except Exception:
            with contextlib.suppress(Exception):
                harness.close()
            raise
        self._harness = harness
        self._runtime_effort = effort
        self._reaper = weakref.finalize(self, harness.close)
        return harness

    def _shut(self) -> None:
        """Closes this session's SDK runtime without ending the conversation."""
        harness, self._harness = self._harness, None
        self._runtime_effort = None
        if self._reaper is not None:
            self._reaper.detach()
            self._reaper = None
        if harness is not None:
            with contextlib.suppress(Exception):
                harness.close()


def _harness_type() -> Callable[..., _Harness]:
    """Loads the SDK only when a dsh turn needs it."""
    try:
        module = importlib.import_module("deepseek_harness")
    except ModuleNotFoundError as why:
        if why.name != "deepseek_harness":
            raise
        raise ModuleNotFoundError(_EXTRA) from why
    return cast("Callable[..., _Harness]", vars(module)["DeepSeekHarness"])


def _runtime_args() -> tuple[str, ...]:
    """Resolves the executable bundled with the SDK."""
    try:
        module = importlib.import_module("deepseek_harness_runtime")
    except ModuleNotFoundError as why:
        if why.name != "deepseek_harness_runtime":
            raise
        raise ModuleNotFoundError(_EXTRA) from why
    resolve = cast(
        "Callable[[], tuple[str, ...]]",
        vars(module)["resolve_bundled_launch_args"],
    )
    return resolve()


def _dsh_home() -> Path:
    """Where dsh keeps durable sessions for SDK turns."""
    return (
        Path(os.environ.get("DSH_HOME") or Path.home() / ".dsh").expanduser().absolute()
    )


class _UniqueSafeLoader(yaml.SafeLoader):
    """A safe YAML loader that refuses silently shadowed duplicate keys."""


def _unique_mapping(
    loader: yaml.SafeLoader, node: yaml.MappingNode, *, deep: bool = False
) -> dict[object, object]:
    """Constructs one mapping while rejecting duplicate or unhashable keys."""
    loader.flatten_mapping(node)
    construct = cast("_ObjectLoader", loader).construct_object
    held: dict[object, object] = {}
    for key_node, value_node in node.value:
        key = construct(key_node, deep)
        try:
            duplicate = key in held
        except TypeError as why:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                "found an unhashable key",
                key_node.start_mark,
            ) from why
        if duplicate:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                "found a duplicate key",
                key_node.start_mark,
            )
        held[key] = construct(value_node, deep)
    return held


_UniqueSafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _unique_mapping
)


def _native_dsh_environment(where: Path) -> dict[str, str]:
    """Resolves the settings and credential layers used by an installed dsh."""
    home = _dsh_home()
    settings = _yaml_mapping(home / "settings.yaml", "settings")
    raw_section = settings.get("llm-deepseek", {})
    if not isinstance(raw_section, dict):
        raise ValueError(  # noqa: TRY004 -- all configuration errors share one API
            f"dsh settings at {home / 'settings.yaml'} must give "
            '"llm-deepseek" a mapping'
        )
    section = cast("dict[object, object]", raw_section)
    raw_ref = section.get("apiKeyEnv", _API_KEY_ENV)
    if not isinstance(raw_ref, str) or _REF.fullmatch(raw_ref) is None:
        raise ValueError(
            f"dsh settings at {home / 'settings.yaml'} have an invalid "
            '"llm-deepseek.apiKeyEnv"'
        )

    credentials = _credentials(home / ".credentials.yaml")
    project_env = _dotenv(where / ".env")
    user_env = {} if home == where else _dotenv(home / ".env")
    key = _nonempty(os.environ, raw_ref)
    if key is None:
        key = credentials.get(raw_ref)
    if key is None:
        key = _nonempty(project_env, raw_ref)
    if key is None:
        key = _nonempty(user_env, raw_ref)

    environment = {_API_KEY_ENV: key or ""}
    if "baseURL" in section:
        base_url = section["baseURL"]
        if not isinstance(base_url, str):
            raise ValueError(
                f"dsh settings at {home / 'settings.yaml'} must give "
                '"llm-deepseek.baseURL" a string'
            )
        environment[_BASE_URL_ENV] = base_url
    else:
        base_url = _layered(os.environ, project_env, user_env, name=_BASE_URL_ENV)
        if base_url is not None:
            environment[_BASE_URL_ENV] = base_url
    return environment


def _yaml_mapping(path: Path, kind: str) -> dict[object, object]:
    """Reads one optional YAML mapping without echoing its possibly secret source."""
    try:
        source = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    except (OSError, UnicodeError):
        raise ValueError(f"dsh could not read {kind} at {path}") from None
    try:
        loaded = yaml.load(source, Loader=_UniqueSafeLoader)  # noqa: S506
    except yaml.YAMLError as why:
        mark = getattr(why, "problem_mark", None)
        location = (
            f" at line {mark.line + 1}, column {mark.column + 1}"
            if mark is not None
            else ""
        )
        raise ValueError(f"dsh {kind} at {path} is invalid YAML{location}") from None
    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        raise ValueError(  # noqa: TRY004 -- all configuration errors share one API
            f"dsh {kind} at {path} must be a mapping"
        )
    return cast("dict[object, object]", loaded)


def _credentials(path: Path) -> dict[str, str]:
    """Reads dsh's owner-only credential mapping and validates every entry."""
    try:
        mode = path.stat().st_mode
    except FileNotFoundError:
        return {}
    except OSError:
        raise ValueError(f"dsh could not inspect credentials at {path}") from None
    if os.name != "nt" and mode & 0o077:
        raise ValueError(
            f"dsh credentials at {path} are readable beyond their owner; "
            f'run "chmod 600 {path}" before starting again'
        )
    raw = _yaml_mapping(path, "credentials")
    credentials: dict[str, str] = {}
    for ref, value in raw.items():
        if not isinstance(ref, str) or _REF.fullmatch(ref) is None:
            raise ValueError(
                f"dsh credentials at {path} contain an invalid credential reference"
            )
        if not isinstance(value, str):
            raise ValueError(  # noqa: TRY004 -- all configuration errors share one API
                f'dsh credentials at {path} must give "{ref}" a string value'
            )
        if not value:
            raise ValueError(
                f'dsh credentials at {path} give "{ref}" an empty value; '
                "remove the entry instead"
            )
        credentials[ref] = value
    return credentials


def _dotenv(path: Path) -> dict[str, str]:
    """Reads one optional dotenv layer without interpolation or process mutation."""
    try:
        source = path.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError, UnicodeError):
        return {}
    try:
        from dotenv import dotenv_values
    except ModuleNotFoundError as why:
        if why.name != "dotenv":
            raise
        raise ModuleNotFoundError(_EXTRA) from why
    values = dotenv_values(stream=io.StringIO(source), interpolate=False)
    return {name: value for name, value in values.items() if value is not None}


def _nonempty(values: Mapping[str, str], name: str) -> str | None:
    """Returns a present nonempty credential value from one layer."""
    value = values.get(name)
    return value or None


def _layered(*layers: Mapping[str, str], name: str) -> str | None:
    """Returns the first layer's value for a setting, including an empty one."""
    return next((layer[name] for layer in layers if name in layer), None)


def _notification(notification: object) -> tuple[str, Mapping[str, Any]]:
    """Reads one SDK notification without importing its optional model type."""
    method = getattr(notification, "method", "")
    payload = getattr(notification, "payload", {})
    return str(method), _mapping(payload)


def _mapping(value: object) -> Mapping[str, Any]:
    """Returns a wire object as a mapping, or an empty one for another JSON value."""
    return cast("Mapping[str, Any]", value) if isinstance(value, dict) else {}


def _receipt(
    method: str,
    payload: Mapping[str, Any],
    session_id: str,
    message_id: str,
) -> bool:
    """Whether a notification says this prompt entered the session inbox."""
    if method != "session.event" or payload.get("sessionId") != session_id:
        return False
    event = _mapping(payload.get("event"))
    if event.get("type") != "agent/inbox/spliced":
        return False
    inserted = _mapping(event.get("data")).get("inserted")
    if not isinstance(inserted, list):
        return False
    return any(
        _mapping(message).get("id") == message_id
        for message in cast("list[object]", inserted)
    )


def _usage(value: object) -> Usage:
    """Maps dsh's disjoint token counts onto humanize's common names."""
    raw = _mapping(value)
    kinds = {
        "input": _tokens(raw.get("inputTokens")),
        "output": _tokens(raw.get("outputTokens")),
    }
    for source, name in (
        ("cacheReadTokens", "cache_read"),
        ("cacheWriteTokens", "cache_write"),
    ):
        if source in raw:
            kinds[name] = _tokens(raw.get(source))
    # reasoningTokens is already part of outputTokens on the dsh contract.
    return Usage(kinds)


def _tokens(value: object) -> float:
    """Returns a non-negative numeric token count from the wire."""
    return (
        float(value)
        if isinstance(value, (int, float)) and not isinstance(value, bool)
        else 0.0
    )


def _failed(
    session_id: str, answer: str, reason: Mapping[str, Any] | None
) -> subprocess.CalledProcessError:
    """Turns a non-completed dsh turn end into the common turn failure."""
    held = reason or {}
    error = _mapping(held.get("error") or held.get("failure"))
    if error.get("code") == "MISSING_CREDENTIAL":
        why = _KEY_REQUIRED
    else:
        detail = error.get("message")
        why = str(detail) if isinstance(detail, str) and detail else json.dumps(held)
    return subprocess.CalledProcessError(
        1,
        ["dsh", session_id],
        output=answer,
        stderr=f"DeepSeek Harness turn did not complete: {why}",
    )


def _diagnostic(refused: subprocess.CalledProcessError) -> str:
    """Returns the useful words from a common turn failure without its traceback."""
    for value in (refused.stderr, refused.output):
        if isinstance(value, str) and value.strip():
            return value.strip()
    return str(refused)


def _require_completed(
    session_id: str, answer: str, reason: Mapping[str, Any] | None
) -> None:
    """Raises the common failure unless the dsh turn completed."""
    if reason is None or reason.get("kind") != "completed":
        raise _failed(session_id, answer, reason)

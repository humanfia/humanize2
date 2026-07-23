"""In-memory model shared by every trajectory collector."""

from __future__ import annotations

import dataclasses
import json
from typing import Any

_LABEL_KEYS = (
    "description",
    "command",
    "cmd",
    "file_path",
    "path",
    "pattern",
    "query",
    "url",
    "task_name",
    "target",
    "objective",
    "prompt",
    "message",
    "input",
)


@dataclasses.dataclass
class Action:
    """A single slice on a session track.

    Attributes:
        name: Human readable summary shown on the slice.
        category: Slice kind, one of turn, llm, tool, message or event, next to
            the session banner the trace adds.
        start: Wall clock start in epoch seconds.
        end: Wall clock end in epoch seconds.
        args: Detailed payload shown when the slice is selected.
        spawn: Key of the session this action started, if any.
    """

    name: str
    category: str
    start: float
    end: float
    args: dict[str, Any] = dataclasses.field(default_factory=dict)
    spawn: str | None = None


@dataclasses.dataclass
class Session:
    """One agent or sub-agent conversation, rendered as its own track.

    Attributes:
        key: Globally unique session identifier.
        agent: Name of the coding agent that produced the log.
        label: Role of this session, such as main or the sub-agent type.
        title: Human readable title, usually an id and the first prompt.
        parent: Key of the session that spawned this one, if any.
        args: Session wide details such as model, cwd and version.
        actions: Slices recorded for this session.
    """

    key: str
    agent: str
    label: str
    title: str
    parent: str | None = None
    args: dict[str, Any] = dataclasses.field(default_factory=dict)
    actions: list[Action] = dataclasses.field(default_factory=list)


def summarize(text: str, limit: int = 96) -> str:
    """Collapses text into a single short line usable as a slice name."""
    line = " ".join(text.split())
    return line if len(line) <= limit else line[: limit - 1] + "…"


def truncate(value: Any, limit: int = 4096) -> Any:
    """Clips long strings and wide containers so the trace stays loadable."""
    if isinstance(value, str):
        if len(value) <= limit:
            return value
        return f"{value[:limit]}… (+{len(value) - limit} chars)"
    if isinstance(value, dict):
        return {str(key): truncate(item, limit) for key, item in value.items()}
    if isinstance(value, list):
        clipped = [truncate(item, limit) for item in value[:32]]
        if len(value) > 32:
            clipped.append(f"… (+{len(value) - 32} items)")
        return clipped
    return value


def mapping(value: Any) -> dict[str, Any]:
    """Reads a log field as a mapping, treating anything else as an absent one."""
    return value if isinstance(value, dict) else {}


def text_of(content: Any) -> str:
    """Extracts the readable text carried by a message or content block."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
                continue
            if not isinstance(block, dict):
                continue
            for key in ("text", "think", "thinking", "output", "content"):
                value = block.get(key)
                if isinstance(value, str):
                    parts.append(value)
                    break
        return "\n".join(part for part in parts if part)
    if isinstance(content, dict):
        return text_of(content.get("text") or content.get("content"))
    return json.dumps(content, ensure_ascii=False)


def label(tool: str, tool_input: Any) -> str:
    """Names a tool slice after the most descriptive field of its input."""
    if isinstance(tool_input, str) and tool_input.strip():
        return f"{tool}: {summarize(tool_input)}"
    if isinstance(tool_input, dict):
        for key in _LABEL_KEYS:
            value = tool_input.get(key)
            if isinstance(value, str) and value.strip():
                return f"{tool}: {summarize(value)}"
    return tool


def wanted(sessions: tuple[str, ...] | None, key: str, *extra: str) -> bool:
    """Reports whether a log known by this key was asked for.

    Args:
        sessions: Session ids asked for, or None to ask for every session.
        key: Key the log is given in the trace, such as claude:<id>.
        extra: Further ids the log answers to, such as the shortened id its
            session slice is named after.

    Returns:
        True when no session was named or one of the ids starts with a named
        one, so that the whole key, the key without its agent prefix and a
        shortened id all select the same log.
    """
    if sessions is None:
        return True
    idents = (key, key.split(":", 1)[-1], *extra)
    return any(ident.startswith(sessions) for ident in idents)


def title_of(ident: str, actions: list[Action]) -> str:
    """Titles a session after the first prompt it was given."""
    for action in actions:
        if action.category != "turn":
            continue
        prompt = action.args.get("prompt")
        if isinstance(prompt, str) and prompt.strip():
            return f"{ident} · {summarize(prompt, 60)}"
    return ident

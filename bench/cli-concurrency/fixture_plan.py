"""Plan deterministic shell work from the newest benchmark turn in a model request."""

# ruff: noqa: INP001 -- standalone benchmark support

from __future__ import annotations

import json
import re
import shlex
from dataclasses import dataclass
from typing import Any

TASK = re.compile(r"Work only in the (cold|warm)/ directory")
MARKER = re.compile(r"MEMORY-[0-9a-f]{32}")
CALL = re.compile(r"fixture_(cold|warm)_(\d+)_")
COMMAND_KEYS = {"command", "cmd", "script", "shell_command", "commandline", "commands"}
SHELL_NAMES = re.compile(
    r"(?:^|[._-])(?:bash|shell|sh|local_shell|exec_command|run_shell_command|"
    r"run_terminal_command|run_command|execute_command|execute_shell|shell_command|terminal)(?:$|[._-])",
    re.IGNORECASE,
)
STEPS = 3


@dataclass(frozen=True)
class Turn:
    """The task identity and completed fixture calls visible in this request."""

    marker: str
    phase: str
    completed: int


def _text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(_text(one) for one in value)
    if isinstance(value, dict) and value.get("type") in (
        "text",
        "input_text",
        "output_text",
    ):
        return str(value.get("text", ""))
    return ""


def _direct_task(value: Any) -> re.Match[str] | None:
    """Recognize the submitted task, excluding task quotes inside injected reminders."""
    if isinstance(value, list):
        return next((match for item in value if (match := _direct_task(item))), None)
    text = _text(value).lstrip()
    if text.startswith("<user_query>"):
        text = text.removeprefix("<user_query>").lstrip()
    return TASK.match(text)


def _outputs(item: dict[str, Any]) -> list[str]:
    if item.get("role") == "tool":
        return [str(item.get("tool_call_id", ""))]
    if str(item.get("type", "")).endswith("_call_output"):
        return [str(item.get("call_id", ""))]
    content = item.get("content")
    if isinstance(content, list):
        return [
            str(block.get("tool_use_id", ""))
            for block in content
            if isinstance(block, dict) and block.get("type") == "tool_result"
        ]
    return []


def locate(body: dict[str, Any], previous: Turn | None = None) -> Turn | None:
    """Reset at the latest explicit task instead of counting tools from earlier turns."""
    items = body.get("messages", body.get("input", []))
    if isinstance(items, str):
        items = [{"role": "user", "content": items}]
    if not isinstance(items, list):
        return previous
    # Locate task prompts only in user messages, never in assistant/tool echoes.
    latest: tuple[int, str] | None = None
    marker = previous.marker if previous else ""
    for index, item in enumerate(items):
        if not isinstance(item, dict) or item.get("role") != "user":
            continue
        text = _text(item.get("content", ""))
        if found := MARKER.search(text):
            marker = found.group()
        if found := _direct_task(item.get("content", "")):
            latest = (index, found.group(1))
    if latest is None and previous is None:
        return None
    phase = latest[1] if latest else previous.phase
    after = items[latest[0] + 1 :] if latest else items
    indices = [
        int(match.group(2)) + 1
        for item in after
        if isinstance(item, dict)
        for call in _outputs(item)
        if (match := CALL.search(call)) and match.group(1) == phase
    ]
    completed = max(indices, default=0 if latest else previous.completed)
    return Turn(marker, phase, completed)


def declared(body: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize Anthropic, Chat, Responses and namespaced function declarations."""
    found: list[dict[str, Any]] = []

    def visit(items: list[Any], namespace: str = "") -> None:
        for tool in items:
            if not isinstance(tool, dict):
                continue
            kind = tool.get("type", "function")
            if kind == "namespace":
                visit(tool.get("tools", []), str(tool.get("name", "")))
                continue
            inner = tool.get("function", tool)
            if not isinstance(inner, dict):
                continue
            name = str(
                inner.get("name", "local_shell" if kind == "local_shell" else "")
            )
            if name:
                found.append(
                    {
                        "name": name,
                        "namespace": namespace,
                        "kind": kind,
                        "schema": inner.get(
                            "parameters", inner.get("input_schema", {})
                        ),
                    }
                )

    visit(body.get("tools", []))
    return found


def shell(body: dict[str, Any]) -> dict[str, Any] | None:
    """Choose a declared command tool; unknown tool grammars are refused explicitly."""
    return next(
        (
            tool
            for tool in declared(body)
            if SHELL_NAMES.search(tool["name"]) and tool["kind"] != "custom"
        ),
        None,
    )


def _completion_review(body: dict[str, Any], turn: Turn) -> bool:
    """Identify a quoted task review only after this turn's completed tool conversation."""
    items = body.get("messages", body.get("input", []))
    if not isinstance(items, list) or turn.completed != STEPS:
        return False
    users = [
        (index, item.get("content", ""))
        for index, item in enumerate(items)
        if isinstance(item, dict) and item.get("role") == "user"
    ]
    if not users:
        return False
    index, last = users[-1]
    if _direct_task(last) or not TASK.search(_text(last)):
        return False
    return any(
        isinstance(item, dict)
        and item.get("role") == "assistant"
        and f"FIXTURE-COMPLETE {turn.marker}" in _text(item.get("content", ""))
        for item in items[:index]
    )


def auxiliary_reason(body: dict[str, Any], turn: Turn | None) -> str | None:
    """Separate metadata calls by declared capability, never by their arrival order."""
    if turn is None:
        return "no_benchmark_task"
    if _completion_review(body, turn):
        return "completion_review"
    selected = shell(body)
    if selected is None:
        return "no_shell_tool"
    choice = body.get("tool_choice")
    if choice == "none" or (isinstance(choice, dict) and choice.get("type") == "none"):
        return "tools_disabled"
    if isinstance(choice, dict):
        forced = choice.get("function", {}).get("name", choice.get("name"))
        if forced and forced != selected["name"]:
            return "other_tool_forced"
    return None


def request_shape(body: dict[str, Any]) -> dict[str, Any]:
    """Retain structural diagnostics and fixed instruction matches, without prompt text."""
    items = body.get("messages", body.get("input", []))
    if isinstance(items, str):
        items = [{"role": "user", "content": items}]
    if not isinstance(items, list):
        items = []
    users = [
        _text(item.get("content", ""))
        for item in items
        if isinstance(item, dict) and item.get("role") == "user"
    ]
    last = users[-1] if users else ""
    instructions = "\n".join(
        [str(body.get("system", "")), str(body.get("instructions", "")), *users]
    ).lower()
    return {
        "message_roles": [
            item.get("role", item.get("type", ""))
            for item in items
            if isinstance(item, dict)
        ],
        "user_task_positions": [text.find("Work only in the ") for text in users],
        "last_user_has_task": bool(TASK.search(last)),
        "last_user_has_direct_task": bool(_direct_task(last)),
        "tool_choice": body.get("tool_choice"),
        "output_token_limit": body.get(
            "max_output_tokens",
            body.get("max_completion_tokens", body.get("max_tokens")),
        ),
        "instruction_hints": [
            hint
            for hint in (
                "generate a session title",
                "session_title",
                "title generation",
                "summarize the conversation",
                "laziness",
                "prewarm",
                "suggest",
            )
            if hint in instructions
        ],
    }


def command(turn: Turn) -> str:
    """Read, modify, then execute the same task files used by the real-model harness."""
    phase = turn.phase
    if turn.completed == 0:
        script = (
            "from pathlib import Path; "
            f"root=Path({phase!r}); "
            "[print(name + '\\n' + (root/name).read_text()) "
            "for name in ('fixture.json','score.py','check_task.py')]"
        )
        return "python3 -c " + shlex.quote(script)
    if turn.completed == 1:
        source = (
            "def score(values):\n"
            "    return sum(value * value for value in values if value > 0)\n"
        )
        script = (
            f"from pathlib import Path; Path('{phase}/score.py').write_text({source!r})"
        )
        return "python3 -c " + shlex.quote(script)
    return f"python3 {phase}/check_task.py"


def arguments(schema: dict[str, Any], script: str) -> dict[str, Any]:
    """Fill declared command arguments and required ancillary schema fields."""
    properties = schema.get("properties", {})
    if not properties:
        return {"command": script}

    def value(name: str, shape: dict[str, Any]) -> Any:
        kind = shape.get("type", "string")
        if isinstance(kind, list):
            kind = next((one for one in kind if one != "null"), "string")
        kind = kind.lower()
        lowered = name.lower()
        if lowered in COMMAND_KEYS:
            if kind == "array":
                return [script] if lowered == "commands" else ["bash", "-lc", script]
            return script
        if "enum" in shape:
            return shape["enum"][0]
        if "default" in shape:
            return shape["default"]
        if kind == "boolean":
            return False
        if kind in ("number", "integer"):
            number = 60000 if "timeout" in lowered else 1000
            if lowered == "waitmsbeforeasync":
                number = 10000
            return min(
                shape.get("maximum", number), max(shape.get("minimum", 0), number)
            )
        if kind == "array":
            return []
        if kind == "object":
            return arguments(shape, script)
        return (
            "."
            if lowered in ("cwd", "workdir", "directory")
            else "deterministic CLI benchmark"
        )

    command_keys = {name for name in properties if name.lower() in COMMAND_KEYS}
    needed = set(schema.get("required", [])) | command_keys
    filled = {name: value(name, properties.get(name, {})) for name in needed}
    if not command_keys:
        raise ValueError("Declared shell tool has no recognized command argument")
    # Ensure values can travel through every one of the supported JSON protocols.
    json.dumps(filled)
    return filled
